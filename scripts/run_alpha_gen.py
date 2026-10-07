"""Run the LTX-2.5 V2V IC-LoRA workflow (Alpha Gen by default) on a clip, headless.

Steps: prepare the clip with ffmpeg (trim to 8n+1 frames, size to multiples of 32,
add a silent audio track if missing) -> upload to ComfyUI -> queue the API-format
workflow -> wait -> download the result -> build a side-by-side
(original | matte | composite over green) and a preview frame.

Only the Python standard library + ffmpeg/ffprobe on PATH are needed.

    python scripts/run_alpha_gen.py path/to/clip.mp4
    python scripts/run_alpha_gen.py clip.mp4 --frames 145 --short-side 768 --out tests/my_run
    # other IC-LoRAs from the same family (prompt usually required, see docs/MODES.md):
    python scripts/run_alpha_gen.py clip.mp4 --lora ltx-2.5-22b-ic-lora-deblur-0.9.safetensors --prompt "..."
"""
import argparse
import json
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / "workflows" / "LTX-2.5_AlphaGen_int8_API.json"

# node ids inside the API workflow
N_VIDEO, N_IMAGE, N_PROMPT, N_NEG = "5001", "2004", "5508", "5509"
N_LORA, N_RESIZE, N_SEED, N_SAVE = "5004:5606", "5548:5026", "5516:4832", "4852"
N_VAE, N_DECODE = "5004:5601", "5518:5538"


