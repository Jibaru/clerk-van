"""
Vectorises the relief masks written by gen_textures.py (textures/print_mask/<panel>_<profile>.png)
into polygons in panel metres for build_print_van.py (which runs inside Blender, without OpenCV).

    python tools/print_mask_polys.py --profile transit

Output: textures/print_mask/polys_<profile>.json
  { panel: [ {"outer": [[a,b],...], "holes": [[[a,b],...], ...]}, ... ] }
Panel coordinates follow the atlas convention used by the builds (see uv mapping in build_transit_van.py):
  side_left  a = y (metres along the van, nose at -y), b = z          (no flip)
  side_right a = y, b = z                                             (flipped: screen-left = rear)
  front      a = x, b = z   (no flip)      rear  a = x, b = z (flipped: driver side screen-left)
  top        a = x (flipped: driver side screen-left), b = -y (nose at the top of the image)
"""
import argparse, json, os
import cv2
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--profile", default="transit")
ap.add_argument("--epsilon", type=float, default=0.3, help="approxPolyDP tolerance in pixels")
args = ap.parse_args()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(ROOT, "textures")
layout = json.load(open(os.path.join(TEX, f"atlas_layout_{args.profile}.json")))
EXT = layout["extents"]
FLIP = {"side_left": False, "side_right": True, "front": False, "rear": True, "top": True}
EXTS = {"side_left": EXT["side"], "side_right": EXT["side"], "front": EXT["front"], "rear": EXT["rear"], "top": EXT["top"]}

out = {}
for name in FLIP:
    path = os.path.join(TEX, "print_mask", f"{name}_{args.profile}.png")
    if not os.path.exists(path):
        continue
    mask = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    mask = (mask > 127).astype(np.uint8) * 255
    # 1 px dilation (~2 mm at full scale): QR modules that only touch at a corner would otherwise give a
    # contour passing twice through one vertex, which extrudes into a non-manifold pinch
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
    h, w = mask.shape
    a0, a1, b0, b1 = EXTS[name]
    flip = FLIP[name]

    def to_m(c):
        pts = []
        for (u, v) in c.reshape(-1, 2).astype(float):
            t = u / w
            if flip:
                t = 1 - t
            pts.append([round(a0 + t * (a1 - a0), 5), round(b1 - v / h * (b1 - b0), 5)])
        return pts

    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    shapes = []
    if hier is not None:
        hier = hier[0]
        for i, c in enumerate(cnts):
            if hier[i][3] != -1 or cv2.contourArea(c) < 4:
                continue
            oc = cv2.approxPolyDP(c, args.epsilon, True)
            if len(oc) < 3:
                continue
            holes = []
            j = hier[i][2]
            while j != -1:
                hc = cv2.approxPolyDP(cnts[j], args.epsilon, True)
                if len(hc) >= 3 and cv2.contourArea(cnts[j]) >= 4:
                    holes.append(to_m(hc))
                j = hier[j][0]
            shapes.append({"outer": to_m(oc), "holes": holes})
    out[name] = shapes
    print(f"{name}: {len(shapes)} shapes, {sum(len(s['outer']) + sum(len(h) for h in s['holes']) for s in shapes)} vertices")

dst = os.path.join(TEX, "print_mask", f"polys_{args.profile}.json")
json.dump(out, open(dst, "w"))
print("written", dst)
