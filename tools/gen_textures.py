"""
Generates the Clerk Van livery atlas (textures/clerk_van_atlas.png) and the
individual panel images used by build_van.py (Blender).

All drawing is done in VEHICLE METRES so the livery lands exactly where the
geometry expects it. Vehicle frame (Blender): front = -Y, rear = +Y,
driver (left) side = +X, passenger (right) side = -X, Z up, ground z = 0.

Atlas layout (4096 x 4096):
  side_left   (0,0)      3000x1200   y in [-2.9, 2.9], z in [0, 2.32], nose on the LEFT
  side_right  (0,1200)   3000x1200   same, nose on the RIGHT
  front       (0,2400)   1200x1200   x in [-1.16, 1.16] (passenger side on the left), z in [0, 2.32]
  rear        (1200,2400)1200x1200   x reversed (driver side on the left)
  top         (3050,0)   1000x2500   driver side on the left, nose at the top
  bottom      (3050,2600) 200x200    flat dark
  wheel       (20,3630)  460x460
  plate       (500,3630) 520x260
  ford        (1040,3630)400x160
  headlight   (1460,3630)600x300
  taillight   (2080,3630)150x450
"""
import os, math, json
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import qrcode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "textures")
os.makedirs(OUT, exist_ok=True)

FONTS = "C:/Windows/Fonts/"
INTER = os.path.join(ROOT, "references", "brand", "Inter.ttf")   # Inter variable font (OFL) — Clerk's web typeface
F_BOLD = (INTER, "Bold")             # FREE COOKIES
F_LOGO = (INTER, "SemiBold")         # (wordmark now comes from the official SVG)
F_TEXT = (INTER, "Medium")           # body copy
F_TEXTB = (INTER, "SemiBold")
BRAND = os.path.join(ROOT, "textures", "brand")                   # rasterised official SVGs (tools/rasterize_logos.js)
F_PLATE = FONTS + "arialbd.ttf"
F_SCRIPT = FONTS + "segoesc.ttf"     # "California" script

# ---- Colours sampled from the reference -------------------------------
PURPLE = (91, 48, 230)      # #5B30E6
BLACK = (38, 40, 47)        # #26282F  livery charcoal
WHITE = (242, 242, 244)
SILL = (52, 55, 61)         # #34373D  lower cladding / bumpers
ARCH = (40, 42, 47)
UNDER = (26, 26, 28)
LIME = (124, 255, 0)        # #7CFF00 (only for previews)
TEXT_W = (246, 244, 255)

ATLAS = 4096
atlas = Image.new("RGB", (ATLAS, ATLAS), UNDER)

# ---- optional layout profile: python gen_textures.py --profile crafter  (tools/profiles/crafter.json)
import sys
PROFILE_NAME = sys.argv[sys.argv.index("--profile") + 1] if "--profile" in sys.argv else None
PROFILE = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles", PROFILE_NAME + ".json"))) if PROFILE_NAME else {}

