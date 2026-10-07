from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

import numpy as np


EPS = 1e-6


@dataclass(frozen=True)
class ChannelAssistResult:
    name: str
    separation: float
    confidence: np.ndarray


def _as_rgb01(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image, dtype=np.float32)
    if array.ndim != 3 or array.shape[-1] < 3:
        raise ValueError("Expected RGB image [H,W,C]")
    return np.clip(array[..., :3], 0.0, 1.0)


def srgb_to_lab(image: np.ndarray) -> np.ndarray:
    rgb = _as_rgb01(image)
    linear = np.where(
        rgb <= 0.04045,
        rgb / 12.92,
        ((rgb + 0.055) / 1.055) ** 2.4,
    )

    r, g, b = np.moveaxis(linear, -1, 0)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    delta = 6.0 / 29.0
    delta3 = delta ** 3
    factor = 1.0 / (3.0 * delta * delta)

    def f(t: np.ndarray) -> np.ndarray:
        return np.where(t > delta3, np.cbrt(t), factor * t + 4.0 / 29.0)

    fx, fy, fz = f(x), f(y), f(z)
    lab = np.stack(
        [
            116.0 * fy - 16.0,
            500.0 * (fx - fy),
            200.0 * (fy - fz),
        ],
        axis=-1,
    )
    return lab.astype(np.float32)


def srgb_to_hsv(image: np.ndarray) -> np.ndarray:
    rgb = _as_rgb01(image)
    r, g, b = np.moveaxis(rgb, -1, 0)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    diff = mx - mn

    h = np.zeros_like(mx)
    nonzero = diff > EPS

    rmax = (mx == r) & nonzero
    gmax = (mx == g) & nonzero
    bmax = (mx == b) & nonzero

    h[rmax] = np.mod((g[rmax] - b[rmax]) / diff[rmax], 6.0)
    h[gmax] = (b[gmax] - r[gmax]) / diff[gmax] + 2.0
    h[bmax] = (r[bmax] - g[bmax]) / diff[bmax] + 4.0
    h /= 6.0

    s = np.where(mx > EPS, diff / np.maximum(mx, EPS), 0.0)
    return np.stack([h, s, mx], axis=-1).astype(np.float32)


def _reference_patch(rgb255: Iterable[int | float]) -> np.ndarray:
    rgb = np.asarray(list(rgb255), dtype=np.float32)
    if rgb.shape != (3,):
        raise ValueError("Reference RGB must contain exactly three channels")
    return np.clip(rgb / 255.0, 0.0, 1.0).reshape(1, 1, 3)


def adaptive_lab_hsv_similarity(
    image: np.ndarray,
    reference_rgb: Iterable[int | float],
    color_range: float = 22.0,
    light_variation: float = 35.0,
    color_strictness: float = 50.0,
) -> np.ndarray:
    """Return a 0..1 confidence map.

    LAB a/b is the primary color signal. LAB L is a separately weighted
    lightness modifier. HSV Hue only contributes when saturation is reliable.
    """
    rgb = _as_rgb01(image)
    ref = _reference_patch(reference_rgb)

    lab = srgb_to_lab(rgb)
    ref_lab = srgb_to_lab(ref)[0, 0]
    hsv = srgb_to_hsv(rgb)
    ref_hsv = srgb_to_hsv(ref)[0, 0]

    dc = np.hypot(lab[..., 1] - ref_lab[1], lab[..., 2] - ref_lab[2])
    dl = np.abs(lab[..., 0] - ref_lab[0])

    chroma_scale = max(float(color_range), 0.5)
    color_score = np.exp(-0.5 * (dc / chroma_scale) ** 2)

    light_free = np.clip(float(light_variation) / 100.0, 0.0, 1.0)
    strict_light = np.exp(-0.5 * (dl / 18.0) ** 2)
    light_modifier = light_free + (1.0 - light_free) * strict_light

    dh = np.abs(hsv[..., 0] - ref_hsv[0])
    dh = np.minimum(dh, 1.0 - dh)
    min_sat = np.minimum(hsv[..., 1], ref_hsv[1])
    hue_reliability = np.clip((min_sat - 0.08) / 0.35, 0.0, 1.0)

    strict = np.clip(float(color_strictness) / 100.0, 0.0, 1.0)
    hue_sigma = 0.25 - 0.20 * strict
    hue_score = np.exp(-0.5 * (dh / max(hue_sigma, 0.03)) ** 2)
    hue_weight = hue_reliability * strict
    hue_modifier = (1.0 - hue_weight) + hue_weight * hue_score

    confidence = color_score * light_modifier * hue_modifier
    return np.clip(confidence, 0.0, 1.0).astype(np.float32)


