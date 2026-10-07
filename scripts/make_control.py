"""Turn a clip into a control video (depth / pose / canny) for the Union Control IC-LoRA.

Runs a ComfyUI preprocessor on every frame and keeps the source fps and audio, so the
result can go straight into run_alpha_gen.py with --lora <union control>.

    python scripts/make_control.py clip.mp4 depth --out clip_depth.mp4
    python scripts/make_control.py clip.mp4 pose  --out clip_pose.mp4
"""
import argparse
import json
import time
import urllib.request
from pathlib import Path

from run_alpha_gen import get_json, probe, upload

PRE = {
    "depth": ("DepthAnythingV2Preprocessor", {"ckpt_name": "depth_anything_v2_vitl.pth"}),
    "pose": ("DWPreprocessor", {"detect_hand": "enable", "detect_body": "enable", "detect_face": "enable",
                                "bbox_detector": "yolox_l.onnx",
                                "pose_estimator": "dw-ll_ucoco_384_bs5.torchscript.pt",
                                "scale_stick_for_xinsr_cn": "disable"}),
    "canny": ("CannyEdgePreprocessor", {"low_threshold": 100, "high_threshold": 200}),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("kind", choices=sorted(PRE))
    ap.add_argument("--out", required=True)
    ap.add_argument("--url", default="http://127.0.0.1:8188")
    args = ap.parse_args()

    w, h, fps, _ = probe(args.video)
    name = upload(args.url, args.video, f"ctrl_src_{Path(args.video).stem}.mp4")
    cls, extra = PRE[args.kind]
    wf = {
        "1": {"class_type": "LoadVideo", "inputs": {"file": name}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "3": {"class_type": cls, "inputs": {"image": ["2", 0], "resolution": min(w, h), **extra}},
        "4": {"class_type": "ImageScale", "inputs": {"image": ["3", 0], "upscale_method": "lanczos",
                                                     "width": w, "height": h, "crop": "disabled"}},
        "5": {"class_type": "CreateVideo", "inputs": {"images": ["4", 0], "fps": fps, "audio": ["2", 1]}},
        "6": {"class_type": "SaveVideo", "inputs": {"video": ["5", 0], "filename_prefix": f"ltx25/ctrl_{args.kind}",
                                                    "format": "auto", "codec": "auto"}},
    }
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
    item = hist["outputs"]["6"]["images"][0]
    q = f"filename={item['filename']}&subfolder={item['subfolder']}&type={item['type']}"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_bytes(urllib.request.urlopen(f"{args.url}/view?{q}").read())
    print(f"{args.kind} control -> {args.out}")


if __name__ == "__main__":
    main()
