# ComfyUI · ARCHVIZ ID Mask

**Status: LAB**

`ARCHVIZ · ID Color Picker Mask` turns a Color ID / Material ID / Object ID pass into a deterministic binary ComfyUI `MASK`.

The production idea is deliberately simple:

```text
Corona / 3ds Max ID pass
        ↓
ARCHVIZ · ID Color Picker Mask
        ↓
click exact ID color
        ↓
MASK + QC preview
        ↓
FLUX / Qwen / material pass / masked composite
```

No VLM, SAM, GroundingDINO or semantic segmentation is required when the 3D scene already provides exact IDs.

## v0.1 scope

- `IMAGE` input;
- in-node picker UI;
- source-image pixel sampling;
- `Sample Radius`: 0 = 1 px, 1 = 3×3 average, 2 = 5×5 average;
- selected RGB swatch + RGB + HEX;
- Euclidean RGB `Tolerance` (default `5`);
- deterministic Python backend mask extraction;
- `Invert`;
- local `ID / MASK` QC view;
- outputs: `MASK`, grayscale `IMAGE` preview, `R`, `G`, `B`, `HEX`.

The frontend is **not** the source of truth for the workflow mask. JavaScript selects RGB; Python calculates the returned mask.

## Current LAB workflow

Because the input arrives as an upstream ComfyUI `IMAGE` tensor, the frontend needs one execution before it can display that exact input preview.

1. Connect the ID pass.
2. Queue once to load the current input preview.
3. Click `🎯 PICK COLOR`, then click the required ID region.
4. Inspect the instant local `MASK` preview.
5. Queue again to update the real backend `MASK` output.

The picker maps the click back to the preview image's natural pixel dimensions before sampling. The real workflow mask is still calculated by Python from the persisted RGB values.

## Algorithm

For selected RGB `S` and pixel RGB `P`:

```text
distance = sqrt((Pr-Sr)^2 + (Pg-Sg)^2 + (Pb-Sb)^2)
mask = 1 when distance <= tolerance, otherwise 0
```

The node does not blur or feather the result.

Recommended baseline for a clean Corona ID pass:

```text
Tolerance = 5
Sample Radius = 0
Invert = OFF
```

Use PNG for production ID passes. JPEG compression may create near-identical colors and normally needs a larger tolerance.

## Installation

Clone into `ComfyUI/custom_nodes/` and restart ComfyUI:

```bash
git clone https://github.com/lutiy-dev/ComfyUI-ARCHVIZ-ID-Mask.git
```

Node path:

```text
ARCHVIZ / Masking / ARCHVIZ · ID Color Picker Mask
```

## Repository verification

```bash
python -m unittest discover -s tests -v
python -m py_compile __init__.py nodes.py mask_core.py
node --check web/id_color_picker.js
```

These checks validate the repository-level code. They do **not** prove ComfyUI runtime compatibility.

## Runtime acceptance required before STABLE

1. Synthetic ID image with known RGB values.
2. Clean PNG Corona ID pass.
3. Anti-aliased boundary.
4. JPEG edge case.
5. Multiple image resolutions and preview scales.
6. Workflow save/reload preserves selected RGB.
7. Output mask resolution equals input resolution.
8. `Tolerance=0` performs exact match.
9. Output `MASK` successfully drives the target material-pass workflow.

Until these pass in the target ComfyUI installation, status remains **LAB**.

## Example workflow

An importable workflow JSON is intentionally not hand-authored yet. It will be exported from the real ComfyUI runtime after the first runtime PASS so the file matches the actual active workflow schema.

## Design rule

This node extracts geometry truth. Mask modification belongs in separate downstream nodes such as Grow, Blur, Feather, Erode or Dilate.
