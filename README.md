# ComfyUI · ARCHVIZ ID Mask Toolkit

<p align="center">
  <img src="docs/assets/id-mask-toolkit-banner.svg" alt="ARCHVIZ ID Mask Toolkit — Color ID to production masks for ComfyUI" width="100%" />
</p>

**Status: PRODUCTION CANDIDATE · real ComfyUI runtime validated**

A small ComfyUI toolkit for deterministic masking from Color ID / Material ID / Object ID passes used in architectural visualization.

## Visual overview

The toolkit is designed as a reusable Scene Truth masking layer for controlled Archviz production.

The core production idea:

```text
Color / Material / Object ID pass
              │
              ▼
OLabVis · ID Palette Picker
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


> **Qwen pseudo-ID branch:** `feat/qwen-material-region-map-v0.1` adds an optional fallback path for scenes that do **not** have a real Material/Object/Color ID pass. Exact scene ID remains preferred when available.

### OLabVis · Qwen Material Region Map — LAB / ALPHA

This node converts a Qwen-generated material/semantic map into a deterministic flat-color pseudo Material ID that the existing toolkit can consume.

Production concept:

```text
BEAUTY RENDER
     │
     ├──────────────→ source_image
     │
     └→ Qwen image-edit / segmentation-style pass
                         │
                         ▼
                 qwen_map IMAGE
                         │
                         ▼
          OLabVis · Qwen Material Region Map
                         │
             ┌───────────┴────────────┐
             ▼                        ▼
        flat ID IMAGE          generated palette
             │
             ▼
      ID Palette Picker
             │
      name / group regions
             │
     Mask From Palette / Group Mask
```

The node does **not** pretend to reconstruct true 3D material metadata. It creates a production-oriented **pseudo Material ID / Material Region Map** when no exact ID pass exists.

Inputs:
- `source_image` — original beauty render, used for boundary protection;
- `qwen_map` — Qwen-generated semantic/material-region image;
- `region_count` — target number of flat regions, default 12;
- `qwen_smoothing` — suppress small generated color noise;
- `cleanup_passes` — majority cleanup of flat regions;
- `edge_protect` — protects strong LAB chroma boundaries from cleanup spill.

Outputs:
- `id_image` — exact flat canonical RGB regions;
- `edge_map` — LAB Chroma Gradient diagnostic;
- `palette` — `ARCHVIZ_ID_PALETTE` for direct downstream use;
- `palette_json` — serialized diagnostic palette;
- `region_count` — actual number of used regions.

If Qwen runs at lower resolution than the beauty render, the node analyzes at Qwen resolution and returns the final ID image at source resolution.

Recommended Qwen instruction for the first test:

```text
Convert this architectural render into a flat material-region ID map.
Preserve the exact camera, silhouette, openings and object boundaries.
Assign one solid flat color to each visually distinct material/surface class:
each facade material, glazing/windows, roof, metal, wood, pavement, road,
curb, vegetation, sky, water and people when present.
Use the same color for the same material across light and shadow.
Use clearly different colors for different materials.
No texture, lighting, shadows, gradients, reflections, outlines, labels or text.
Output only the flat material-region map.
```

Qwen is used as the semantic/material grouping stage. The custom node then removes generated color drift and converts the result into stable exact IDs. Flux is intentionally not part of this v0.1 branch.


Acceptance workflow:

`example_workflows/ARCHVIZ_QWEN_MATERIAL_REGION_MAP_v0.1.json`

For the first test, save one Qwen material-map output as `qwen_material_map.png`, load it together with the original beauty render, and verify that the node returns a stable flat-color ID image. The generated `palette` can feed `Mask From Palette` directly; `id_image` can also be routed into `ID Palette Picker` when manual naming/curation is preferred.

## Nodes

### OLabVis · ID Color Picker Mask

Quick mode: one clicked RGB color → one deterministic binary mask.

Use when you only need one surface.

### OLabVis · ID Palette Picker

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

### OLabVis · Mask From Palette

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

### OLabVis · ID Group Mask

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

### Current v0.2 candidate branch

Clone directly into `ComfyUI/custom_nodes`:

```bash
cd ComfyUI/custom_nodes
git clone -b feat/id-mask-toolkit-v0.2 https://github.com/lutiy-dev/ComfyUI-ARCHVIZ-ID-Mask.git
```

Restart ComfyUI.

Nodes are under:

```text
OLabVis / Masking
```

This branch has passed synthetic and real-scene ComfyUI runtime validation. Final integration into the full production material workflow is still pending before release/registry publication.

## Ready-made stress-test workflow

The repository includes a complete LAB integration graph:

**`example_workflows/ARCHVIZ_ID_MASK_TOOLKIT_STRESS_TEST_v0.2.json`**

and a deterministic synthetic Color ID image:

**`example_assets/ARCHVIZ_ID_STRESS_TEST.png`**

The graph is prewired as:

```text
Load Image
    ↓
