"""Location swap with a shadow pass and automatic colour match.

Classic comp trick, made possible by the Clean Plate IC-LoRA: the ratio between the original
shot and its clean plate (same shot, subjects removed) isolates the shadows the subjects cast.
That shadow pass is multiplied onto the new background, and the foreground is colour-matched
to the new plate (mean/std transfer in Lab, blended).

    python scripts/composite_shadow.py orig.mp4 clean_plate.mp4 matte.mp4 new_plate.mp4 --out dir
    (--extra-matte car_mask.mp4 to keep more objects; --crop "725:544:10:0" to map a matte made at
    another size: scale to WxH then crop x:y)
"""
import argparse
import subprocess
from pathlib import Path

import cv2
import numpy as np


def read(path, w, h, n, gray=False, scale=None, crop=None):
    vf = []
    if scale:
        vf.append(f"scale={scale}:flags=lanczos")
    if crop:
        vf.append(f"crop={crop}")
    vf.append(f"scale={w}:{h}")
    fmt = "gray" if gray else "rgb24"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", ",".join(vf), "-frames:v", str(n),
                          "-f", "rawvideo", "-pix_fmt", fmt, "-"], check=True, capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8)
    return a.reshape(-1, h, w) if gray else a.reshape(-1, h, w, 3)


def write(frames, path, fps):
    h, w = frames.shape[1:3]
    gray = frames.ndim == 3
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray" if gray else "rgb24",
                    "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "16",
                    "-pix_fmt", "yuv420p", str(path)], input=frames.tobytes(), check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("orig")
    ap.add_argument("clean_plate")
    ap.add_argument("matte")
    ap.add_argument("new_plate")
    ap.add_argument("--extra-matte", action="append", default=[])
    ap.add_argument("--matte-scale", help="scale a differently sized matte first, e.g. 725:544")
    ap.add_argument("--matte-crop", help="then crop it, e.g. 704:544:10:0")
    ap.add_argument("--frames", type=int, required=True)
    ap.add_argument("--fps", type=float, default=24)
    ap.add_argument("--shadow-strength", type=float, default=0.65)
    ap.add_argument("--floor-from", type=float, default=0.33, help="only look for shadows below this fraction of the height")
    ap.add_argument("--near", type=int, default=0, help="only keep shadows within N px of the subject (0 = anywhere)")
    ap.add_argument("--color-match", type=float, default=0.5, help="0 = off, 1 = full transfer")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    n = args.frames
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", args.orig], capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(probe[0]), int(probe[1])

    O = read(args.orig, w, h, n).astype(np.float32) / 255
    P = read(args.clean_plate, w, h, n).astype(np.float32) / 255
    B = read(args.new_plate, w, h, n).astype(np.float32) / 255
    M = read(args.matte, w, h, n, gray=True, scale=args.matte_scale, crop=args.matte_crop).astype(np.float32) / 255
    for extra in args.extra_matte:
        M = np.maximum(M, read(extra, w, h, n, gray=True, scale=args.matte_scale, crop=args.matte_crop)
                       .astype(np.float32) / 255)
    n = min(len(O), len(P), len(B), len(M))
    O, P, B, M = O[:n], P[:n], B[:n], M[:n]

    def luma(x):
        return 0.299 * x[..., 0] + 0.587 * x[..., 1] + 0.114 * x[..., 2]

    shadow = np.zeros((n, h, w), np.float32)
    comp_plain = np.zeros_like(O)
    comp = np.zeros_like(O)
    for i in range(n):
        m = M[i]
        hard = cv2.dilate((m > 0.05).astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
        ratio = (luma(O[i]) + 0.02) / (luma(P[i]) + 0.02)
        med = np.median(ratio[~hard]) if (~hard).any() else 1.0  # global exposure drift of the plate
        s = np.clip((1 - ratio / med - 0.06) * 2.5, 0, 1)
        s[hard] = 0
        s[: int(h * args.floor_from)] = 0  # cast shadows land on the ground, not in the sky / walls
        if args.near:
            k = 2 * args.near + 1
            s[~cv2.dilate((m > 0.3).astype(np.uint8), np.ones((k, k), np.uint8)).astype(bool)] = 0
        s = cv2.GaussianBlur(s, (0, 0), 3)
        shadow[i] = s

        # colour match the foreground to the new plate (Lab mean/std, blended)
        fg = O[i]
        if args.color_match > 0:
            lab_fg = cv2.cvtColor(fg, cv2.COLOR_RGB2LAB)
            lab_src = cv2.cvtColor(P[i], cv2.COLOR_RGB2LAB)  # the original environment
            lab_dst = cv2.cvtColor(B[i], cv2.COLOR_RGB2LAB)
            ms, ss = lab_src.reshape(-1, 3).mean(0), lab_src.reshape(-1, 3).std(0) + 1e-3
            md, sd = lab_dst.reshape(-1, 3).mean(0), lab_dst.reshape(-1, 3).std(0) + 1e-3
            moved = (lab_fg - ms) / ss * sd + md
            moved = cv2.cvtColor(moved.astype(np.float32), cv2.COLOR_LAB2RGB)
            fg = np.clip(fg * (1 - args.color_match) + moved * args.color_match, 0, 1)

        a = m[..., None]
        comp_plain[i] = O[i] * a + B[i] * (1 - a)
        bg = B[i] * (1 - args.shadow_strength * s[..., None])
        comp[i] = fg * a + bg * (1 - a)

    to8 = lambda x: (np.clip(x, 0, 1) * 255).astype(np.uint8)
    write(to8(comp), out / "composite_shadow.mp4", args.fps)
    write(to8(comp_plain), out / "composite_plain.mp4", args.fps)
    write(to8(shadow), out / "shadow_pass.mp4", args.fps)
    print(f"{n} frames -> {out}")


if __name__ == "__main__":
    main()
