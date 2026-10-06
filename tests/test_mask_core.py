import math
import unittest

from mask_core import MAX_RGB_DISTANCE, euclidean_rgb_distance, normalize_rgb, rgb_to_hex


class MaskCoreTests(unittest.TestCase):
    def test_rgb_is_clamped_and_rounded(self):
        self.assertEqual(normalize_rgb(-4, 127.6, 300), (0, 128, 255))

    def test_hex_is_uppercase_and_padded(self):
        self.assertEqual(rgb_to_hex(0, 15, 255), "#000FFF")

    def test_exact_color_distance_is_zero(self):
        self.assertEqual(
            euclidean_rgb_distance((10, 20, 30), (10, 20, 30)),
            0,
        )

    def test_known_distance(self):
        self.assertAlmostEqual(
            euclidean_rgb_distance((0, 0, 0), (3, 4, 0)),
            5.0,
        )

    def test_max_distance(self):
        self.assertTrue(
            math.isclose(
                MAX_RGB_DISTANCE,
                math.sqrt(3 * 255 * 255),
            )
        )


if __name__ == "__main__":
    unittest.main()
