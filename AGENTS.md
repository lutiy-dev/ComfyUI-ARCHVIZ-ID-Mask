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
Current status: **PRODUCTION CANDIDATE**.

Verified in the target ComfyUI runtime:
- synthetic stress-test workflow;
- real architectural ID pass;
- palette picking;
- single and grouped masks;
- rename/delete propagation;
- workflow persistence;
- Invert and tolerance behavior.

Do not promote to PRODUCTION until the full ARCHVIZ material workflow integration test passes.


## Pre-runtime verification rule

Before asking the user to perform a manual runtime test:

1. Complete all repository-level checks that can be done without the user's machine.
2. Run static checks, unit tests, schema/config validation, and synthetic/stress tests where applicable.
3. Proactively inspect likely failure points and harden them when the fix is clear and low-risk.
4. Prefer one integrated final acceptance test over many intermediate manual checks.
5. Leave only environment-specific/runtime verification to the user.
6. Do not claim PRODUCTION/STABLE until that final real-runtime test passes.

Goal: minimize manual testing time while preserving evidence and reproducibility.
