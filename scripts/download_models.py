"""Download the LTX-2.5 weights used in this repo into a ComfyUI models folder.

The Lightricks repos are gated: accept the license on each Hugging Face page and
log in once (see docs/INSTALL.md). The token is read from ~/.cache/huggingface.

Usage (run with the ComfyUI embedded Python, which already has huggingface_hub):
    python_embeded\\python.exe scripts\\download_models.py --comfy D:\\path\\to\\ComfyUI
    python_embeded\\python.exe scripts\\download_models.py --comfy ... --extra clean-plate day-to-night
"""
import argparse
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download

BASE = "Lightricks/LTX-2.5"

# (repo, file in repo, models subfolder)  -- int8 variants fit a 24 GB GPU
CORE = [
    (BASE, "diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors", "diffusion_models"),  # 21.5 GB
    (BASE, "text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors", "text_encoders"),  # 15.4 GB
    (BASE, "vae/ltx-2.5-video-vae-bf16.safetensors", "vae"),  # 1.47 GB, best quality decoder
    (BASE, "vae/ltx-2.5-video-vae-conv-bf16.safetensors", "vae"),  # 1.45 GB, lower memory / faster
    (BASE, "vae/ltx-2.5-audio-vae-bf16.safetensors", "vae"),  # 0.36 GB
    ("Comfy-Org/gemma-4", "text_encoders/gemma4_e2b_it_int8_convrot.safetensors", "text_encoders"),  # 5.2 GB, prompt enhancer (not gated)
    ("Lightricks/LTX-2.5-22b-IC-LoRA-Alpha-Gen", "ltx-2.5-22b-ic-lora-alpha-gen-0.9.safetensors", "loras"),  # 1.31 GB
    ("Lightricks/LTX-2.5-22b-IC-LoRA-Deblur", "ltx-2.5-22b-ic-lora-deblur-0.9.safetensors", "loras"),  # 0.91 GB
]

# Optional adapters, selectable with --extra <key>
EXTRA = {
    "clean-plate": ("Lightricks/LTX-2.5-22b-IC-LoRA-Clean-Plate", "ltx-2.5-22b-ic-lora-clean-plate-1.0.safetensors"),
    "colorization": ("Lightricks/LTX-2.5-22b-IC-LoRA-Colorization", "ltx-2.5-22b-ic-lora-colorization-0.9.safetensors"),
    "day-to-night": ("Lightricks/LTX-2.5-22b-IC-LoRA-Day-To-Night", "ltx-2.5-22b-ic-lora-day-to-night-0.9.safetensors"),
    "decompression": ("Lightricks/LTX-2.5-22b-IC-LoRA-Decompression", "ltx-2.5-22b-ic-lora-decompression-0.9.safetensors"),
    "ingredients": ("Lightricks/LTX-2.5-22b-IC-LoRA-Ingredients", "ltx-2.5-22b-ic-lora-ingredients-0.9.safetensors"),
    "layout-to-render": ("Lightricks/LTX-2.5-22b-IC-LoRA-Layout-To-Render", "ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors"),
    "pixel-upscaler": ("Lightricks/LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler", "ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors"),
    "refine-details": ("Lightricks/LTX-2.5-22b-IC-LoRA-Refine-Details", "ltx-2.5-22b-ic-lora-refine-details-1.0.safetensors"),
    "restore": ("Lightricks/LTX-2.5-22b-IC-LoRA-Restore", "ltx-2.5-22b-ic-lora-restore-1.0.safetensors"),
    "water": ("Lightricks/LTX-2.5-22b-IC-LoRA-Water-Simulation", "ltx-2.5-22b-ic-lora-water-simulation-0.9.safetensors"),
    "cinemagraph": ("Lightricks/LTX-2.5-22b-LoRA-Cinemagraph", "ltx-2.5-22b-lora-cinemagraph-0.9.safetensors"),
    "slow-motion": ("Lightricks/LTX-2.5-22b-LoRA-Slow-Motion-Control", "ltx-2.5-22b-lora-slow-motion-control-1.0.safetensors"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comfy", required=True, help="path to the ComfyUI folder (the one containing models/)")
    ap.add_argument("--extra", nargs="*", default=[], choices=sorted(EXTRA), help="optional LoRAs to add")
    ap.add_argument("--skip-core", action="store_true", help="only download --extra adapters")
    args = ap.parse_args()

    models = Path(args.comfy) / "models"
    tmp = Path(args.comfy).parent / "_hf_tmp"
    todo = [] if args.skip_core else list(CORE)
    todo += [(repo, f, "loras") for repo, f in (EXTRA[k] for k in args.extra)]

    for repo, fname, dest in todo:
        target = models / dest / Path(fname).name
        if target.exists():
            print("exists:", target.name, flush=True)
            continue
        print("downloading:", target.name, flush=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        path = hf_hub_download(repo, fname, local_dir=tmp)
        shutil.move(path, target)
    shutil.rmtree(tmp, ignore_errors=True)
    print("done")


if __name__ == "__main__":
    main()
