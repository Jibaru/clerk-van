"""
Decodes the QR codes on the generated livery panels and fails if any of them does not read
https://clerk.com. Run after gen_textures.py (gen_textures.py also calls it when OpenCV is installed):

    python tools/verify_qr.py --profile transit

The panels draw the QR white on dark paint; OpenCV's detector wants dark modules on light, so the
panel is inverted first, and tried at full and half resolution (the side panels are 2900 px wide).
"""
import argparse, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def verify(profile="transit", expected="https://clerk.com", panels=("side_left", "side_right", "rear")):
    import cv2
    import numpy as np
    det = cv2.QRCodeDetector()
    results = {}
    for name in panels:
        path = os.path.join(ROOT, "textures", f"panel_{name}_{profile}.png")
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            results[name] = None
            continue
        inv = 255 - img
        text = ""
        for scale in (1.0, 0.5, 0.75):
            probe = inv if scale == 1.0 else cv2.resize(inv, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            text, _, _ = det.detectAndDecode(probe)
            if text:
                break
        results[name] = text
    ok = all(v == expected for v in results.values())
    return ok, results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="transit")
    ap.add_argument("--expected", default="https://clerk.com")
    args = ap.parse_args()
    ok, results = verify(args.profile, args.expected)
    for k, v in results.items():
        print(f"{k}: {v!r}")
    print("QR OK" if ok else "QR FAILED")
    sys.exit(0 if ok else 1)
