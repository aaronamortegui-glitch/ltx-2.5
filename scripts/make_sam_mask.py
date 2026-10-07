"""Text-prompted mask video with SAM3 (comfyui-rmbg SAM3Segment), one or more concepts merged.

    python scripts/make_sam_mask.py clip.mp4 "dress" --out dress_mask.mp4
    python scripts/make_sam_mask.py clip.mp4 "bowl of candy" "hand" --out bowl_mask.mp4
"""
import argparse
import json
import time
import urllib.request
from pathlib import Path

from run_alpha_gen import get_json, probe, upload

OPT = {"max_segments": 0, "segment_pick": 0, "mask_blur": 0, "mask_offset": 0, "device": "Auto",
       "invert_output": False, "unload_model": False, "background": "Alpha", "background_color": "#222222"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("concepts", nargs="+")
    ap.add_argument("--threshold", type=float, default=0.4)
    ap.add_argument("--grow", type=int, default=0, help="mask_offset in px (positive grows)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--url", default="http://127.0.0.1:8188")
    args = ap.parse_args()

    _, _, fps, _ = probe(args.video)
    name = upload(args.url, args.video, f"sam_src_{Path(args.video).stem}.mp4")
    wf = {"1": {"class_type": "LoadVideo", "inputs": {"file": name}},
          "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}}}
    last = None
    for i, c in enumerate(args.concepts):
        nid = f"s{i}"
        wf[nid] = {"class_type": "SAM3Segment", "inputs": {
            "image": ["2", 0], "prompt": c, "output_mode": "Merged", "confidence_threshold": args.threshold,
            **dict(OPT, mask_offset=args.grow, unload_model=(i == len(args.concepts) - 1))}}
        if last is None:
            last = [nid, 1]
        else:
            wf[f"m{i}"] = {"class_type": "MaskComposite", "inputs": {"destination": last, "source": [nid, 1],
                                                                     "x": 0, "y": 0, "operation": "add"}}
            last = [f"m{i}", 0]
    wf["3"] = {"class_type": "MaskToImage", "inputs": {"mask": last}}
    wf["4"] = {"class_type": "CreateVideo", "inputs": {"images": ["3", 0], "fps": fps}}
    wf["5"] = {"class_type": "SaveVideo", "inputs": {"video": ["4", 0], "filename_prefix": "ltx25/sam_mask",
                                                     "format": "auto", "codec": "auto"}}
    req = urllib.request.Request(f"{args.url}/prompt", data=json.dumps({"prompt": wf}).encode(),
                                 headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req).read())
    if resp.get("node_errors"):
        raise SystemExit(json.dumps(resp["node_errors"], indent=1)[:3000])
    pid = resp["prompt_id"]
    while True:
        hist = get_json(f"{args.url}/history/{pid}").get(pid)
        if hist and hist["status"].get("status_str") in ("success", "error"):
            break
        time.sleep(3)
    if hist["status"]["status_str"] != "success":
        raise SystemExit(json.dumps(hist["status"]["messages"], indent=1)[-3000:])
    item = hist["outputs"]["5"]["images"][0]
    q = f"filename={item['filename']}&subfolder={item['subfolder']}&type={item['type']}"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_bytes(urllib.request.urlopen(f"{args.url}/view?{q}").read())
    print(f"mask {args.concepts} -> {args.out}")


if __name__ == "__main__":
    main()
