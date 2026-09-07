"""Local synthetic custodian vault: private ownership and descriptor-based reads.

This protects supported access paths; the host owner remains trusted. Real
multiuser custody is not deployed by this library.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from matric_eval.data.roles import RoleError, RoleInventory, parse_inventory, sha256

MAX_SOURCE_BYTES = 1024 * 1024


def private_descriptor(fd: int, *, directory: bool) -> None:
    status = os.fstat(fd)
    kind = stat.S_ISDIR(status.st_mode) if directory else stat.S_ISREG(status.st_mode)
    if not kind or status.st_uid != os.geteuid() or status.st_mode & 0o077:
        raise RoleError("custodian_private_ownership_required")


class SourceVault:
    def __init__(self, root: Path):
        self.root = root
        try:
            self.fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            private_descriptor(self.fd, directory=True)
        except (OSError, RoleError) as exc:
            if hasattr(self, "fd"):
                os.close(self.fd)
            raise RoleError("custodian_vault_unavailable") from exc

    def close(self) -> None:
        os.close(self.fd)

    def read(self, relative: str) -> bytes:
        pieces = relative.split("/")
        if any(piece in {"", ".", ".."} for piece in pieces) or "\x00" in relative:
            raise RoleError("unsafe_source_path")
        directory = os.dup(self.fd)
        try:
            for piece in pieces[:-1]:
                child = os.open(
                    piece, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                )
                os.close(directory)
                directory = child
                private_descriptor(directory, directory=True)
            fd = os.open(pieces[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                private_descriptor(fd, directory=False)
                with os.fdopen(os.dup(fd), "rb") as stream:
                    payload = stream.read(MAX_SOURCE_BYTES + 1)
                if len(payload) > MAX_SOURCE_BYTES:
                    raise RoleError("source_limit_exceeded")
                return payload
            finally:
                os.close(fd)
        except OSError as exc:
            raise RoleError("source_unavailable") from exc
        finally:
            os.close(directory)

    def inventory(self) -> tuple[RoleInventory, str]:
        """Read the authoritative fixed inventory; requests cannot substitute a subset."""
        payload = self.read("inventory.json")
        result = parse_inventory(payload)
        if sha256(self.read(result.consent_file)) != result.consent_sha256:
            raise RoleError("consent_artifact_mismatch")
        # The custodian checks the complete declared inventory, including heldouts.
        # Plaintext is never sent to the worker or persisted in the use ledger.
        for row in result.rows:
            if sha256(self.read(row.input_file)) != row.input_sha256:
                raise RoleError("inventory_input_mismatch")
        return result, sha256(payload)