# ---- geometry constants shared with build_van.py ------------------------
L = 5.59
Y_FRONT, Y_REAR = -L / 2, L / 2          # -2.795 .. 2.795
Y_AXLE_F, Y_AXLE_R = -1.875, 1.595
WHEEL_R = 0.355
Y_B = -0.45          # B-pillar
Z_BELT = 1.30        # window sill line
Z_SILL = 0.56        # top of the dark lower cladding
Z_ROOF = 2.12
Y_PURPLE_ROOF = 0.55    # where the purple diagonal meets the roof (45 deg, leaning back)
WHITE_RUN = 0.90        # horizontal run of the white/black diagonal from the belt line to the ground (55 deg)
PILLAR_DX = 0.06        # black above the belt starts this far ahead of the diagonal start (covers the door's rear window post)
DIAG_TOP_Z = None       # z where the cab-door diagonal starts at the door front (default: the belt line)
DIAG = None             # [y at belt, y at sill]: cab-door diagonal (black frame over the whole door, white triangle at the lower front)
LOGO_Y = 2.12           # centre of the rotated side logo
LOGO_Z = 1.30
LOGO_H = 0.30           # symbol height of the rotated side logo
REAR = dict(logo=(0.20, 0.30, 1.72), copy=(-0.09, 1.50, 0.085), qr=(0.38, 0.97, 0.30), learn=(0.04, 0.95, 0.105))
FREE_SIZE = 0.205
GFX = 1.0               # scale of the whole FREE COOKIES / QR block
SIDE_R_LINES = None     # passenger-side claim lines instead of FREE COOKIES, e.g. ["Auth as easy as", "<SignIn/>", "clerk.com"]
BLOCK_Z = 1.86          # top of "FREE"
QR_Z = 0.89             # centre of the QR / Learn more line
BLOCK_DY = 0.0
QR_DX = 0.0
PASS_DY = 0.06        # passenger side: block sits further back so 'Learn more' clears the white diagonal
STEP = (-1.50, 0.08)    # white step strip under the cab door (None to skip)
ARCH_R = 0.50           # painted arch flare radius (0 to skip)
HOOD_Y = -2.10          # hood / windscreen boundary in the top view
VENTS = True
HOOD_LOGO_Y = -2.50
HOOD_LOGO_H = 0.12
ROOF_LOGO = None        # (y centre, symbol height) of the white lockup on the roof; None to skip
FRONT_SILL = 0.68
REAR_SILL = 0.72
EXT_SIDE = [-2.9, 2.9, 0.0, 2.32]
EXT_FRONT = [-1.16, 1.16, 0.0, 2.32]
EXT_TOP = [-1.16, 1.16, -2.9, 2.9]
globals().update(PROFILE)
ROOF_EDGE = PROFILE.get("ROOF_EDGE", 2.03)
Y_FRONT, Y_REAR = -L / 2, L / 2
SIDE_W = PROFILE.get("SIDE_W", 3000)
SIDE_H = int(round(SIDE_W * (EXT_SIDE[3] - EXT_SIDE[2]) / (EXT_SIDE[1] - EXT_SIDE[0])))
FRONT_W = 1200
FRONT_H = int(round(FRONT_W * (EXT_FRONT[3] - EXT_FRONT[2]) / (EXT_FRONT[1] - EXT_FRONT[0])))
TOP_W = 960
TOP_H = int(round(TOP_W * (EXT_TOP[3] - EXT_TOP[2]) / (EXT_TOP[1] - EXT_TOP[0])))
ROOF_TOP = EXT_SIDE[3]          # top of the painted area in metres
ROOF_Z = PROFILE.get("ROOF_Z", ROOF_TOP)   # real roof edge: the side diagonal reaches Y_PURPLE_ROOF here, matching the roof panel
def diag_y(z):
    """y of the purple diagonal (45 deg, leaning back) at height z"""
    return Y_PURPLE_ROOF + (ROOF_Z - z)
assert max(SIDE_W, 2 * FRONT_W) <= 3040, "atlas layout overflow"

def fnt(path, px):
    if isinstance(path, tuple):
        f = ImageFont.truetype(path[0], max(1, int(px)))
        try:
            f.set_variation_by_name(path[1])
        except Exception:
            try:
                f.set_variation_by_name(path[1].encode())
            except Exception:
                pass
        return f
    return ImageFont.truetype(path, max(1, int(px)))


MASKS = {}   # panel name -> relief mask (filled by draw_* through View.done)


