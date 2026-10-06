# ComfyUI · ARCHVIZ ID Mask Toolkit

**Status: LAB**

A small ComfyUI toolkit for deterministic masking from Color ID / Material ID / Object ID passes used in architectural visualization.

The core production idea:

```text
Color / Material / Object ID pass
              │
              ▼
ARCHVIZ · ID Palette Picker
              │
        ARCHVIZ_ID_PALETTE
              │
        ┌─────┴─────────┐
        ▼               ▼
Mask From Palette   ID Group Mask
        │               │
        ▼               ▼
   single MASK      grouped MASK
```

No VLM, SAM, GroundingDINO or semantic segmentation is required when the 3D scene already provides exact IDs.

## Nodes

### ARCHVIZ · ID Color Picker Mask

Quick mode: one clicked RGB color → one deterministic binary mask.

Use when you only need one surface.

### ARCHVIZ · ID Palette Picker

Production mode palette builder.

- one `IMAGE` ID pass;
- in-node preview;
- `+ ADD COLOR`;
- click exact ID color;
- rename/delete slots;
- RGB + HEX diagnostics;
- Sample Radius `0 / 1 / 2` = `1×1 / 3×3 / 5×5`;
- outputs:
  - `ARCHVIZ_ID_PALETTE`;
  - passthrough `IMAGE`.

Palette schema:

```json
{
  "version": 1,
  "colors": [
    {
      "id": "stable-id",
      "name": "Facade Blue",
      "rgb": [41, 78, 166],
      "hex": "#294EA6"
    }
  ]
}
```

The serialized palette widget is the workflow truth source. Browser-only state is not used as the production source of truth.

The picker and backend intentionally operate in the same **8-bit RGB domain (0..255)**. This keeps the clicked preview color and backend exact-match behavior deterministic, including when an upstream image originally had higher channel precision.

### ARCHVIZ · Mask From Palette

Takes:

```text
IMAGE
ARCHVIZ_ID_PALETTE
selected palette color
Tolerance
Invert
```

Returns:

```text
MASK
PREVIEW
HEX
```

Use multiple copies for Road, Greenery, Windows, etc.

### ARCHVIZ · ID Group Mask

Unions several palette slots into one semantic mask.

Example:

```text
Facade Blue
OR
Facade Brown
OR
Stone Arch
=
FACADE MASK
```

Colors are matched independently and combined with logical OR. RGB values are never averaged together.

An empty group is valid and returns an all-black mask (or all-white when `Invert` is enabled), so an unfinished group does not break the graph.

## Baseline mask algorithm

For selected RGB `S` and source pixel `P`:

```text
distance = sqrt((Pr-Sr)^2 + (Pg-Sg)^2 + (Pb-Sb)^2)
mask = 1 when distance <= tolerance, otherwise 0
```

Recommended clean Corona ID baseline:

```text
Tolerance = 5
Sample Radius = 0
Invert = OFF
```

Use PNG for production ID passes. JPEG compression may require a larger tolerance.

## Connection behavior

Palette consumers refresh when the palette is renamed, edited, or deleted. If a selected single slot is deleted, the consumer falls back to the first remaining palette slot. Group selections automatically drop deleted IDs.

The frontend palette resolver follows upstream connections through reroute/pass-through nodes, so normal graph organization does not require a direct visual wire from the palette node to every consumer.

## Important design rule

These nodes perform **ID extraction**, not mask modification.

Do not mix:

```text
Blur
Feather
Grow
Erode
Dilate
```

into extraction. Use separate downstream mask-processing nodes.

## Installation

For the current LAB branch:

```bash
cd ComfyUI/custom_nodes
git clone -b feat/id-mask-toolkit-v0.2 https://github.com/lutiy-dev/ComfyUI-ARCHVIZ-ID-Mask.git
```

Restart ComfyUI.

Nodes are under:

```text
ARCHVIZ / Masking
```

## Repository verification

```bash
python -m unittest discover -s tests -v
python -m py_compile __init__.py nodes.py mask_core.py palette_core.py
node --check web/id_color_picker.js
node --check web/id_palette_system.js
```

Repository checks do **not** prove ComfyUI frontend/runtime compatibility.

## Runtime acceptance

The full toolkit remains LAB until the following pass in a real target ComfyUI install:

1. synthetic known-color ID pass;
2. real Corona ID PNG;
3. palette with at least 5 colors;
4. rename/delete palette slots;
5. workflow save/reload preserves palette;
6. Mask From Palette correctly switches between slots;
7. Group Mask correctly unions multiple slots;
8. `Tolerance=0` performs exact match;
9. masks preserve input resolution;
10. external Preview Mask matches the internal QC result;
11. outputs successfully drive the target FLUX/Qwen/material-pass graph.

## Current validation status

- repository CI: expected to validate syntax and pure palette/mask helpers;
- original quick picker: **LAB / provisional pass**;
- Palette / Single Mask / Group Mask: **LAB / runtime not yet confirmed**.

An importable example workflow JSON will be exported from a real ComfyUI runtime only after the first full runtime PASS.
