from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

try:
    from .mask_core import normalize_rgb, rgb_to_hex
except ImportError:  # repository-level tests
    from mask_core import normalize_rgb, rgb_to_hex

SCHEMA_VERSION = 1


def empty_palette() -> dict[str, Any]:
    return {"version": SCHEMA_VERSION, "colors": []}


def normalize_palette(value: Any) -> dict[str, Any]:
    if value is None:
        return empty_palette()
    if isinstance(value, str):
        value = json.loads(value or "{}")
    if not isinstance(value, dict):
        raise ValueError("Palette must be an object")
    if int(value.get("version", SCHEMA_VERSION)) != SCHEMA_VERSION:
        raise ValueError("Unsupported palette version")

    colors = value.get("colors", [])
    if not isinstance(colors, list):
        raise ValueError("Palette colors must be a list")

    seen: set[str] = set()
    normalized = []
    for index, item in enumerate(colors):
        if not isinstance(item, dict):
            raise ValueError("Palette entry must be an object")
        color_id = str(item.get("id", "")).strip()
        if not color_id:
            raise ValueError(f"Palette entry {index} has no id")
        if color_id in seen:
            raise ValueError(f"Duplicate palette id: {color_id}")
        seen.add(color_id)

        name = str(item.get("name", "")).strip() or f"Color {index + 1}"
        rgb_value = item.get("rgb")
        if not isinstance(rgb_value, (list, tuple)) or len(rgb_value) != 3:
            raise ValueError(f"Palette entry {color_id} must contain RGB")
        rgb = list(normalize_rgb(*rgb_value))
        normalized.append(
            {
                "id": color_id,
                "name": name[:120],
                "rgb": rgb,
                "hex": rgb_to_hex(*rgb),
            }
        )

    return {"version": SCHEMA_VERSION, "colors": normalized}


def palette_to_json(value: Any) -> str:
    return json.dumps(normalize_palette(value), separators=(",", ":"), ensure_ascii=False)


def find_color(palette: Any, color_id: str | None = None) -> dict[str, Any]:
    data = normalize_palette(palette)
    if not data["colors"]:
        raise ValueError("Palette has no colors")
    if not color_id:
        return deepcopy(data["colors"][0])
    for color in data["colors"]:
        if color["id"] == color_id:
            return deepcopy(color)
    raise ValueError(f"Palette color not found: {color_id}")


def find_colors(palette: Any, color_ids: list[str]) -> list[dict[str, Any]]:
    data = normalize_palette(palette)
    requested = list(dict.fromkeys(str(item) for item in color_ids if str(item)))
    if not requested:
        raise ValueError("No palette colors selected")
    by_id = {item["id"]: item for item in data["colors"]}
    missing = [item for item in requested if item not in by_id]
    if missing:
        raise ValueError("Palette colors not found: " + ", ".join(missing))
    return [deepcopy(by_id[item]) for item in requested]
