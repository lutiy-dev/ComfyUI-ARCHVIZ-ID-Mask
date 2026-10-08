from __future__ import annotations

import json
import os
import uuid

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

import folder_paths

from .mask_core import MAX_RGB_DISTANCE, normalize_rgb, rgb_to_hex
from .palette_core import find_color, find_colors, normalize_palette
from .color_range_core import (
    adaptive_lab_hsv_similarity,
    apply_channel_assist,
    best_channel_assist,
    connected_component_4,
    lab_chroma_gradient,
)
from .qwen_material_region_core import build_qwen_material_region_map
from .qwen_material_plan_core import (
    DEFAULT_ANALYZER_PROMPT,
    bbox_to_pixel_json,
    material_plan_to_json,
    normalize_material_plan,
    select_material_region,
)


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

    CATEGORY = "OLabVis/Masking"
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

    CATEGORY = "OLabVis/Masking"
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

    CATEGORY = "OLabVis/Masking"
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

    CATEGORY = "OLabVis/Masking"
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

    CATEGORY = "OLabVis/Masking"
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


class ARCHVIZQwenMaterialRegionMap:
    """Convert a Qwen-produced material/semantic map into a deterministic pseudo Material ID."""

    CATEGORY = "OLabVis/Masking"
    FUNCTION = "build"
    RETURN_TYPES = ("IMAGE", "IMAGE", "ARCHVIZ_ID_PALETTE", "STRING", "INT")
    RETURN_NAMES = ("id_image", "edge_map", "palette", "palette_json", "region_count")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_image": ("IMAGE",),
                "qwen_map": ("IMAGE",),
                "region_count": ("INT", {"default": 12, "min": 2, "max": 24, "step": 1}),
                "qwen_smoothing": ("INT", {"default": 1, "min": 0, "max": 3, "step": 1}),
                "cleanup_passes": ("INT", {"default": 1, "min": 0, "max": 3, "step": 1}),
                "edge_protect": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.05}),
            }
        }

    def build(
        self,
        source_image: torch.Tensor,
        qwen_map: torch.Tensor,
        region_count: int,
        qwen_smoothing: int,
        cleanup_passes: int,
        edge_protect: float,
    ):
        source = _to_rgb(source_image)
        generated = _to_rgb(qwen_map)

        if source.shape[0] != generated.shape[0]:
            raise ValueError(
                f"Source and Qwen map batch size must match, got {source.shape[0]} vs {generated.shape[0]}"
            )

        device = source.device
        source_h, source_w = int(source.shape[1]), int(source.shape[2])
        analysis_h, analysis_w = int(generated.shape[1]), int(generated.shape[2])

        source_analysis = source
        if (source_h, source_w) != (analysis_h, analysis_w):
            source_analysis = F.interpolate(
                source.permute(0, 3, 1, 2),
                size=(analysis_h, analysis_w),
                mode="bilinear",
                align_corners=False,
            ).permute(0, 2, 3, 1)
        id_images = []
        edge_images = []
        palettes = []
        palette_jsons = []
        counts = []

        for batch_index in range(source.shape[0]):
            source_np = source_analysis[batch_index].detach().cpu().numpy()
            qwen_np = generated[batch_index].detach().cpu().numpy()

            id_np, edge_np, palette_json, actual_count = build_qwen_material_region_map(
                source_np,
                qwen_np,
                region_count=region_count,
                qwen_smoothing=qwen_smoothing,
                cleanup_passes=cleanup_passes,
                edge_protect=edge_protect,
            )

            id_t = torch.from_numpy(id_np).to(device=device, dtype=torch.float32)
            edge_t = torch.from_numpy(edge_np).to(device=device, dtype=torch.float32)

            if (analysis_h, analysis_w) != (source_h, source_w):
                id_t = F.interpolate(
                    id_t.permute(2, 0, 1).unsqueeze(0),
                    size=(source_h, source_w),
                    mode="nearest",
                ).squeeze(0).permute(1, 2, 0)
                edge_t = F.interpolate(
                    edge_t.unsqueeze(0).unsqueeze(0),
                    size=(source_h, source_w),
                    mode="bilinear",
                    align_corners=False,
                ).squeeze(0).squeeze(0)

            edge_rgb = edge_t.unsqueeze(-1).repeat(1, 1, 3)

            id_images.append(id_t)
            edge_images.append(edge_rgb)
            palette_jsons.append(palette_json)
            palettes.append(normalize_palette(palette_json))
            counts.append(int(actual_count))

        if len(id_images) != 1:
            raise ValueError(
                "ARCHVIZ · Qwen Material Region Map v0.1 currently supports batch size 1"
            )

        id_image = torch.stack(id_images, dim=0)
        edge_image = torch.stack(edge_images, dim=0)
        palette = palettes[0]
        palette_json = palette_jsons[0]
        actual_count = counts[0]

        return {
            "ui": {
                "images": _save_ui_preview(id_image, "archviz_qwen_material_region_map"),
                "archviz_qwen_material_region_map": {
                    "region_count": actual_count,
                    "palette": palette,
                    "source": "qwen",
                    "analysis_resolution": [analysis_w, analysis_h],
                    "output_resolution": [source_w, source_h],
                },
            },
            "result": (id_image, edge_image, palette, palette_json, actual_count),
        }


