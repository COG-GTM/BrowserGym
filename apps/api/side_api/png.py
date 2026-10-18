"""Tiny dependency-free PNG canvas used by the FakeRunner to produce screenshots."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

RGB = tuple[int, int, int]

# 3x5 bitmap font for the characters the fake screenshots need.
_FONT = {
    "0": "111101101101111",
    "1": "010110010010111",
    "2": "111001111100111",
    "3": "111001111001111",
    "4": "101101111001001",
    "5": "111100111001111",
    "6": "111100111101111",
    "7": "111001001001001",
    "8": "111101111101111",
    "9": "111101111001111",
    "/": "001001010100100",
    " ": "000000000000000",
    "S": "111100111001111",
    "T": "111010010010010",
    "E": "111100111100111",
    "P": "111101111100100",
}


class Canvas:
    def __init__(self, width: int, height: int, color: RGB = (255, 255, 255)):
        self.width = width
        self.height = height
        self.buf = bytearray(bytes(color) * (width * height))

    def rect(self, x: int, y: int, w: int, h: int, color: RGB) -> None:
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.width, x + w), min(self.height, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            start = (yy * self.width + x0) * 3
            self.buf[start : start + len(row)] = row

    def text(self, x: int, y: int, s: str, color: RGB, scale: int = 3) -> None:
        for ch in s.upper():
            glyph = _FONT.get(ch, _FONT[" "])
            for i, bit in enumerate(glyph):
                if bit == "1":
                    self.rect(x + (i % 3) * scale, y + (i // 3) * scale, scale, scale, color)
            x += 4 * scale

    def to_png(self) -> bytes:
        raw = bytearray()
        stride = self.width * 3
        for yy in range(self.height):
            raw.append(0)
            raw += self.buf[yy * stride : (yy + 1) * stride]

        def chunk(tag: bytes, data: bytes) -> bytes:
            body = tag + data
            return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

        ihdr = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + chunk(b"IEND", b"")
        )

    def save(self, path: Path) -> None:
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_bytes(self.to_png())
        tmp.replace(path)