OLabVis · ID Palette Picker
    ├─ Mask From Palette → Road → Preview
    ├─ Mask From Palette → Greenery → Preview
    └─ ID Group Mask → Facade → Preview
```

The synthetic palette includes:

```text
Facade Blue
Facade Brown
Road
Greenery
Windows
Sand
```

and the image also contains near-color stress zones to probe tolerance behavior.

### Run the test

1. Install the LAB branch and restart ComfyUI.
2. Copy `example_assets/ARCHVIZ_ID_STRESS_TEST.png` to `ComfyUI/input/`.
3. Drag `example_workflows/ARCHVIZ_ID_MASK_TOOLKIT_STRESS_TEST_v0.2.json` into ComfyUI.
4. Queue once.
5. Expected:
   - Road preview = only Road;
   - Greenery preview = only Greenery;
   - Facade group = Facade Blue + Facade Brown + Sand.
6. In Palette Picker, add/resample a color with the pipette.
7. Rename it, delete another slot, save/reload the workflow and verify downstream selectors remain valid.
8. Replace the synthetic input with a real Corona Color/Material/Object ID PNG and repeat.

### Red-test checklist

Stress the graph deliberately:

```text
Tolerance: 0 / 1 / 5 / 20
Sample Radius: 0 / 1 / 2
rename palette slot
delete selected slot
empty group
Invert
Reroute between palette and consumer
save → close → reopen
replace source ID image
large palette / many grouped colors
```

The workflow JSON and toolkit have passed real ComfyUI runtime validation on the synthetic stress-test and on a real architectural ID pass.

## Repository verification

```bash
python -m unittest discover -s tests -v
python -m py_compile __init__.py nodes.py mask_core.py palette_core.py color_range_core.py qwen_material_region_core.py
node --check web/id_color_picker.js
node --check web/id_palette_system.js
```

Repository checks do **not** prove ComfyUI frontend/runtime compatibility.

## Runtime acceptance

The following runtime acceptance matrix is used for release gating:

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

**VERIFIED**
- repository CI: PASS;
- custom nodes register and load in the target ComfyUI runtime;
- synthetic stress-test workflow: PASS;
- palette picker click → RGB/HEX slot update: PASS;
- rename/delete propagation: PASS;
- workflow save/reload persistence: PASS;
- single palette masks: PASS;
- grouped OR masks: PASS;
- Invert: PASS;
- Tolerance 0 / 20 behavior: PASS;
- real architectural ID pass: PASS;
- masks preserve source resolution in tested runs.

**NOT YET CONFIRMED**
- final integration inside the full ARCHVIZ production material graph;
- dedicated Reroute acceptance test in the target frontend;
- Comfy Registry/API publication.

Current release gate: **PRODUCTION CANDIDATE**.

The included stress-test workflow remains the reproducible public example. The next milestone is integration into the main production workflow, followed by release/registry preparation.


## Qwen pre-sampler Material ID path — LAB / ALPHA

The preferred Qwen masking architecture now runs **before** the main material-edit sampler:

```text
Beauty IMAGE
   │
   ├─ Qwen3-VL / Generate Text
   │       │
   │       ▼
   │  OLabVis · Qwen Material Analyzer
   │       │
   │       ▼
   │    material plan
   │       │
   │       ▼
   │     SAM3
   │       │
   │       ▼
   │  OLabVis · Material ID Builder
   │       │
   │       ├─ flat RGB pseudo Material ID
   │       └─ ARCHVIZ_ID_PALETTE
   │
   └────────────────────────────→ main Qwen Image 2.1 material-edit sampler
                                   using the selected MASK
```

Important: the Qwen diffusion `MODEL` socket is not a semantic/mask output. Scene understanding is performed by the Qwen3-VL vision/text path before sampling.

### New nodes

**`OLabVis · Qwen Analyzer Prompt`**
- outputs the controlled JSON-only Qwen3-VL analysis prompt.

**`OLabVis · Qwen Material Analyzer`**
- input: TextGenerate output + source IMAGE;
- validates/normalizes the Qwen material plan;
- outputs: normalized plan JSON, selected `sam_prompt`, material name, bbox diagnostic and region count;
- `region_index` lets you inspect one detected material region at a time.

**`OLabVis · Material ID Builder`**
- accepts up to eight SAM masks;
- assigns deterministic exact RGB IDs;
- outputs flat ID IMAGE + `ARCHVIZ_ID_PALETTE`;
- overlap rule v0.1: earlier slots win, so put specific masks (glass/frame/curb) before generic masks (facade/road).

### First runtime checkpoint

Test only this first:

```text
Qwen3-VL CLIP + Beauty IMAGE
        ↓
ComfyUI Generate Text
        ↓
OLabVis · Qwen Material Analyzer
        ↓
plan_json / sam_prompt / material_name
```

Do **not** connect SAM3 until this checkpoint returns a valid material plan. This follows the project Checkpoint Workflow and isolates Qwen analysis from segmentation errors.

The older **`OLabVis · Qwen Material Region Map`** is kept as a fallback for workflows that already produce a generated semantic/flat map image.
