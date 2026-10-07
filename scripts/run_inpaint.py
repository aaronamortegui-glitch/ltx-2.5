"""LTX-2.5 + In/Outpainting IC-LoRA (two stage), headless: regenerate only the masked area.

The prompt describes what should be in the masked region (a scene description, not an
edit command). The mask video is white where content is regenerated.

    python scripts/run_inpaint.py clip.mp4 mask.mp4 "a woman in a red sequin evening dress ..." --out out_dir
"""
import argparse
import json
import shutil
import time
import urllib.request
from pathlib import Path

from run_alpha_gen import VramPeak, get_json, upload

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / "workflows" / "LTX-2.5_Inpaint_int8_API.json"
N_VIDEO, N_MASK, N_PROMPT, N_NEG = "5368", "5375", "5404", "9008"
N_SHORT, N_RADIUS, N_ENHANCE = "5408:5399", "5408:5400", "5408:5610"
N_SEED1, N_SEED2, N_SAVE, N_IMAGE = "5410:4832", "5414:5210", "5228", "2004"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("mask")
    ap.add_argument("prompt")
    ap.add_argument("--negative", default="pc game, console game, video game, cartoon, childish, ugly")
    ap.add_argument("--short-side", type=int, default=768, help="stage-2 size (stage 1 runs at half)")
    ap.add_argument("--radius", type=int, default=15, help="mask dilation radius")
    ap.add_argument("--no-enhance", action="store_true")
    ap.add_argument("--seed", type=int, default=43)
    ap.add_argument("--url", default="http://127.0.0.1:8188")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    wf[N_VIDEO]["inputs"]["file"] = upload(args.url, args.video, f"inp_{out.name}_src.mp4")
    wf[N_MASK]["inputs"]["file"] = upload(args.url, args.mask, f"inp_{out.name}_mask.mp4")
    wf[N_IMAGE]["inputs"]["image"] = "ltx_placeholder.png"
    wf[N_PROMPT]["inputs"]["value"] = args.prompt
    wf[N_NEG]["inputs"]["value"] = args.negative
    wf[N_SHORT]["inputs"]["resize_type.shorter_size"] = args.short_side
    wf[N_RADIUS]["inputs"]["value"] = args.radius
    wf[N_ENHANCE]["inputs"]["switch"] = not args.no_enhance
    wf[N_SEED1]["inputs"]["noise_seed"] = args.seed
    wf[N_SEED2]["inputs"]["noise_seed"] = args.seed - 1
    wf[N_SAVE]["inputs"]["filename_prefix"] = f"ltx25/{out.name}"

    req = urllib.request.Request(f"{args.url}/prompt", data=json.dumps({"prompt": wf}).encode(),
                                 headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req).read())
    if resp.get("node_errors"):
        raise SystemExit(json.dumps(resp["node_errors"], indent=1)[:3000])
    pid = resp["prompt_id"]
    print(f"queued {pid}", flush=True)
    t0, vram = time.time(), VramPeak()
    vram.start()
    while True:
        hist = get_json(f"{args.url}/history/{pid}").get(pid)
        if hist and hist["status"].get("status_str") in ("success", "error"):
            break
        time.sleep(5)
    elapsed = time.time() - t0
    vram.stop.set()
    if hist["status"]["status_str"] != "success":
        raise SystemExit(json.dumps(hist["status"]["messages"], indent=1)[-3000:])
    item = hist["outputs"][N_SAVE]["images"][0]
    q = f"filename={item['filename']}&subfolder={item['subfolder']}&type={item['type']}"
    with urllib.request.urlopen(f"{args.url}/view?{q}") as r, open(out / "output.mp4", "wb") as f:
        shutil.copyfileobj(r, f)
    (out / "run.json").write_text(json.dumps({
        "video": Path(args.video).name, "mask": Path(args.mask).name, "prompt": args.prompt,
        "negative": args.negative, "short_side": args.short_side, "radius": args.radius,
        "enhance": not args.no_enhance, "seed": args.seed, "seconds": round(elapsed, 1),
        "vram_peak_gb": round(vram.peak / 1024, 1), "prompt_id": pid}, indent=2), encoding="utf-8")
    print(f"done in {elapsed:.0f} s, VRAM peak {vram.peak / 1024:.1f} GB -> {out}")


if __name__ == "__main__":
    main()
