# Clerk Van — Clerk livery on the Ford Transit

**Live viewer:** https://jibaru.github.io/clerk-van/ (downloads for the .glb, .blend, livery atlas and turntable are in the page's Download section).

Shipped model (`export/`, `web/`, `godot/`): **`tools/build_transit_van.py`**, built on
"Ford Transit With Light Bar" by circlegent (Sketchfab, CC-BY 4.0) — a 2019 Transit high roof,
long wheelbase, 149k triangles with interior. The build strips the roof light bar, roof rails and
the conversion's interior shelving, replaces the sliding door (shipped open, raised, with an open window and step well) by a copy of the driver-side flank mirrored over the opening, blanks the rear
door glass, scales the asset to metres (wheelbase 3.75 m) and centres it, repaints every
body-colour panel with the Clerk livery atlas by box projection in metres (no photo projection),
and rigs doors / wheels / lights / clips. Reference for the intended look: `references/target-diecast.png`. Livery text: FREE COOKIES on the driver side (as in the captures) and "Auth as easy as / <SignIn/> / clerk.com" on the passenger side (as on the die-cast toy); profile key `SIDE_R_LINES`.

**Printable version** (`export/clerk_van_print.stl`, `_body.stl`, `_relief.stl`, `.glb`, built by `tools/build_print_van.py`):
one watertight shell of the exterior (interior dropped, every panel given a 4 cm wall, voxel remesh at
6.5 mm + smoothing) with every livery graphic - logos, wordmarks, text, QR codes - raised 15 mm as relief so
it shows on a 3D print. The shell is coloured like the display model (livery atlas by the same box
projection, dark glass and tyres, silver rims, white / purple relief) so the GLB doubles as a paint guide;
the relief comes from `textures/print_mask/` (written by `gen_textures.py` next to the atlas), vectorised by
`tools/print_mask_polys.py` and conformed to the body by ray-casting. Every mesh is checked closed (0 open
edges) before export. The STL is in millimetres at 1:24 (250 x 107 x 113 mm, 1.7 mm walls, 0.6 mm relief);
`_body.stl` + `_relief.stl` are the same geometry split for a two-colour print; scale them together in the
slicer for other sizes. The web page shows it with the "Model" selector (key **P**, or `?model=print`);
doors, wheels and lights are static in this model.

Earlier builds are kept as alternatives: `build_gen_van.py` (Hunyuan3D body), `build_crafter_van.py`
(VW Crafter repaint) and `build_van.py` (fully procedural Transit).

```
textures/clerk_van_atlas_transit.png   livery atlas for the Transit body (tools/profiles/transit.json)
textures/clerk_van_atlas_*.png         atlases for the other builds (profiles in tools/profiles/)
textures/brand/                        official Clerk logo rasterised (tools/rasterize_logos.js)
references/transit/                    the Sketchfab asset (git-ignored source), parts explorer renders
references/views/                      the eight reference cells + bboxes.json
export/clerk_van.glb / .blend          shipped model: embedded textures, KHR lights, named pivots, 7 clips
export/clerk_van_print*.stl / .glb     printable version: coloured watertight shell, livery in relief (STL at 1:24, mm)
textures/print_mask/                   relief masks + vectorised polygons for the printable build
web/                                   Three.js test page (wheels, lights, doors, turntable)
godot/                                 Godot 4.3 project with the same controls
renders/                               360° turntable (mp4 + gif + frames), hero stills, comparison sheets
tools/                                 gen_textures.py, build_transit_van.py, explore_parts.py, inspect_transit.py,
                                       render_turntable.py, compare_sheet.py, encode_turntable.ps1, older builds
```

## Rebuild

```powershell
Expand-Archive ford-transit-with-light-bar.zip references/transit -Force    # once; then copy source/*.glb to references/transit/transit.glb
node tools/rasterize_logos.js                                              # once; needs playwright-core + Chrome
python tools/gen_textures.py --profile transit                             # livery atlas for the Transit body
& "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" --background --python tools/build_transit_van.py -- (Get-Location)
& "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" --background export/clerk_van.blend --python tools/render_turntable.py -- (Get-Location) turntable 120
powershell tools/encode_turntable.ps1                                       # needs ffmpeg
python tools/print_mask_polys.py --profile transit                          # relief outlines (needs opencv)
& "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" --background export/clerk_van.blend --python tools/build_print_van.py -- (Get-Location) 15 24   # printable: relief mm, scale 1:N
```

Each build script copies its GLB into `web/` and `godot/`, so the last one run is the one the
test pages load. Livery placement per body lives in `tools/profiles/*.json` (B-pillar, axles,
belt line, diagonal start, logo positions, hood logo): edit, regenerate the atlas, rebuild.
Python needs `Pillow`, `qrcode`, `numpy`, `opencv-python-headless` and `gradio_client`.

