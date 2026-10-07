# greenscreen_01: chroma key vs Alpha Gen on a green-screen pour

**Clip:** `clips/pour_v3_1080p.mp4`, a 3840x2160 product shot at ~16 fps that was
downscaled to 960x544. The test uses the first 97 frames.
- A shaker pours into a martini glass, with splashes and droplets.
- It was shot on a vignetted green screen.

| file | what |
|---|---|
| `input.mp4` | prepared clip fed to both methods |
| `output.mp4` | LTX Alpha Gen matte (`run.json` has the settings) |
| `chromakey_matte.mp4` | `ffmpeg -vf "format=yuva444p,chromakey=0x14c814:0.22:0.08,alphaextract"` |
| `comparison.mp4` | top row: composites over grey after `despill`. Bottom row: mattes |

## Findings

- **Glass:** the chroma key treats it as semi-transparent, which is correct. Alpha Gen
  makes the whole glass opaque, so the green seen through it stays in the composite.
- **Droplets and splashes:** Alpha Gen catches them but draws them larger than they are.
  The extra area is background, so it shows as dark halos after despill. The chroma key
  gives tighter edges.
- **Solid objects (the shaker):** both methods give a clean, hole-free matte.
- **Verdict at 544 (superseded, see [greenscreen_02](../greenscreen_02_resolution)):** at this resolution a conventional keyer plus despill looked better.
  At the source resolution (1088), with a levels fix, Alpha Gen wins on this shot.
