from __future__ import annotations

import json
import re
from typing import Any

MAX_REGIONS = 16

DEFAULT_ANALYZER_PROMPT = """Analyze this architectural render before any material-edit sampling.

Return ONLY valid JSON with this exact top-level structure:
{
  "version": 1,
  "regions": [
    {
      "name": "short stable material/region name",
      "semantic_class": "facade|glass|metal|wood|road|paving|curb|vegetation|sky|water|people|other",
      "material_description": "brief visible material/surface description",
      "sam_prompt": "short concrete phrase for SAM3 open-vocabulary segmentation",
      "bbox_2d": [x1, y1, x2, y2],
      "priority": 100
    }
  ]
}

Rules:
- Identify visible production-relevant material/surface regions, not lighting effects.
- The same material in light and shadow must remain one material class.
- Separate glazing/windows from frames and facade.
- Separate road, paving, curb, vegetation and sky when present.
- bbox_2d coordinates must be normalized integers 0..1000. Omit bbox_2d when uncertain.
- sam_prompt must name the visible region directly and avoid style words.
- Higher priority means a more specific region should win if masks overlap.
- Do not invent hidden materials.
- Do not output markdown, comments, prose, or code fences.
"""

def _strip_code_fences(text: str) -> str:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    return value.strip()

def _extract_json_object(text: str) -> str:
    value = _strip_code_fences(text)
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Qwen output does not contain a JSON object")
    return value[start : end + 1]

def normalize_material_plan(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(_extract_json_object(value))
    if not isinstance(value, dict):
        raise ValueError("Material plan must be a JSON object")

    regions = value.get("regions", [])
    if not isinstance(regions, list):
        raise ValueError("Material plan regions must be a list")

    normalized = []
    seen = set()
    for index, item in enumerate(regions[:MAX_REGIONS]):
        if not isinstance(item, dict):
            continue
        raw_name = str(item.get("name", "")).strip() or f"Region {index + 1:02d}"
        base_id = re.sub(r"[^a-z0-9]+", "-", raw_name.lower()).strip("-") or f"region-{index + 1:02d}"
        region_id = base_id
        suffix = 2
        while region_id in seen:
            region_id = f"{base_id}-{suffix}"
            suffix += 1
        seen.add(region_id)
        semantic_class = str(item.get("semantic_class", "other")).strip().lower() or "other"
        description = str(item.get("material_description", "")).strip()[:240]
        sam_prompt = str(item.get("sam_prompt", raw_name)).strip()[:160] or raw_name
        try:
            priority = int(item.get("priority", 50))
        except (TypeError, ValueError):
            priority = 50
        priority = max(0, min(priority, 1000))
        bbox = item.get("bbox_2d")
        normalized_bbox = None
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            try:
                coords = [max(0, min(int(round(float(v))), 1000)) for v in bbox]
                x1, y1, x2, y2 = coords
                if x2 > x1 and y2 > y1:
                    normalized_bbox = coords
            except (TypeError, ValueError):
                normalized_bbox = None
        region = {
            "id": region_id,
            "name": raw_name[:120],
            "semantic_class": semantic_class[:80],
            "material_description": description,
            "sam_prompt": sam_prompt,
            "priority": priority,
        }
        if normalized_bbox is not None:
            region["bbox_2d"] = normalized_bbox
        normalized.append(region)
    normalized.sort(key=lambda item: (-item["priority"], item["name"].lower(), item["id"]))
    return {"version": 1, "source": "qwen3-vl", "regions": normalized}

def material_plan_to_json(value: Any) -> str:
    return json.dumps(normalize_material_plan(value), ensure_ascii=False, separators=(",", ":"))

def select_material_region(plan: Any, index: int = 0) -> dict[str, Any]:
    data = normalize_material_plan(plan)
    regions = data["regions"]
    if not regions:
        raise ValueError("Material plan has no regions")
    idx = max(0, min(int(index), len(regions) - 1))
    return regions[idx]

def bbox_to_pixel_json(region: dict[str, Any], width: int, height: int) -> str:
    bbox = region.get("bbox_2d")
    if not bbox:
        return "[]"
    x1, y1, x2, y2 = bbox
    result = [{
        "x": round(x1 / 1000.0 * width, 2),
        "y": round(y1 / 1000.0 * height, 2),
        "width": round((x2 - x1) / 1000.0 * width, 2),
        "height": round((y2 - y1) / 1000.0 * height, 2),
    }]
    return json.dumps(result, separators=(",", ":"))
