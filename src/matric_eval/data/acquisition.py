"""Pinned raw HTTP acquisition with atomic artifacts and replayable receipts."""

from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import closing
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from matric_eval.data.catalog import DatasetSource
from matric_eval.data.roles import canonical, sha256


def acquire_source(
    source: DatasetSource,
    destination: Path,
    *,
    max_bytes: int = 2_000_000_000,
) -> dict[str, Any]:
    """Fetch a reviewed public source. A failure never produces a complete receipt.

    No credentials, remote scripts, extraction, or inferred license approval.
    Artifacts are stored by content digest; source paths are receipt metadata only.
    """
    if max_bytes <= 0:
        raise ValueError("positive_download_budget_required")
    if source.access["status"] != "public" or source.acquisition["status"] != "mapped":
        raise ValueError("source_acquisition_unavailable")
    revision = source.upstream.get("revision")
    if not revision or not source.files:
        raise ValueError("pinned_source_files_required")
    expected_total = sum(item.get("size_bytes") or 0 for item in source.files)
    if expected_total > max_bytes:
        raise ValueError("source_exceeds_download_budget")
    destination.mkdir(parents=True, exist_ok=True)
    blobs = destination / "blobs"
    blobs.mkdir(exist_ok=True)
    entries: list[dict[str, Any]] = []
    total = 0
    with httpx.Client(follow_redirects=False, timeout=120, trust_env=False) as client:
        for item in source.files:
            url = item["url"]
            parsed = urlparse(url)
            path = PurePosixPath(item["path"])
            if (
                parsed.scheme != "https"
                or parsed.username
                or parsed.password
                or revision not in parsed.path.split("/")
                or path.is_absolute()
                or ".." in path.parts
                or parsed.hostname
                not in {
                    "huggingface.co",
                    "raw.githubusercontent.com",
                    "media.githubusercontent.com",
                }
            ):
                raise ValueError("untrusted_or_unpinned_source_file")
            fd, temporary = tempfile.mkstemp(prefix=".download-", dir=blobs)
            try:
                digest = hashlib.sha256()
                size = 0
                os.close(fd)
                for _ in range(10):
                    request = client.build_request("GET", url)
                    response = client.send(request, stream=True)
                    if not response.is_redirect:
                        break
                    location = response.headers.get("location", "")
                    response.close()
                    url = urljoin(url, location)
                    redirect = urlparse(url)
                    host = redirect.hostname or ""
                    if (
                        redirect.scheme != "https"
                        or redirect.username
                        or redirect.password
                        or not any(
                            host == domain or host.endswith("." + domain)
                            for domain in ("huggingface.co", "hf.co", "githubusercontent.com")
                        )
                    ):
                        raise ValueError("untrusted_source_redirect")
                else:
                    raise ValueError("source_redirect_limit")
                with Path(temporary).open("wb") as output, closing(response):
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError("source_exceeds_download_budget")
                        output.write(chunk)
                        digest.update(chunk)
                checksum = digest.hexdigest()
                expected = item.get("expected_sha256")
                if expected and checksum != expected:
                    raise ValueError("upstream_artifact_digest_mismatch")
                if item.get("size_bytes") is not None and size != item["size_bytes"]:
                    raise ValueError("upstream_artifact_size_mismatch")
                target = blobs / checksum
                if target.exists():
                    if sha256(target.read_bytes()) != checksum:
                        raise ValueError("existing_artifact_digest_mismatch")
                else:
                    os.link(temporary, target)
                entries.append(
                    {**item, "sha256": checksum, "size_bytes": size, "blob": f"blobs/{checksum}"}
                )
            finally:
                Path(temporary).unlink(missing_ok=True)
    receipt = {
        "version": "1",
        "source_id": source.id,
        "source_revision": revision,
        "catalog_source_sha256": sha256(canonical(source.model_dump())),
        "status": "complete",
        "files": entries,
        "total_bytes": total,
    }
    receipt_digest = sha256(canonical(receipt))
    receipts = destination / "receipts"
    receipts.mkdir(exist_ok=True)
    target = receipts / f"{source.id}-{receipt_digest}.json"
    encoded = canonical(receipt) + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=".receipt-", dir=receipts)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != encoded:
                raise ValueError("existing_receipt_mismatch") from None
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {**receipt, "receipt_sha256": receipt_digest, "receipt_path": str(target)}
