from __future__ import annotations

import json
import os
import uuid

import numpy as np
import torch
from PIL import Image

import folder_paths

from .mask_core import MAX_RGB_DISTANCE, normalize_rgb, rgb_to_hex
from .palette_core import find_color, find_colors, normalize_palette


def _to_rgb(image: torch.Tensor) -> torch.Tensor:
    if image.ndim != 4:
        raise ValueError(f"Expected IMAGE tensor [B,H,W,C], got shape {tuple(image.shape)}")
    if image.shape[-1] < 3:
        raise ValueError("IMAGE input must contain at least RGB channels")
    return image[..., :3].to(dtype=torch.float32).clamp(0.0, 1.0)


def _save_ui_preview(preview: torch.Tensor, prefix: str) -> list[dict]:
    first = preview[0].detach().cpu().clamp(0.0, 1.0).numpy()
    array = np.rint(first * 255.0).astype(np.uint8)
    filename = f"{prefix}_{uuid.uuid4().hex}.png"
    temp_dir = folder_paths.get_temp_directory()
    os.makedirs(temp_dir, exist_ok=True)
    Image.fromarray(array, mode="RGB").save(
        os.path.join(temp_dir, filename),
        compress_level=1,
    )
    return [{"filename": filename, "subfolder": "", "type": "temp"}]


def _mask_for_colors(
    image: torch.Tensor,
    colors: list[dict],
    tolerance: float,
    invert: bool,
) -> torch.Tensor:
    rgb = _to_rgb(image)
    mask = torch.zeros(rgb.shape[:-1], dtype=torch.bool, device=rgb.device)

    for color in colors:
        r, g, b = normalize_rgb(*color["rgb"])
        selected = torch.tensor([r, g, b], dtype=rgb.dtype, device=rgb.device) / 255.0
        delta = (rgb - selected) * 255.0
        distance_sq = torch.sum(delta * delta, dim=-1)
        mask |= distance_sq <= float(tolerance) ** 2

    result = mask.to(dtype=torch.float32)
    return 1.0 - result if invert else result


def _mask_preview(mask: torch.Tensor) -> torch.Tensor:
    return mask.unsqueeze(-1).repeat(1, 1, 1, 3)


class ARCHVIZIDColorPickerMask:
    """Quick mode: extract one deterministic binary mask from an RGB ID pass."""

    CATEGORY = "ARCHVIZ/Masking"
    FUNCTION = "extract"
    RETURN_TYPES = ("MASK", "IMAGE", "INT", "INT", "INT", "STRING")
    RETURN_NAMES = ("mask", "preview", "r", "g", "b", "hex")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "red": ("INT", {"default": 0, "min": 0, "max": 255, "step": 1}),
                "green": ("INT", {"default": 0, "min": 0, "max": 255, "step": 1}),
                "blue": ("INT", {"default": 0, "min": 0, "max": 255, "step": 1}),
                "tolerance": (
                    "FLOAT",
                    {
                        "default": 5.0,
                        "min": 0.0,
                        "max": round(MAX_RGB_DISTANCE, 3),
                        "step": 0.5,
                    },
                ),
                "sample_radius": ("INT", {"default": 0, "min": 0, "max": 2, "step": 1}),
                "invert": ("BOOLEAN", {"default": False}),
            }
        }

    def extract(
        self,
        image: torch.Tensor,
        red: int,
        green: int,
        blue: int,
        tolerance: float,
        sample_radius: int,
        invert: bool,
    ):
        del sample_radius
        r, g, b = normalize_rgb(red, green, blue)
        mask = _mask_for_colors(
            image,
            [{"rgb": [r, g, b]}],
            tolerance,
            invert,
        )
        preview = _mask_preview(mask)
        color_hex = rgb_to_hex(r, g, b)

        return {
            "ui": {
                "images": _save_ui_preview(preview, "archviz_id_mask"),
                "archviz_id_mask": {
                    "selected_rgb": [r, g, b],
                    "hex": color_hex,
                    "tolerance": float(tolerance),
                },
            },
            "result": (mask, preview, r, g, b, color_hex),
        }