class View:
    """Maps a 2-D vehicle coordinate pair (a, b) to pixels of an image."""

    def __init__(self, w, h, a0, a1, b0, b1, flip_a=False):
        self.w, self.h = w, h
        self.a0, self.a1, self.b0, self.b1 = a0, a1, b0, b1
        self.flip_a = flip_a
        self.img = Image.new("RGB", (w, h), WHITE)
        self.d = ImageDraw.Draw(self.img)
        self.s = w / (a1 - a0)  # px per metre
        # relief mask for the printable model: every pasted graphic / text is white here, base paint is black
        self.mask = Image.new("L", (w, h), 0)
        self.dm = ImageDraw.Draw(self.mask)

    def p(self, a, b):
        t = (a - self.a0) / (self.a1 - self.a0)
        if self.flip_a:
            t = 1 - t
        u = t * self.w
        v = (self.b1 - b) / (self.b1 - self.b0) * self.h
        return (u, v)

    def poly(self, pts, fill):
        self.d.polygon([self.p(a, b) for a, b in pts], fill=fill)

    def rect(self, a0, b0, a1, b1, fill, radius=0):
        p0, p1 = self.p(a0, b1), self.p(a1, b0)
        x0, y0 = min(p0[0], p1[0]), min(p0[1], p1[1])
        x1, y1 = max(p0[0], p1[0]), max(p0[1], p1[1])
        if radius:
            self.d.rounded_rectangle([x0, y0, x1, y1], radius=radius * self.s, fill=fill)
        else:
            self.d.rectangle([x0, y0, x1, y1], fill=fill)

    def ellipse(self, a, b, ra, rb, fill):
        c = self.p(a, b)
        self.d.ellipse([c[0] - ra * self.s, c[1] - rb * self.s, c[0] + ra * self.s, c[1] + rb * self.s], fill=fill)

    def paste(self, layer, a, b, angle=0.0):
        """Paste an RGBA layer centred on vehicle point (a,b), rotated by angle (deg, CCW on screen)."""
        if angle:
            layer = layer.rotate(angle, resample=Image.BICUBIC, expand=True)
        c = self.p(a, b)
        pos = (int(c[0] - layer.width / 2), int(c[1] - layer.height / 2))
        self.img.paste(layer, pos, layer)
        self.mask.paste(255, pos, layer.getchannel("A"))

    def text(self, a, b, s, font_path, size_m, fill, anchor="la", angle=0.0):
        """Draw text with its anchor at vehicle (a,b). size_m is the em size in metres."""
        f = fnt(font_path, size_m * self.s)
        if angle == 0:
            self.d.text(self.p(a, b), s, font=f, fill=fill, anchor=anchor)
            self.dm.text(self.p(a, b), s, font=f, fill=255, anchor=anchor)
        else:
            tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
            bb = tmp.textbbox((0, 0), s, font=f)
            layer = Image.new("RGBA", (bb[2] - bb[0] + 8, bb[3] - bb[1] + 8), (0, 0, 0, 0))
            ImageDraw.Draw(layer).text((-bb[0] + 4, -bb[1] + 4), s, font=f, fill=fill)
            self.paste(layer, a, b, angle)

    def done(self, name):
        MASKS[name] = self.mask
        return self.img


# ---- Clerk logomark + wordmark ------------------------------------------

def logo_block(height_px, color):
    """Official Clerk lockup (symbol + wordmark) from clerk.com/brand-assets, rasterised to PNG.
    height_px = height of the symbol. color: TEXT_W -> all-white version, otherwise purple-text version."""
    name = "logo_white" if color == TEXT_W else "logo_purple"
    im = Image.open(os.path.join(BRAND, name + ".png")).convert("RGBA")
    h = max(2, int(height_px))
    w = int(im.width * h / im.height)
    return im.resize((w, h), Image.LANCZOS)


def logomark(size_px, color):
    name = "symbol_white" if color == TEXT_W else "symbol_primary"
    im = Image.open(os.path.join(BRAND, name + ".png")).convert("RGBA")
    S = max(2, int(size_px))
    return im.resize((S, S), Image.LANCZOS)


def qr_layer(size_px, data="https://clerk.com", color=(255, 255, 255)):
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=1, box_size=10)
    q.add_data(data)
    q.make(fit=True)
    im = q.make_image(fill_color=color, back_color=(0, 0, 0)).convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if (r, g, b) == (0, 0, 0):
                px[x, y] = (0, 0, 0, 0)
    return im.resize((int(size_px), int(size_px)), Image.NEAREST)


