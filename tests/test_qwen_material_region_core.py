import json
import unittest

import numpy as np

from qwen_material_region_core import (
    CANONICAL_ID_COLORS,
    build_qwen_material_region_map,
)


class QwenMaterialRegionCoreTests(unittest.TestCase):
    def test_builds_exact_canonical_id_colors(self):
        source = np.zeros((16, 16, 3), dtype=np.float32)
        source[:, :8] = [0.75, 0.25, 0.20]
        source[:, 8:] = [0.20, 0.70, 0.25]

        qwen = source.copy()
        qwen[:, :8] += np.linspace(0.0, 0.06, 8, dtype=np.float32)[None, :, None]
        qwen[:, 8:] -= np.linspace(0.0, 0.04, 8, dtype=np.float32)[None, :, None]
        qwen = np.clip(qwen, 0.0, 1.0)

        id_image, edge, palette_json, count = build_qwen_material_region_map(
            source,
            qwen,
            region_count=2,
            qwen_smoothing=1,
            cleanup_passes=1,
        )

        self.assertEqual(count, 2)
        unique = np.unique(np.rint(id_image.reshape(-1, 3) * 255.0).astype(np.uint8), axis=0)
        self.assertEqual(unique.shape[0], 2)
        allowed = {tuple(row.tolist()) for row in CANONICAL_ID_COLORS[:2]}
        self.assertEqual({tuple(row.tolist()) for row in unique}, allowed)
        self.assertEqual(edge.shape, source.shape[:2])

        palette = json.loads(palette_json)
        self.assertEqual(len(palette["colors"]), 2)
        self.assertEqual(palette["colors"][0]["id"], "region-01")

    def test_is_deterministic(self):
        rng = np.random.default_rng(1234)
        source = rng.random((20, 24, 3), dtype=np.float32)
        qwen = np.round(source * 3.0) / 3.0

        a = build_qwen_material_region_map(source, qwen, region_count=4)
        b = build_qwen_material_region_map(source, qwen, region_count=4)

        np.testing.assert_array_equal(a[0], b[0])
        self.assertEqual(a[2], b[2])
        self.assertEqual(a[3], b[3])

    def test_rejects_resolution_mismatch(self):
        source = np.zeros((10, 10, 3), dtype=np.float32)
        qwen = np.zeros((8, 10, 3), dtype=np.float32)
        with self.assertRaises(ValueError):
            build_qwen_material_region_map(source, qwen)

    def test_region_count_is_clamped_to_palette_capacity(self):
        source = np.zeros((6, 24, 3), dtype=np.float32)
        qwen = np.zeros_like(source)
        for x in range(24):
            qwen[:, x] = [(x % 6) / 5.0, ((x * 2) % 6) / 5.0, ((x * 3) % 6) / 5.0]

        _, _, palette_json, count = build_qwen_material_region_map(
            source,
            qwen,
            region_count=999,
            qwen_smoothing=0,
            cleanup_passes=0,
        )
        palette = json.loads(palette_json)
        self.assertLessEqual(count, len(CANONICAL_ID_COLORS))
        self.assertEqual(len(palette["colors"]), count)


if __name__ == "__main__":
    unittest.main()