class OLabVisQwenMaterialAnalyzer:
    """Validate Qwen3-VL material analysis and expose one SAM3-ready region at a time."""

    CATEGORY = "OLabVis/Masking"
    FUNCTION = "analyze"
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("plan_json", "sam_prompt", "material_name", "bbox_json", "region_count")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "qwen_text": ("STRING", {"default": "", "multiline": True, "forceInput": True}),
                "source_image": ("IMAGE",),
                "region_index": ("INT", {"default": 0, "min": 0, "max": 15, "step": 1}),
            }
        }

    def analyze(self, qwen_text: str, source_image: torch.Tensor, region_index: int):
        plan = normalize_material_plan(qwen_text)
        region = select_material_region(plan, region_index)
        rgb = _to_rgb(source_image)
        height = int(rgb.shape[1])
        width = int(rgb.shape[2])
        bbox_json = bbox_to_pixel_json(region, width, height)
        return (
            material_plan_to_json(plan),
            region["sam_prompt"],
            region["name"],
            bbox_json,
            len(plan["regions"]),
        )


class OLabVisQwenAnalyzerPrompt:
    """Provide the controlled Qwen3-VL prompt for material analysis before the main sampler."""

    CATEGORY = "OLabVis/Masking"
    FUNCTION = "prompt"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    def prompt(self):
        return (DEFAULT_ANALYZER_PROMPT,)


