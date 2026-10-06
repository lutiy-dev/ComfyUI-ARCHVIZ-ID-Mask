import json
import unittest

from palette_core import empty_palette, find_color, find_colors, normalize_palette, palette_to_json


class PaletteCoreTests(unittest.TestCase):
    def test_empty_palette(self):
        self.assertEqual(empty_palette(), {"version": 1, "colors": []})

    def test_normalization_adds_hex_and_clamps_rgb(self):
        p = normalize_palette({"version": 1, "colors": [{"id": "a", "name": "Facade", "rgb": [-1, 127.6, 300]}]})
        self.assertEqual(p["colors"][0]["rgb"], [0, 128, 255])
        self.assertEqual(p["colors"][0]["hex"], "#0080FF")

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            normalize_palette({"version": 1, "colors": [
                {"id": "a", "name": "A", "rgb": [1, 2, 3]},
                {"id": "a", "name": "B", "rgb": [4, 5, 6]},
            ]})

    def test_roundtrip_serialization(self):
        raw = {"version": 1, "colors": [{"id": "road", "name": "Road", "rgb": [10, 20, 30]}]}
        restored = normalize_palette(palette_to_json(raw))
        self.assertEqual(restored["colors"][0]["name"], "Road")
        self.assertEqual(restored["colors"][0]["hex"], "#0A141E")

    def test_find_color_defaults_to_first(self):
        raw = {"version": 1, "colors": [{"id": "a", "name": "A", "rgb": [1, 2, 3]}]}
        self.assertEqual(find_color(raw)["id"], "a")

    def test_find_colors_preserves_requested_order(self):
        raw = {"version": 1, "colors": [
            {"id": "a", "name": "A", "rgb": [1, 2, 3]},
            {"id": "b", "name": "B", "rgb": [4, 5, 6]},
        ]}
        self.assertEqual([x["id"] for x in find_colors(raw, ["b", "a"])], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
