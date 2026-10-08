# VFX use cases with LTX-2.5 (and what we learned building them)

What can be done today on a 24 GB GPU, by chaining LTX-2.5 IC-LoRAs with SAM3 and plain
compositing. Every recipe below was run in this repo.

- **Public tests:** results are in `tests/`.
- **Private tests:** these use personal footage of two people and are kept out of the repo
  (`tests_private/`, gitignored). Only text findings and settings from them are published.

All runs are on an RTX 5090 Laptop (24 GB), each at an 18.3–19.4 GB peak.

## The building blocks

| block | what it does | script |
|---|---|---|
| **Alpha Gen** | soft alpha matte of the main subject (people first), no green screen | `run_alpha_gen.py`, `run_alpha_gen_chunked.py` |
| **SAM3** (text prompt) | mask of any object you can name: "car", "dress", "bowl of candy", "face" | `make_sam_mask.py` |
| **Clean Plate** | removes the moving subjects and rebuilds the empty set behind them | `run_alpha_gen.py --lora ...clean-plate...` |
| **Union Control** (pose / depth) | regenerates the whole shot with a new prompt, keeping motion and layout | `make_control.py` + `run_alpha_gen.py --lora ...union-control... --align 64` |
| **In/Outpainting** | regenerates only the masked region (two stage) | `run_inpaint.py` |
| **T2V / I2V** | generates new plates (backgrounds) or shots from a frame | `run_t2v.py` |
| **Composite** | puts a matted foreground over a new plate, ping-pong looping the plate | `composite.py` |
| **Shadow + colour** | shadow pass from the Clean Plate ratio, Lab colour match | `composite_shadow.py` |

## Recipes

### 1. Change of location (keep the people, replace the world)
`Alpha Gen matte (+ SAM3 for objects) -> T2V background plate -> composite`

- **Halloween porch to castle (private):** the couple plus the bowl of candy was placed in a
  generated torch-lit castle hall. Alpha Gen does the people and SAM3 ("bowl of candy",
  "hand") adds the bowl. A warm grade on the foreground plus a light background blur sold it.
- **Suburban street to Miami (private):** Alpha Gen for the couple plus SAM3 "car" for the car
  they lean on, over a generated Ocean Drive plate.
  - What went wrong:
    - SAM3 also picked up a second, parked car in the background. Use one segment, or a
      tighter prompt.
    - The car has no contact shadow on the new ground, and the plate's perspective does not
      match, so it looks pasted.
  - **Lesson:** location swaps work best for people framed from the waist up; full bodies
    and vehicles need shadow and perspective matching.

### 2. Costume / wardrobe change (keep identity)
`SAM3 mask of the garment - SAM3 mask of face (and hair) -> In/Outpainting with a scene prompt`

- **Mummy bandages to medieval knight armour with a chainmail hood (private).** Best result
  of the session: the costume is replaced, his face is preserved, and the other person is
  untouched. 141 s at 1024x768 x 49 frames.
  - Side effect: the candy bowl in front of him overlapped the costume mask, so it was
    redrawn too (it became a glass bowl). Subtract held objects from the mask as well.
- **Floral dress to emerald satin slip dress (private).**
  - First run: the "dress" mask touched her head, so her face was partly regenerated and
    drifted.
  - Re-run with `face` and `hair` subtracted from the mask: her face and hairstyle are kept
    and the dress is cleanly replaced, in 142 s.
- **Lessons:**
  - Always subtract `face` (and `hair`) from a clothing mask.
  - SAM3 concept names matter: "white bandages" returned an empty mask, while "mummy costume"
    found it.
  - Write the inpaint prompt as a description of the whole scene, not as an edit command.

### 3. Turn people into creatures (aliens) inside the real shot
`Clean Plate (empty street) + Union Control on pose (aliens) -> Alpha Gen on the aliens -> composite`

- **Private run:** two green aliens wearing the couple's own outfits (floral dress, round
  sunglasses, leather jacket), posing in the real suburban street. The street came from Clean
  Plate of the same clip.
- **Lesson:** pose control keeps the poses but not the exact scale and position, so the
  aliens sit slightly smaller and shifted. Fine for stylised work; tracking-accurate
  replacement would need depth control or per-shot alignment.

### 4. Replace the whole scene (new world, same performance)
`Union Control on depth with a new prompt`

- **Suburban couple to space-suited couple with a chrome hover car on Mars (private).**
  - Poses, framing and the car's shape are kept.
  - **Identity is lost:** the faces become new people. Depth and pose control keep shape, not
    likeness.
- **Claymation style (private): failed.** The distilled model ignored "claymation" and
  produced photoreal people. Photoreal look changes work; stylisation into animation did not.

### 5. Remove people / get a clean plate
`Clean Plate`: see [vfx_01](../tests/vfx_01_clean_plate). It also rebuilt the hidden half of a
car behind two people, across hard cuts (private).

### 6. Relight: day to night
`Day-to-Night IC-LoRA`

- **Private run:** a sunny suburban shot became blue hour, with porch lights and car lights
  switched on and people lit consistently.
- **It does not get fully dark.** The card uses guidance 3–4 on the dev model for a darker
  night; the distilled CFG-1 graph gives dusk.

### 7. Restoration
- **Deblur, Decompression, Colorization:** see the restore_* tests.
- **Common pattern:** detail that the damage destroyed comes back plausible, not faithful
  (re-invented faces, arm positions, colours of the lighting).

### 8. Motion design
- **Cinemagraph:** works on product shots (5 % of pixels move); weaker on people.
- **Layout to Render:** follows a layout and first frame closely (proxy test).

## Round 2: going deeper on what worked

