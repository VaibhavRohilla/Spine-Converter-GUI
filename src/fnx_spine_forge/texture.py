"""Bounded PNG container integrity checks; no rendering or visual certification."""

from __future__ import annotations

from zlib import crc32


def validate_png(data: bytes) -> None:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Texture has an invalid PNG signature")
    offset, chunks = 8, 0
    image_data = False
    while offset < len(data):
        if len(data) - offset < 12:
            raise ValueError("Truncated PNG chunk")
        length = int.from_bytes(data[offset : offset + 4], "big")
        end = offset + 12 + length
        if end > len(data):
            raise ValueError("PNG chunk exceeds texture bounds")
        kind = data[offset + 4 : offset + 8]
        content = data[offset + 8 : end - 4]
        checksum = int.from_bytes(data[end - 4 : end], "big")
        if crc32(kind + content) & 0xFFFFFFFF != checksum:
            raise ValueError("PNG chunk CRC mismatch")
        if chunks == 0:
            if kind != b"IHDR" or length != 13:
                raise ValueError("PNG must start with a valid IHDR")
            width = int.from_bytes(content[:4], "big")
            height = int.from_bytes(content[4:8], "big")
            if not (0 < width <= 32768 and 0 < height <= 32768):
                raise ValueError("PNG dimensions exceed supported bounds")
        elif kind == b"IHDR":
            raise ValueError("Duplicate PNG IHDR")
        if kind == b"IDAT":
            image_data = True
        if kind == b"IEND":
            if length != 0 or end != len(data) or not image_data:
                raise ValueError("Invalid PNG ending or missing image data")
            return
        offset = end
        chunks += 1
    raise ValueError("PNG is missing IEND")