def ford_oval(w, h):
    im = Image.new("RGBA", (w * 4, h * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, w * 4 - 1, h * 4 - 1], fill=(205, 208, 214))
    m = int(h * 4 * 0.07)
    d.ellipse([m, m, w * 4 - 1 - m, h * 4 - 1 - m], fill=(20, 60, 150))
    m2 = int(h * 4 * 0.16)
    d.ellipse([m2, m2, w * 4 - 1 - m2, h * 4 - 1 - m2], outline=(190, 200, 220), width=int(h * 4 * 0.03))
    f = fnt(FONTS + "timesbi.ttf", h * 4 * 0.62)
    d.text((w * 2, h * 2 + h * 0.12), "Ford", font=f, fill=(235, 240, 250), anchor="mm")
    return im.resize((w, h), Image.LANCZOS)


# ---- SIDE panels ---------------------------------------------------------

def draw_side(nose_left):
    """Side livery. Drawn in SCREEN space s (left->right on the image):
    s = y for the driver side (nose on the left), s = -y for the passenger
    side (nose on the right). The physical layout is therefore mirrored
    about the vehicle's centre plane, exactly as in the references."""
    V = View(SIDE_W, SIDE_H, EXT_SIDE[0], EXT_SIDE[1], EXT_SIDE[2], EXT_SIDE[3])
    m = 1.0 if nose_left else -1.0
    S = lambda y: m * y
    big = 3.5
    # black band: B-pillar above belt, 45 deg diagonal leaning back below it
    if DIAG:
        yb, ys = DIAG
        zt = DIAG_TOP_Z or Z_BELT                                  # where the diagonal leaves the door's front edge
        y0 = yb + (ys - yb) * zt / (zt - Z_SILL)                   # boundary extended down to z = 0
        V.poly([(S(yb), big), (S(yb), zt), (S(y0), 0.0), (S(big), 0.0), (S(big), big)], BLACK)
    else:
        V.poly([(S(Y_B - PILLAR_DX), big), (S(Y_B - PILLAR_DX), Z_BELT), (S(Y_B), Z_BELT),
                (S(Y_B + WHITE_RUN), 0.0), (S(big), 0.0), (S(big), big)], BLACK)
    # purple band: 45 deg from the roof point
    V.poly([(S(diag_y(ROOF_TOP + 0.5)), ROOF_TOP + 0.5), (S(diag_y(0.0)), 0.0), (S(big), 0.0), (S(big), ROOF_TOP + 0.5)], PURPLE)
    # roof edge strip above the white cab is black (roof / drip rail)
    V.poly([(S(-big), ROOF_EDGE), (S(diag_y(ROOF_EDGE)), ROOF_EDGE), (S(diag_y(ROOF_TOP + 0.5)), ROOF_TOP + 0.5), (S(-big), ROOF_TOP + 0.5)], BLACK)
    # lower cladding
    V.rect(-big, 0.0, big, Z_SILL, SILL)
    V.rect(S(-big), 0.0, S(-2.55), 0.68, SILL)   # front bumper corner
    V.rect(S(2.52), 0.0, S(big), 0.74, SILL)     # rear bumper corner
    # wheel arch flares
    for ya in ((Y_AXLE_F, Y_AXLE_R) if ARCH_R else ()):
        V.ellipse(S(ya), WHEEL_R, ARCH_R, ARCH_R, ARCH)
    V.rect(-big, 0.0, big, 0.30, UNDER)  # under-sill shadow line
    # white step strip under the cab door
    if STEP:
        V.poly([(S(STEP[0]), 0.50), (S(STEP[1]), 0.50), (S(STEP[1] - 0.17), 0.40), (S(STEP[0]), 0.40)], WHITE)

    # ---- FREE COOKIES block (screen-left edge s0, same physical y-range on both sides)
    if DIAG:
        yb, ys = DIAG
        zt = DIAG_TOP_Z or Z_BELT
        y_edge = yb + (ys - yb) * (zt - 0.69) / (zt - Z_SILL)
    else:
        y_edge = Y_B + (Z_BELT - 0.69) * WHITE_RUN / Z_BELT
    y0, w = y_edge + BLOCK_DY + (0 if nose_left else PASS_DY), 1.14   # block starts where the white diagonal meets the QR bottom
    s0 = y0 if nose_left else -(y0 + w)
    g = GFX                                   # overall scale of the side block (1 = low-roof captures)
    zt = BLOCK_Z                              # top of "FREE"
    if (not nose_left) and SIDE_R_LINES:
        # passenger side: three-line claim (as on the die-cast reference), same block height as FREE COOKIES
        ls = 0.62 * FREE_SIZE * g
        for i, (line, font) in enumerate(zip(SIDE_R_LINES, (F_TEXTB, F_BOLD, F_TEXTB))):
            V.text(s0, zt - i * 1.12 * ls, line, font, ls, TEXT_W, anchor="lt")
    else:
        V.text(s0, zt, "FREE", F_BOLD, FREE_SIZE * g, TEXT_W, anchor="lt")
        V.text(s0, zt - 0.88 * FREE_SIZE * g, "COOKIES", F_BOLD, FREE_SIZE * g, TEXT_W, anchor="lt")
        V.text(s0 + 0.015, zt - 1.85 * FREE_SIZE * g, "* up to 10,000 mau", F_TEXT, 0.08 * g, TEXT_W, anchor="lt")
    qs = 0.40 * g
    qr = qr_layer(qs * V.s)
    qdx = QR_DX if nose_left else -QR_DX      # push the QR/Learn-more group away from the white diagonal on both sides
    zq = QR_Z
    V.paste(qr, s0 + qs / 2 + qdx, zq)
    V.text(s0 + qs + 0.09 * g + qdx, zq, "← Learn more", F_TEXTB, 0.115 * g, TEXT_W, anchor="lm")

    # ---- rotated clerk logo in the purple band (baseline along the diagonal)
    blk = logo_block(LOGO_H * V.s, TEXT_W)
    V.paste(blk, S(LOGO_Y), LOGO_Z, angle=(-45 if nose_left else 45))
    return V.done("side_left" if nose_left else "side_right")


