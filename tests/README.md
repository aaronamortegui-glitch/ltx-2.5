# Tests

Each folder contains one run: `input.mp4` (the prepared clip), `output.mp4` (model output),
`side_by_side.mp4` (original | matte | composite over green), `preview_frame.jpg` and
`run.json` (settings and time).

Hardware: RTX 5090 Laptop 24 GB, ComfyUI 0.34.0 started with `--reserve-vram 7 --cache-none`,
int8 distilled transformer + int8 Gemma 12B encoder, video VAE `ltx-2.5-video-vae-bf16`.

| test | LoRA | clip | size | frames | time | VRAM peak | result |
|---|---|---|---|---|---|---|---|
| [alpha_gen_01](alpha_gen_01) | Alpha Gen 0.9, strength 1, empty prompt | dancer, ponytail, purple backlit wall | 544x960 | 97 @ 25 fps | 119 s | ~19 GB | Clean silhouette; ponytail and sleeves keep soft edges; floor reflection excluded |
| [alpha_gen_02](alpha_gen_02) | same (run with `scripts/run_alpha_gen.py`) | dancer, graffiti wall, skateboard on floor | 544x960 | 97 @ 25 fps | 112 s | not logged | Clean subject; skateboard and background excluded; small loss on a hand held in front of the chest |

| [greenscreen_01_pour](greenscreen_01_pour) | Alpha Gen 0.9 vs ffmpeg `chromakey` + `despill` | green-screen product shot: shaker, martini glass, splashes ([clips/pour_v3_1080p.mp4](../clips/pour_v3_1080p.mp4), first 97 frames) | 960x544 | 97 @ 16 fps | 115 s | 18.6 GB | **Classic key wins on real green screen.** Alpha Gen makes the glass fully opaque and draws fat blobs around droplets, so green background is kept inside the matte (dark halos after despill). Its strength is solid, hole-free mattes on the shaker; it is meant for footage *without* a green screen |

![alpha_gen_01](alpha_gen_01/preview_frame.jpg)
![alpha_gen_02](alpha_gen_02/preview_frame.jpg)

![greenscreen_01_pour](greenscreen_01_pour/cmp_5.jpg)

*greenscreen_01: top = composites over slate grey, bottom = mattes. Left original, middle
ffmpeg `chromakey=0x14c814:0.22:0.08` + `despill`, right LTX Alpha Gen + `despill`.*

Runs on personal clips are kept out of this public repo (`tests_private/`, gitignored).

Source clips: Pexels stock videos 7197864 and 8688886 (Pexels license), downscaled and trimmed
to 97 frames.
