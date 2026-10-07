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