# ---- FRONT panel --------------------------------------------------------

def draw_front():
    V = View(FRONT_W, FRONT_H, *EXT_FRONT)   # u=0 at -X (passenger) => screen left
    V.rect(-2, ROOF_EDGE, 2, ROOF_TOP + 0.5, BLACK)   # roof edge
    V.rect(-2, 0.0, 2, FRONT_SILL, SILL)    # lower bumper
    V.rect(-2, 0.0, 2, 0.30, UNDER)
    # lower intake slot + fog recesses
    V.rect(-0.55, 0.41, 0.55, 0.47, UNDER, radius=0.02)
    for sx in (-1, 1):
        V.rect(sx * 0.95 - 0.13, 0.50, sx * 0.95 + 0.13, 0.58, UNDER, radius=0.02)
    # hood vents near the windscreen base are on the top panel.
    return V.done("front")


# ---- REAR panel ---------------------------------------------------------

def draw_rear():
    V = View(FRONT_W, FRONT_H, *EXT_FRONT, flip_a=True)  # driver side on screen left
    V.rect(-2, 0.0, 2, ROOF_TOP + 0.5, PURPLE)
    V.rect(-2, 0.0, 2, REAR_SILL, SILL)
    V.rect(-2, 0.0, 2, 0.30, UNDER)
    # bumper step strip and reflectors
    V.rect(-1.1, 0.33, 1.1, 0.42, (44, 46, 52))
    for sx in (-1, 1):
        V.rect(sx * 0.75 - 0.06, 0.26, sx * 0.75 + 0.06, 0.31, (200, 30, 40))
    # logo block (icon + wordmark) upper area, slightly to the driver side
    lh, lx, lz = REAR["logo"]
    blk = logo_block(lh * V.s, TEXT_W)
    V.paste(blk, lx, lz)
    # copy on the passenger-side door
    cx, cz, cs = REAR["copy"]
    V.text(cx, cz, "We built <SignIn/>", F_TEXTB, cs, TEXT_W, anchor="lt")
    V.text(cx, cz - 1.25 * cs, "so you don\u2019t have to", F_TEXTB, cs, TEXT_W, anchor="lt")
    V.text(cx, cz - 2.5 * cs, "clerk.com", F_TEXTB, cs, TEXT_W, anchor="lt")
    # QR on the driver door, Learn more on the passenger door
    qx, qz, qs = REAR["qr"]
    qr = qr_layer(qs * V.s)
    V.paste(qr, qx, qz)
    ex, ez, es = REAR["learn"]
    V.text(ex, ez, "Learn more \u2192", F_TEXTB, es, TEXT_W, anchor="lm")
    # hinges (dark marks at the outer edges)
    for sx in (-1, 1):
        for z in (0.95, 1.55):
            V.rect(sx * 0.985 - 0.03, z - 0.07, sx * 0.985 + 0.03, z + 0.07, (60, 50, 110), radius=0.01)
    return V.done("rear")


