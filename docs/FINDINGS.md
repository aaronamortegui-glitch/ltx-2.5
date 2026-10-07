# Findings: LTX-2.5 Alpha Gen

These are the results and conclusions so far (2026-10-07). Each claim links to the test
behind it in [tests/](../tests/README.md).

Hardware: RTX 5090 Laptop with 24 GB VRAM and 64 GB RAM, ComfyUI 0.34.0, int8 distilled
transformer and int8 Gemma 12B encoder.

## Summary

1. **Alpha Gen works without a green screen.** On ordinary footage of dancers on busy
   backgrounds it pulls a clean subject matte. Ponytail and sleeve edges stay soft, and floor
   reflections and props on the floor (a skateboard) are left out.
   See [alpha_gen_01](../tests/alpha_gen_01) and [alpha_gen_02](../tests/alpha_gen_02).
2. **Resolution is the main quality setting.** Run it at the source resolution, with a 1088
   short side. At 544 the matte is too coarse: glass becomes opaque, droplets come out too
   big, and edges get dark fringes. At 768 and 1088 the glass stays semi-transparent and the
   edges are tight. See [greenscreen_02](../tests/greenscreen_02_resolution).
3. **On real green screen, Alpha Gen at source resolution beat a basic chroma key on our
   product shot.** The keyer (`chromakey` + `despill`) erased most of the transparent martini
   glass. Alpha Gen kept it, along with the liquid and the splash. At 544 the result was the
   opposite, which is why our first verdict was wrong
   ([greenscreen_01](../tests/greenscreen_01_pour)).
4. **Clamp the matte's black level.** At 768 and above the matte background sits at about
   23–29 instead of 0. That makes the background partly opaque and tints the composite. A
   levels pass of black 32 and white 235 fixes it (`--levels 32,235`).
5. **Subject choice with several people works, but held objects get dropped.** On two
   personal test clips (not published):
   - Both people in frame were matted in every shot. A car they sit on and lean against was
     excluded. The matte stayed correct across hard camera cuts.
   - Dark hair against a dark night background was clean.
   - A bowl held out by an *off-screen* hand was treated as background, which left a hole in
     the person behind it. Anything that is not part of the people, or not held by them, can
     be dropped, and there is no way to ask for it.
6. **Alpha Gen + SAM3 recovers dropped objects.** Running `SAM3Segment` with text prompts
   ("bowl of candy", "hand") and merging that mask with the Alpha Gen matte (lighten / max)
   put the held bowl back. You get Alpha Gen's fine people edges plus objects you can pick by
   name. This removes the "can't choose the subject" limit when an object matters.
7. **Deblur sharpens strong defocus but re-invents detail**
   ([restore_01](../tests/restore_01_deblur)). SSIM went from 0.916 to 0.935; patterns and
   facial detail came back plausible but not identical.
8. **The base model also generates usable clips.** T2V and I2V at 960x544 x 5 s took about
   65 s each at about 19.7 GB, with audio ([gen_01](../tests/gen_01_t2v_coffee),
   [gen_02](../tests/gen_02_i2v_pour)).
9. **The video VAE choice doesn't matter for mattes.** The conv VAE gives a virtually
   identical matte (0.16 % of pixels differ noticeably) and is a bit faster, so use it.
10. **VRAM sets the limit on a 24 GB card.**

   | size | frames | time | VRAM peak |
   |---|---|---|---|
   | 960x544 | 97 | ~2 min | 18.6–19 GB |
   | 1344x768 | 97 | ~3 min | **23.0 GB, at the limit** |
   | 1920x1088 | 25 | ~1.7 min | 18.4–19 GB |
   | 1024x768 | 49 | ~1.1 min | 18.6–18.8 GB |

   Full HD over a whole shot means processing it in short windows. Don't search for the
   ceiling by pushing higher on this machine.

## Recommended recipe

| step | setting |
|---|---|
| input | source resolution up to 1920x1088, padded to multiples of 32; frames 8n+1, at most 121; audio track required (the script adds a silent one) |
| model | distilled int8 transformer + `ltx-2.5-22b-ic-lora-alpha-gen-0.9`, strength 1.0, empty prompt |
| sampler | 8 distilled steps, `euler_ancestral`, CFG 1, seed 1234 |
| decode | `VAEDecodeTiled` 512/64, temporal 64/8; the conv video VAE is fine for mattes |
| post | levels 32/235 on the matte, then `out = source * alpha + bg * (1 - alpha)` on the original clip (despill if it was shot on green) |

```bat
python scripts\run_alpha_gen.py clip.mp4 --short-side 1088 --frames 25 --seed 1234 ^
       --decode-temporal 64,8 --levels 32,235
```

## When to use it

| footage | use |
|---|---|
| No green screen: people, products, hair, smoke, glass | **Alpha Gen.** Nothing else in this set of tools does it without a mask or roto |
| Green screen with transparent or splashy elements | **Alpha Gen at source resolution**, or as a core matte combined with a keyer |
| Clean green screen of opaque subjects | A conventional keyer is faster and good enough |
| Fast human motion over long shots | Community reports say mask trackers (SAM, SAMMIE) are steadier; combine mattes if needed |

## Limitations

- You cannot choose which object becomes the foreground; the model picks the dominant
  subject. People come first: objects held by someone out of frame are dropped.
- 145 frames at most, 121 recommended. Longer shots need chunking, and the seams between
  windows are untested.
- The output is a plain video. There is no EXR or alpha output from the stock workflow, so
  combine the matte with the source in a compositor.
- Slow and heavy: about 2 min per 4 s clip at a 544 short side, and about 47 GB of weights
  on disk.

## Open questions and next tests

- Chunked full-HD processing over a whole shot, and whether the matte jumps at the seams.
- 145 vs 97 frames.
- A hybrid that uses the Alpha Gen matte as the core and a keyer for the edges.
- Pending a Hugging Face license click: Clean Plate, Decompression, Colorization, Day-to-Night, Layout to Render, Cinemagraph.
- Clean Plate (subject removal) to get a matte plus a clean background pair.
