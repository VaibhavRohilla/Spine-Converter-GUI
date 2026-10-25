"""Bounded, read-only source abstraction for folders and ZIP archives."""

from __future__ import annotations

import re
import stat
import unicodedata
from dataclasses import dataclass
from math import isfinite
from pathlib import Path, PurePosixPath
from types import TracebackType
from zipfile import BadZipFile, ZipFile


class UnsafeSourceError(ValueError):
    pass


@dataclass(frozen=True)
class SourceLimits:
    max_members: int = 20_000
    max_member_uncompressed: int = 128 * 1024 * 1024
    max_total_uncompressed: int = 1024 * 1024 * 1024
    max_member_compressed: int = 128 * 1024 * 1024
    max_total_compressed: int = 512 * 1024 * 1024
    max_compression_ratio: float = 250.0
    max_read_bytes: int = 128 * 1024 * 1024

    def __post_init__(self) -> None:
        for field_name in (
            "max_members",
            "max_member_uncompressed",
            "max_total_uncompressed",
            "max_member_compressed",
            "max_total_compressed",
            "max_read_bytes",
        ):
            limit: object = getattr(self, field_name)
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
                raise ValueError(f"{field_name} must be non-negative")
        if not isfinite(self.max_compression_ratio) or self.max_compression_ratio <= 0:
            raise ValueError("max_compression_ratio must be a positive finite number")


DEFAULT_LIMITS = SourceLimits()


def canonical_path(name: str) -> str:
    if (
        not name
        or "\\" in name
        or "\x00" in name
        or name.startswith("/")
        or re.match(r"^[A-Za-z]:", name)
    ):
        raise UnsafeSourceError(f"Unsafe path: {name!r}")
    if any(part in ("..", ".", "") for part in name.rstrip("/").split("/")):
        raise UnsafeSourceError(f"Unsafe path: {name!r}")
    return unicodedata.normalize("NFC", PurePosixPath(name).as_posix())


class AssetSource:
    def __init__(self, origin: str | Path, limits: SourceLimits | None = None):
        self.origin = Path(origin)
        self.limits = limits or DEFAULT_LIMITS
        if not (
            self.origin.is_dir() or (self.origin.is_file() and self.origin.suffix.lower() == ".zip")
        ):
            raise ValueError("Provide an existing folder or .zip file")
        self._archive: ZipFile | None = None
        self._files: dict[str, Path | str] = {}
        self._sizes: dict[str, int] = {}

    def __enter__(self) -> AssetSource:
        try:
            if self.origin.is_dir():
                self._index_folder()
            else:
                self._index_zip()
            self._check_collisions()
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def _index_folder(self) -> None:
        root = self.origin.resolve()

        def relative_name(path: Path) -> str:
            return path.relative_to(self.origin).as_posix()

        paths = sorted(self.origin.rglob("*"), key=relative_name)
        if len(paths) > self.limits.max_members:
            raise UnsafeSourceError("Too many entries in input folder")
        members = []
        total = 0
        for path in paths:
            if path.is_symlink():
                resolved = path.resolve(strict=False)
                if root not in resolved.parents:
                    raise UnsafeSourceError(f"Folder symlink escapes source root: {path}")
                raise UnsafeSourceError(f"Folder symlink is not accepted: {path}")
            if not path.is_file():
                continue
            name = canonical_path(path.relative_to(self.origin).as_posix())
            size = path.stat().st_size
            if size > self.limits.max_member_uncompressed:
                raise UnsafeSourceError(f"File too large: {name}")
            members.append((name, path, size))
            total += size
        if len(members) > self.limits.max_members:
            raise UnsafeSourceError("Too many files in input folder")
        if total > self.limits.max_total_uncompressed:
            raise UnsafeSourceError("Input folder exceeds total size limit")
        self._files = {n: p for n, p, _ in members}
        self._sizes = {n: s for n, _, s in members}

    def _index_zip(self) -> None:
        try:
            self._archive = ZipFile(self.origin, "r")
        except (BadZipFile, OSError) as exc:
            raise UnsafeSourceError(f"Invalid ZIP archive: {exc}") from exc
        entries = self._archive.infolist()
        if len(entries) > self.limits.max_members:
            raise UnsafeSourceError("Too many entries in ZIP")
        total_u = total_c = 0
        seen: dict[str, str] = {}
        for info in entries:
            raw_name = info.filename.rstrip("/") if info.is_dir() else info.filename
            name = canonical_path(raw_name)
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise UnsafeSourceError(f"ZIP symlink not accepted: {name}")
            collision_key = unicodedata.normalize("NFC", name).casefold()
            if collision_key in seen:
                raise UnsafeSourceError(
                    f"Normalized path collision: {seen[collision_key]!r}, {name!r}"
                )
            seen[collision_key] = name
            if info.file_size > self.limits.max_member_uncompressed:
                raise UnsafeSourceError(f"ZIP member exceeds uncompressed size limit: {name}")
            if info.compress_size > self.limits.max_member_compressed:
                raise UnsafeSourceError(f"ZIP member exceeds compressed size limit: {name}")
            if info.file_size and not info.compress_size:
                raise UnsafeSourceError(f"Invalid compressed size: {name}")
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > self.limits.max_compression_ratio:
                raise UnsafeSourceError(f"Compression ratio exceeds limit: {name}")
            total_u += info.file_size
            total_c += info.compress_size
            if total_u > self.limits.max_total_uncompressed:
                raise UnsafeSourceError("ZIP exceeds total uncompressed size limit")
            if total_c > self.limits.max_total_compressed:
                raise UnsafeSourceError("ZIP exceeds total compressed size limit")
            if info.is_dir():
                continue
            self._files[name] = info.filename
            self._sizes[name] = info.file_size

    def _check_collisions(self) -> None:
        found: dict[str, str] = {}
        for path in self._files:
            key = unicodedata.normalize("NFC", path).casefold()
            if key in found:
                raise UnsafeSourceError(f"Normalized path collision: {found[key]!r}, {path!r}")
            found[key] = path

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._archive is not None:
            self._archive.close()
            self._archive = None

    def names(self) -> list[str]:
        return sorted(self._files)

    def size(self, name: str) -> int:
        return self._sizes[name]

    def read(self, name: str, max_bytes: int | None = None) -> bytes:
        if name not in self._files:
            raise KeyError(name)
        limit = min(
            max_bytes if max_bytes is not None else self.limits.max_read_bytes,
            self.limits.max_read_bytes,
        )
        if self._sizes[name] > limit:
            raise UnsafeSourceError(f"Read exceeds configured byte limit: {name}")
        item = self._files[name]
        if isinstance(item, Path):
            with item.open("rb") as handle:
                data = handle.read(limit + 1)
        else:
            assert self._archive is not None
            with self._archive.open(item, "r") as handle:
                data = handle.read(limit + 1)
        if len(data) > limit:
            raise UnsafeSourceError(f"Read exceeds configured byte limit: {name}")
        return data
