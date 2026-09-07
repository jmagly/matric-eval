"""Explicitly opted-in, bounded real-runtime qualification; never a default CI probe.

Run only on the authorized validation host after reviewing this file. Configure
MATRIC_EVAL_TEST_ISOLATION=1, MATRIC_EVAL_SANDBOX_COMMAND (JSON argv), and an
already-present MATRIC_EVAL_SANDBOX_IMAGE pinned by digest. No image is pulled.
"""

import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

import pytest

from matric_eval.scorers import isolated_execution
from matric_eval.scorers.isolated_execution import OUTPUT_BYTES, execute_python

pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


def _assert_removed(result: dict[str, Any]) -> None:
    provenance = result["provenance"]
    assert provenance["cleanup"] == "verified_absent", result
    container_id = provenance["container_id"]
    _assert_container_absent(container_id)


def _assert_container_absent(container_id: str) -> None:
    assert re.fullmatch(r"[a-f0-9]{64}", container_id)
    launcher = json.loads(os.environ["MATRIC_EVAL_SANDBOX_COMMAND"])
    socket_path = os.environ.get("MATRIC_EVAL_SANDBOX_SOCKET", "/var/run/docker.sock")
    with tempfile.TemporaryDirectory(prefix="matric-isolation-check-") as config:
        query = subprocess.run(
            [
                *launcher,
                "--config",
                config,
                "--host",
                f"unix://{socket_path}",
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"id={container_id}",
            ],
            capture_output=True,
            check=False,
            timeout=20,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"},
        )
    assert query.returncode == 0, query.stderr.decode(errors="replace")
    assert query.stdout.strip() == b"", "Exact execution container survived cleanup"


@pytest.fixture(scope="module", autouse=True)
def qualified_runtime() -> None:
    if os.environ.get("MATRIC_EVAL_TEST_ISOLATION") != "1":
        pytest.skip("Real isolation probes require MATRIC_EVAL_TEST_ISOLATION=1")
    if not os.environ.get("MATRIC_EVAL_SANDBOX_COMMAND") or not os.environ.get(
        "MATRIC_EVAL_SANDBOX_IMAGE"
    ):
        pytest.skip("Explicit runtime launcher and pinned image must be configured")
    assert re.fullmatch(
        r"[a-zA-Z0-9][a-zA-Z0-9._:/-]*@sha256:[a-f0-9]{64}",
        os.environ["MATRIC_EVAL_SANDBOX_IMAGE"],
    ), "Qualification requires a digest-pinned image"
    # Every later payload also passes the runner's effective-container preflight.
    # A configured but rejected runtime fails qualification rather than skipping.
    result = execute_python("print('preflight-ok')")
    assert result["status"] == "passed", result
    assert result["stdout"] == "preflight-ok\n"
    assert result["provenance"]["restrictions_verified"] is True
    _assert_removed(result)


@pytest.fixture
def run_probe(record_property: Any) -> Any:
    record_property("fixture_file_sha256", hashlib.sha256(Path(__file__).read_bytes()).hexdigest())

    def run(code: str, stdin_input: str = "", timeout: float = 30) -> dict[str, Any]:
        record_property("payload_sha256", hashlib.sha256(code.encode()).hexdigest())
        result = execute_python(code, stdin_input=stdin_input, timeout=timeout)
        record_property("isolation_provenance", json.dumps(result["provenance"], sort_keys=True))
        assert result["provenance"].get("restrictions_verified") is True, result
        _assert_removed(result)
        return result

    return run


def test_correct_incorrect_and_stdin(run_probe: Any) -> None:
    correct = run_probe("a, b = map(int, input().split()); print(a + b)", "19 23\n")
    assert correct["status"] == "passed"
    assert correct["stdout"] == "42\n"
    incorrect = run_probe("assert 19 + 23 == 41")
    assert incorrect["status"] == "incorrect"
    assert incorrect["provenance"]["native_exit_code"] != 0


def test_parent_environment_and_host_file_are_inaccessible(
    run_probe: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key = "MATRIC_ISOLATION_FAKE_CREDENTIAL_SENTINEL"
    monkeypatch.setenv(key, "controlled-fake-value-never-a-real-credential")
    sentinel = tmp_path / "host-only-sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    result = run_probe(
        "import os\n"
        f"assert {key!r} not in os.environ\n"
        f"path = {str(sentinel)!r}\n"
        "for mode in ('r', 'w'):\n"
        "    try:\n"
        "        with open(path, mode): pass\n"
        "    except OSError: pass\n"
        "    else: raise AssertionError('host path accessible')\n"
        "print('isolated')\n"
    )
    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert result["status"] == "passed", result


def test_network_namespace_cannot_reach_owned_host_listener(run_probe: Any) -> None:
    # No external service is contacted. The listening socket belongs to this test.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(0.2)
        port = listener.getsockname()[1]
        result = run_probe(
            "import socket\n"
            "assert set(socket.if_nameindex()) == {(1, 'lo')}\n"
            "with socket.socket() as connection:\n"
            "    connection.settimeout(1)\n"
            f"    assert connection.connect_ex(('127.0.0.1', {port})) != 0\n"
        )
        assert result["status"] == "passed", result
        with pytest.raises(TimeoutError):
            listener.accept()


