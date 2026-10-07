# Usage

## What this is for

LTX-2.5 V2V IC-LoRA takes an existing clip as guide frames and returns a transformed version
with the same framing, timing and frame count. The LoRA decides what the transformation is
(see [MODES.md](MODES.md)). This repo focuses on **Alpha Gen**, which pulls a soft alpha
matte from normal footage so you can key people or objects out of footage shot without a
green screen and composite them in After Effects, Nuke or Resolve.

## Option A: in the ComfyUI UI

1. Open `workflows/LTX-2.5_AlphaGen_int8_UI.json`. Drag it onto the canvas, or use
   Workflow → Open.
2. **Load Video:** pick your clip. It must have an audio track, so add a silent one if
   needed (see below).
3. Leave **Prompt (positive)** empty for Alpha Gen.
4. **Load Image** must point to any existing image even when *use image input* is off,
   because the node still validates its file.
5. Press **Run**. The matte is saved by **Save Video** in `ComfyUI/output/`.

What drives size and length:
- **Resolution:** the source video is resized inside the *Source video* subgraph
  (`ResizeImageMaskNode`, "scale shorter dimension"). The default shorter side is **544**.
  Set it to 1088 for full HD if your GPU allows.
- **Length and fps:** taken from the clip. Trim it to **8n+1** frames (49, 97, 121, 145).
  Alpha Gen goes up to 145 frames.
- **Long side:** should be a multiple of 32. Crop or pad rather than stretch.

To use another IC-LoRA, open the **Load Models** subgraph, change `ic_lora` and write the
prompt its card asks for (see [MODES.md](MODES.md)).

## Option B: headless script

`scripts/run_alpha_gen.py` does the prep work and queues the API-format workflow
(`workflows/LTX-2.5_AlphaGen_int8_API.json`) against a running ComfyUI. It needs only
Python and ffmpeg.

```bat
python scripts\run_alpha_gen.py clip.mp4                       :: 97 frames, shorter side 544
python scripts\run_alpha_gen.py clip.mp4 --start 3 --frames 145
python scripts\run_alpha_gen.py clip.mp4 --short-side 768 --out tests\my_run
:: recommended quality settings (full HD needs short windows on 24 GB):
python scripts\run_alpha_gen.py clip.mp4 --short-side 1088 --frames 25 --start 3 --seed 1234 ^
       --decode-temporal 64,8 --levels 32,235 --bg 0x303848
python scripts\run_alpha_gen.py clip.mp4 --lora ltx-2.5-22b-ic-lora-deblur-0.9.safetensors ^
       --prompt "Reference shows a street, heavily out of focus. DEBLUR a sharp street scene"
```

It writes these files into `--out` (default: `<clip>_ltx` next to the clip):

| file | content |
|---|---|
| `input.mp4` | the prepared clip: trimmed, sized to multiples of 32, silent audio added if missing |
| `output.mp4` | the model output (for Alpha Gen, the grayscale matte) |
| `side_by_side.mp4` | original, matte, and the composite over green |
| `preview_frame.jpg` | one frame of the side-by-side |
| `run.json` | settings, seconds taken, prompt_id |

## Using the matte

The matte is a normal grayscale video, where white is the subject. In a compositor, plug it
in as the **luma matte** of the original clip. With ffmpeg:

```bat
ffmpeg -i input.mp4 -i output.mp4 -filter_complex "[1:v]format=gray[m];[0:v][m]alphamerge" -c:v prores_ks -profile:v 4444 -pix_fmt yuva444p10le subject_with_alpha.mov
```

## Recommended Alpha Gen settings (official guide + community, tested here)

| setting | value | source |
|---|---|---|
| resolution | **the source resolution**, up to 1920x1088 (1088 short side). Pad to multiples of 32 rather than stretching | official guide; Alex Villabon and Ok Todd workflows use 1088 |
| frames | **121 or fewer** for predictable results; 122–145 "may work"; above 145, RGB leaks into the matte | official guide. The Villabon workflow allows up to 241 ("works a lot of the time"), which we have not verified |
| prompt / strength | empty / 1.0 | official |
| sampler | distilled 8 steps, `euler_ancestral`, CFG 1, seed 1234 | official example and Villabon workflow |
| decode | `VAEDecodeTiled` 512 / 64 with temporal **64 / 8** (lower memory than 128 / 32) | Villabon workflow |
| matte post | clamp the black level: the matte background sits at about 23–29 at 768+, so apply levels 32/235 before compositing | measured here ([greenscreen_02](../tests/greenscreen_02_resolution)) |
| compositing | `out = source_rgb * alpha + bg * (1 - alpha)`; use the matte on the **original** clip, never the generated RGB | official guide |

What the resolution test showed: at a 544 short side, Alpha Gen made glass opaque and drew
droplets too fat. At 768 and 1088 the glass is semi-transparent and the edges are tight. Run
it at the source resolution.

**On a 24 GB GPU:** 1344x768 x 97 frames peaked at 23.0 GB, which is the limit. 1920x1088
works with short windows (25 frames, about 19 GB). For full HD, process the shot in short
chunks with a few frames of overlap and join the mattes. People on the
[Logik forum](https://forum.logik.tv/t/ltx-2-5-alpha-gen/15024) ran 3200x1900 x 49 frames
using about 90 GB, and UHD x 145 frames took 39 min, both on large GPUs.

Community verdict on the Logik forum: the results were "amazingly clean for what it is",
with occasional slight dilation. Mask-based tools such as SAMMIE or SAM are steadier on fast
human motion, while Alpha Gen does better on hair and semi-transparent material. Several
users combine the mattes from two tools.

## Tips and gotchas found while testing

- **Prompt must be empty** for Alpha Gen. Text does not control which object is matted, and
  you cannot pick the foreground.
- **No audio track means the run fails.** The workflow encodes the source audio and passes
  it through. The script adds a silent track automatically.
- **Exporting the UI workflow to API format:** the ComfyUI frontend left a `Reroute` inside
  the *Load Models* subgraph unresolved (frontend bundled with 0.34). ComfyUI then rejects
  the prompt with `KeyError: '5004:5603'` on `GemmaAPITextEncode.ckpt_name`. The API file in
  this repo already has the reroute replaced by the checkpoint name.
- **VRAM:** at 544x960 and 97 frames the peak was about 19 GB on a 24 GB card. The card says
  1920x1088 at 145 frames needs H100/B200-class memory. Scale up step by step (544, then 768,
  then 1088) and watch the peak. Don't try to find the limit by pushing the GPU to it.
- **Decode tiles:** the default `VAEDecodeTiled` setting `512 / 64 / 128 / 32` is the
  low-VRAM preset. Bigger tiles are faster but use more memory.
