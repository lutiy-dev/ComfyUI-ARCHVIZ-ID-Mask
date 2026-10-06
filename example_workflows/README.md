# Example workflows

## LAB stress test

`ARCHVIZ_ID_MASK_TOOLKIT_STRESS_TEST_v0.2.json` is the integration test graph for the toolkit.

It exercises:

- one ID image → one palette;
- two independent `Mask From Palette` branches;
- one multi-color `ID Group Mask`;
- external `Preview Image` QC outputs;
- preloaded palette IDs for the synthetic test image.

### Required test image

Copy:

`example_assets/ARCHVIZ_ID_STRESS_TEST.png`

into:

`ComfyUI/input/ARCHVIZ_ID_STRESS_TEST.png`

before opening/running the workflow.

### Expected baseline

- Road preview = only the neutral grey Road zone.
- Greenery preview = only the green zone.
- Facade group preview = Facade Blue + Facade Brown + Sand.
- `Tolerance = 5`.
- `Sample Radius = 0`.

Then use the palette picker manually: add/resample colors, rename slots, delete one, save/reload the workflow, and verify all downstream selectors/groups remain valid.

> Status: **LAB**. The JSON has been syntax-validated in-repo, but final ComfyUI import/runtime compatibility is not claimed until the real target installation passes.
