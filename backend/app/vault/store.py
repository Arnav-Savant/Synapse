"""Atomic note file writes and content hashing.

Hashes are over the exact bytes on disk, so `file_hash` of a file Synapse
just wrote equals the hash `write_note_atomic` returned. This is the single
place vault files are written.
"""

import hashlib
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class VaultWriteError(OSError):
    """A note file could not be written; the original file (if any) is untouched."""


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_note_atomic(path: Path, text: str) -> str:
    """Writes via a temp file in the same folder plus `os.replace`, so a crash
    never leaves a half-written note. Returns the sha256 hex of what was written."""
    data = text.encode("utf-8")
    tmp_path: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".synapse-", suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        tmp_path = None
    except OSError as exc:
        logger.error("could not write note file %s: %s", path, exc.strerror or exc)
        raise VaultWriteError(f"could not write note file {str(path)!r}: {exc.strerror or exc}") from exc
    finally:
        if tmp_path is not None:
            Path(tmp_path).unlink(missing_ok=True)
    logger.info("note file written: %s (%d bytes)", path, len(data))
    return hashlib.sha256(data).hexdigest()