class ARCHVIZIDPalettePicker:
    """Build a named RGB palette from one Color/Object/Material ID pass."""

    CATEGORY = "ARCHVIZ/Masking"
    FUNCTION = "build"
    RETURN_TYPES = ("ARCHVIZ_ID_PALETTE", "IMAGE")
    RETURN_NAMES = ("palette", "image")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "palette_json": (
                    "STRING",
                    {
                        "default": '{"version":1,"colors":[]}',
                        "multiline": True,
                    },
                ),
                "sample_radius": ("INT", {"default": 0, "min": 0, "max": 2, "step": 1}),
            }
        }

    def build(self, image: torch.Tensor, palette_json: str, sample_radius: int):
        del sample_radius
        palette = normalize_palette(palette_json)
        rgb = _to_rgb(image)
        return {
            "ui": {
                "images": _save_ui_preview(rgb, "archviz_id_palette"),
                "archviz_palette": palette,
            },
            "result": (palette, image),
        }


class ARCHVIZMaskFromPalette:
    """Convert one palette slot into a deterministic binary mask."""

    CATEGORY = "ARCHVIZ/Masking"
    FUNCTION = "extract"
    RETURN_TYPES = ("MASK", "IMAGE", "STRING")
    RETURN_NAMES = ("mask", "preview", "hex")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "palette": ("ARCHVIZ_ID_PALETTE",),
                "color_id": ("STRING", {"default": ""}),
                "tolerance": (
                    "FLOAT",
                    {
                        "default": 5.0,
                        "min": 0.0,
                        "max": round(MAX_RGB_DISTANCE, 3),
                        "step": 0.5,
                    },
                ),
                "invert": ("BOOLEAN", {"default": False}),
            }
        }

    def extract(
        self,
        image: torch.Tensor,
        palette: dict,
        color_id: str,
        tolerance: float,
        invert: bool,
    ):
        color = find_color(palette, color_id)
        mask = _mask_for_colors(image, [color], tolerance, invert)
        preview = _mask_preview(mask)
        return {
            "ui": {
                "images": _save_ui_preview(preview, "archviz_palette_mask"),
                "archviz_palette_mask": {
                    "id": color["id"],
                    "name": color["name"],
                    "hex": color["hex"],
                },
            },
            "result": (mask, preview, color["hex"]),
        }


class ARCHVIZIDGroupMask:
    """Union multiple palette slots into one semantic production mask."""

    CATEGORY = "ARCHVIZ/Masking"
    FUNCTION = "extract"
    RETURN_TYPES = ("MASK", "IMAGE", "STRING")
    RETURN_NAMES = ("mask", "preview", "group_name")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "palette": ("ARCHVIZ_ID_PALETTE",),
                "color_ids_json": (
                    "STRING",
                    {"default": "[]", "multiline": True},
                ),
                "group_name": ("STRING", {"default": "Facade"}),
                "tolerance": (
                    "FLOAT",
                    {
                        "default": 5.0,
                        "min": 0.0,
                        "max": round(MAX_RGB_DISTANCE, 3),
                        "step": 0.5,
                    },
                ),
                "invert": ("BOOLEAN", {"default": False}),
            }
        }

    def extract(
        self,
        image: torch.Tensor,
        palette: dict,
        color_ids_json: str,
        group_name: str,
        tolerance: float,
        invert: bool,
    ):
        try:
            color_ids = json.loads(color_ids_json or "[]")
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid selected-color list") from exc
        if not isinstance(color_ids, list):
            raise ValueError("Selected colors must be a list")

        colors = find_colors(palette, color_ids)
        mask = _mask_for_colors(image, colors, tolerance, invert)
        preview = _mask_preview(mask)
        name = (group_name or "Group").strip()[:120]
        return {
            "ui": {
                "images": _save_ui_preview(preview, "archviz_group_mask"),
                "archviz_group_mask": {
                    "group_name": name,
                    "selected_ids": [item["id"] for item in colors],
                },
            },
            "result": (mask, preview, name),
        }


NODE_CLASS_MAPPINGS = {
    "ARCHVIZIDColorPickerMask": ARCHVIZIDColorPickerMask,
    "ARCHVIZIDPalettePicker": ARCHVIZIDPalettePicker,
    "ARCHVIZMaskFromPalette": ARCHVIZMaskFromPalette,
    "ARCHVIZIDGroupMask": ARCHVIZIDGroupMask,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ARCHVIZIDColorPickerMask": "ARCHVIZ · ID Color Picker Mask",
    "ARCHVIZIDPalettePicker": "ARCHVIZ · ID Palette Picker",
    "ARCHVIZMaskFromPalette": "ARCHVIZ · Mask From Palette",
    "ARCHVIZIDGroupMask": "ARCHVIZ · ID Group Mask",
}
