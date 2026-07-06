"""Restrictive, atomic file creation for protected GMV artifacts."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

DIRECTORY_MODE = 0o700
FILE_MODE = 0o600


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def require_private(path: Path, expected: int) -> None:
    actual = mode(path)
    if actual != expected:
        raise PermissionError(f"unsafe mode {actual:04o} for {path}; expected {expected:04o}")


def secure_directory(path: Path) -> None:
    if path.exists():
        require_private(path, DIRECTORY_MODE)
        return
    path.mkdir(parents=True, mode=DIRECTORY_MODE)
    os.chmod(path, DIRECTORY_MODE)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    secure_directory(path.parent)
    if path.exists():
        require_private(path, FILE_MODE)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, FILE_MODE)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        require_private(path, FILE_MODE)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))
