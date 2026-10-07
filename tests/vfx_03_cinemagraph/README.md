# vfx_03: Cinemagraph LoRA

Plain LoRA (not an IC-LoRA) applied to the LTX-2.5 image-to-video graph
(`run_t2v.py --lora`).

**Settings:** start frame from the pour shot (704x512), `CINEMAGRAPH_MOTION` prompt
naming what moves and what stays frozen, LoRA strength 1.1, I2V strength 1.0, 25 frames,
distilled 8 steps. 65 s, VRAM peak 18.5 GB.

![cinemagraph](cinemagraph.gif)

**Findings:**
- **Product shot:** only about 5 % of the pixels move (the liquid stream and splash). The
  shaker, glass and background stay frozen.
- **The loop seam is small but visible** (mean diff 3.25/255 between the last and first
  frame). Add a short cross-fade for a perfect loop.
- **On a private clip of two people at a car, the effect is weaker.** About 26 % of the
  frame changed, with the trees moving and a slight camera drift. For people shots, combine
  it with a freeze mask.
- **The card's settings were not reproduced.** It recommends 30 steps at guidance 4 on the
  dev model; we used the distilled 8-step graph.