class OLabVisMaterialIDBuilder:
    """Compose up to eight SAM masks into a deterministic pseudo Material ID image."""

    CATEGORY = "OLabVis/Masking"
    FUNCTION = "build"
    RETURN_TYPES = ("IMAGE", "ARCHVIZ_ID_PALETTE", "STRING", "INT")
    RETURN_NAMES = ("id_image", "palette", "palette_json", "region_count")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        required = {
            "source_image": ("IMAGE",),
            "name_1": ("STRING", {"default": "Material 1"}),
        }
        optional = {"mask_1": ("MASK",)}
        for index in range(2, 9):
            optional[f"mask_{index}"] = ("MASK",)
            optional[f"name_{index}"] = ("STRING", {"default": f"Material {index}"})
        return {"required": required, "optional": optional}

    def build(self, source_image: torch.Tensor, name_1: str, mask_1=None, **kwargs):
        source = _to_rgb(source_image)
        if source.shape[0] != 1:
            raise ValueError("OLabVis · Material ID Builder v0.1 supports batch size 1")

        height, width = int(source.shape[1]), int(source.shape[2])
        device = source.device
        slots = [(mask_1, name_1)]
        for index in range(2, 9):
            slots.append((kwargs.get(f"mask_{index}"), kwargs.get(f"name_{index}", f"Material {index}")))

        active = []
        for mask, name in slots:
            if mask is None:
                continue
            m = mask.to(device=device, dtype=torch.float32)
            if m.ndim == 2:
                m = m.unsqueeze(0)
            if m.ndim != 3:
                raise ValueError("MASK input must have shape [B,H,W] or [H,W]")
            if m.shape[0] != 1:
                raise ValueError("Material ID Builder expects one mask per slot")
            if (int(m.shape[1]), int(m.shape[2])) != (height, width):
                m = F.interpolate(m.unsqueeze(1), size=(height, width), mode="nearest").squeeze(1)
            active.append((m[0] > 0.5, str(name or "Material").strip()[:120]))

        if not active:
            raise ValueError("Connect at least one SAM mask to Material ID Builder")

        colors = [
            [230, 25, 75], [60, 180, 75], [255, 225, 25], [0, 130, 200],
            [245, 130, 48], [145, 30, 180], [70, 240, 240], [240, 50, 230],
        ]
        id_image = torch.zeros((height, width, 3), dtype=torch.float32, device=device)
        occupied = torch.zeros((height, width), dtype=torch.bool, device=device)
        palette_colors = []

        for index, (mask, name) in enumerate(active):
            # Slot order is deterministic overlap arbitration: earlier/more-specific slots win.
            effective = mask & ~occupied
            rgb8 = colors[index]
            rgb = torch.tensor(rgb8, dtype=torch.float32, device=device) / 255.0
            id_image[effective] = rgb
            occupied |= mask
            palette_colors.append({
                "id": f"material-{index + 1:02d}",
                "name": name,
                "rgb": rgb8,
            })

        palette = normalize_palette({"version": 1, "colors": palette_colors})
        palette_json = json.dumps(palette, ensure_ascii=False, separators=(",", ":"))
        batched = id_image.unsqueeze(0)
        return {
            "ui": {
                "images": _save_ui_preview(batched, "olabvis_material_id"),
                "olabvis_material_id": {
                    "region_count": len(active),
                    "overlap_rule": "earlier slot wins",
                },
            },
            "result": (batched, palette, palette_json, len(active)),
        }


NODE_CLASS_MAPPINGS = {
    "ARCHVIZIDColorPickerMask": ARCHVIZIDColorPickerMask,
    "ARCHVIZIDPalettePicker": ARCHVIZIDPalettePicker,
    "ARCHVIZMaskFromPalette": ARCHVIZMaskFromPalette,
    "ARCHVIZIDGroupMask": ARCHVIZIDGroupMask,
    "ARCHVIZColorRangeMask": ARCHVIZColorRangeMask,
    "ARCHVIZQwenMaterialRegionMap": ARCHVIZQwenMaterialRegionMap,
    "OLabVisQwenAnalyzerPrompt": OLabVisQwenAnalyzerPrompt,
    "OLabVisQwenMaterialAnalyzer": OLabVisQwenMaterialAnalyzer,
    "OLabVisMaterialIDBuilder": OLabVisMaterialIDBuilder,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ARCHVIZIDColorPickerMask": "OLabVis · ID Color Picker Mask",
    "ARCHVIZIDPalettePicker": "OLabVis · ID Palette Picker",
    "ARCHVIZMaskFromPalette": "OLabVis · Mask From Palette",
    "ARCHVIZIDGroupMask": "OLabVis · ID Group Mask",
    "ARCHVIZColorRangeMask": "OLabVis · Color Range Mask",
    "ARCHVIZQwenMaterialRegionMap": "OLabVis · Qwen Material Region Map",
    "OLabVisQwenAnalyzerPrompt": "OLabVis · Qwen Analyzer Prompt",
    "OLabVisQwenMaterialAnalyzer": "OLabVis · Qwen Material Analyzer",
    "OLabVisMaterialIDBuilder": "OLabVis · Material ID Builder",
}
