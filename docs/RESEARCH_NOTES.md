# Research notes

Sources reviewed on 2026-10-07 and what each one contributed.

## Sources

- **[LTX for VFX](https://ltx.io/solution/vfx):** Lightricks' VFX landing page. It groups the
  VFX tools:
  - Native Resolution (TiledFusion at 4K/8K on one GPU)
  - Refine and Restore
  - SDR to HDR, and native HDR (EXR in, EXR out, ACES)
  - Layout to Render (beta)
  - Alpha Gen (beta)

  The page says the model "runs locally on 12GB VRAM". That number refers to the base model
  in quantized form. The IC-LoRA workflow tested here peaked at about 19 GB.
- **[Alpha Gen model card](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Alpha-Gen):**
  the settings in [MODES.md](MODES.md#alpha-gen-beta-tested-in-this-repo).
- **[Video: "LTX Alpha Gen Changed My Entire VFX Pipeline" (Jonathan Winbush, 2026-10-02, 14:47)](https://www.youtube.com/watch?v=mzn9R9RJIHs):**
  it uses the same official workflow.
  - Chapters: workflow setup (1:05), generation and compositing (2:12), analysing the matte
    (4:04), complex transparency (5:39), advanced edge extraction (8:03), resolution and
    aspect ratio (9:11), fixing problematic footage (10:42).
  - There is a hosted version to compare against on
    [LTX Explore](https://app.ltx.io/workflows/96d13cde-772a-4b78-a65c-d91c4b144b18).
  - The transcript could not be fetched, so only the chapters and description were used.
- **[ComfyUI-LTXVideo 2.5 example workflows](https://github.com/Lightricks/ComfyUI-LTXVideo/tree/master/example_workflows/2.5):**
  the README has a "which workflow should I use" tree. The workflow used here,
  `LTX-2.5_V2V_ICLoRA_Single_Stage_Distilled.json`, is described as "video-to-video using
  the source frames as IC-LoRA guides". Its original audio is frozen through.
- **[LTX-2.5 base card](https://huggingface.co/Lightricks/LTX-2.5):** the list of weight
  variants and sizes, and the sampling rules (distilled: 8 steps, CFG 1; frames 8n+1;
  dimensions multiples of 32).
- **[Comfy docs: LTX-2.5](https://docs.comfy.org/tutorials/video/ltx/ltx-2-5):** core
  support landed before ComfyUI v0.32.0.

- **[LTX docs: Alpha Gen guide](https://docs.ltx.io/open-source-model/vfx-post-production/alpha-gen):**
  - 121 frames or fewer is recommended; 122–145 is less reliable.
  - The Python CLI uses `--skip-stage-2` with 2x width and height, so stage 1 runs at the
    source resolution.
  - Long clips need chunking; nothing splits them automatically.
- **[Logik forum thread](https://forum.logik.tv/t/ltx-2-5-alpha-gen/15024):** Flame artists
  testing it in production.
  - Comparisons against Silhouette Matte ML, Flame AutoMatte and SAMMIE.
  - VRAM use of about 90 GB at 3200x1900.
  - 1920x1080 sources come back at 1088, so crop the matte to the source.
  - Advice to choose seam points carefully when chunking.
- **Community workflows:**
  [Alex Villabon](https://github.com/avillabon/Tutorial_Files/tree/main/LTX%202.5%20Alpha%20Gen%20Beta)
  and the Ok Todd version of it
  ([video](https://www.youtube.com/watch?v=J-3rK-8ths4)). Both:
  - use a 1088 short side, seed 1234 and decode temporal 64/8
  - export alpha, premult and over-green previews, plus a contact sheet
- **Not useful:** a community-merged NVFP4 single file
  ([mskim8584/LTX-2.5-Alpha-Gen-VideoOnly-NVFP4](https://huggingface.co/mskim8584/LTX-2.5-Alpha-Gen-VideoOnly-NVFP4)).
  Its own card says it failed the author's matte-quality gates.
- Reddit had no threads with settings at the time of writing (2026-10-07).

## How the V2V IC-LoRA workflow works

The graph has five subgraphs, read left to right:

1. **Load Models:**
   - UNET (distilled transformer)
   - `LTXICLoRALoaderModelOnly` (applies the IC-LoRA and returns its `latent_downscale_factor`)
   - two VAEs
   - two CLIPs: the 12B encoder and the E2B prompt enhancer
2. **Inputs / Source video:**
   - `LoadVideo`, then `GetVideoComponents` and a resize to the shorter side 544
   - width, height, length, fps and audio are all read from the clip
   - prompt encoding has an optional enhancer
   - if an LTX API key is filled in, the graph switches to remote Gemma encoding (`GemmaAPITextEncode`)
3. **Preprocess:**
   - `EmptyLTXVLatentVideo` at the source size
   - optional first-frame image (`LTXVImgToVideoInplace`)
   - `LTXAddVideoICLoRAGuide` injects the source frames as guides
   - the source audio is encoded and frozen (`LTXVSetAudioRefTokens`)
4. **Generate:**
   - `SamplerCustomAdvanced` with `ManualSigmas`, 8 distilled steps, `euler_ancestral`, CFG 1
   - `LTXVCropGuides` then removes the guide frames from the latent
5. **Decode:** `VAEDecodeTiled` for video and `LTXVAudioVAEDecode` for audio, then `CreateVideo` and `SaveVideo`.

## Setup log for this machine

- **ComfyUI:** portable 0.34.0. Its LTX core nodes were already enough.
- **ComfyUI-LTXVideo:** updated from `aceeae9` (2026-06-30) to `3bf3ca6` (2026-10-01). The
  old version predates LTX-2.5.
- **Gated downloads:** the Lightricks repos are gated, so downloads need the license
  accepted plus a login. The portable `hf.exe` is broken (no `venv` module), so the login
  was done with a system Python.
- **Weights:** the int8-convrot variants (21.5 GB transformer and 15.4 GB encoder). They load
  and run on a 24 GB laptop GPU.
- **Results:** two Alpha Gen runs, in [tests/](../tests/README.md).

## Open questions and next experiments

- Same clip at shorter side 768 and 1088, to measure the VRAM peak and edge quality.
- 145 frames (the Alpha Gen maximum) against 97.
- Semi-transparent material such as smoke, glass or a veil, which is the case the card
  advertises.
- Several people in frame, to see which one becomes the foreground.
- Clean Plate on the same clips, to build a matte plus clean background pair for compositing.
- Video VAE `conv` against the diffusion decoder, comparing speed and matte edges.
