# Changelog

## v0.2.0 — Production Candidate

Status: **PRODUCTION CANDIDATE**

### Added
- ARCHVIZ · ID Palette Picker
- ARCHVIZ · Mask From Palette
- ARCHVIZ · ID Group Mask
- reusable palette workflow state
- single and grouped binary masks
- synthetic stress-test workflow and ID asset
- README hero/banner and installation guide

### Hardened
- direct executed-preview capture for picker UI
- palette rename/delete propagation
- stale palette ID cleanup
- empty-group handling
- Reroute-aware palette source resolution
- 8-bit frontend/backend RGB consistency
- mask comparison performance

### Verified
- repository CI
- synthetic ComfyUI stress-test
- real architectural ID pass
- picker RGB/HEX updates
- rename/delete behavior
- workflow save/reload persistence
- single masks
- grouped OR masks
- Invert
- Tolerance 0 / 20

### Pending
- full ARCHVIZ production material-graph integration
- dedicated Reroute runtime acceptance
- Comfy Registry/API publication
