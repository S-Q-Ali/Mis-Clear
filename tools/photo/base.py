"""Shared helpers for photo forensics adapters (Phase 7).

All pipelines are local-first. Uploaded/read images are untrusted data:
metadata and decoded payloads are parsed, never executed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image


def load_rgb(path: str | Path) -> Image.Image:
    img = Image.open(path)
    img.load()
    if img.mode not in ("RGB", "L", "RGBA"):
        img = img.convert("RGB")
    return img


def md5_hex(path: str | Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_hex(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def dhash_hex(path: str | Path, hash_size: int = 8) -> str:
    """Perceptual d-hash: grayscale resize (hash_size+1 x hash_size), compare
    adjacent pixel intensities → 64-bit value. Robust to minor resizing/compression."""
    img = load_rgb(path).convert("L").resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
    pixels = img.tobytes()
    bits: list[str] = []
    for row in range(hash_size):
        row_start = row * (hash_size + 1)
        for col in range(hash_size):
            left = pixels[row_start + col]
            right = pixels[row_start + col + 1]
            bits.append("1" if left > right else "0")
    return format(int("".join(bits), 2), "016x")


def hamming_distance(a_hex: str, b_hex: str) -> int:
    try:
        return (int(a_hex, 16) ^ int(b_hex, 16)).bit_count()
    except ValueError:
        return -1