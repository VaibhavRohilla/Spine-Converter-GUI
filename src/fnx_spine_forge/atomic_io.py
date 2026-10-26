"""Single owner for safe staging and exclusive filesystem publication."""

from __future__ import annotations

import errno
import os
import tempfile
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import cast

from .bundle_models import FileDigest
from .source import canonical_path, validate_member_paths


def stage_files(root: Path, files: Mapping[str, bytes]) -> None:
    validate_member_paths(files)
    for name, data in sorted(files.items()):
        safe = canonical_path(name)
        target = root / safe
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


_RENAME_EXCL_MACOS = 0x04
_RENAME_NOREPLACE_LINUX = 0x01
_AT_FDCWD = -100


def publish_directory(source: Path, target: Path) -> None:
    """Use the OS no-replace rename primitive; fail closed on unsupported platforms."""
    import ctypes
    import sys

    if os.name == "nt":
        # On Windows os.rename always rejects an occupied destination.
        os.rename(source, target)
        return
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if sys.platform == "darwin":
            rename = libc.renamex_np
            rename.restype = ctypes.c_int
            rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
            result = cast(int, rename(os.fsencode(source), os.fsencode(target), _RENAME_EXCL_MACOS))
        elif sys.platform.startswith("linux"):
            rename = libc.renameat2
            rename.restype = ctypes.c_int
            rename.argtypes = (
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            )
            result = cast(
                int,
                rename(
                    _AT_FDCWD,
                    os.fsencode(source),
                    _AT_FDCWD,
                    os.fsencode(target),
                    _RENAME_NOREPLACE_LINUX,
                ),
            )
        else:
            raise ValueError("No exclusive folder rename implementation for this platform")
    except AttributeError as exc:
        raise OSError(errno.ENOTSUP, "Native exclusive folder rename is unavailable") from exc
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(target))


def file_digests(files: Mapping[str, bytes]) -> tuple[FileDigest, ...]:
    return tuple(FileDigest(name, sha256(data).hexdigest()) for name, data in sorted(files.items()))


def publish_file(source: Path, target: Path) -> None:
    with source.open("r+b") as stream:
        os.fsync(stream.fileno())
    os.link(source, target)


def write_bytes_exclusive(target: Path, content: bytes) -> None:
    """Publish a complete standalone file without replacing any existing path."""
    canonical_path(target.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{target.name}.", dir=target.parent) as directory:
        source = Path(directory) / "payload"
        source.write_bytes(content)
        publish_file(source, target)
