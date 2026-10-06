# Agent Rules

## Scope
This repository contains the ARCHVIZ ID Mask Toolkit for ComfyUI.

Current LAB nodes:
- `ARCHVIZ · ID Color Picker Mask` — quick one-color → one-mask mode.
- `ARCHVIZ · ID Palette Picker` — build named RGB slots from one ID pass.
- `ARCHVIZ · Mask From Palette` — one palette slot → one mask.
- `ARCHVIZ · ID Group Mask` — union multiple palette slots into one semantic mask.

## Production invariants
- Color ID / Material ID / Object ID is the geometry truth source.
- Frontend code may select RGB and provide QC controls, but Python backend produces workflow `MASK` outputs.
- Extraction must remain binary. Do not add blur, feather, grow, erode, dilate, or generative segmentation to these extraction nodes.
- Do not silently replace RGB Euclidean tolerance with another color metric.
- Preserve input image resolution in returned masks.
- Do not add model dependencies.
- `ID_PALETTE` must be serializable through workflow widgets; do not make browser-only state the source of truth.
- Palette RGB is truth; tolerance belongs to mask extraction, not palette storage.

## Workflow
INSPECT → UNDERSTAND → PLAN → CHANGE → VERIFY → DOCUMENT → REPORT.

## Status
Until a real ComfyUI runtime test passes on synthetic and Corona ID passes, the toolkit remains **LAB**.
