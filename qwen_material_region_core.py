from __future__ import annotations

import json
from collections import deque

import numpy as np

from color_range_core import lab_chroma_gradient


CANONICAL_ID_COLORS = np.asarray(
    [
        [230, 25, 75], [60, 180, 75], [255, 225, 25], [0, 130, 200],
        [245, 130, 48], [145, 30, 180], [70, 240, 240], [240, 50, 230],
        [210, 245, 60], [250, 190, 212], [0, 128, 128], [220, 190, 255],
        [170, 110, 40], [255, 250, 200], [128, 0, 0], [170, 255, 195],
        [128, 128, 0], [255, 215, 180], [0, 0, 128], [128, 128, 128],
        [0, 255, 127], [127, 255, 212], [255, 99, 71], [106, 90, 205],
    ],
    dtype=np.uint8,
)


def _rgb01(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image, dtype=np.float32)
    if array.ndim != 3 or array.shape[-1] < 3:
        raise ValueError("Expected image [H,W,C] with RGB channels")
    return np.clip(array[..., :3], 0.0, 1.0)


def _box_blur3(image: np.ndarray, passes: int) -> np.ndarray:
    result = _rgb01(image)
    for _ in range(max(0, int(passes))):
        padded = np.pad(result, ((1, 1), (1, 1), (0, 0)), mode="edge")
        acc = np.zeros_like(result, dtype=np.float32)
        for dy in range(3):
            for dx in range(3):
                acc += padded[dy:dy + result.shape[0], dx:dx + result.shape[1]]
        result = acc / 9.0
    return result


def _deterministic_sample(pixels: np.ndarray, maximum: int = 50000) -> np.ndarray:
    if pixels.shape[0] <= maximum:
        return pixels
    indexes = np.linspace(0, pixels.shape[0] - 1, maximum, dtype=np.int64)
    return pixels[indexes]


def _init_centers_farthest(samples: np.ndarray, count: int) -> np.ndarray:
    count = max(1, min(int(count), samples.shape[0]))
    centers = [samples.mean(axis=0)]

    while len(centers) < count:
        stack = np.stack(centers, axis=0)
        distance = ((samples[:, None, :] - stack[None, :, :]) ** 2).sum(axis=2)
        nearest = distance.min(axis=1)
        centers.append(samples[int(np.argmax(nearest))])

    return np.stack(centers, axis=0).astype(np.float32)


def _kmeans_labels(image: np.ndarray, count: int, iterations: int = 10) -> tuple[np.ndarray, np.ndarray]:
    rgb = _rgb01(image)
    flat = rgb.reshape(-1, 3)
    samples = _deterministic_sample(flat)
    centers = _init_centers_farthest(samples, count)

    for _ in range(max(1, int(iterations))):
        sample_distance = ((samples[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        assignment = sample_distance.argmin(axis=1)

        updated = centers.copy()
        for index in range(centers.shape[0]):
            members = samples[assignment == index]
            if members.size:
                updated[index] = members.mean(axis=0)

        if np.max(np.abs(updated - centers)) < 1e-4:
            centers = updated
            break
        centers = updated

    full_distance = ((flat[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    labels = full_distance.argmin(axis=1).reshape(rgb.shape[:2]).astype(np.int32)
    return labels, centers


def _majority_filter(labels: np.ndarray, edge_map: np.ndarray, edge_protect: float, passes: int) -> np.ndarray:
    result = np.asarray(labels, dtype=np.int32).copy()
    h, w = result.shape
    protect = np.asarray(edge_map, dtype=np.float32) >= float(edge_protect)

    for _ in range(max(0, int(passes))):
        padded = np.pad(result, ((1, 1), (1, 1)), mode="edge")
        neighborhoods = np.stack(
            [padded[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3)],
            axis=-1,
        )

        maximum_label = int(result.max(initial=0))
        counts = np.stack(
            [(neighborhoods == label).sum(axis=-1) for label in range(maximum_label + 1)],
            axis=-1,
        )
        majority = counts.argmax(axis=-1).astype(np.int32)
        result = np.where(protect, result, majority)

    return result


def _component_sizes(labels: np.ndarray) -> list[tuple[int, int, int]]:
    array = np.asarray(labels, dtype=np.int32)
    h, w = array.shape
    visited = np.zeros((h, w), dtype=bool)
    components: list[tuple[int, int, int]] = []

    for y in range(h):
        for x in range(w):
            if visited[y, x]:
                continue

            label = int(array[y, x])
            queue: deque[tuple[int, int]] = deque([(y, x)])
            visited[y, x] = True
            size = 0

            while queue:
                cy, cx = queue.popleft()
                size += 1
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if (
                        0 <= ny < h
                        and 0 <= nx < w
                        and not visited[ny, nx]
                        and int(array[ny, nx]) == label
                    ):
                        visited[ny, nx] = True
                        queue.append((ny, nx))

            components.append((label, size, y * w + x))

    return components


def build_qwen_material_region_map(
    source_image: np.ndarray,
    qwen_map: np.ndarray,
    region_count: int = 12,
    qwen_smoothing: int = 1,
    cleanup_passes: int = 1,
    edge_protect: float = 0.35,
) -> tuple[np.ndarray, np.ndarray, str, int]:
    """Stabilize a Qwen-produced material/semantic image into a deterministic pseudo-ID map.

    Qwen provides semantic grouping. This function turns its potentially soft/generated colors
    into a finite set of exact canonical RGB IDs, while source-image LAB chroma edges protect
    strong material boundaries during cleanup.
    """
    source = _rgb01(source_image)
    generated = _rgb01(qwen_map)

    if source.shape[:2] != generated.shape[:2]:
        raise ValueError(
            f"Source and Qwen map resolution must match, got {source.shape[:2]} vs {generated.shape[:2]}"
        )

    requested = max(2, min(int(region_count), len(CANONICAL_ID_COLORS)))
    prepared = _box_blur3(generated, qwen_smoothing)
    labels, centers = _kmeans_labels(prepared, requested)

    edge = lab_chroma_gradient(source)
    labels = _majority_filter(labels, edge, edge_protect, cleanup_passes)

    counts = np.bincount(labels.reshape(-1), minlength=centers.shape[0])
    used = [index for index in np.argsort(-counts) if counts[index] > 0]

    remap = np.full(centers.shape[0], -1, dtype=np.int32)
    for rank, old_index in enumerate(used):
        remap[old_index] = rank

    ranked_labels = remap[labels]
    id_rgb8 = CANONICAL_ID_COLORS[ranked_labels]
    id_image = id_rgb8.astype(np.float32) / 255.0

    colors = []
    for rank, old_index in enumerate(used):
        rgb = CANONICAL_ID_COLORS[rank].tolist()
        colors.append(
            {
                "id": f"region-{rank + 1:02d}",
                "name": f"Region {rank + 1:02d}",
                "rgb": rgb,
                "hex": f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}",
                "pixel_count": int(counts[old_index]),
                "source_center_rgb": [round(float(v) * 255.0, 2) for v in centers[old_index]],
            }
        )

    palette_json = json.dumps(
        {"version": 1, "source": "qwen-material-region-map", "colors": colors},
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return id_image.astype(np.float32), edge.astype(np.float32), palette_json, len(used)