# ---- TOP panel ----------------------------------------------------------

def draw_top():
    V = View(TOP_W, TOP_H, EXT_TOP[0], EXT_TOP[1], -EXT_TOP[3], -EXT_TOP[2], flip_a=True)  # screen-left = +X (driver); b = -y, nose at the TOP
    # View maps b1 (=2.9, rear) to the top row, we want the nose at top: invert b by drawing with -y
    def P(x, y):
        return (x, -y)
    # roof: black from windscreen top back to the purple line, purple behind it
    V.rect(-2, -3, 2, 3, BLACK)
    V.poly([P(-2, Y_PURPLE_ROOF), P(2, Y_PURPLE_ROOF), P(2, 4), P(-2, 4)], PURPLE)
    # hood white (in front of the windscreen base, y < -2.10)
    V.poly([P(-2, -4), P(2, -4), P(2, HOOD_Y), P(-2, HOOD_Y)], WHITE)
    # hood vents
    for sx in ((-1, 1) if VENTS else ()):
        V.poly([P(sx * 0.30, HOOD_Y - 0.12), P(sx * 0.62, HOOD_Y - 0.12), P(sx * 0.62, HOOD_Y - 0.06), P(sx * 0.30, HOOD_Y - 0.06)], UNDER)
    # purple clerk logo on the hood, readable from the front (rotated 180 deg)
    blk = logo_block(HOOD_LOGO_H * V.s, PURPLE)
    V.paste(blk, 0.0, -HOOD_LOGO_Y, angle=180)
    # white wordmark on the purple roof, reading from the driver's side (screen-left = +X)
    if ROOF_LOGO:
        y_c, h = ROOF_LOGO
        blk = logo_block(h * V.s, TEXT_W)
        V.paste(blk, 0.0, -y_c, angle=90)
    return V.done("top")


# ---- small parts --------------------------------------------------------

def draw_wheel(S=460):
    im = Image.new("RGB", (S * 2, S * 2), (28, 28, 30))
    d = ImageDraw.Draw(im)
    c = S
    R = S * 0.98
    d.ellipse([c - R, c - R, c + R, c + R], fill=(150, 152, 156))          # rim lip
    R2 = S * 0.88
    d.ellipse([c - R2, c - R2, c + R2, c + R2], fill=(118, 120, 125))      # dish
    # 8 slots
    for i in range(8):
        a = math.radians(i * 45 + 22.5)
        rr = S * 0.70
        x, y = c + math.cos(a) * rr, c + math.sin(a) * rr
        slot = Image.new("RGBA", (int(S * 0.30), int(S * 0.16)), (0, 0, 0, 0))
        ImageDraw.Draw(slot).rounded_rectangle([0, 0, slot.width - 1, slot.height - 1], radius=slot.height // 2, fill=(18, 18, 20))
        slot = slot.rotate(-(i * 45 + 22.5) - 90, expand=True, resample=Image.BICUBIC)
        im.paste(slot, (int(x - slot.width / 2), int(y - slot.height / 2)), slot)
    R3 = S * 0.50
    d.ellipse([c - R3, c - R3, c + R3, c + R3], fill=(172, 174, 178))      # hub cap
    R4 = S * 0.42
    d.ellipse([c - R4, c - R4, c + R4, c + R4], fill=(120, 121, 125))
    for i in range(5):                                                     # lug nuts
        a = math.radians(i * 72 - 90)
        x, y = c + math.cos(a) * S * 0.30, c + math.sin(a) * S * 0.30
        d.ellipse([x - S * 0.05, y - S * 0.05, x + S * 0.05, y + S * 0.05], fill=(150, 152, 156))
    d.ellipse([c - S * 0.12, c - S * 0.12, c + S * 0.12, c + S * 0.12], fill=(40, 40, 42))
    return im.resize((S, S), Image.LANCZOS)


def draw_plate(W=520, H=260):
    im = Image.new("RGB", (W * 2, H * 2), (248, 248, 246))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, W * 2 - 1, H * 2 - 1], radius=24, outline=(170, 170, 170), width=6)
    f = fnt(F_SCRIPT, H * 2 * 0.22)
    d.text((W, H * 2 * 0.17), "California", font=f, fill=(190, 30, 40), anchor="mm")
    f2 = fnt(F_PLATE, H * 2 * 0.52)
    d.text((W, H * 2 * 0.60), "40312P2", font=f2, fill=(22, 36, 96), anchor="mm")
    return im.resize((W, H), Image.LANCZOS)