def lab_chroma_gradient(image: np.ndarray) -> np.ndarray:
    lab = srgb_to_lab(image)
    a = lab[..., 1]
    b = lab[..., 2]

    ay, ax = np.gradient(a)
    by, bx = np.gradient(b)
    magnitude = np.sqrt(ax * ax + ay * ay + bx * bx + by * by)

    positive = magnitude[magnitude > EPS]
    if positive.size == 0:
        return np.zeros_like(magnitude, dtype=np.float32)

    scale = float(np.percentile(positive, 99.0))
    if scale <= EPS:
        scale = float(np.max(positive))
    return np.clip(magnitude / max(scale, EPS), 0.0, 1.0).astype(np.float32)


def connected_component_4(mask: np.ndarray, seed_x: int, seed_y: int) -> np.ndarray:
    binary = np.asarray(mask, dtype=bool)
    if binary.ndim != 2:
        raise ValueError("Connected mask must be 2D")

    h, w = binary.shape
    x = int(np.clip(seed_x, 0, max(0, w - 1)))
    y = int(np.clip(seed_y, 0, max(0, h - 1)))
    if h == 0 or w == 0 or not binary[y, x]:
        return np.zeros_like(binary, dtype=bool)

    out = np.zeros_like(binary, dtype=bool)
    queue: deque[tuple[int, int]] = deque([(y, x)])
    out[y, x] = True

    while queue:
        cy, cx = queue.popleft()
        for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
            if 0 <= ny < h and 0 <= nx < w and binary[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True
                queue.append((ny, nx))

    return out


def _dilate4(mask: np.ndarray, iterations: int) -> np.ndarray:
    result = np.asarray(mask, dtype=bool).copy()
    for _ in range(max(0, int(iterations))):
        expanded = result.copy()
        expanded[1:] |= result[:-1]
        expanded[:-1] |= result[1:]
        expanded[:, 1:] |= result[:, :-1]
        expanded[:, :-1] |= result[:, 1:]
        result = expanded
    return result


def outside_ring(mask: np.ndarray, radius: int = 4) -> np.ndarray:
    binary = np.asarray(mask, dtype=bool)
    return _dilate4(binary, radius) & ~binary


def _candidate_channels(image: np.ndarray) -> dict[str, np.ndarray]:
    rgb = _as_rgb01(image)
    lab = srgb_to_lab(rgb)
    hsv = srgb_to_hsv(rgb)
    r, g, b = np.moveaxis(rgb, -1, 0)

    return {
        "R": r,
        "G": g,
        "B": b,
        "LAB_a": lab[..., 1],
        "LAB_b": lab[..., 2],
        "HSV_S": hsv[..., 1],
        "G-R": g - r,
        "R-G": r - g,
        "ExG": 2.0 * g - r - b,
    }


def best_channel_assist(
    image: np.ndarray,
    rough_mask: np.ndarray,
    ring_radius: int = 4,
) -> ChannelAssistResult | None:
    inside = np.asarray(rough_mask, dtype=bool)
    ring = outside_ring(inside, ring_radius)
    if inside.sum() < 4 or ring.sum() < 4:
        return None

    best: tuple[float, str, np.ndarray] | None = None

    for name, channel in _candidate_channels(image).items():
        vin = channel[inside]
        vout = channel[ring]
        med_in = float(np.median(vin))
        med_out = float(np.median(vout))
        mad_in = float(np.median(np.abs(vin - med_in)))
        mad_out = float(np.median(np.abs(vout - med_out)))
        separation = abs(med_in - med_out) / (mad_in + mad_out + 1e-3)

        direction = 1.0 if med_in >= med_out else -1.0
        midpoint = 0.5 * (med_in + med_out)
        scale = max(abs(med_in - med_out), 1e-3)
        z = direction * (channel - midpoint) / scale
        confidence = 1.0 / (1.0 + np.exp(-4.0 * np.clip(z, -10.0, 10.0)))

        if best is None or separation > best[0]:
            best = (separation, name, confidence.astype(np.float32))

    if best is None:
        return None
    return ChannelAssistResult(name=best[1], separation=float(best[0]), confidence=best[2])


def apply_channel_assist(
    confidence: np.ndarray,
    assist: ChannelAssistResult | None,
    minimum_separation: float = 1.25,
    strength: float = 0.25,
) -> np.ndarray:
    base = np.asarray(confidence, dtype=np.float32)
    if assist is None or assist.separation < minimum_separation:
        return base

    alpha = float(np.clip(strength, 0.0, 1.0))
    modifier = (1.0 - alpha) + alpha * assist.confidence
    return np.clip(base * modifier, 0.0, 1.0).astype(np.float32)
