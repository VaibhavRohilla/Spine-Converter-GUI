"""Bounded PNG structural validation; no bitmap rendering or visual certification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from zlib import crc32, decompressobj
from zlib import error as ZlibError


class PNGColorType(IntEnum):
    GRAYSCALE = 0
    RGB = 2
    INDEXED = 3
    GRAYSCALE_ALPHA = 4
    RGBA = 6


@dataclass(frozen=True)
class TextureLimits:
    max_bytes: int = 128 * 1024 * 1024
    max_dimension: int = 32768
    max_pixels: int = 64 * 1024 * 1024
    max_decoded_bytes: int = 256 * 1024 * 1024
    max_chunks: int = 100000
    work_chunk_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        for value in (
            self.max_bytes,
            self.max_dimension,
            self.max_pixels,
            self.max_decoded_bytes,
            self.max_chunks,
            self.work_chunk_bytes,
        ):
            if type(value) is not int or value <= 0:
                raise ValueError("PNG resource limits must be positive integers")


@dataclass(frozen=True)
class PNGInfo:
    width: int
    height: int
    bit_depth: int
    color_type: PNGColorType
    interlaced: bool

    @property
    def channels(self) -> int:
        return {
            PNGColorType.GRAYSCALE: 1,
            PNGColorType.RGB: 3,
            PNGColorType.INDEXED: 1,
            PNGColorType.GRAYSCALE_ALPHA: 2,
            PNGColorType.RGBA: 4,
        }[self.color_type]

    def scanlines(self) -> tuple[tuple[int, int], ...]:
        # PNG's seven Adam7 passes are wire-format constants, not layout guesses.
        passes = (
            (
                (0, 0, 8, 8),
                (4, 0, 8, 8),
                (0, 4, 4, 8),
                (2, 0, 4, 4),
                (0, 2, 2, 4),
                (1, 0, 2, 2),
                (0, 1, 1, 2),
            )
            if self.interlaced
            else ((0, 0, 1, 1),)
        )
        rows: list[tuple[int, int]] = []
        for x, y, dx, dy in passes:
            width = max(0, (self.width - x + dx - 1) // dx)
            height = max(0, (self.height - y + dy - 1) // dy)
            if width and height:
                rows.append((height, (width * self.channels * self.bit_depth + 7) // 8))
        return tuple(rows)


class _Scanlines:
    def __init__(self, info: PNGInfo, limits: TextureLimits):
        self.passes = info.scanlines()
        self.expected = sum(rows * (size + 1) for rows, size in self.passes)
        if self.expected > limits.max_decoded_bytes:
            raise ValueError("PNG decoded data exceeds configured limit")
        self.total = 0
        self.pass_index = 0
        self.row_index = 0
        self.remaining = 0

    def accept(self, data: bytes) -> None:
        self.total += len(data)
        if self.total > self.expected:
            raise ValueError("PNG image stream exceeds declared geometry")
        position = 0
        while position < len(data):
            if self.remaining == 0:
                if self.pass_index >= len(self.passes):
                    raise ValueError("PNG has excess scanline data")
                rows, size = self.passes[self.pass_index]
                if data[position] > 4:
                    raise ValueError("PNG has an invalid scanline filter")
                position += 1
                self.remaining = size
                self.row_index += 1
                if self.row_index == rows:
                    self.pass_index += 1
                    self.row_index = 0
            taken = min(self.remaining, len(data) - position)
            self.remaining -= taken
            position += taken

    def finish(self) -> None:
        if self.total != self.expected or self.remaining:
            raise ValueError("PNG image stream does not match declared geometry")


def _header(content: memoryview, limits: TextureLimits) -> PNGInfo:
    if len(content) != 13:
        raise ValueError("PNG IHDR must contain thirteen bytes")
    width = int.from_bytes(content[:4], "big")
    height = int.from_bytes(content[4:8], "big")
    if not (0 < width <= limits.max_dimension and 0 < height <= limits.max_dimension):
        raise ValueError("PNG dimensions exceed configured bounds")
    if width * height > limits.max_pixels:
        raise ValueError("PNG pixel count exceeds configured limit")
    try:
        color = PNGColorType(content[9])
    except ValueError as exc:
        raise ValueError("PNG has an invalid color type") from exc
    depths = (
        (1, 2, 4, 8, 16)
        if color == PNGColorType.GRAYSCALE
        else ((1, 2, 4, 8) if color == PNGColorType.INDEXED else (8, 16))
    )
    if content[8] not in depths:
        raise ValueError("PNG has an invalid bit depth for its color type")
    if content[10] != 0 or content[11] != 0 or content[12] not in (0, 1):
        raise ValueError("PNG has an unsupported compression, filter or interlace method")
    return PNGInfo(width, height, content[8], color, bool(content[12]))


def validate_png(data: bytes, limits: TextureLimits | None = None) -> PNGInfo:
    policy = limits or TextureLimits()
    if len(data) > policy.max_bytes:
        raise ValueError("PNG file exceeds configured byte limit")
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Texture has an invalid PNG signature")
    view = memoryview(data)
    offset, chunks = 8, 0
    info: PNGInfo | None = None
    lines: _Scanlines | None = None
    inflater = decompressobj()
    image_data = False
    image_ended = False
    palette = False
    while offset < len(data):
        if chunks >= policy.max_chunks:
            raise ValueError("PNG chunk count exceeds configured limit")
        chunks += 1
        if len(data) - offset < 12:
            raise ValueError("Truncated PNG chunk")
        length = int.from_bytes(view[offset : offset + 4], "big")
        end = offset + 12 + length
        if end > len(data):
            raise ValueError("PNG chunk exceeds texture bounds")
        kind = bytes(view[offset + 4 : offset + 8])
        if not all(65 <= value <= 90 or 97 <= value <= 122 for value in kind) or kind[2] & 32:
            raise ValueError("PNG has an invalid chunk type")
        content = view[offset + 8 : end - 4]
        checksum = int.from_bytes(view[end - 4 : end], "big")
        if crc32(content, crc32(kind)) & 0xFFFFFFFF != checksum:
            raise ValueError("PNG chunk CRC mismatch")
        if chunks == 1:
            if kind != b"IHDR":
                raise ValueError("PNG must start with a valid IHDR")
            info = _header(content, policy)
            lines = _Scanlines(info, policy)
        elif kind == b"IHDR":
            raise ValueError("Duplicate PNG IHDR")
        if info is None or lines is None:
            raise ValueError("PNG is missing its header")
        if kind == b"PLTE":
            if (
                palette
                or image_data
                or length == 0
                or length % 3
                or length > 768
                or info.color_type in (PNGColorType.GRAYSCALE, PNGColorType.GRAYSCALE_ALPHA)
                or (info.color_type == PNGColorType.INDEXED and length // 3 > (1 << info.bit_depth))
            ):
                raise ValueError("PNG has an invalid palette")
            palette = True
        if kind == b"IDAT":
            if image_ended or (info.color_type == PNGColorType.INDEXED and not palette):
                raise ValueError("PNG has invalid image-data ordering or a missing palette")
            image_data = True
            try:
                for start in range(0, length, policy.work_chunk_bytes):
                    pending = bytes(content[start : start + policy.work_chunk_bytes])
                    while True:
                        decode_limit = min(
                            policy.work_chunk_bytes, lines.expected - lines.total + 1
                        )
                        expanded = inflater.decompress(pending, decode_limit)
                        if inflater.unused_data:
                            raise ValueError("PNG contains data after its compressed image stream")
                        lines.accept(expanded)
                        pending = inflater.unconsumed_tail
                        if not pending and len(expanded) < decode_limit:
                            break
            except ZlibError as exc:
                raise ValueError("PNG contains invalid compressed image data") from exc
        elif image_data:
            image_ended = True
        if kind == b"IEND":
            if length != 0 or end != len(data) or not image_data or not inflater.eof:
                raise ValueError("Invalid PNG ending or truncated image data")
            lines.finish()
            return info
        if not kind[0] & 32 and kind not in (b"IHDR", b"PLTE", b"IDAT", b"IEND"):
            raise ValueError("PNG contains an unsupported critical chunk")
        offset = end
    raise ValueError("PNG is missing IEND")