### 9. Shadow pass + colour match for location swaps (fixes the "pasted" look)
`original / Clean Plate luminance ratio -> shadow pass -> multiply onto the new plate; Lab colour transfer on the foreground`

- **Public test:** see [vfx_05](../tests/vfx_05_shadow_pass).
  - The real floor shadow is recovered and the feet are grounded.
  - The colour match is the biggest gain.
  - Limit the search to the floor and near the subject, because the regenerated plate is not
    pixel-identical and the raw ratio flags texture differences.
- **Private, waist-up shot at a car:** almost no shadow to recover, because the shadow fell
  on the car, which belongs to the matte. **The floor must be in frame.**

### 10. Remove one person, keep the other
`Clean Plate (everyone removed) + Alpha Gen matte limited to one SAM3 region ("woman") -> composite`

- **Private run: works very well.** He disappears, she stays untouched, and the car he was
  covering is rebuilt, across all three camera angles.
- **Only artefact:** a thin strip of his jacket where their bodies touched. Tighten the mask
  edge there.

### 11. Replace a person in place: Inpaint versus Union Control
`SAM3 "person" mask -> Inpaint with an alien prompt` compared with the Union pose version (recipe 3).

| | Inpaint (person mask) | Union Control (pose) |
|---|---|---|
| placement and scale | **exact** (stays inside the silhouette) | drifts a little |
| pose and gesture | **lost** (arms down instead of hands on hips) | **kept** |
| background | untouched original | regenerated, so it needs a Clean Plate composite |

Neither gives both. A pose-conditioned inpaint would, but the inpaint graph has no control
input.

### 12. Remove an object people interact with: fails
`SAM3 "car" - "person" -> Inpaint with an "empty street" prompt`

- **Private run:** the couple leans on the car, and the inpaint simply drew a different
  (grey) car.
- **Lesson:** removal works for people and free-standing objects. Anything a subject touches
  or leans on gets re-imagined, not removed.

### 13. Product pipeline: one green-screen shot into many ads
`Alpha Gen full-clip matte (1080p, chunked) -> N generated plates -> composite`

- **Public test:** see [vfx_04](../tests/vfx_04_product_pipeline). Three backgrounds at
  about 1 min each.
- **The semi-transparent glass shows each new background through it**, which a basic chroma
  key cannot do.

## Results at a glance (private runs, text only)

| run | blocks | size x frames | time | peak | verdict |
|---|---|---|---|---|---|
| couple to castle | Alpha Gen + SAM3 + T2V plate + composite | 1024x768 x 192 | plate 65 s | 18.5 GB | works; best for waist-up framing |
| couple + car to Miami | Alpha Gen + SAM3 car + T2V plate | 1024x768 x 124 | plate 65 s | 18.3 GB | works; extra car picked; no contact shadow |
| aliens in the real street | Clean Plate + Union pose + Alpha Gen + composite | 704x576 x 89 | ~4.5 min total | 19.4 GB | strong; scale and position drift a little |
| Mars, new scene | Union depth | 704x576 x 89 | 90 s | 18.9 GB | strong look, identity lost |
| aliens on the porch | Union pose | 704x576 x 89 | 90 s | 18.7 GB | humanoid "zombie" more than alien |
| claymation | Union depth | 704x576 x 89 | 85 s | 18.9 GB | **failed**: stayed photoreal |
| knight armour | SAM3 (costume - face) + Inpaint | 1024x768 x 49 | 141 s | 19.3 GB | **best**: costume swapped, face kept |
| emerald dress (v1) | SAM3 dress + Inpaint | 1024x768 x 49 | 340 s | 19.1 GB | dress swapped, face drifted |
| emerald dress (v2) | SAM3 (dress - face - hair) + Inpaint | 1024x768 x 49 | 142 s | 19.1 GB | **dress swapped, face and hair kept** |
| day to night | Day-to-Night | 704x544 x 97 | 90 s | 18.9 GB | blue hour, not full night |
| clean plate of the car | Clean Plate | 704x544 x 97 | 90 s | 19.1 GB | rebuilt the hidden car |
| cinemagraph of people | Cinemagraph LoRA | 704x512 x 25 | 65 s | 18.9 GB | weak; trees and camera drift |
| remove him, keep her | Clean Plate + Alpha Gen limited by SAM3 "woman" | 704x544 x 89 | CPU comp | — | **works**; thin jacket strip where they touch |
| aliens via inpaint | SAM3 "person" + Inpaint | 1024x768 x 49 | 127 s | 19.0 GB | exact placement, pose lost |
| remove the car | SAM3 car - person + Inpaint | 1024x768 x 49 | 135 s | 19.0 GB | **failed**: drew another car |
| shadow pass at the car | Clean Plate ratio | 704x544 x 89 | CPU | — | no usable shadow (floor out of frame) |

## Gotchas found
- **Union Control (ref 0.5) needs width and height as multiples of 64.** At 704x544 it fails
  with an einops error in `LTXAddVideoICLoRAGuide`. Use `--align 64`.
- **The `VideoDepthAnything` nodes from the official Union workflow are not installed.** Make
  the control video with the `comfyui_controlnet_aux` preprocessors instead
  (`make_control.py`), then feed it to the plain V2V IC-LoRA graph.
- **DWPose runs on CPU here** and takes about 8–10 min for 97 frames.
- **SAM3 (`SAM3Segment`):**
  - Pass all of its optional inputs over the API, or it fails with a missing `device`
    argument.
  - A concept that doesn't match returns an empty mask silently. Check the coverage before
    using it.
- **Negative prompts do nothing at CFG 1** (distilled). Steer with the positive prompt only.
- **The inpaint workflow defaults to a 1024 short side at stage 2.** That is too much for
  long clips on 24 GB; 768 x 49 frames peaked at 19.3 GB.
EOF
echo ok