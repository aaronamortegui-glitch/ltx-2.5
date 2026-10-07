"""Composite a foreground clip over a new background plate using a matte (location swap).

The plate is scaled/cropped to the foreground size and looped ping-pong to the foreground
length. Light matching is a simple grade on the foreground (--fg-grade) and an optional
background blur (depth of field). Writes composite.mp4 and a side-by-side review.

    python scripts/composite.py fg.mp4 matte.mp4 plate.mp4 --out out_dir --fg-grade "colorbalance=rs=.08:bs=-.05"
"""
import argparse
import subprocess
from pathlib import Path

from run_alpha_gen import probe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fg")
    ap.add_argument("matte")
    ap.add_argument("plate")
    ap.add_argument("--out", required=True)
    ap.add_argument("--levels", default="32,235")
    ap.add_argument("--fg-grade", default="null", help="ffmpeg filter applied to the foreground")
    ap.add_argument("--bg-blur", type=float, default=0.0)
    ap.add_argument("--matte-erode", type=int, default=0, help="shrink matte by N px (removes fringe)")
    args = ap.parse_args()

    w, h, fps, _ = probe(args.fg)
    n = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", args.fg],
                           capture_output=True, text=True).stdout.strip())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    lo, hi = (int(x) for x in args.levels.split(","))
    erode = ",erosion" * args.matte_erode
    blur = f",gblur=sigma={args.bg_blur}" if args.bg_blur else ""
    fc = (f"[2:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},"
          f"split[p1][p2];[p2]reverse[pr];[p1][pr]concat=n=2:v=1,loop=loop=-1:size=32767,"
          f"trim=end_frame={n},setpts=N/FRAME_RATE/TB{blur}[bg];"
          rf"[1:v]scale={w}:{h},format=gray,lutyuv=y='clip((val-{lo})*255/({hi}-{lo})\,0\,255)'{erode}[m];"
          f"[0:v]{args.fg_grade}[fgg];[fgg][m]alphamerge[fga];[bg][fga]overlay=shortest=1,format=yuv420p[comp]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", args.fg, "-i", args.matte, "-i", args.plate,
                    "-filter_complex", fc, "-map", "[comp]", "-map", "0:a?", "-c:v", "libx264", "-crf", "16",
                    "-c:a", "aac", str(out / "composite.mp4")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", args.fg, "-i", str(out / "composite.mp4"),
                    "-filter_complex", "[0:v][1:v]hstack=2,format=yuv420p", "-c:v", "libx264", "-crf", "20",
                    str(out / "side_by_side.mp4")], check=True)
    print(f"composite -> {out}")


if __name__ == "__main__":
    main()
