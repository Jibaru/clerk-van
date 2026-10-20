"""Composite reference cells next to renders/compare/*.png -> renders/compare_sheet.png"""
import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ref = Image.open(os.path.join(ROOT, "references", "clerk-van-views.png")).convert("RGB")
W, H = ref.size
cw, ch = W / 4, H / 3
CELLS = {  # render name -> (row, col) of the reference grid
    "r1c2_front": (0, 1), "r2c2_rear": (1, 1), "r1c4_sideL": (0, 3), "r2c4_sideR": (1, 3),
    "r1c1_front34L": (0, 0), "r1c3_front34R": (0, 2), "r2c1_rear34L": (1, 0), "r2c3_rear34R": (1, 2),
}
TW, TH = 600, 400
rows = []
for name, (r, c) in CELLS.items():
    cell = ref.crop((int(c * cw), int(r * ch), int((c + 1) * cw), int((r + 1) * ch))).resize((TW, TH), Image.LANCZOS)
    rp = os.path.join(ROOT, "renders", "compare", name + ".png")
    rend = Image.open(rp).convert("RGB").resize((TW, TH), Image.LANCZOS) if os.path.exists(rp) else Image.new("RGB", (TW, TH), (40, 40, 40))
    row = Image.new("RGB", (TW * 2 + 10, TH), (0, 0, 0))
    row.paste(cell, (0, 0)); row.paste(rend, (TW + 10, 0))
    ImageDraw.Draw(row).text((8, 6), name, fill=(0, 0, 0))
    rows.append(row)
sheet = Image.new("RGB", (TW * 2 + 10, (TH + 10) * len(rows)), (0, 0, 0))
for i, r in enumerate(rows):
    sheet.paste(r, (0, i * (TH + 10)))
sheet.save(os.path.join(ROOT, "renders", "compare_sheet.png"))
# two half sheets for easier viewing
sheet.crop((0, 0, sheet.width, (TH + 10) * 4)).save(os.path.join(ROOT, "renders", "compare_sheet_a.png"))
sheet.crop((0, (TH + 10) * 4, sheet.width, sheet.height)).save(os.path.join(ROOT, "renders", "compare_sheet_b.png"))
print("sheet written")
