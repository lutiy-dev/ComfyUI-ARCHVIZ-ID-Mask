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
from .color_range_core import (\n    adaptive_lab_hsv_similarity,\n    apply_channel_assist,\n    best_channel_assist,\n    connected_component_4,\n    lab_chroma_gradient,\n)\n

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
    rgb8 = torch.round(rgb * 255.0)
    mask = torch.zeros(rgb.shape[:-1], dtype=torch.bool, device=rgb.device)

    for color in colors:
        r, g, b = normalize_rgb(*color["rgb"])
        selected = torch.tensor([r, g, b], dtype=rgb8.dtype, device=rgb8.device)
        delta = rgb8 - selected
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
                "images": _save_ui_preview(_to_rgb(image), "archviz_id_source"),
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

        if color_ids:
            colors = find_colors(palette, color_ids)
            mask = _mask_for_colors(image, colors, tolerance, invert)
        else:
            colors = []
            shape = _to_rgb(image).shape[:-1]
            mask = torch.zeros(shape, dtype=torch.float32, device=image.device)
            if invert:
                mask = 1.0 - mask
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


class ARCHVIZColorRangeMask:
    """Beauty-image color range masking with adaptive color and boundary diagnostics."""

    CATEGORY = "ARCHVIZ/Masking"
    FUNCTION = "extract"
    RETURN_TYPES = ("MASK", "IMAGE", "IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("mask", "preview", "confidence", "edge_map", "hex")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "red": ("INT", {"default": 128, "min": 0, "max": 255, "step": 1}),
                "green": ("INT", {"default": 128, "min": 0, "max": 255, "step": 1}),
                "blue": ("INT", {"default": 128, "min": 0, "max": 255, "step": 1}),
                "seed_x": ("INT", {"default": 0, "min": 0, "max": 32768, "step": 1}),
                "seed_y": ("INT", {"default": 0, "min": 0, "max": 32768, "step": 1}),
                "color_range": ("FLOAT", {"default": 22.0, "min": 0.5, "max": 100.0, "step": 0.5}),
                "light_variation": ("FLOAT", {"default": 35.0, "min": 0.0, "max": 100.0, "step": 1.0}),
                "color_strictness": ("FLOAT", {"default": 50.0, "min": 0.0, "max": 100.0, "step": 1.0}),
                "threshold": ("FLOAT", {"default": 0.5, "min": 0.05, "max": 0.95, "step": 0.01}),
                "connected": ("BOOLEAN", {"default": True}),
                "channel_assist": ("BOOLEAN", {"default": True}),
                "invert": ("BOOLEAN", {"default": False}),
            }
        }

    def extract(
        self,
        image: torch.Tensor,
        red: int,
        green: int,
        blue: int,
        seed_x: int,
        seed_y: int,
        color_range: float,
        light_variation: float,
        color_strictness: float,
        threshold: float,
        connected: bool,
        channel_assist: bool,
        invert: bool,
    ):
        rgb_tensor = _to_rgb(image)
        device = rgb_tensor.device
        masks = []
        previews = []
        confidences = []
        edges = []
        assist_meta = []

        r, g, b = normalize_rgb(red, green, blue)
        color_hex = rgb_to_hex(r, g, b)

        for batch_index in range(rgb_tensor.shape[0]):
            rgb_np = rgb_tensor[batch_index].detach().cpu().numpy()
            confidence = adaptive_lab_hsv_similarity(
                rgb_np,
                [r, g, b],
                color_range=color_range,
                light_variation=light_variation,
                color_strictness=color_strictness,
            )

            candidate = confidence >= float(threshold)
            if connected:
                candidate = connected_component_4(candidate, seed_x, seed_y)

            assist_name = None
            assist_separation = 0.0
            if channel_assist and candidate.any():
                assist = best_channel_assist(rgb_np, candidate)
                if assist is not None:
                    confidence = apply_channel_assist(confidence, assist)
                    assist_name = assist.name
                    assist_separation = float(assist.separation)
                    candidate = confidence >= float(threshold)
                    if connected:
                        candidate = connected_component_4(candidate, seed_x, seed_y)

            edge = lab_chroma_gradient(rgb_np)
            mask_np = candidate.astype(np.float32)
            if invert:
                mask_np = 1.0 - mask_np

            mask_t = torch.from_numpy(mask_np).to(device=device, dtype=torch.float32)
            conf_t = torch.from_numpy(confidence.astype(np.float32)).to(device=device)
            edge_t = torch.from_numpy(edge.astype(np.float32)).to(device=device)

            masks.append(mask_t)
            confidences.append(conf_t.unsqueeze(-1).repeat(1, 1, 3))
            edges.append(edge_t.unsqueeze(-1).repeat(1, 1, 3))

            base = rgb_tensor[batch_index]
            overlay = base * 0.35 + mask_t.unsqueeze(-1).repeat(1, 1, 3) * 0.65
            previews.append(overlay.clamp(0.0, 1.0))
            assist_meta.append({"name": assist_name, "separation": assist_separation})

        mask = torch.stack(masks, dim=0)
        preview = torch.stack(previews, dim=0)
        confidence_image = torch.stack(confidences, dim=0)
        edge_image = torch.stack(edges, dim=0)

        return {
            "ui": {
                "images": _save_ui_preview(rgb_tensor, "archviz_color_range_source"),
                "archviz_color_range": {
                    "selected_rgb": [r, g, b],
                    "hex": color_hex,
                    "seed": [int(seed_x), int(seed_y)],
                    "threshold": float(threshold),
                    "connected": bool(connected),
                    "channel_assist": assist_meta,
                },
            },
            "result": (mask, preview, confidence_image, edge_image, color_hex),
        }


NODE_CLASS_MAPPINGS = {
    "ARCHVIZIDColorPickerMask": ARCHVIZIDColorPickerMask,
    "ARCHVIZIDPalettePicker": ARCHVIZIDPalettePicker,
    "ARCHVIZMaskFromPalette": ARCHVIZMaskFromPalette,
    "ARCHVIZIDGroupMask": ARCHVIZIDGroupMask,\n    "ARCHVIZColorRangeMask": ARCHVIZColorRangeMask,\n}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ARCHVIZIDColorPickerMask": "ARCHVIZ · ID Color Picker Mask",
    "ARCHVIZIDPalettePicker": "ARCHVIZ · ID Palette Picker",
    "ARCHVIZMaskFromPalette": "ARCHVIZ · Mask From Palette",
    "ARCHVIZIDGroupMask": "ARCHVIZ · ID Group Mask",\n    "ARCHVIZColorRangeMask": "ARCHVIZ · Color Range Mask",\n}
