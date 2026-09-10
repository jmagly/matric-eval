"""Pinned Tau request-guard and tokenizer attestation support."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

JsonObject = dict[str, Any]
TokenCounter = Callable[[list[dict[str, Any]], list[dict[str, Any]] | None], int]


class ChatTemplateTokenizer(Protocol):
    """Subset of the Transformers tokenizer API required by the guard."""

    def apply_chat_template(self, conversation: list[dict[str, Any]], **kwargs: Any) -> Any:
        """Render and tokenize one OpenAI-compatible conversation."""


@dataclass(frozen=True)
class TauPatchContract:
    """Content-addressed contract for the local Tau source patch."""

    upstream_revision: str
    patch_path: Path
    patch_sha256: str
    patched_diff_sha256: str
    changed_paths: tuple[str, ...]
    transformers_version: str


@dataclass
class TargetContextGuard:
    """Reject over-budget target requests after Tau serialization and before HTTP."""

    target_model: str
    budget: JsonObject
    count_tokens: TokenCounter
    observations: list[JsonObject] = field(default_factory=list)
    last_request: JsonObject | None = None

    def __call__(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | None,
        call_name: str | None,
        kwargs: dict[str, Any],
    ) -> None:
        """Validate only the configured target's agent-response call."""
        if model != self.target_model or call_name != "agent_response":
            return
        output_tokens = kwargs.get("max_tokens")
        if output_tokens != self.budget["max_output_tokens"]:
            raise RuntimeError("target request output budget diverged from the sealed contract")
        input_tokens = self.count_tokens(messages, tools)
        combined_tokens = input_tokens + output_tokens + self.budget["safety_margin_tokens"]
        canonical_request = json.loads(
            json.dumps(
                {"messages": messages, "tools": tools, "tool_choice": tool_choice},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        self.last_request = canonical_request
        observation = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "safety_margin_tokens": self.budget["safety_margin_tokens"],
            "combined_tokens": combined_tokens,
            "context_limit": self.budget["max_context_tokens"],
            "tool_choice": tool_choice,
            "request_sha256": hashlib.sha256(
                json.dumps(canonical_request, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }
        self.observations.append(observation)
        if input_tokens > self.budget["max_input_tokens"]:
            raise TargetContextRuntimeInvalid(observation)


class TargetContextRuntimeInvalid(RuntimeError):
    """Typed analytic-invalid result for a target request rejected before HTTP."""

    def __init__(self, observation: JsonObject):
        self.observation = dict(observation)
        super().__init__(
            "serialized target request exceeds the sealed combined-context budget: "
            f"{observation['combined_tokens']} > {observation['context_limit']}"
        )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash one regular file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_patch_contract(manifest_path: Path) -> TauPatchContract:
    """Load and validate the repository-owned Tau patch manifest."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "1":
        raise ValueError("Tau patch manifest must be a schema-version 1 object")
    patch_name = payload.get("patch_file")
    if not isinstance(patch_name, str) or Path(patch_name).name != patch_name:
        raise ValueError("Tau patch filename must be a basename")
    patch_path = (manifest_path.parent / patch_name).resolve()
    digest = sha256_file(patch_path)
    if digest != payload.get("patch_sha256"):
        raise ValueError("Tau patch SHA-256 does not match its manifest")
    changed_paths = payload.get("changed_paths")
    if not isinstance(changed_paths, list) or not all(
        isinstance(path, str) and path for path in changed_paths
    ):
        raise ValueError("Tau patch changed_paths must be a nonempty string list")
    if changed_paths != sorted(set(changed_paths)):
        raise ValueError("Tau patch changed_paths must be sorted and unique")
    hashes = (payload.get("patched_diff_sha256"), payload.get("patch_sha256"))
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes):
        raise ValueError("Tau patch hashes must be lowercase SHA-256 values")
    upstream_revision = payload.get("upstream_revision")
    if not isinstance(upstream_revision, str) or not re.fullmatch(
        r"[0-9a-f]{40}", upstream_revision
    ):
        raise ValueError("Tau patch upstream_revision must be a full lowercase Git SHA")
    transformers_version = payload.get("transformers_version")
    if not isinstance(transformers_version, str) or not transformers_version:
        raise ValueError("Tau patch must pin a Transformers version")
    return TauPatchContract(
        upstream_revision=upstream_revision,
        patch_path=patch_path,
        patch_sha256=digest,
        patched_diff_sha256=str(payload["patched_diff_sha256"]),
        changed_paths=tuple(changed_paths),
        transformers_version=transformers_version,
    )


def _git(checkout: Path, arguments: list[str], *, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(checkout), *arguments],
        check=True,
        capture_output=True,
        text=text,
        timeout=60,
    )
    stdout = result.stdout
    if text:
        if not isinstance(stdout, str):
            raise TypeError("text Git command returned non-text output")
        return stdout
    if not isinstance(stdout, bytes):
        raise TypeError("binary Git command returned non-binary output")
    return stdout


def verify_tau_checkout(checkout: Path, contract: TauPatchContract) -> JsonObject:
    """Verify the exact upstream revision and exact content-addressed patch diff."""
    revision = str(_git(checkout, ["rev-parse", "HEAD"])).strip()
    if revision != contract.upstream_revision:
        raise RuntimeError("Tau checkout is not at the patch contract's upstream revision")
    status = str(_git(checkout, ["status", "--porcelain=v1", "--untracked-files=all"]))
    changed_paths = tuple(
        sorted(line[3:].strip() for line in status.splitlines() if len(line) >= 4)
    )
    if changed_paths != tuple(sorted(contract.changed_paths)):
        raise RuntimeError("Tau checkout changed paths do not match the patch contract")
    diff = _git(checkout, ["diff", "HEAD", "--binary", "--", *changed_paths], text=False)
    assert isinstance(diff, bytes)
    diff_sha256 = _sha256_bytes(diff)
    if diff_sha256 != contract.patched_diff_sha256:
        raise RuntimeError("Tau checkout diff does not match the content-addressed patch")
    return {
        "tracked_changes": list(changed_paths),
        "tracked_diff_sha256": diff_sha256,
        "patch_file_sha256": contract.patch_sha256,
        "upstream_revision": revision,
    }


def apply_tau_patch(checkout: Path, contract: TauPatchContract) -> JsonObject:
    """Apply the patch once to an exact clean Tau checkout, then verify its diff."""
    revision = str(_git(checkout, ["rev-parse", "HEAD"])).strip()
    if revision != contract.upstream_revision:
        raise RuntimeError("Tau checkout is not at the patch contract's upstream revision")
    status = str(_git(checkout, ["status", "--porcelain=v1", "--untracked-files=all"]))
    if status.strip():
        raise RuntimeError("Tau patch application requires a clean tracked worktree")
    subprocess.run(
        ["git", "-C", str(checkout), "apply", "--check", str(contract.patch_path)],
        check=True,
        timeout=60,
    )
    subprocess.run(
        ["git", "-C", str(checkout), "apply", str(contract.patch_path)],
        check=True,
        timeout=60,
    )
    return verify_tau_checkout(checkout, contract)


def tokenizer_file_hashes(model_path: Path) -> JsonObject:
    """Attest tokenizer assets used by the local pre-HTTP counter."""
    required = ("tokenizer.json", "tokenizer_config.json")
    missing = [name for name in required if not (model_path / name).is_file()]
    if missing:
        raise RuntimeError("model tokenizer assets are missing: " + ", ".join(missing))
    optional = ("added_tokens.json", "special_tokens_map.json")
    names = required + tuple(name for name in optional if (model_path / name).is_file())
    return {name: sha256_file(model_path / name) for name in names}


def build_token_counter(
    tokenizer: ChatTemplateTokenizer,
    template: str,
) -> TokenCounter:
    """Build the exact chat-template counter shared with the pinned server runtime."""

    def count(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> int:
        # Tau retains OpenAI wire-format tool-call arguments as JSON strings.
        # Transformers renders the server's Qwen template locally, where the
        # template's ``items`` filter requires the decoded object. Normalize a
        # private copy for token counting without changing the outbound request.
        template_messages = json.loads(json.dumps(messages))
        for message in template_messages:
            calls = message.get("tool_calls")
            if not isinstance(calls, list):
                continue
            for call in calls:
                if not isinstance(call, dict):
                    raise RuntimeError("tool call must be an object for token counting")
                function = call.get("function", call)
                if not isinstance(function, dict):
                    raise RuntimeError("tool-call function must be an object for token counting")
                arguments = function.get("arguments")
                if isinstance(arguments, str) and arguments:
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError as error:
                        raise RuntimeError(
                            "tool-call arguments must contain a JSON object for token counting"
                        ) from error
                    if not isinstance(arguments, dict):
                        raise RuntimeError(
                            "tool-call arguments must contain a JSON object for token counting"
                        )
                    function["arguments"] = arguments
                elif arguments is not None and not isinstance(arguments, (dict, str)):
                    raise RuntimeError(
                        "tool-call arguments must contain a JSON object for token counting"
                    )
        encoded = tokenizer.apply_chat_template(
            template_messages,
            tools=tools,
            tokenize=True,
            add_generation_prompt=True,
            chat_template=template,
            enable_thinking=False,
        )
        token_ids = encoded.get("input_ids") if isinstance(encoded, Mapping) else encoded
        if not isinstance(token_ids, list) or not all(
            isinstance(token_id, int) and not isinstance(token_id, bool) for token_id in token_ids
        ):
            raise RuntimeError("tokenizer did not return one flat integer token sequence")
        return len(token_ids)

    return count


def load_attested_tokenizer(
    *,
    model_path: Path,
    chat_template_path: Path,
    expected_template_sha256: str,
    expected_transformers_version: str,
    tokenizer_factory: Callable[..., ChatTemplateTokenizer] | None = None,
) -> tuple[TokenCounter, JsonObject]:
    """Load the local tokenizer only after matching server versions and template."""
    installed = importlib.metadata.version("transformers")
    if installed != expected_transformers_version:
        raise RuntimeError("local Transformers version does not match the server runtime")
    template = chat_template_path.read_text(encoding="utf-8")
    template_sha256 = _sha256_bytes(template.encode())
    if template_sha256 != expected_template_sha256:
        raise RuntimeError("local chat template does not match the server receipt")
    if tokenizer_factory is None:
        from transformers import AutoTokenizer

        tokenizer_factory = AutoTokenizer.from_pretrained
    tokenizer = tokenizer_factory(str(model_path), local_files_only=True, trust_remote_code=False)
    assets = tokenizer_file_hashes(model_path)
    return build_token_counter(tokenizer, template), {
        "transformers_version": installed,
        "chat_template_sha256": template_sha256,
        "tokenizer_class": type(tokenizer).__name__,
        "tokenizer_files": assets,
    }


def exception_chain(exc: BaseException) -> list[JsonObject]:
    """Return a bounded, content-free exception chain for private evidence."""
    chain: list[JsonObject] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        chain.append({"type": type(current).__name__, "message": str(current)[:500]})
        current = current.__cause__ or current.__context__
    return chain
