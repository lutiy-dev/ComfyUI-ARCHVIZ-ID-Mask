# Agent Rules

## Scope
This repository contains the OLabVis ID Mask Toolkit for ComfyUI.

Current nodes:
- `OLabVis · ID Color Picker Mask` — quick one-color → one-mask mode.
- `OLabVis · ID Palette Picker` — build named RGB slots from one ID pass.
- `OLabVis · Mask From Palette` — one palette slot → one mask.
- `OLabVis · ID Group Mask` — union multiple palette slots into one semantic mask.
- `OLabVis · Color Range Mask` — beauty-image rough masking using adaptive LAB+HSV similarity, Connected selection, channel assistance, and LAB chroma boundary diagnostics.
- `OLabVis · Qwen Material Region Map` — stabilizes a Qwen-generated semantic/material map into deterministic flat-color pseudo Material ID regions for downstream palette and mask nodes.

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

## Color Range v0.1 prototype rules
- Keep the deterministic ID extraction nodes unchanged unless a bug is independently verified.
- Beauty-image masking is a separate path and must not change ID-mask semantics.
- Python backend remains source of truth for workflow outputs.
- LAB chroma is the primary beauty-image color signal; lightness is handled separately; HSV Hue is saturation-reliability weighted.
- Connected mode uses a 4-connected component from the clicked seed.
- LAB Chroma Gradient is the default boundary diagnostic/guidance signal.
- Channel Assist is auxiliary and confidence-gated; it must never silently replace the primary selector.
- Random Walker, SAM, HED, PiDiNet, DexiNed, M-LSD, Depth and Normals are not required dependencies for the first prototype.
- Preserve diagnostic outputs (confidence and edge map) so failures can be localized before adding more algorithms.
- Do not promote the Color Range node beyond LAB/ALPHA until real ComfyUI runtime tests and graph integration pass.


## Qwen Material Region Map v0.1 rules
- Qwen is an upstream semantic/material-map generator; this custom node does not embed or replace the Qwen model runtime.
- Input contract: original beauty/source IMAGE + Qwen-produced material/semantic IMAGE.
- Output contract: deterministic flat-color ID IMAGE + ARCHVIZ_ID_PALETTE + palette JSON + edge diagnostic.
- Canonical output colors must be exact and stable so existing Palette / Mask From Palette / Group Mask nodes can consume them deterministically.
- Qwen output may be lower resolution than the source; analyze at Qwen resolution and return the final ID map at source resolution.
- Source-image LAB Chroma Gradient protects strong material boundaries during cleanup.
- Do not claim the pseudo map is scene truth. Exact Material/Object/Color ID passes remain higher-confidence inputs when available.
- No Flux integration in v0.1. Flux-specific support is a separate future extension and must not alter the Qwen baseline.


## Branding / discovery
- User-facing node display names must start with `OLabVis ·`.
- User-facing node category must be `OLabVis/Masking`.
- Keep internal node class keys stable for workflow compatibility unless a migration is explicitly planned.


## Qwen pre-sampler architecture v0.1
- Primary path is pre-sampler analysis, not post-sampler image analysis.
- Qwen diffusion MODEL is not treated as a mask/semantic output.
- Use the Qwen3-VL text/vision encoder through ComfyUI TextGenerate with the beauty IMAGE before the main Qwen sampler.
- `OLabVis · Qwen Analyzer Prompt` provides the controlled JSON-only analysis prompt.
- `OLabVis · Qwen Material Analyzer` validates/normalizes TextGenerate output and exposes one SAM3-ready material region at a time.
- SAM3 remains the pixel segmentation/refinement stage.
- `OLabVis · Material ID Builder` converts SAM masks into exact flat RGB pseudo Material ID + serializable palette.
- Overlap arbitration in Material ID Builder v0.1 is deterministic: earlier slots win. Put more specific masks first.
- Existing `OLabVis · Qwen Material Region Map` remains a fallback normalizer for already-generated flat/semantic images; it is not the preferred pre-sampler route.
- First runtime checkpoint is Qwen3-VL TextGenerate → Qwen Material Analyzer. Do not add SAM3 until the JSON/material plan checkpoint passes.
