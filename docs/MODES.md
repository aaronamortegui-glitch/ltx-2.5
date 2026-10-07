# Use modes: LTX-2.5 and its LoRAs

What each model in the LTX-2.5 family is for, and how to drive it. Summarized from the
official Hugging Face model cards (October 2026). "Not stated" means the card does not say.
Always check the card before relying on a value.

- [Quick reference](#quick-reference)
- [Base model](#base-model-ltx-25)
- [VFX: mattes and plates](#vfx-mattes-and-plates): Alpha Gen, Clean Plate, Water Simulation
- [Restoration](#restoration): Deblur, Decompression, Colorization, Restore, Refine Details, Pixel Spatial Upscaler
- [Look change](#look-change): Day-to-Night, SDR-to-HDR
- [Generation control](#generation-control): Layout to Render, Ingredients
- [Motion](#motion): Cinemagraph, Slow Motion Control

## Quick reference

| LoRA | Category | Input | Prompt | One-line use | ComfyUI workflow |
|---|---|---|---|---|---|
| **Alpha Gen** | VFX | RGB video | **must be empty** | Alpha matte for compositing (hair, smoke, glass) | V2V IC-LoRA single stage |
| Clean Plate | VFX | video with subjects | yes | Remove people and vehicles to get an empty background plate | V2V IC-LoRA single stage |
| Water Simulation | VFX | "dry" video | yes, `ADD WATER` | Add interacting water to a live-action shot | V2V IC-LoRA single stage |
| Deblur | Restoration | out-of-focus video | yes, `DEBLUR` | Sharpen defocus (not motion blur) | V2V IC-LoRA single stage |
| Decompression | Restoration | low-bitrate video | yes, `ENHANCE QUALITY` | Remove macroblocking, ringing and banding | V2V IC-LoRA single stage |
| Colorization | Restoration | grayscale video | yes, `COLORIZE` | Colorize black-and-white footage | V2V IC-LoRA single stage |
| Restore | Restoration | archive video | yes (period, place, light) | Clean and colorize old film or tape | TiledFusion Upscale |
| Refine Details | Restoration | video resized to the output size | yes (generic look) | Tiled detail rebuild, 1080p to 4K | TiledFusion Upscale |
| Pixel Spatial Upscaler | Restoration | half-resolution video | not stated | Generative 2x upscale of a draft | V2V IC-LoRA single stage |
| Day-to-Night | Look | day video | yes | Relight a daytime shot as night | V2V IC-LoRA single stage |
| SDR-to-HDR | Look | SDR video | no (uses an embedding file) | 8-bit SDR to 16-bit EXR + HLG | ICLoRA SDR to HDR |
| Layout to Render | Generation | 3D blocking video + styled first frame | yes | Turn a clay or blocking playblast into the final shot | Layout To Render two stage |
| Ingredients | Generation | reference-sheet image | yes (two parts) | Keep cast, props and set consistent with a sheet | ICLoRA Ingredients |
| Cinemagraph | Motion | still image | yes, `CINEMAGRAPH_MOTION` | Looping cinemagraph | T2V/I2V single stage |
| Slow Motion Control | Motion | still image + `speed` | yes (plain caption) | Image-to-video at 1x to 40x slow motion | I2V Speed Control (in the LoRA repo) |

**IC-LoRA** means "in-context LoRA": the model sees a reference video (or image) as guide
frames and transforms it. All the V2V ones share
[`LTX-2.5_V2V_ICLoRA_Single_Stage_Distilled.json`](../workflows/LTX-2.5_V2V_ICLoRA_Single_Stage_Distilled.json).
To switch between them, change the LoRA in the **Load Models** subgraph and write the prompt
the card asks for.

Rules shared by most cards:
- Use the **distilled** base: 8 steps, CFG 1, no negative prompt.
- Stay **stage 1 only**, at native resolution. The two-stage path drifts identity or erases the effect.
- Frames must be **8n+1** and width and height **multiples of 32**.
- The stock V2V workflow encodes the source audio, so a clip with no audio track needs a silent one. `scripts/run_alpha_gen.py` adds it.

---

## Base model: LTX-2.5

A 22B open-weights audio and video model. It generates synchronized video and sound from
text, images, video and audio (T2V, I2V, V2V, A2V).

New in 2.5:
- native multishot, keeping characters, voice and style consistent across cuts
- a diffusion video decoder
- a Gemma 4 12B text encoder
- a prompt enhancer
- an optional duration predictor
- a stronger distilled model

| piece | files |
|---|---|
| transformer | `dev` (full, trainable) and `distilled` (8 steps, CFG 1). Each comes in bf16 42 GB and Comfy int8-convrot 21.5 GB. Distilled also comes in NVFP4, 18.7 GB |
| text encoder | Gemma 4 12B with projection: bf16 26 GB or int8 15.4 GB |
| video VAE | `video-vae` (diffusion decoder, best quality) or `video-vae-conv` (lower memory, faster) |
| audio VAE | `audio-vae` with vocoder |
| upscalers | latent spatial x2 (needed for the two-stage graphs) and latent temporal x2 |
| extras | `distilled-lora-450` (to use dev like distilled) and `duration-head` (predicts clip length from the prompt) |

According to the card, most LoRAs trained on LTX-2.3 also run on 2.5. Validate each one first.

---

## VFX: mattes and plates

### Alpha Gen (beta), tested in this repo
- **Does:** Turns an ordinary RGB clip into a grayscale alpha matte (white is foreground). No green screen, mask or prompt is needed. Handles hair, fur, smoke, fire, glass and water.
- **File:** `ltx-2.5-22b-ic-lora-alpha-gen-0.9.safetensors` (step 25000), on the distilled base.
- **Prompt:** always empty (`""`). Text does not steer the matte.
- **Strength:** 1.0. The reference conditioning strength is also 1.0.
- **Limits:**
  - Up to 1920x1088 and 145 frames. Pad the clip rather than stretching it.
  - Above 145 frames, RGB leaks into the matte, so split long clips.
  - You cannot choose which object becomes the foreground.
  - The card says full HD at 145 frames needs an H100/B200-class GPU.
- **Output:** use it as the alpha of the original clip, as `side_by_side.mp4` in `tests/` does.

### Clean Plate
- **Does:** Removes moving subjects (people, cars) and rebuilds the empty background.
- **File:** `ltx-2.5-22b-ic-lora-clean-plate-1.0.safetensors`, strength 1.0.
- **Prompt:**
  - Describe the *empty* scene, for example "An empty clean plate of the exact same location…". Don't write a "remove X" command.
  - Put unwanted subjects in the negative prompt.
  - To force an object out, name it in both the positive ("no bicycle") and the negative.
- **Limits:**
  - Trained at 1024x576 and 576x1024, 49 frames at 25 fps. Validated up to 1920x1088.
  - Struggles when the subject fills the center of the frame (use mask inpainting for that).
  - No mask input.

### Water Simulation
- **Does:** Adds realistic water (rivers, surf, rain, floods, wet surfaces). Identity, clothing and framing stay the same.
- **File:** `ltx-2.5-22b-ic-lora-water-simulation-0.9.safetensors`.
- **Prompt:** uses the trigger `ADD WATER`. Template: "Reference shows <dry scene>. Edited shows the same scene with water added. ADD WATER <water>…"
- **Strength:**
  - 1.0 to 1.05 is the default.
  - 1.1 to 1.5 for hard surface replacement.
  - 0.9 or lower is too weak.
  - 1.5 or higher can warp faces.
- **Limits:**
  - 1920x1088 or 1088x1920 at 24 fps, up to 185 frames.
  - Stay on stage 1. Two-stage erases the water.

---

## Restoration

### Deblur
- **Does:** Brings back sharpness in out-of-focus footage. It does not fix motion blur, noise or compression.
- **File:** `ltx-2.5-22b-ic-lora-deblur-0.9.safetensors`. The original workflow ships with the 2.3 version, `ltx-2.3-22b-ic-lora-deblur-0.9`.
- **Prompt:** "Reference shows <scene>, heavily out of focus… DEBLUR <scene>…"
- **Strength:** 1.0. Lower it toward 0.8 if you see halos.
- **Limits:**
  - Trained at 960x544, 121 frames at 24 fps.
  - If the effect is weak at 1080p, try around 1536x896.

### Decompression
- **Does:** Removes macroblocking, chroma bleed, ringing and banding from low-bitrate video.
- **File:** `ltx-2.5-22b-ic-lora-decompression-0.9.safetensors`, strength 1.0.
- **Prompt:** "Reference shows {scene}, heavily compressed… ENHANCE QUALITY {scene}…"
- **Limits:** Trained at 960x544, 121 frames. If artifacts remain at high resolution, lower the resolution.

### Colorization
- **Does:** Adds natural color to grayscale or desaturated video. Only the color changes.
- **File:** `ltx-2.5-22b-ic-lora-colorization-0.9.safetensors`.
- **Prompt:** "Reference shows {gray scene}. Edited shows the same scene with natural colors restored. COLORIZE {colors}…"
- **Strength:** 1.0. Use 0.8 to 0.9 if colors bleed.
- **Limits:**
  - Trained at 960x544, 121 frames at 24 fps.
  - Color washes out far above that size.

### Restore
- **Does:** Cleans and colorizes archive footage (film scans, tape, broadcast). It removes compression, color casts, flicker, dirt and scratches.
- **File:** `ltx-2.5-22b-ic-lora-restore-1.0.safetensors`. It was trained on 2.3 and validated on the 2.5 distilled model.
- **Prompt:** describe the period, place, light and clothing, because the color comes from the prompt. Put anything modern in the negative.
- **Strength:** 1.0. It acts like a switch: 0.7 stays monochrome and 1.4 over-tints.
- **Workflow:** `LTX-2.5_V2V_TiledFusion_Upscale.json` with this LoRA swapped in and tiles at 960x544.
- **Order of work:**
  1. Deinterlace first.
  2. Restore.
  3. Run Refine Details.
  4. Chain 97-frame windows with a 17-frame prefix so the color doesn't drift.

### Refine Details
- **Does:** Rebuilds texture, edges and grain on soft or upscaled video. Used tiled, it upscales to 4K.
- **File:** `ltx-2.5-22b-ic-lora-refine-details-1.0.safetensors`.
- **Prompt:** generic and about the look, not the subjects. Example: "sharp photographic detail, crisp natural texture, natural film grain…"
- **Workflow:** `LTX-2.5_V2V_TiledFusion_Upscale.json` at every size. Tiles are 1024x576.
- **Limits:**
  - 1080p to 4K is the sweet spot. For 8K, go in steps.
  - Text and logos can turn into glyph noise.
  - Pad the clip with 8 extra frames, because the last ones lose detail.

### Pixel Spatial Upscaler (x2)
- **Does:** Generative 2x upscale that adds detail to a low-resolution draft (about 280p).
- **File:** `ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors`. The reference must be at half the output size.
- **Limits:** Not a denoiser. Not meant for live action where fidelity matters.

---

## Look change

### Day-to-Night
- **Does:** Relights a daytime shot as night, frame for frame.
- **File:** `ltx-2.5-22b-ic-lora-day-to-night-0.9.safetensors`.
- **Prompt:** describe the night look. The card suggests a negative prompt ("daytime, bright sunlight, blue sky…").
- **Settings:** The card's settings are 30 steps and guidance 3 to 4 (lower guidance gives a brighter result).
- **Limits:**
  - Trained at 768x448, 97 frames at 24 fps.
  - Re-encode the input to 24 fps first.
  - Long clips drift.

### SDR-to-HDR
- **Does:** Converts 8-bit SDR video into 16-bit HDR: ACEScg EXR frames plus an HLG BT.2020 master.
- **Files:** `ltx-2.5-22b-ic-lora-sdr-to-hdr-1.0.safetensors` and `…-scene-emb.safetensors`, which holds precomputed text embeddings. No prompt is used.
- **Workflow:** `HDR_workflows/LTX-2.5_ICLoRA_SDR_to_HDR_Distilled.json`, or the tiled 4K/8K version.
- **Requirements:** Needs `colour-science` and `openimageio`.

---

## Generation control

### Layout to Render (beta)
- **Does:** Turns a 3D viewport or playblast (clay or blocking from Blender, Unreal and similar) into the finished shot. Camera and placement stay the same, and the look comes from a styled first frame.
- **File:** `ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors`.
- **Input:**
  - The layout clip.
  - A first frame made by running the clay frame through an image model. Never use the grey frame itself.
  - Optional mid and last keyframes.
- **Prompt:** one or two sentences describing the finished shot. Don't write "clay" or "3D".
- **Workflow:** `LTX-2.5_ICLoRA_Layout_To_Render_Two_Stage_Distilled.json`. Stage 1 is 960x544 at 8 steps, then 1920x1088 at 3 steps.

### Ingredients
- **Does:** Generates a new clip that keeps characters, props and the location from a reference sheet.
- **File:** `ltx-2.5-22b-ic-lora-ingredients-0.9.safetensors`.
- **Input:** a reference-sheet image on black with no text, looped into a static video of at least 121 frames.
- **Prompt:** two parts, "Reference sheet: <panels>" and "Generated video: <action>".
- **Limits:** One trained size, 768x448 at 121 frames. Give each character a front close-up and a turnaround.

---

## Motion

### Cinemagraph
- **Does:** Turns a still into a loop where one element moves and everything else stays frozen.
- **File:** `ltx-2.5-22b-lora-cinemagraph-0.9.safetensors`. This is a plain LoRA, not an IC-LoRA.
- **Prompt:** uses the trigger `CINEMAGRAPH_MOTION`. Say what moves and what stays frozen, plus "tripod locked-off static camera… seamless natural loop".
- **Strength:** 1.0 to 1.2.
- **Limits:**
  - Best at 512x704 with 25 frames.
  - No camera or body motion.

### Slow Motion Control
- **Does:** Image-to-video with a `speed` setting from 1.0 (real time) down to 0.025 (40x slow). Playback stays at 24 fps.
- **File:** `ltx-2.5-22b-lora-slow-motion-control-1.0.safetensors`.
- **Workflow:** `LTX-2.5_I2V_Speed_Control_flow.json`, which ships in the LoRA repo. A plain LoRA loader ignores `speed`.
- **Prompt:**
  - A normal I2V caption, with no trigger word.
  - Don't write "slow motion".
  - Use the same caption at every speed.
