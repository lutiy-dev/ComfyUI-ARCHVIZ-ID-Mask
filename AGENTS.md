# Agent Rules

## Scope
This repository contains one focused ComfyUI custom node: `ARCHVIZ · ID Color Picker Mask`.

## Production invariants
- Color ID / Material ID / Object ID is the geometry truth source.
- The frontend may select RGB and provide QC preview, but Python backend produces the workflow `MASK` output.
- Extraction must remain binary. Do not add blur, feather, grow, erode, dilate, or generative segmentation to this node.
- Do not silently replace RGB Euclidean tolerance with another color metric.
- Preserve input image resolution in the returned mask.
- Do not add model dependencies.

## Workflow
INSPECT → UNDERSTAND → PLAN → CHANGE → VERIFY → DOCUMENT → REPORT.

## Status
Until a real ComfyUI runtime test passes on synthetic and Corona ID passes, the project remains **LAB**.