def draw_plate_eu(W=1040, H=220):
    im = Image.new("RGB", (W * 2, H * 2), (248, 248, 246))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, W * 2 - 1, H * 2 - 1], radius=24, outline=(170, 170, 170), width=6)
    f = fnt(F_SCRIPT, H * 2 * 0.30)
    d.text((W * 0.22, H), "California", font=f, fill=(190, 30, 40), anchor="mm")
    f2 = fnt(F_PLATE, H * 2 * 0.80)
    d.text((W * 1.22, H * 1.05), "40312P2", font=f2, fill=(22, 36, 96), anchor="mm")
    return im.resize((W, H), Image.LANCZOS)


def draw_headlight(W=600, H=300):
    im = Image.new("RGB", (W * 2, H * 2), (18, 18, 20))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([4, 4, W * 2 - 5, H * 2 - 5], radius=100, fill=(196, 200, 208))     # silver housing
    d.rounded_rectangle([34, 34, W * 2 - 35, H * 2 - 35], radius=86, fill=(168, 172, 180))  # reflector area
    for cx in (W * 0.62, W * 1.36):
        r = H * 0.62
        d.ellipse([cx - r, H - r, cx + r, H + r], fill=(120, 124, 132))
        r2 = H * 0.50
        d.ellipse([cx - r2, H - r2, cx + r2, H + r2], fill=(205, 208, 216))
        r3 = H * 0.27
        d.ellipse([cx - r3, H - r3, cx + r3, H + r3], fill=(96, 100, 110))
        r4 = H * 0.11
        d.ellipse([cx - r4, H - r4, cx + r4, H + r4], fill=(245, 246, 250))
    d.rounded_rectangle([40, H * 1.55, W * 0.30, H * 2 - 40], radius=26, fill=(236, 120, 20))  # amber turn signal
    return im.resize((W, H), Image.LANCZOS)


def draw_taillight(W=150, H=450):
    im = Image.new("RGB", (W * 2, H * 2), (190, 20, 30))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, W * 2 - 1, H * 2 - 1], radius=30, fill=(200, 24, 34))
    d.rectangle([14, H * 2 * 0.40, W * 2 - 15, H * 2 * 0.74], fill=(225, 226, 230))   # reverse lamp
    d.rectangle([20, H * 2 * 0.47, W * 2 - 21, H * 2 * 0.53], fill=(236, 120, 20))     # amber bar
    for y in range(0, int(H * 2 * 0.38), 40):                                           # ribbing
        d.rectangle([10, y, W * 2 - 11, y + 10], fill=(160, 18, 28))
    for y in range(int(H * 2 * 0.78), H * 2, 40):
        d.rectangle([10, y, W * 2 - 11, y + 10], fill=(160, 18, 28))
    return im.resize((W, H), Image.LANCZOS)


