# Install

How to get LTX-2.5 and the IC-LoRAs running in ComfyUI on Windows. It was tested on an
RTX 5090 Laptop (24 GB VRAM, 64 GB RAM), with ComfyUI portable 0.34.0 and torch with cu130.

## 1. Requirements

| | minimum used here |
|---|---|
| GPU | 24 GB VRAM. Use the int8 weights, because the bf16 transformer alone is 42 GB |
| RAM | 64 GB. The models are offloaded between stages |
| Disk | ~50 GB for the core set, plus 0.3–1.7 GB per extra LoRA |
| ComfyUI | 0.32.0 or newer (LTX-2.5 core support landed before v0.32.0) |
| Custom nodes | [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo), October 2026 or newer |
| Tools | `ffmpeg` and `ffprobe` on PATH (only for `scripts/run_alpha_gen.py`) |

## 2. ComfyUI and the LTXVideo nodes

Install ComfyUI first, or update an existing install. Then add or update the Lightricks
node pack:

```bat
cd ComfyUI\custom_nodes
git clone https://github.com/Lightricks/ComfyUI-LTXVideo
REM existing clone:  cd ComfyUI-LTXVideo && git pull
..\..\python_embeded\python.exe -m pip install -r ComfyUI-LTXVideo\requirements.txt
```

The October 2026 requirements add `colour-science` and `openimageio`. They are only used
by the HDR nodes, but the pack lists them.

Restart ComfyUI. Check that these nodes exist: `LTXICLoRALoaderModelOnly`,
`LTXAddVideoICLoRAGuide`, `LTXVSetAudioRefTokens`, `GemmaAPITextEncode`, `LTXVCropGuides`.

> **Upgrading from an older pack (June 2026 or earlier):** an older `pyramid_blending.py`
> imports `pad` from kornia, and kornia 0.8.3 removed that export. Upstream fixed it, so
> `git pull` is enough. If you patched the file locally, discard your patch first with
> `git checkout -- pyramid_blending.py`.

## 3. Hugging Face access (the weights are gated)

1. Log in at huggingface.co and click **Agree and access** on each repo you need:
   - [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5) (base weights)
   - [Lightricks/LTX-2.5-22b-IC-LoRA-Alpha-Gen](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Alpha-Gen)
   - [Lightricks/LTX-2.5-22b-IC-LoRA-Deblur](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Deblur)
   - any other LoRA from [docs/MODES.md](MODES.md)
2. Create a **Read** token at https://huggingface.co/settings/tokens.
3. Save it once on the machine. The token goes to `~/.cache/huggingface/token`, which every
   Python install shares:

```bat
python -c "from huggingface_hub import login; login(token='hf_xxx')"
```

> The `hf.exe` CLI in the ComfyUI portable `python_embeded` fails with
> `ModuleNotFoundError: No module named 'venv'`, because the embedded Python has no `venv`.
> Log in with any regular Python that has `huggingface_hub`, as above.

## 4. Download the weights

```bat
cd ltx-2.5
<ComfyUI>\..\python_embeded\python.exe scripts\download_models.py --comfy <path\to\ComfyUI>
REM optional adapters:
... scripts\download_models.py --comfy <...> --skip-core --extra clean-plate day-to-night restore
```

The core set goes into `ComfyUI/models`:

| file | folder | size |
|---|---|---|
| ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors | diffusion_models | 21.5 GB |
| gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors | text_encoders | 15.4 GB |
| gemma4_e2b_it_int8_convrot.safetensors (prompt enhancer, from Comfy-Org, not gated) | text_encoders | 5.2 GB |
| ltx-2.5-video-vae-bf16.safetensors (best quality) | vae | 1.47 GB |
| ltx-2.5-video-vae-conv-bf16.safetensors (lower memory) | vae | 1.45 GB |
| ltx-2.5-audio-vae-bf16.safetensors | vae | 0.36 GB |
| ltx-2.5-22b-ic-lora-alpha-gen-0.9.safetensors | loras | 1.31 GB |
| ltx-2.5-22b-ic-lora-deblur-0.9.safetensors | loras | 0.91 GB |

The official workflow names the bf16 files. The workflows in `workflows/` with `int8` in
their name already point to the int8 files. With more than 48 GB of VRAM you can use bf16,
or try `distilled-transformer-nvfp4` (18.7 GB) on Blackwell GPUs.

## 5. Check it works

Drag `workflows/LTX-2.5_AlphaGen_int8_UI.json` onto the ComfyUI canvas, load a short clip
in **Load Video** and press **Run**. You can also run it headless:

```bat
python scripts\run_alpha_gen.py path\to\clip.mp4
```

A 544x960, 97-frame clip took about 2 minutes, with a peak of about 19 GB VRAM
(ComfyUI started with `--reserve-vram 7 --cache-none`).