class VramPeak(threading.Thread):
    """Poll nvidia-smi once a second and keep the highest memory.used (MiB)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.peak, self.stop = 0, threading.Event()

    def run(self):
        while not self.stop.is_set():
            try:
                used = run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"])
                self.peak = max(self.peak, int(used.splitlines()[0]))
            except (OSError, subprocess.CalledProcessError, ValueError):
                return
            self.stop.wait(1)


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def probe(path):
    out = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)]))
    v = next(s for s in out["streams"] if s["codec_type"] == "video")
    num, den = v["r_frame_rate"].split("/")
    has_audio = any(s["codec_type"] == "audio" for s in out["streams"])
    return int(v["width"]), int(v["height"]), float(num) / float(den), has_audio


def prepare(src, dst, frames, short_side, start):
    """Scale so the shorter side == short_side, center-crop the long side to a multiple of 32."""
    w, h, fps, has_audio = probe(src)
    if w <= h:
        sw, sh = short_side, round(h * short_side / w)
        cw, ch = sw, sh // 32 * 32
    else:
        sw, sh = round(w * short_side / h), short_side
        cw, ch = sw // 32 * 32, sh
    vf = f"scale={sw}:{sh}:flags=lanczos,crop={cw}:{ch}"
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-i", str(src)]
    if not has_audio:  # the workflow encodes the source audio, so it must exist
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += ["-map", "0:v:0", "-map", "1:a:0" if not has_audio else "0:a:0",
            "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-crf", "14",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(dst)]
    run(cmd)
    return cw, ch, fps


def upload(url, path, name):
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + Path(path).read_bytes() + \
           (f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n"
            f"--{boundary}--\r\n").encode()
    req = urllib.request.Request(f"{url}/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(urllib.request.urlopen(req).read())["name"]


def get_json(url):
    return json.loads(urllib.request.urlopen(url).read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--url", default="http://127.0.0.1:8188")
    ap.add_argument("--frames", type=int, default=97, help="snapped to 8n+1; Alpha Gen max 145")
    ap.add_argument("--short-side", type=int, default=544, help="multiple of 32; 544 = safe on 24 GB, 1088 = full HD")
    ap.add_argument("--start", type=float, default=0.0, help="start time in seconds")
    ap.add_argument("--lora", default="ltx-2.5-22b-ic-lora-alpha-gen-0.9.safetensors")
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--prompt", default="", help="Alpha Gen: keep empty")
    ap.add_argument("--negative", default="", help="negative prompt (Clean Plate, Day-to-Night)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--vae", default="ltx-2.5-video-vae-bf16.safetensors",
                    help="video VAE; ltx-2.5-video-vae-conv-bf16.safetensors = lower memory, faster")
    ap.add_argument("--decode-temporal", default="128,32",
                    help="VAEDecodeTiled temporal_size,temporal_overlap; 64,8 lowers decode memory")
    ap.add_argument("--levels", default="0,255",
                    help="black,white points applied to the matte in the side-by-side composite; "
                         "768+ outputs have a lifted black (~23-29), 32,235 fixes it")
    ap.add_argument("--bg", default="0x20c040", help="composite background colour (use a non-green one for green-screen sources)")
    ap.add_argument("--out", help="output folder (default: <video name>_ltx next to the video)")
    args = ap.parse_args()

    src = Path(args.video).resolve()
    frames = (args.frames - 1) // 8 * 8 + 1
    if args.short_side % 32:
        raise SystemExit("--short-side must be a multiple of 32")
    out = Path(args.out) if args.out else src.parent / f"{src.stem}_ltx"
    out.mkdir(parents=True, exist_ok=True)

    tag = f"{src.stem}_{uuid.uuid4().hex[:6]}"
    prepared = out / "input.mp4"
    w, h, fps = prepare(src, prepared, frames, args.short_side, args.start)
    with tempfile.TemporaryDirectory() as td:  # LoadImage needs a file even when "use image input" is off
        ph = Path(td) / "placeholder.png"
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64", "-frames:v", "1", str(ph)])
        ph_name = upload(args.url, ph, "ltx_placeholder.png")
    vid_name = upload(args.url, prepared, f"{tag}.mp4")

    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    wf[N_VIDEO]["inputs"]["file"] = vid_name
    wf[N_IMAGE]["inputs"]["image"] = ph_name
    wf[N_PROMPT]["inputs"]["value"] = args.prompt
    wf[N_NEG]["inputs"]["value"] = args.negative
    wf[N_LORA]["inputs"]["lora_name"] = args.lora
    wf[N_LORA]["inputs"]["strength_model"] = args.strength
    wf[N_RESIZE]["inputs"]["resize_type.shorter_size"] = args.short_side
    wf[N_SEED]["inputs"]["noise_seed"] = args.seed
    wf[N_VAE]["inputs"]["vae_name"] = args.vae
    t_size, t_overlap = (int(x) for x in args.decode_temporal.split(","))
    wf[N_DECODE]["inputs"]["temporal_size"] = t_size
    wf[N_DECODE]["inputs"]["temporal_overlap"] = t_overlap
    wf[N_SAVE]["inputs"]["filename_prefix"] = f"ltx25/{tag}"

    req = urllib.request.Request(f"{args.url}/prompt", data=json.dumps({"prompt": wf}).encode(),
                                 headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req).read())
    if resp.get("node_errors"):
        raise SystemExit(json.dumps(resp["node_errors"], indent=1)[:3000])
    pid = resp["prompt_id"]
    print(f"queued {pid}  {w}x{h}  {frames} frames  @ {fps:.2f} fps", flush=True)

    t0 = time.time()
    vram = VramPeak()
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
    matte = out / "output.mp4"
    with urllib.request.urlopen(f"{args.url}/view?{q}") as r, open(matte, "wb") as f:
        shutil.copyfileobj(r, f)

    side = out / "side_by_side.mp4"
    lo, hi = (int(x) for x in args.levels.split(","))
    lv = rf"lutyuv=y='clip((val-{lo})*255/({hi}-{lo})\,0\,255)'"
    fc = (f"[0:v]split[o1][o2];[1:v]format=gray,{lv},split[m1][m2];[o2][m2]alphamerge[fg];"
          f"color=c={args.bg}:s={w}x{h}:r={fps}[bg];[bg][fg]overlay=shortest=1[comp];"
          f"[m1]format=yuv420p[mv];[o1][mv][comp]hstack=inputs=3,format=yuv420p[out]")
    run(["ffmpeg", "-v", "error", "-y", "-i", str(prepared), "-i", str(matte), "-filter_complex", fc,
         "-map", "[out]", "-c:v", "libx264", "-crf", "18", str(side)])
    run(["ffmpeg", "-v", "error", "-y", "-ss", str(min(2.0, frames / fps / 2)), "-i", str(side),
         "-frames:v", "1", "-vf", "scale=-2:640", str(out / "preview_frame.jpg")])

    meta = {"source": src.name, "width": w, "height": h, "frames": frames, "fps": fps, "lora": args.lora,
            "strength": args.strength, "prompt": args.prompt, "negative": args.negative, "seed": args.seed, "vae": args.vae, "decode_temporal": args.decode_temporal, "levels": args.levels,
            "seconds": round(elapsed, 1), "vram_peak_gb": round(vram.peak / 1024, 1), "prompt_id": pid}
    (out / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"done in {elapsed:.0f} s, VRAM peak {vram.peak / 1024:.1f} GB -> {out}")


if __name__ == "__main__":
    main()