# ---- assemble -----------------------------------------------------------
side_l = draw_side(nose_left=True)
side_r = draw_side(nose_left=False)
front = draw_front()
rear = draw_rear()
top = draw_top()
wheel = draw_wheel()
plate = draw_plate()
ford = ford_oval(400, 160)
head = draw_headlight()
tail = draw_taillight()

FY = 2 * SIDE_H
PX, PY = 3050, TOP_H + 20       # small-parts block under the top panel
LAYOUT = {
    "side_left": (0, 0, SIDE_W, SIDE_H),
    "side_right": (0, SIDE_H, SIDE_W, 2 * SIDE_H),
    "front": (0, FY, FRONT_W, FY + FRONT_H),
    "rear": (FRONT_W, FY, 2 * FRONT_W, FY + FRONT_H),
    "top": (3050, 0, 3050 + TOP_W, TOP_H),
    "wheel": (PX, PY, PX + 460, PY + 460),
    "taillight": (PX + 480, PY, PX + 630, PY + 450),
    "bottom": (PX + 650, PY, PX + 850, PY + 200),
    "plate": (PX, PY + 480, PX + 520, PY + 740),
    "ford": (PX, PY + 760, PX + 400, PY + 920),
    "headlight": (PX, PY + 940, PX + 600, PY + 1240),
    "plate_eu": (PX, PY + 1260, PX + 600, PY + 1387),
}
assert PY + 1387 <= ATLAS and 2 * SIDE_H + FRONT_H <= ATLAS, "atlas layout overflow"
atlas.paste(side_l, LAYOUT["side_left"][:2])
atlas.paste(side_r, LAYOUT["side_right"][:2])
atlas.paste(front, LAYOUT["front"][:2])
atlas.paste(rear, LAYOUT["rear"][:2])
atlas.paste(top, LAYOUT["top"][:2])
ImageDraw.Draw(atlas).rectangle(LAYOUT["bottom"], fill=UNDER)
atlas.paste(wheel, LAYOUT["wheel"][:2])
atlas.paste(plate, LAYOUT["plate"][:2])
atlas.paste(ford.convert("RGB"), LAYOUT["ford"][:2], ford)
atlas.paste(head, LAYOUT["headlight"][:2])
atlas.paste(tail, LAYOUT["taillight"][:2])
atlas.paste(draw_plate_eu().resize((600, 127), Image.LANCZOS), LAYOUT["plate_eu"][:2])

SUFFIX = f"_{PROFILE_NAME}" if PROFILE_NAME else ""
os.makedirs(os.path.join(OUT, "print_mask"), exist_ok=True)
atlas.save(os.path.join(OUT, f"clerk_van_atlas{SUFFIX}.png"), optimize=True)
for name, im in [("side_left", side_l), ("side_right", side_r), ("front", front), ("rear", rear), ("top", top)]:
    im.save(os.path.join(OUT, f"panel_{name}{SUFFIX}.png"), optimize=True)
    MASKS[name].save(os.path.join(OUT, "print_mask", f"{name}{SUFFIX}.png"), optimize=True)   # relief mask for build_print_van.py
with open(os.path.join(OUT, f"atlas_layout{SUFFIX}.json"), "w") as f:
    json.dump({"size": ATLAS, "regions": LAYOUT,
               "extents": {"side": EXT_SIDE, "front": EXT_FRONT, "rear": EXT_FRONT, "top": EXT_TOP}}, f, indent=2)
print("atlas written", os.path.join(OUT, f"clerk_van_atlas{SUFFIX}.png"))

# every generation checks that the QR codes still decode (tools/verify_qr.py; needs opencv-python-headless)
if PROFILE_NAME:
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from verify_qr import verify
        qr_ok, qr_res = verify(PROFILE_NAME)
        print("QR check:", qr_res, "OK" if qr_ok else "FAILED")
        if not qr_ok:
            sys.exit("QR verification failed: " + str(qr_res))
    except ImportError:
        print("QR check skipped: opencv not installed (pip install opencv-python-headless)")
