import json
import unittest

from qwen_material_plan_core import (
    DEFAULT_ANALYZER_PROMPT,
    bbox_to_pixel_json,
    material_plan_to_json,
    normalize_material_plan,
    select_material_region,
)


class QwenMaterialPlanCoreTests(unittest.TestCase):
    def test_prompt_requires_json_and_material_regions(self):
        self.assertIn("Return ONLY valid JSON", DEFAULT_ANALYZER_PROMPT)
        self.assertIn("sam_prompt", DEFAULT_ANALYZER_PROMPT)

    def test_normalizes_and_sorts_by_priority(self):
        raw = {
            "version": 1,
            "regions": [
                {"name": "Facade Stone", "semantic_class": "facade", "sam_prompt": "stone facade", "priority": 40},
                {"name": "Glass", "semantic_class": "glass", "sam_prompt": "windows and glazing", "priority": 100},
            ],
        }
        plan = normalize_material_plan(raw)
        self.assertEqual(plan["regions"][0]["name"], "Glass")
        self.assertEqual(plan["regions"][1]["id"], "facade-stone")

    def test_accepts_fenced_json(self):
        raw = """```json\n{"version":1,"regions":[{"name":"Road","sam_prompt":"road surface","priority":10}]}\n```"""
        plan = normalize_material_plan(raw)
        self.assertEqual(plan["regions"][0]["name"], "Road")

    def test_bbox_is_clamped_and_converted_to_pixels(self):
        plan = normalize_material_plan({
            "regions": [{"name": "Glass", "bbox_2d": [-5, 100, 1200, 900]}]
        })
        region = plan["regions"][0]
        self.assertEqual(region["bbox_2d"], [0, 100, 1000, 900])
        box = json.loads(bbox_to_pixel_json(region, 2000, 1000))[0]
        self.assertEqual(box["x"], 0.0)
        self.assertEqual(box["y"], 100.0)
        self.assertEqual(box["width"], 2000.0)
        self.assertEqual(box["height"], 800.0)

    def test_select_clamps_index(self):
        plan = {
            "regions": [
                {"name": "A", "priority": 2},
                {"name": "B", "priority": 1},
            ]
        }
        self.assertEqual(select_material_region(plan, 99)["name"], "B")

    def test_serialization_is_stable(self):
        raw = {"regions": [{"name": "Metal", "semantic_class": "metal", "sam_prompt": "metal frames"}]}
        a = material_plan_to_json(raw)
        b = material_plan_to_json(json.loads(a))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
