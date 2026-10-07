"""LTX-2.5 text-to-video / image-to-video (single stage, distilled, int8), headless.

Queues workflows/LTX-2.5_T2V_I2V_int8_API.json on a running ComfyUI, waits, and saves
output.mp4 (video + generated audio), the effective (enhanced) prompt and run.json.

    python scripts/run_t2v.py "a slow dolly shot of ..." --out tests/gen_01
    python scripts/run_t2v.py "the shaker pours ..." --image start.png --out tests/gen_02
    python scripts/run_t2v.py "..." --seconds 4 --width 544 --height 960 --no-enhance
"""
import argparse
import json
import shutil
import time
import urllib.request
from pathlib import Path

from run_alpha_gen import VramPeak, get_json, upload

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / "workflows" / "LTX-2.5_T2V_I2V_int8_API.json"

N_PROMPT, N_NEG, N_IMAGE, N_USE_IMAGE = "5508", "5509", "2004", "5014:5506"
N_FPS, N_SECONDS, N_ENHANCE, N_LATENT = "5511", "5512", "5014:5556", "5514:3059"
N_I2V, N_SEED, N_SAVE, N_PREVIEW = "5514:3159", "5516:4832", "4852", "5544"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--url", default="http://127.0.0.1:8188")
    ap.add_argument("--image", help="start frame (image-to-video)")
    ap.add_argument("--i2v-strength", type=float, default=0.7)
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--fps", type=float, default=24.0)
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=544)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--negative", default="")
    ap.add_argument("--no-enhance", action="store_true", help="skip the Gemma E2B prompt enhancer")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.width % 32 or args.height % 32:
        raise SystemExit("width and height must be multiples of 32")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    wf[N_PROMPT]["inputs"]["value"] = args.prompt
    wf[N_NEG]["inputs"]["value"] = args.negative
    wf[N_FPS]["inputs"]["value"] = args.fps
    wf[N_SECONDS]["inputs"]["value"] = args.seconds
    wf[N_ENHANCE]["inputs"]["switch"] = not args.no_enhance
    wf[N_LATENT]["inputs"]["width"] = args.width
    wf[N_LATENT]["inputs"]["height"] = args.height
    wf[N_I2V]["inputs"]["strength"] = args.i2v_strength
    wf[N_SEED]["inputs"]["noise_seed"] = args.seed
    wf[N_SAVE]["inputs"]["filename_prefix"] = f"ltx25/{out.name}"
    wf[N_USE_IMAGE]["inputs"]["value"] = bool(args.image)
    if args.image:
        wf[N_IMAGE]["inputs"]["image"] = upload(args.url, args.image, Path(args.image).name)
        shutil.copy(args.image, out / ("start" + Path(args.image).suffix))
    else:  # LoadImage still validates its file
        wf[N_IMAGE]["inputs"]["image"] = "ltx_placeholder.png"

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
    effective = hist["outputs"].get(N_PREVIEW, {}).get("text", [""])
    effective = effective[0] if isinstance(effective, list) and effective else str(effective)
    meta = {"prompt": args.prompt, "effective_prompt": effective, "image": Path(args.image).name if args.image else None,
            "i2v_strength": args.i2v_strength, "seconds": args.seconds, "fps": args.fps,
            "size": [args.width, args.height], "seed": args.seed, "enhance": not args.no_enhance,
            "gen_seconds": round(elapsed, 1), "vram_peak_gb": round(vram.peak / 1024, 1), "prompt_id": pid}
    (out / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"done in {elapsed:.0f} s, VRAM peak {vram.peak / 1024:.1f} GB -> {out}")


if __name__ == "__main__":
    main()
