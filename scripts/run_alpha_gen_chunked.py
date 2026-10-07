"""Alpha Gen over a whole shot in short overlapping windows, then an RGBA PNG sequence.

Full HD does not fit a 24 GB GPU in one pass, so the shot is processed in windows of
--window frames (25 = ~19 GB peak at 1920x1088, measured) overlapping by --overlap frames.
Mattes are cross-faded across each overlap, then black/white levels are fixed and the
matte is merged with the (optionally despilled) source into straight-alpha PNGs.

    python scripts/run_alpha_gen_chunked.py clip.mp4 --despill green
    python scripts/run_alpha_gen_chunked.py clip.mp4 --window 25 --overlap 4 --out D:/shots/clip_alpha

Needs: ComfyUI running, ffmpeg/ffprobe, numpy + Pillow (system Python).
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def probe(path):
    out = json.loads(run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames",
                          "-of", "json", str(path)]))["streams"][0]
    num, den = out["r_frame_rate"].split("/")
    return int(out["width"]), int(out["height"]), float(num) / float(den), int(out["nb_read_frames"])


def gpu_temp():
    try:
        return int(run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"]))
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080, help="output height; padded to a multiple of 32 for the model")
    ap.add_argument("--window", type=int, default=25, help="frames per pass, 8n+1 (25 = ~19 GB at 1920x1088)")
    ap.add_argument("--overlap", type=int, default=4)
    ap.add_argument("--levels", default="32,235", help="matte black,white points")
    ap.add_argument("--despill", choices=["none", "green", "blue"], default="none")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--vae", default="ltx-2.5-video-vae-bf16.safetensors")
    ap.add_argument("--cool-down", type=int, default=15, help="seconds to wait between windows")
    ap.add_argument("--max-temp", type=int, default=80, help="wait until the GPU is below this (C)")
    ap.add_argument("--out", help="output folder (default: <clip>_alpha next to the clip)")
    args = ap.parse_args()

    src = Path(args.video).resolve()
    out = Path(args.out) if args.out else src.parent / f"{src.stem}_alpha"
    work = out / "_work"
    work.mkdir(parents=True, exist_ok=True)
    W, H = args.width, args.height
    Hp = (H + 31) // 32 * 32
    pad = Hp - H
    top = pad // 2

    # 1. full prepared clip: scale to W x H, mirror-pad to W x Hp (pad, don't stretch)
    full = work / "full_padded.mp4"
    if not full.exists():
        vf = f"scale={W}:{H}:flags=lanczos"
        if pad:
            vf += f",pad={W}:{Hp}:0:{top},fillborders=top={top}:bottom={pad - top}:mode=mirror"
        run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", vf, "-an",
             "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(full)])
    _, _, fps, total = probe(full)
    print(f"{total} frames @ {fps:.2f} fps, model size {W}x{Hp}", flush=True)

    # 2. windows
    step = args.window - args.overlap
    starts = list(range(0, max(total - args.window, 0) + 1, step))
    if starts[-1] + args.window < total:
        starts.append(total - args.window)
    print(f"{len(starts)} windows: {starts}", flush=True)

    mattes = {}
    for i, s in enumerate(starts):
        wdir = work / f"win_{i:02d}_{s:04d}"
        if not (wdir / "output.mp4").exists():
            clip = work / f"win_{i:02d}.mp4"
            run(["ffmpeg", "-v", "error", "-y", "-i", str(full), "-vf",
                 f"select='between(n\\,{s}\\,{s + args.window - 1})',setpts=N/FRAME_RATE/TB",
                 "-r", str(fps), "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(clip)])
            while gpu_temp() > args.max_temp:
                time.sleep(10)
            print(f"window {i + 1}/{len(starts)} frames {s}-{s + args.window - 1}", flush=True)
            subprocess.run([sys.executable, str(HERE / "run_alpha_gen.py"), str(clip),
                            "--short-side", str(min(W, Hp)), "--frames", str(args.window),
                            "--seed", str(args.seed), "--decode-temporal", "64,8", "--vae", args.vae,
                            "--levels", args.levels, "--bg", "0x303848", "--out", str(wdir)], check=True)
            if i < len(starts) - 1:
                time.sleep(args.cool_down)
        data = subprocess.run(["ffmpeg", "-v", "error", "-i", str(wdir / "output.mp4"), "-vf", "format=gray",
                               "-f", "rawvideo", "-pix_fmt", "gray", "-"], check=True, capture_output=True).stdout
        mw, mh = probe(wdir / "output.mp4")[:2]
        mattes[s] = np.frombuffer(data, np.uint8).reshape(-1, mh, mw)[: args.window]

    # 3. cross-fade overlaps into one matte track
    mh, mw = next(iter(mattes.values())).shape[1:]
    acc = np.zeros((total, mh, mw), np.float32)
    wsum = np.zeros((total, 1, 1), np.float32)
    for s, m in mattes.items():
        n = m.shape[0]
        w = np.ones(n, np.float32)
        ov_in = args.overlap if s > 0 else 0
        ov_out = args.overlap if s + n < total else 0
        if ov_in:
            w[:ov_in] = np.linspace(0, 1, ov_in + 2)[1:-1]
        if ov_out:
            w[-ov_out:] = np.minimum(w[-ov_out:], np.linspace(1, 0, ov_out + 2)[1:-1])
        acc[s:s + n] += m.astype(np.float32) * w[:, None, None]
        wsum[s:s + n] += w[:, None, None]
    matte = acc / np.maximum(wsum, 1e-6)
    lo, hi = (int(x) for x in args.levels.split(","))
    matte = np.clip((matte - lo) * 255.0 / (hi - lo), 0, 255).astype(np.uint8)
    if mw != W or mh != Hp:
        raise SystemExit(f"matte size {mw}x{mh} != {W}x{Hp}")
    matte = matte[:, top:top + H]

    # 4. RGB frames (source scaled, optional despill) + matte -> straight-alpha PNGs
    png_dir = out / "png"
    png_dir.mkdir(exist_ok=True)
    vf = f"scale={W}:{H}:flags=lanczos" + (f",despill=type={args.despill}" if args.despill != "none" else "")
    rgb = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-vf", vf, "-frames:v", str(total),
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True, capture_output=True).stdout
    rgb = np.frombuffer(rgb, np.uint8).reshape(-1, H, W, 3)
    n = min(len(rgb), total)
    for f in range(n):
        Image.fromarray(np.dstack([rgb[f], matte[f]]), "RGBA").save(png_dir / f"{src.stem}_{f:04d}.png", compress_level=4)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}",
                    "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p",
                    str(out / "matte.mp4")], input=matte[:n].tobytes(), check=True)
    # 5. review video: source | matte | RGBA over grey
    vf_src = f"scale={W}:{H}:flags=lanczos" + (f",despill=type={args.despill}" if args.despill != "none" else "")
    fc = (f"[0:v]{vf_src},split[o1][o2];[1:v]format=gray,split[m1][m2];[o2][m2]alphamerge[fg];"
          f"color=c=0x303848:s={W}x{H}:r={fps}[bg];[bg][fg]overlay=shortest=1[comp];"
          f"[m1]format=yuv420p[mv];[o1][mv][comp]hstack=inputs=3,format=yuv420p[out]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-i", str(out / "matte.mp4"),
                    "-filter_complex", fc, "-map", "[out]", "-frames:v", str(n), "-c:v", "libx264", "-crf", "18",
                    str(out / "side_by_side.mp4")], check=True)
    peaks = []
    for i, s0 in enumerate(starts):
        rj = work / f"win_{i:02d}_{s0:04d}" / "run.json"
        if rj.exists():
            r = json.loads(rj.read_text(encoding="utf-8"))
            peaks.append({"start": s0, "seconds": r.get("seconds"), "vram_peak_gb": r.get("vram_peak_gb")})
    (out / "run.json").write_text(json.dumps({
        "source": src.name, "frames": n, "fps": fps, "size": [W, H], "model_size": [W, Hp],
        "window": args.window, "overlap": args.overlap, "windows": starts, "levels": args.levels,
        "despill": args.despill, "seed": args.seed, "vae": args.vae, "per_window": peaks}, indent=2), encoding="utf-8")
    print(f"done: {n} PNGs -> {png_dir}")


if __name__ == "__main__":
    main()
