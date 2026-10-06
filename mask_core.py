from __future__ import annotations

from math import sqrt
from typing import Iterable, Tuple

RGB = Tuple[int, int, int]
MAX_RGB_DISTANCE = sqrt(3 * (255 ** 2))


def clamp_channel(value: int | float) -> int:
    return max(0, min(255, int(round(value))))


def normalize_rgb(red: int | float, green: int | float, blue: int | float) -> RGB:
    return (clamp_channel(red), clamp_channel(green), clamp_channel(blue))


def rgb_to_hex(red: int | float, green: int | float, blue: int | float) -> str:
    r, g, b = normalize_rgb(red, green, blue)
    return f"#{r:02X}{g:02X}{b:02X}"


def euclidean_rgb_distance(pixel: Iterable[int | float], selected: Iterable[int | float]) -> float:
    pr, pg, pb = pixel
    sr, sg, sb = selected
    return sqrt((pr - sr) ** 2 + (pg - sg) ** 2 + (pb - sb) ** 2)
