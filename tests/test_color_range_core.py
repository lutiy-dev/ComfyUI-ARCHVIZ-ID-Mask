import unittest

import numpy as np

from color_range_core import (
    adaptive_lab_hsv_similarity,
    apply_channel_assist,
    best_channel_assist,
    connected_component_4,
    lab_chroma_gradient,
    outside_ring,
    srgb_to_hsv,
    srgb_to_lab,
)


class ColorRangeCoreTests(unittest.TestCase):
    def test_lab_reference_black_and_white(self):
        image = np.array([[[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]], dtype=np.float32)
        lab = srgb_to_lab(image)
        self.assertAlmostEqual(float(lab[0, 0, 0]), 0.0, places=3)
        self.assertAlmostEqual(float(lab[0, 1, 0]), 100.0, places=3)

    def test_hsv_green_has_green_hue(self):
        hsv = srgb_to_hsv(np.array([[[0.0, 1.0, 0.0]]], dtype=np.float32))[0, 0]
        self.assertAlmostEqual(float(hsv[0]), 1.0 / 3.0, places=4)
        self.assertAlmostEqual(float(hsv[1]), 1.0, places=4)

    def test_similarity_prefers_reference_color(self):
        image = np.array(
            [[[0.55, 0.42, 0.30], [0.10, 0.65, 0.15]]],
            dtype=np.float32,
        )
        ref = [140, 107, 77]
        score = adaptive_lab_hsv_similarity(image, ref)
        self.assertGreater(float(score[0, 0]), float(score[0, 1]))

    def test_low_saturation_hue_does_not_dominate(self):
        image = np.array(
            [[[0.50, 0.50, 0.50], [0.52, 0.51, 0.50]]],
            dtype=np.float32,
        )
        ref = [128, 128, 128]
        loose = adaptive_lab_hsv_similarity(image, ref, color_strictness=100)
        self.assertGreater(float(loose[0, 1]), 0.5)

    def test_connected_component_uses_four_neighbors(self):
        mask = np.array(
            [
                [1, 0, 0],
                [0, 1, 1],
                [0, 1, 1],
            ],
            dtype=bool,
        )
        out = connected_component_4(mask, 0, 0)
        self.assertEqual(int(out.sum()), 1)

    def test_connected_component_returns_seed_region(self):
        mask = np.zeros((5, 6), dtype=bool)
        mask[1:4, 1:3] = True
        mask[1:4, 4:6] = True
        out = connected_component_4(mask, 1, 2)
        self.assertEqual(int(out.sum()), 6)
        self.assertFalse(bool(out[2, 4]))

    def test_outside_ring_excludes_source_mask(self):
        mask = np.zeros((7, 7), dtype=bool)
        mask[3, 3] = True
        ring = outside_ring(mask, radius=1)
        self.assertEqual(int(ring.sum()), 4)
        self.assertFalse(bool(ring[3, 3]))

    def test_chroma_gradient_detects_color_boundary(self):
        image = np.zeros((12, 12, 3), dtype=np.float32)
        image[:, :6] = [0.7, 0.2, 0.2]
        image[:, 6:] = [0.2, 0.7, 0.2]
        edge = lab_chroma_gradient(image)
        self.assertGreater(float(edge[:, 5:7].mean()), float(edge[:, :3].mean()) + 0.5)

    def test_channel_assist_detects_green_separation(self):
        image = np.zeros((20, 20, 3), dtype=np.float32)
        image[:] = [0.45, 0.35, 0.30]
        image[6:14, 6:14] = [0.18, 0.65, 0.20]
        rough = np.zeros((20, 20), dtype=bool)
        rough[7:13, 7:13] = True

        assist = best_channel_assist(image, rough, ring_radius=4)
        self.assertIsNotNone(assist)
        self.assertGreater(assist.separation, 1.25)

        base = np.ones((20, 20), dtype=np.float32)
        refined = apply_channel_assist(base, assist)
        self.assertGreater(float(refined[9, 9]), float(refined[3, 3]))


if __name__ == "__main__":
    unittest.main()