To regenerate the body: run the `tencent/Hunyuan3D-2mv` Space with the four views in
`references/views/` (parameters used: 50 steps, guidance 5, octree 512, seed 7, see
`references/gen/gen_jobs.log`), then `tools/gen_measure.py <root> <name>` to check scale on a
metric grid and `build_gen_van.py <root> <name>` to build from it. The free Space allows two or
three runs a day without a Hugging Face token.

To check any build against the captures: `... render_turntable.py -- (Get-Location) compare`
then `python tools/compare_sheet.py` writes `renders/compare_sheet_a.png` / `_b.png` with the
eight reference cells next to the renders. `... fit` renders orthographic views for livery fitting.

## Web test page

Serve the repo over http (ES modules + GLB fetch do not work from `file://`):

```powershell
python -m http.server 8080
# open http://localhost:8080/web/
```

Controls: **W/S** drive (wheels roll), **A/D** steer, **L** headlights, **K** tail lights,
**1–5** individual doors, **O** all doors, **T** turntable, **R** reset. The "Exported glTF
clips" dropdown plays the animations baked in the GLB. Three.js is loaded from unpkg (r170).

## Godot

Open `godot/project.godot` in Godot 4.3+ (the GLB is imported automatically). `main.gd` finds
the pivots by name and offers the same toggles and keys as the web page. Lens materials are
duplicated at runtime so emission can be driven. The project has not been run inside the Godot
editor on this machine (Godot is not installed here), so treat it as a starting point.

## Blender

Open `export/clerk_van.blend`. The NLA editor holds one track per clip on each door/wheel
(muted so the file opens in the rest pose). Hierarchy: `ClerkVan` (root) → `Body` → doors,
interior boxes, wheel wells, lights; wheels hang off the root (`Steer_L`/`Steer_R` →
`Wheel_FL`/`Wheel_FR`). Body materials: `Livery` (atlas, UV map `LiveryUV`), `Photo_front/back/
left/right` (reference photos, UV map `PhotoUV`), `Headlight_Lens`, `Taillight_Lens`, `Underbody`.

## Runtime node names (identical in Blender, Three.js and Godot)

| Node | How to drive it |
| --- | --- |
| `Door_FL`, `Door_FR` | rotate about local up axis, hinge at the front edge (FL −65°, FR +65°) |
| `Door_Slide` | passenger side: translate 0.10 m outward (−X), then ~1.15 m rearward |
| `Door_RL`, `Door_RR` | rotate about local up axis, hinge at the outer edge (RL −95°, RR +95°) |
| `Wheel_FL/FR/RL/RR` | rotate about local X (positive = rolling forward); radius 0.35 m |
| `Steer_L`, `Steer_R` | parents of the front wheels, rotate about local up axis |
| `Light_HeadL/R` | spot lights (KHR_lights_punctual) |
| `Light_TailL/R` | point lights |
| `Headlight_Lens`, `Taillight_Lens` | materials on the lamp areas; set emissive strength to switch on |

Animation clips in the GLB: `DoorFL_Open`, `DoorFR_Open`, `DoorSlide_Open`, `DoorRL_Open`,
`DoorRR_Open`, `AllDoors_Open` (30 frames each) and `Wheels_Spin` (one full turn per second).

Axes: Blender front = −Y, glTF front = +Z (Y-up), driver side = +X in both.

## Third-party parts and licence

* Body, interior, wheels, lamps and mirrors: "Ford Transit With Light Bar" by circlegent on
  Sketchfab, licensed CC Attribution 4.0 — https://sketchfab.com/3d-models/aa98280d18014f3491fc528b6efdefe3.
  Credit the author wherever the model is published. The zip and `references/transit/source/` are
  git-ignored only to keep the repo small; the licence allows redistribution with attribution.
* The alternative builds use "Volkswagen Crafter" by geyges (Sketchfab Free Standard, not
  redistributable) and a Hunyuan3D-2mv generated body; see their scripts for details.

## Brand assets

* Roof: white Clerk lockup on the purple roof, reading from the driver's side (as on the die-cast reference); profile key `ROOF_LOGO`. The asset's light-bar mount hole is covered by `RoofPatch`.
* Logo: the official Clerk lockup and symbol from clerk.com/brand-assets
  (`references/brand/*.svg`, brand purple #6C47FF), rasterised with `tools/rasterize_logos.js`
  into `textures/brand/*.png` (all-white for the dark and purple panels, purple-text version for
  the hood).
* Typeface: Inter (OFL, `references/brand/Inter.ttf`), Bold for FREE COOKIES, SemiBold for the
  copy, Medium for the footnote. Clerk's brand page does not name its typeface; Inter is the
  closest match to the captures.
* QR codes encode `https://clerk.com` and are verified to decode (OpenCV) on both sides and
  the rear every time the atlas is generated.