def test_readonly_root_and_writable_tmpfs(run_probe: Any) -> None:
    result = run_probe(
        "from pathlib import Path\n"
        "mounts = [line.split() for line in Path('/proc/mounts').read_text().splitlines()]\n"
        "assert any(row[1] == '/' and 'ro' in row[3].split(',') for row in mounts)\n"
        "assert any(row[1] == '/tmp' and row[2] == 'tmpfs' for row in mounts)\n"
        "try: Path('/matric-controlled-probe').write_text('bounded')\n"
        "except OSError: pass\n"
        "else: raise AssertionError('root writable')\n"
        "path = Path('/tmp/controlled-probe'); path.write_text('ok')\n"
        "assert path.read_text() == 'ok'\n"
    )
    assert result["status"] == "passed", result


def test_finite_output_flood_is_bounded(run_probe: Any) -> None:
    result = run_probe("import sys\nfor _ in range(256): sys.stdout.write('x' * 4096)\n")
    assert result["status"] == "output_limit", result
    assert len(result["stdout"].encode()) + len(result["stderr"].encode()) <= OUTPUT_BYTES


def test_invalid_utf8_output_has_bounded_text_and_explicit_loss(run_probe: Any) -> None:
    result = run_probe("import os\nfor _ in range(16): os.write(1, b'\\xff' * 4096)\n")
    assert result["status"] == "output_limit", result
    assert len(result["stdout"].encode()) + len(result["stderr"].encode()) <= OUTPUT_BYTES
    evidence = result["provenance"]["output"]
    assert evidence["invalid_utf8_replaced"] is True
    assert evidence["text_truncated"] is True
    assert evidence["stdout_raw_bytes"] == OUTPUT_BYTES
    assert evidence["stdout_raw_sha256"] == hashlib.sha256(b"\xff" * OUTPUT_BYTES).hexdigest()


def test_keyboard_interrupt_removes_exact_created_container(
    monkeypatch: pytest.MonkeyPatch,
    record_property: Any,
) -> None:
    code = "import time; time.sleep(15)"
    record_property("payload_sha256", hashlib.sha256(code.encode()).hexdigest())
    record_property("fixture_file_sha256", hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    original_command = isolated_execution._command
    created_ids: list[str] = []
    cleanup_queries: list[Any] = []
    delivered = threading.Event()
    timers: list[threading.Timer] = []

    def interrupt_this_process() -> None:
        delivered.set()
        os.kill(os.getpid(), signal.SIGINT)

    def command(argv: list[str], **kwargs: Any) -> Any:
        is_start = any(argv[i : i + 2] == ["container", "start"] for i in range(len(argv) - 1))
        if is_start:
            # The real runner has verified the effective profile before this call.
            assert len(created_ids) == 1
            timer = threading.Timer(1, interrupt_this_process)
            timers.append(timer)
            timer.start()
            try:
                return original_command(argv, **kwargs)
            finally:
                timer.cancel()
                timer.join()
        result = original_command(argv, **kwargs)
        if any(argv[i : i + 2] == ["container", "create"] for i in range(len(argv) - 1)):
            assert result.returncode == 0, result
            created_ids.append(result.stdout.decode().strip())
        if any(argv[i : i + 2] == ["container", "ls"] for i in range(len(argv) - 1)):
            cleanup_queries.append(result)
        return result

    monkeypatch.setattr(isolated_execution, "_command", command)
    try:
        with pytest.raises(KeyboardInterrupt):
            execute_python(code, timeout=10)
    finally:
        # No delayed SIGINT may reach subsequent tests, including on assertion failure.
        for timer in timers:
            timer.cancel()
            timer.join()
        for container_id in created_ids:
            _assert_container_absent(container_id)
    assert delivered.is_set()
    assert len(created_ids) == 1
    assert len(cleanup_queries) == 1
    assert cleanup_queries[0].returncode == 0
    assert cleanup_queries[0].limit is None
    assert cleanup_queries[0].stdout.strip() == b""
    record_property("interrupted_container_id", created_ids[0])


def test_bounded_children_hit_pid_limit_and_timeout_cleanup(run_probe: Any) -> None:
    # At most 64 attempts; every child independently exits after 15 seconds even
    # if the resource profile were broken. This is deliberately not a fork bomb.
    result = run_probe(
        "import os, time\n"
        "limited = False\n"
        "for _ in range(64):\n"
        "    try: pid = os.fork()\n"
        "    except BlockingIOError:\n"
        "        limited = True; break\n"
        "    if pid == 0:\n"
        "        time.sleep(15); os._exit(0)\n"
        "assert limited, 'PID cap not enforced'\n"
        "print('pid-limit-enforced', flush=True)\n"
        "time.sleep(15)\n",
        timeout=5,
    )
    assert result["status"] == "timeout", result
    assert "pid-limit-enforced" in result["stdout"]


def test_unavailable_backend_refuses_payload_before_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "must-not-exist"
    monkeypatch.setenv("MATRIC_EVAL_SANDBOX_COMMAND", json.dumps([str(tmp_path / "absent-docker")]))
    result = execute_python(f"from pathlib import Path; Path({str(sentinel)!r}).touch()")
    assert result["status"] == "unavailable", result
    assert result["error"] == "runtime_unavailable"
    assert result["provenance"]["cleanup"] == "not_created"
    assert "container_id" not in result["provenance"]
    assert not sentinel.exists()
