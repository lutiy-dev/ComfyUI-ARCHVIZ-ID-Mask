from __future__ import annotations

import os
import uuid

import numpy as np
import torch
from PIL import Image

import folder_paths

from .mask_core import MAX_RGB_DISTANCE, normalize_rgb, rgb_to_hex


class ARCHVIZIDColorPickerMask:
    """Extract a deterministic binary mask from an RGB Color/Object/Material ID pass."""

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

    @staticmethod
    def _to_rgb(image: torch.Tensor) -> torch.Tensor:
        if image.ndim != 4:
            raise ValueError(f"Expected IMAGE tensor [B,H,W,C], got shape {tuple(image.shape)}")
        if image.shape[-1] < 3:
            raise ValueError("IMAGE input must contain at least RGB channels")
        return image[..., :3].to(dtype=torch.float32).clamp(0.0, 1.0)

    @staticmethod
    def _save_ui_preview(preview: torch.Tensor) -> list[dict]:
        first = preview[0].detach().cpu().clamp(0.0, 1.0).numpy()
        array = np.rint(first * 255.0).astype(np.uint8)
        filename = f"archviz_id_mask_{uuid.uuid4().hex}.png"
        temp_dir = folder_paths.get_temp_directory()
        os.makedirs(temp_dir, exist_ok=True)
        Image.fromarray(array, mode="RGB").save(
            os.path.join(temp_dir, filename),
            compress_level=1,
        )
        return [{"filename": filename, "subfolder": "", "type": "temp"}]

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
        # Sampling is applied by the frontend picker before RGB reaches Python.
        # Keeping the widget as a backend input makes the chosen sampling mode
        # part of the serialized workflow state.
        del sample_radius

        rgb = self._to_rgb(image)
        r, g, b = normalize_rgb(red, green, blue)
        selected = torch.tensor(
            [r, g, b],
            dtype=rgb.dtype,
            device=rgb.device,
        ) / 255.0

        # Convert normalized tensor distance back to 0..255 RGB-distance units.
        distance = torch.linalg.vector_norm(rgb - selected, dim=-1) * 255.0
        mask = (distance <= float(tolerance)).to(dtype=torch.float32)
        if invert:
            mask = 1.0 - mask

        preview = mask.unsqueeze(-1).repeat(1, 1, 1, 3)
        color_hex = rgb_to_hex(r, g, b)

        return {
            "ui": {
                "images": self._save_ui_preview(preview),
                "archviz_id_mask": {
                    "selected_rgb": [r, g, b],
                    "hex": color_hex,
                    "tolerance": float(tolerance),
                },
            },
            "result": (mask, preview, r, g, b, color_hex),
        }


NODE_CLASS_MAPPINGS = {
    "ARCHVIZIDColorPickerMask": ARCHVIZIDColorPickerMask,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ARCHVIZIDColorPickerMask": "ARCHVIZ · ID Color Picker Mask",
}
