"""
Builds the Clerk Van (Ford Transit, low roof, regular wheelbase) procedurally
in Blender and exports:
  export/clerk_van.glb      (textures embedded, lights, named pivots, NLA clips)
  export/clerk_van.blend

Run:  blender --background --python tools/build_van.py -- <project root>

Vehicle frame (Blender, Z up): front = -Y, rear = +Y, driver/left = +X,
passenger/right = -X. Ground is z = 0. Dimensions are metres, taken from the
2015+ Ford Transit 130" WB low-roof cargo van (5.59 L x 2.03 W x 2.12 H,
3.30 WB, 235/65R16 tyres).

Node names you can drive at runtime (Three.js / Godot / Blender):
  Door_FL, Door_FR       rotate about local Z (hinge at the front edge) ; FL opens with -Z, FR with +Z
  Door_Slide             translate: -X 0.10 then +Y ~1.05 (passenger side sliding door)
  Door_RL, Door_RR       rotate about local Z (hinge at the outer edge) ; RL opens -Z, RR +Z
  Wheel_FL/FR/RL/RR      rotate about local X (positive = rolling forward)
  Steer_L / Steer_R      rotate about local Z for steering (parents of the front wheels)
  Light_HeadL/R          spot lights, Light_TailL/R point lights (KHR_lights_punctual)
  Headlight_L/R, Taillight_L/R, BrakeLight  meshes with emissive materials
"""
import bpy, bmesh, math, os, sys, json
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = os.path.abspath(argv[0]) if argv else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(ROOT, "textures", "clerk_van_atlas.png")
LAYOUT = json.load(open(os.path.join(ROOT, "textures", "atlas_layout.json")))
EXPORT = os.path.join(ROOT, "export")
os.makedirs(EXPORT, exist_ok=True)

# ---------------------------------------------------------------- constants
L, W, H = 5.59, 2.03, 2.12
YF, YR = -L / 2, L / 2
HW = W / 2
Y_AXLE_F, Y_AXLE_R = -1.875, 1.595   # matched to the reference captures (0.92 m front overhang)
WHEEL_R, TIRE_W, TRACK = 0.355, 0.235, 1.73
Y_B = -0.45                 # B-pillar
Y_DF = -1.40                # front edge of the cab doors
Z_DOOR0, Z_DOOR1 = 0.62, 1.98
WALL = 0.06
GAP = 0.008
ATLAS = LAYOUT["size"]
R = LAYOUT["regions"]

# ---------------------------------------------------------------- helpers

def clean_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for col in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights, bpy.data.actions):
        for x in list(col):
            col.remove(x)


def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def set_active(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply_all(obj):
    set_active(obj)
    for m in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def mesh_from_bm(name, bm, mat=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    if mat is not None:
        me.materials.append(mat)
    return link(ob)


def box(name, x0, x1, y0, y1, z0, z1, mat=None):
    x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1)); z0, z1 = sorted((z0, z1))
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(x1 - x0, y1 - y0, z1 - z0), verts=bm.verts)
    bmesh.ops.translate(bm, vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), verts=bm.verts)
    return mesh_from_bm(name, bm, mat)


def rounded_box(name, sx, sy, sz, r, matrix, mat=None, seg=6):
    """Rounded rectangle (sx by sy, corner radius r) in local XY, extruded sz along local Z, then transformed."""
    bm = bmesh.new()
    pts = []
    cx, cy = sx / 2 - r, sy / 2 - r
    for (ox, oy, a0) in ((cx, cy, 0), (-cx, cy, 90), (-cx, -cy, 180), (cx, -cy, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((ox + r * math.cos(a), oy + r * math.sin(a), -sz / 2))
    verts = [bm.verts.new(p) for p in pts]
    f = bm.faces.new(verts)
    res = bmesh.ops.extrude_face_region(bm, geom=[f])
    vs = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, sz), verts=vs)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.transform(matrix)
    return mesh_from_bm(name, bm, mat)


def prism_yz(name, pts, x0, x1, mat=None):
    """Polygon given in (y, z), extruded between x0 and x1."""
    bm = bmesh.new()
    verts = [bm.verts.new((x0, y, z)) for y, z in pts]
    f = bm.faces.new(verts)
    res = bmesh.ops.extrude_face_region(bm, geom=[f])
    vs = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(x1 - x0, 0, 0), verts=vs)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_from_bm(name, bm, mat)


def prism_xy(name, pts, z0, z1, mat=None):
    bm = bmesh.new()
    verts = [bm.verts.new((x, y, z0)) for x, y in pts]
    f = bm.faces.new(verts)
    res = bmesh.ops.extrude_face_region(bm, geom=[f])
    vs = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, z1 - z0), verts=vs)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_from_bm(name, bm, mat)


def prism_xz(name, pts, y0, y1, mat=None):
    """Polygon given in (x, z), extruded between y0 and y1."""
    bm = bmesh.new()
    verts = [bm.verts.new((x, y0, z)) for x, z in pts]
    f = bm.faces.new(verts)
    res = bmesh.ops.extrude_face_region(bm, geom=[f])
    vs = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, y1 - y0, 0), verts=vs)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_from_bm(name, bm, mat)


def offset_poly(pts, k):
    """Scale a 2-D polygon about its centroid by factor k."""
    cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
    return [(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in pts]


def cylinder(name, r, depth, axis="X", segs=48, mat=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r, radius2=r, depth=depth)
    if axis == "X":
        bm.transform(Matrix.Rotation(math.radians(90), 4, "Y"))
    elif axis == "Y":
        bm.transform(Matrix.Rotation(math.radians(90), 4, "X"))
    return mesh_from_bm(name, bm, mat)


def boolean(target, cutter, op, keep_cutter=False):
    mod = target.modifiers.new("bool", "BOOLEAN")
    mod.operation = op
    mod.object = cutter
    mod.solver = "EXACT"
    try:
        mod.material_mode = "TRANSFER"
    except Exception:
        pass
    try:
        mod.use_hole_tolerant = True
    except Exception:
        pass
    set_active(target)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    if not keep_cutter:
        bpy.data.objects.remove(cutter, do_unlink=True)


def bevel(obj, width, segs=4, angle=None):
    m = obj.modifiers.new("bevel", "BEVEL")
    m.width = width
    m.segments = segs
    m.limit_method = "ANGLE" if angle else "NONE"
    if angle:
        m.angle_limit = math.radians(angle)
    m.use_clamp_overlap = True
    apply_all(obj)


def smooth(obj, angle=35):
    """Smooth faces, mark edges sharper than `angle` as sharp (Blender 4.1+ semantics)."""
    me = obj.data
    bm = bmesh.new(); bm.from_mesh(me)
    rad = math.radians(angle)
    for e in bm.edges:
        if len(e.link_faces) == 2:
            a = e.calc_face_angle(None)
            e.smooth = not (a is not None and a > rad)
        else:
            e.smooth = False
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(me); bm.free()
    me.update()


def set_origin(obj, pivot):
    pv = Vector(pivot)
    obj.data.transform(Matrix.Translation(-pv))
    obj.location = pv


def parent(child, par):
    bpy.context.view_layer.update()
    child.parent = par
    child.matrix_parent_inverse = par.matrix_world.inverted()


# ---------------------------------------------------------------- materials

def new_mat(name, color=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, image=None, alpha=1.0, emissive=None, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if coat:
        try:
            bsdf.inputs["Coat Weight"].default_value = coat
            bsdf.inputs["Coat Roughness"].default_value = 0.08
        except KeyError:
            pass
    if image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.location = (-400, 300)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            m.blend_method = "BLEND"
        m.show_transparent_back = False
    if emissive is not None:
        bsdf.inputs["Emission Color"].default_value = (*emissive, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 0.0
    return m


def uv_rect(region):
    x0, y0, x1, y1 = R[region]
    return (x0 / ATLAS, 1 - y1 / ATLAS, x1 / ATLAS, 1 - y0 / ATLAS)  # u0, v0, u1, v1 (v up)


def project_uv(obj, mat_index=0):
    """Box-project every face that uses material slot `mat_index` into the atlas."""
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = me.uv_layers.active.data
    extents = LAYOUT["extents"]
    for poly in me.polygons:
        if poly.material_index != mat_index:
            continue
        n = poly.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        for li in poly.loop_indices:
            p = me.vertices[me.loops[li].vertex_index].co
            if ax >= ay and ax >= az:
                a0, a1, b0, b1 = extents["side"]
                v = (p.z - b0) / (b1 - b0)
                if n.x > 0:
                    u = (p.y - a0) / (a1 - a0); reg = "side_left"
                else:
                    u = (a1 - p.y) / (a1 - a0); reg = "side_right"
            elif ay >= az:
                a0, a1, b0, b1 = extents["front"]
                v = (p.z - b0) / (b1 - b0)
                if n.y < 0:
                    u = (p.x - a0) / (a1 - a0); reg = "front"
                else:
                    u = (a1 - p.x) / (a1 - a0); reg = "rear"
            else:
                if n.z > 0:
                    a0, a1, b0, b1 = extents["top"]
                    u = (a1 - p.x) / (a1 - a0)
                    v = (b1 - p.y) / (b1 - b0); reg = "top"
                else:
                    u, v, reg = 0.5, 0.5, "bottom"
            u0, v0, u1, v1 = uv_rect(reg)
            uv[li].uv = (u0 + u * (u1 - u0), v0 + v * (v1 - v0))


def map_planar(obj, region, axis, bounds, flip_u=False, only_normal=None):
    """Map faces (optionally only those whose normal points along `only_normal`) with a planar
    projection into an atlas region. axis: 'x' -> (u from y, v from z), 'y' -> (u from x, v from z), 'z' -> (u from x, v from y)
    bounds = (a0, a1, b0, b1)."""
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = me.uv_layers.active.data
    u0, v0, u1, v1 = uv_rect(region)
    a0, a1, b0, b1 = bounds
    for poly in me.polygons:
        if only_normal is not None and poly.normal.dot(Vector(only_normal)) < 0.5:
            continue
        for li in poly.loop_indices:
            p = me.vertices[me.loops[li].vertex_index].co
            if axis == "x":
                a, b = p.y, p.z
            elif axis == "y":
                a, b = p.x, p.z
            else:
                a, b = p.x, p.y
            u = (a - a0) / (a1 - a0)
            if flip_u:
                u = 1 - u
            v = (b - b0) / (b1 - b0)
            uv[li].uv = (u0 + u * (u1 - u0), v0 + v * (v1 - v0))


clean_scene()
img = bpy.data.images.load(TEX)
img.colorspace_settings.name = "sRGB"
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"

M_LIVERY = new_mat("Livery", image=img, rough=0.22, coat=1.0)
M_INTERIOR = new_mat("Interior", (0.09, 0.09, 0.10), rough=0.85)
M_UNDER = new_mat("Underbody", (0.05, 0.05, 0.055), rough=0.9)
M_GLASS = new_mat("Glass", (0.06, 0.07, 0.09), rough=0.03, alpha=0.6)
M_CHROME = new_mat("Chrome", (0.86, 0.87, 0.89), rough=0.15, metal=1.0)
M_PLASTIC = new_mat("BlackPlastic", (0.03, 0.03, 0.032), rough=0.55)
M_GRILLE = new_mat("GrilleBar", (0.10, 0.10, 0.11), rough=0.35)
M_TIRE = new_mat("Tire", (0.035, 0.035, 0.035), rough=0.92)
M_WHEEL = new_mat("Wheel_Face", image=img, rough=0.35, metal=0.7)
M_HEAD = new_mat("Headlight_Lens", image=img, rough=0.1, emissive=(1.0, 0.98, 0.9))
M_TAIL = new_mat("Taillight_Lens", image=img, rough=0.2, emissive=(1.0, 0.05, 0.05))
M_PLATE = new_mat("Plate", image=img, rough=0.5)
M_FORD = new_mat("FordBadge", image=img, rough=0.25, metal=0.3)
M_SEAT = new_mat("Seat", (0.12, 0.12, 0.13), rough=0.9)
M_MIRROR = new_mat("MirrorGlass", (0.9, 0.9, 0.92), rough=0.03, metal=1.0)

# ---------------------------------------------------------------- body shell
# side profile (y, z), bevel weight of the cap edge AFTER this point (towards next point),
# and bevel weight of the width-wise crease edge AT this point.
PROFILE = [
    # (y,      z,    seg_w, crease_w)
    (-2.76,   0.40, 0.70, 0.25),   # 0 bumper bottom
    (YF,      0.50, 0.95, 0.30),   # 1 bumper low
    (YF,      0.72, 1.00, 0.25),   # 2 bumper top
    (-2.765,  0.95, 1.00, 0.30),   # 3 grille mid
    (-2.71,   1.10, 0.95, 0.40),   # 4 grille top
    (-2.62,   1.17, 0.75, 0.75),   # 5 bonnet lip
    (-2.40,   1.31, 0.55, 0.30),   # 6 bonnet mid
    (-2.08,   1.38, 0.35, 0.30),   # 7 windscreen base
    (-1.25,   2.06, 0.45, 0.90),   # 8 windscreen top
    (-1.06,   2.12, 0.50, 0.55),   # 9 roof front
    (2.70,    2.12, 0.50, 0.45),   # 10 roof rear
    (YR,      2.02, 0.30, 0.35),   # 11 rear top
    (YR,      0.45, 0.30, 0.20),   # 12 rear bottom
    (2.52,    0.40, 0.10, 0.10),   # 13 underside rear
    (-2.60,   0.40, 0.12, 0.10),   # 14 underside front
]
BEVEL_BASE = 0.30
WS_BASE, WS_TOP = Vector((-2.08, 1.38)), Vector((-1.25, 2.06))

bm = bmesh.new()
wl = bm.edges.layers.float.new("bevel_weight_edge")
n = len(PROFILE)
vl = [bm.verts.new((+HW, p[0], p[1])) for p in PROFILE]
vr = [bm.verts.new((-HW, p[0], p[1])) for p in PROFILE]
fl = bm.faces.new(vl)
fr = bm.faces.new(list(reversed(vr)))
for i in range(n):
    j = (i + 1) % n
    bm.faces.new([vl[i], vr[i], vr[j], vl[j]])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.edges.ensure_lookup_table()
for e in bm.edges:
    a, b = e.verts
    if abs(a.co.x - b.co.x) > 1e-6:          # width-wise crease edge
        i = min(range(n), key=lambda k: (Vector((PROFILE[k][0], PROFILE[k][1])) - Vector((a.co.y, a.co.z))).length)
        e[wl] = PROFILE[i][3]
    else:                                     # cap edge (profile segment)
        ia = min(range(n), key=lambda k: (Vector((PROFILE[k][0], PROFILE[k][1])) - Vector((a.co.y, a.co.z))).length)
        ib = min(range(n), key=lambda k: (Vector((PROFILE[k][0], PROFILE[k][1])) - Vector((b.co.y, b.co.z))).length)
        i = min(ia, ib) if {ia, ib} != {0, n - 1} else n - 1
        e[wl] = PROFILE[i][2]
body = mesh_from_bm("Body", bm, M_LIVERY)
body.data.materials.append(M_INTERIOR)
body.data.materials.append(M_UNDER)
m = body.modifiers.new("bevel", "BEVEL")
m.width = BEVEL_BASE
m.segments = 6
m.limit_method = "WEIGHT"
m.use_clamp_overlap = True
m.miter_outer = "MITER_ARC"
apply_all(body)


def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


# plan-view taper: the nose narrows towards the bumper, the roof is narrower than the sides
for v in body.data.vertices:
    x, y, z = v.co
    f_nose = 1.0 - 0.08 * smoothstep(-1.85, YF, y)
    f_roof = 1.0 - 0.04 * smoothstep(1.75, 2.12, z)
    tb = (z - 1.0) / 0.9
    f_side = 1.0 + 0.02 * max(0.0, 1.0 - tb * tb)         # gentle bulge around the belt line
    v.co.x = x * f_nose * f_roof * f_side
body.data.update()

# interior cavity (leaves ~WALL thick skin). Dash and firewall are part of the cavity shape.
d = (WS_TOP - WS_BASE).normalized()              # windscreen direction in (y, z)
nrm = Vector((-d.y, d.x))                        # outward normal
wb = WS_BASE - nrm * WALL                        # inner windscreen base / top
wt = WS_TOP - nrm * WALL
HW_IN = 0.93
cavity = prism_yz("cavity", [
    (-1.95, 0.52), (-1.95, 1.12), (wb.x, wb.y), (wt.x, wt.y), (-1.00, 2.04), (YR - WALL, 2.04), (YR - WALL, 0.52),
], -HW_IN, HW_IN, M_INTERIOR)
boolean(body, cavity, "DIFFERENCE")

# wheel wells
for ya in (Y_AXLE_F, Y_AXLE_R):
    for sx in (1, -1):
        c = cylinder("well", 0.44, 0.62, "X", 40, M_UNDER)
        c.location = (sx * (HW - 0.31 + 0.12), ya, WHEEL_R)
        bpy.context.view_layer.update()
        c.data.transform(c.matrix_world); c.matrix_world = Matrix()
        boolean(body, c, "DIFFERENCE")

# windscreen opening + glass
mid = (WS_BASE + WS_TOP) / 2
seglen = (WS_TOP - WS_BASE).length
frame = Matrix(((1, 0, 0, 0), (0, d.x, nrm.x, mid.x), (0, d.y, nrm.y, mid.y), (0, 0, 0, 1)))
cut = rounded_box("ws_cut", 1.84, seglen - 0.10, 0.5, 0.14, frame, M_INTERIOR)
boolean(body, cut, "DIFFERENCE")
glass_ws = rounded_box("Glass_Windscreen", 1.88, seglen - 0.07, 0.012, 0.14, frame @ Matrix.Translation((0, 0, -0.014)), M_GLASS)

# lower intake recess in the bumper
boolean(body, box("intake", -0.52, 0.52, -2.95, -2.72, 0.41, 0.47, M_UNDER), "DIFFERENCE")


def shell_piece(name, x0, x1, y0, y1, z0, z1, mat):
    """Cut a piece out of the shell so it inherits the body curvature (used for lamps and grille);
    the body keeps a GAP-wide seam around it."""
    cutter = box("piece_box", x0, x1, y0, y1, z0, z1, M_INTERIOR)
    piece = body.copy(); piece.data = body.data.copy(); piece.name = name; link(piece)
    boolean(piece, cutter, "INTERSECT")
    big = box("piece_gap", x0 - GAP, x1 + GAP, y0 - GAP, y1 + GAP, z0 - GAP, z1 + GAP, M_INTERIOR)
    boolean(body, big, "DIFFERENCE")
    piece.data.materials.clear()
    piece.data.materials.append(mat)
    for poly in piece.data.polygons:
        poly.material_index = 0
    return piece


def shell_piece_xz(name, pts, y0, y1, mat, gap_scale=1.03):
    """Like shell_piece but with a front-view (x,z) outline."""
    cutter = prism_xz("piece_poly", pts, y0, y1, M_INTERIOR)
    piece = body.copy(); piece.data = body.data.copy(); piece.name = name; link(piece)
    boolean(piece, cutter, "INTERSECT")
    big = prism_xz("piece_gap", offset_poly(pts, gap_scale), y0 - GAP, y1 + GAP, M_INTERIOR)
    boolean(body, big, "DIFFERENCE")
    piece.data.materials.clear()
    piece.data.materials.append(mat)
    for poly in piece.data.polygons:
        poly.material_index = 0
    return piece


# ---- high-detail parts borrowed from the VW Crafter asset (references/crafter/crafter_parts.blend)
PARTS = os.path.join(ROOT, "references", "crafter", "crafter_parts.blend")


def load_part(name, new_name):
    with bpy.data.libraries.load(PARTS, link=False) as (src, dst):
        dst.objects = [name]
    ob = dst.objects[0]
    ob.name = new_name
    link(ob)
    return ob


def convex_hull_cutter(ob, scale, mat):
    bm = bmesh.new()
    for v in ob.data.vertices:
        bm.verts.new(v.co)
    bm.verts.ensure_lookup_table()
    res = bmesh.ops.convex_hull(bm, input=bm.verts)
    hull_verts = {v.index for g in res["geom"] if isinstance(g, bmesh.types.BMVert) for v in (g,)}
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in hull_verts], context="VERTS")
    c = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)
    bmesh.ops.scale(bm, vec=(scale, scale, scale), verts=bm.verts, space=Matrix.Translation(-c))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_from_bm("hull_cutter", bm, mat)


# lamps: swept units cut from the shell so they follow the nose / corner curvature
headlights = {}
for sx, nm in ((1, "Headlight_L"), (-1, "Headlight_R")):
    outline = [(0.56, 0.90), (0.56, 1.10), (0.74, 1.19), (1.12, 1.25), (1.12, 0.97), (0.88, 0.90)]
    outline = [(sx * x, z) for x, z in outline]
    if sx < 0:
        outline = list(reversed(outline))
    hl = shell_piece_xz(nm, outline, -2.95, -2.48, M_HEAD)
    map_planar(hl, "headlight", "y", (sx * 1.0, sx * 0.56, 0.90, 1.23) if sx < 0 else (0.56, 1.0, 0.90, 1.23), flip_u=(sx > 0))
    smooth(hl, 40)
    headlights[nm] = hl
# chrome grille surround (ring) + recessed black grille inside it; Transit-style wide hexagon
GR_OUT = [(-0.58, 0.63), (0.58, 0.63), (0.68, 0.84), (0.68, 1.15), (-0.68, 1.15), (-0.68, 0.84)]
GR_IN = offset_poly(GR_OUT, 0.88)
grille_frame = body.copy(); grille_frame.data = body.data.copy(); grille_frame.name = "GrilleFrame"; link(grille_frame)
boolean(grille_frame, prism_xz("gf_poly", GR_OUT, -2.95, -2.50, M_INTERIOR), "INTERSECT")
boolean(grille_frame, prism_xz("gf_hole", GR_IN, -3.0, -2.40, M_INTERIOR), "DIFFERENCE")
grille_frame.data.materials.clear(); grille_frame.data.materials.append(M_CHROME)
for poly in grille_frame.data.polygons:
    poly.material_index = 0
smooth(grille_frame, 40)
grille = body.copy(); grille.data = body.data.copy(); grille.name = "Grille"; link(grille)
boolean(grille, prism_xz("g_poly", GR_IN, -2.95, -2.50, M_INTERIOR), "INTERSECT")
grille.data.materials.clear(); grille.data.materials.append(M_PLASTIC)
for poly in grille.data.polygons:
    poly.material_index = 0
grille.location = (0, 0.035, 0)      # recessed behind the chrome surround
smooth(grille, 40)
boolean(body, prism_xz("g_gap", offset_poly(GR_OUT, 1.012), -2.95, -2.50 + GAP, M_INTERIOR), "DIFFERENCE")
taillights = {}
for sx, nm in ((1, "Taillight_L"), (-1, "Taillight_R")):
    tl = shell_piece(nm, sx * 0.89, sx * 1.10, 2.69, 2.95, 0.72, 1.38, M_TAIL)
    map_planar(tl, "taillight", "y", (sx * 1.10, sx * 0.89, 0.72, 1.38) if sx > 0 else (sx * 0.89, sx * 1.10, 0.72, 1.38), flip_u=False)
    smooth(tl, 40)
    taillights[nm] = tl

# ---------------------------------------------------------------- doors (cut from the shell)
def make_door(name, x0, x1, y0, y1, z0, z1):
    cutter = box("door_box", x0, x1, y0, y1, z0, z1, M_INTERIOR)
    door = body.copy(); door.data = body.data.copy(); door.name = name; link(door)
    boolean(door, cutter, "INTERSECT", keep_cutter=True)
    bpy.data.objects.remove(cutter, do_unlink=True)
    big = box("door_gap", x0 - GAP, x1 + GAP, y0 - GAP, y1 + GAP, z0 - GAP, z1 + GAP, M_INTERIOR)
    boolean(body, big, "DIFFERENCE")
    return door

door_fl = make_door("Door_FL", 0.80, 1.30, Y_DF, Y_B, Z_DOOR0, Z_DOOR1)
door_fr = make_door("Door_FR", -1.30, -0.80, Y_DF, Y_B, Z_DOOR0, Z_DOOR1)
door_sl = make_door("Door_Slide", -1.30, -0.80, Y_B + 0.02, Y_B + 1.32, Z_DOOR0, Z_DOOR1)
door_rl = make_door("Door_RL", GAP / 2, 0.88, 2.55, 3.0, 0.72, Z_DOOR1)
door_rr = make_door("Door_RR", -0.88, -GAP / 2, 2.55, 3.0, 0.72, Z_DOOR1)

# cab door windows
WIN = [(-1.36, 1.28), (Y_B - 0.07, 1.28), (Y_B - 0.07, 1.94), (-1.12, 1.94)]
win_glass = {}
for door, sx in ((door_fl, 1), (door_fr, -1)):
    cut = prism_yz("win_cut", WIN, sx * 0.8, sx * 1.3, M_INTERIOR)
    boolean(door, cut, "DIFFERENCE")
    g = prism_yz("Glass_" + door.name, [(y + (0.01 if i in (0, 3) else -0.01), z + (0.01 if i < 2 else -0.01)) for i, (y, z) in enumerate(WIN)],
                 sx * (HW - WALL + 0.018), sx * (HW - WALL + 0.028), M_GLASS)
    win_glass[door.name] = g

# UVs for the shell and doors (world space, before moving origins)
for ob in (body, door_fl, door_fr, door_sl, door_rl, door_rr):
    project_uv(ob, 0)
    smooth(ob, 35)

# ---------------------------------------------------------------- pivots / hierarchy
root = bpy.data.objects.new("ClerkVan", None); link(root)
parent(body, root)
set_origin(door_fl, (HW - 0.02, Y_DF, 1.28))
set_origin(door_fr, (-(HW - 0.02), Y_DF, 1.28))
set_origin(door_sl, (-(HW - 0.03), Y_B + 0.67, 1.28))
set_origin(door_rl, (0.88, YR - 0.01, 1.28))
set_origin(door_rr, (-0.88, YR - 0.01, 1.28))
for dr in (door_fl, door_fr, door_sl, door_rl, door_rr):
    parent(dr, body)
parent(glass_ws, body)
for name, g in win_glass.items():
    parent(g, bpy.data.objects[name])

# ---------------------------------------------------------------- interior
dash = box("Dashboard", -0.95, 0.95, -2.0, -1.55, 0.95, 1.27, M_INTERIOR); parent(dash, body)
bevel(dash, 0.04, 3)
for sx, nm in ((1, "Seat_Driver"), (-1, "Seat_Passenger")):
    cu = box(nm, sx * 0.30, sx * 0.80, -1.30, -0.78, 0.78, 1.02, M_SEAT); bevel(cu, 0.05, 3); parent(cu, body)
    bk = box(nm + "_Back", sx * 0.30, sx * 0.80, -0.80, -0.66, 1.00, 1.62, M_SEAT); bevel(bk, 0.05, 3); parent(bk, body)
bpy.ops.mesh.primitive_torus_add(major_radius=0.19, minor_radius=0.02, major_segments=32, minor_segments=10)
sw = bpy.context.active_object; sw.name = "SteeringWheel"
sw.data.materials.append(M_INTERIOR)
sw.location = (0.55, -1.50, 1.12); sw.rotation_euler = (math.radians(65), 0, 0); parent(sw, body)

# ---------------------------------------------------------------- front details
for hl in headlights.values():
    parent(hl, body)
parent(grille, body)
parent(grille_frame, body)
for i, (z, hw) in enumerate(((0.74, 0.50), (0.88, 0.56), (1.02, 0.58))):
    bar = box(f"GrilleBar_{i}", -hw, hw, -2.80, -2.73, z - 0.034, z + 0.034, M_GRILLE); bevel(bar, 0.012, 2); parent(bar, body)
ford = rounded_box("FordBadge", 0.22, 0.088, 0.015, 0.044, Matrix.Translation((0, -2.82, 0.88)) @ Matrix.Rotation(math.radians(90), 4, "X"), M_FORD)
map_planar(ford, "ford", "y", (-0.11, 0.11, 0.836, 0.924), flip_u=False)
parent(ford, body)
ford_r = rounded_box("FordBadge_Rear", 0.10, 0.04, 0.012, 0.02, Matrix.Translation((-0.46, 2.80, 0.78)) @ Matrix.Rotation(math.radians(90), 4, "X"), M_FORD)
map_planar(ford_r, "ford", "y", (-0.51, -0.41, 0.76, 0.80), flip_u=True)
parent(ford_r, door_rr)

plate_f = box("Plate_Front", -0.155, 0.155, -2.81, -2.795, 0.50, 0.655, M_PLATE)
map_planar(plate_f, "plate", "y", (-0.155, 0.155, 0.50, 0.655)); parent(plate_f, body)
plate_r = box("Plate_Rear", -0.49, -0.18, 2.795, 2.815, 0.44, 0.595, M_PLATE)
map_planar(plate_r, "plate", "y", (-0.18, -0.49, 0.44, 0.595)); parent(plate_r, body)

for sx, nm in ((1, "Wiper_L"), (-1, "Wiper_R")):
    wp = box(nm, sx * 0.10, sx * 0.78, -2.09, -2.06, 1.345, 1.365, M_PLASTIC); parent(wp, body)

# ---------------------------------------------------------------- rear details
for tl in taillights.values():
    parent(tl, body)
brake = box("BrakeLight", -0.18, 0.18, 2.75, 2.805, 2.03, 2.085, M_TAIL)
map_planar(brake, "taillight", "y", (-0.18, 0.18, 2.0, 2.8)); parent(brake, body)
handle_r = box("Handle_Rear", -0.30, -0.08, 2.80, 2.83, 1.08, 1.14, M_PLASTIC); bevel(handle_r, 0.012, 2); parent(handle_r, door_rr)
for sx in (1, -1):
    for z in (0.95, 1.55):
        hg = box("Hinge", sx * 0.85, sx * 0.905, 2.795, 2.825, z - 0.07, z + 0.07, M_PLASTIC); parent(hg, body)

# ---------------------------------------------------------------- side details
def handle(name, x, y, z, par):
    h = box(name, x - 0.012 * (1 if x > 0 else -1), x + 0.022 * (1 if x > 0 else -1), y - 0.09, y + 0.09, z - 0.02, z + 0.02, M_PLASTIC)
    bevel(h, 0.008, 2); parent(h, par)

handle("Handle_FL", HW, Y_B - 0.20, 1.07, door_fl)
handle("Handle_FR", -HW, Y_B - 0.20, 1.07, door_fr)
handle("Handle_Slide", -HW, Y_B + 0.16, 1.07, door_sl)

for sx, nm, dr, src in ((1, "Mirror_L", door_fl, "Crafter_MirrorL"), (-1, "Mirror_R", door_fr, "Crafter_MirrorR")):
    hs = load_part(src, nm)
    hs.rotation_mode = "XYZ"
    hs.data.transform(Matrix.Translation((0, 1.075, -0.10)))     # Crafter A-pillar position -> our door front
    parent(hs, dr)

# wheel-arch mouldings (black plastic rings following the arch)
for ya, tag in ((Y_AXLE_F, "F"), (Y_AXLE_R, "R")):
    for sx, side in ((1, "L"), (-1, "R")):
        pts = [(ya + 0.495 * math.cos(math.radians(a)), WHEEL_R + 0.495 * math.sin(math.radians(a))) for a in range(8, 173, 6)]
        pts += [(ya + 0.445 * math.cos(math.radians(a)), WHEEL_R + 0.445 * math.sin(math.radians(a))) for a in range(172, 7, -6)]
        fl_ = prism_yz("ArchFlare_" + tag + side, pts, sx * 0.955, sx * 1.040, M_PLASTIC)
        smooth(fl_, 40)
        parent(fl_, body)

# chassis / axles
ch = box("Chassis", -0.85, 0.85, -2.25, 2.55, 0.26, 0.41, M_UNDER); parent(ch, body)
for ya in (Y_AXLE_F, Y_AXLE_R):
    ax = cylinder("Axle", 0.045, 1.60, "X", 16, M_UNDER); ax.location = (0, ya, WHEEL_R); parent(ax, body)

# ---------------------------------------------------------------- wheels
wheels = []
wheel_src = load_part("Crafter_Wheel", "Crafter_Wheel_src")
wheel_src.data.transform(Matrix.Scale(WHEEL_R / 0.348, 4))       # tyre radius -> 235/65R16
for ya, tag in ((Y_AXLE_F, "F"), (Y_AXLE_R, "R")):
    for sx, side in ((1, "L"), (-1, "R")):
        center = Vector((sx * 0.985, ya, WHEEL_R))                 # local x=0 is the outer face of the tyre
        tire = wheel_src.copy(); tire.data = wheel_src.data.copy(); tire.name = "Wheel_" + tag + side; link(tire)
        tire.rotation_mode = "XYZ"          # glTF-imported objects default to quaternions; clips key Euler X
        if sx < 0:
            tire.data.transform(Matrix.Rotation(math.pi, 4, "Z"))
        if tag == "F":
            st = bpy.data.objects.new("Steer_" + side, None); link(st)
            st.location = center; parent(st, root)
            tire.location = (0, 0, 0); tire.parent = st   # identity parent-inverse: wheel sits on the pivot
        else:
            tire.location = center; parent(tire, root)
        wheels.append(tire)
bpy.data.objects.remove(wheel_src, do_unlink=True)


# ---------------------------------------------------------------- lights (KHR_lights_punctual)
def add_light(name, kind, loc, energy, color=(1, 1, 1), rot=None, size=None):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    if kind == "SPOT":
        ld.spot_size = math.radians(70)
        ld.spot_blend = 0.6
    ob = bpy.data.objects.new(name, ld); link(ob)
    ob.location = loc
    if rot:
        ob.rotation_euler = rot
    parent(ob, body)
    return ob

for sx, nm in ((1, "Light_HeadL"), (-1, "Light_HeadR")):
    add_light(nm, "SPOT", (sx * 0.70, -2.85, 1.0), 60.0, (1.0, 0.97, 0.88), rot=(math.radians(-85), 0, 0))
for sx, nm in ((1, "Light_TailL"), (-1, "Light_TailR")):
    add_light(nm, "POINT", (sx * 0.95, 2.90, 1.05), 8.0, (1.0, 0.08, 0.05))

# ---------------------------------------------------------------- animation clips (NLA tracks -> glTF animations)
scene.render.fps = 30

def add_clip(obj, clip, path, keys, index=-1):
    """keys = [(frame, value_or_tuple)]. Each call adds one NLA track; existing tracks are kept."""
    if obj.animation_data is None:
        obj.animation_data_create()
    obj.animation_data.action = None
    for f, val in keys:
        if index >= 0:
            v = list(getattr(obj, path)); v[index] = val; setattr(obj, path, v)
        else:
            setattr(obj, path, val)
        obj.keyframe_insert(data_path=path, frame=f, index=index)
    act = obj.animation_data.action
    act.name = f"{clip}.{obj.name}"
    try:
        for fc in act.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR" if clip == "Wheels_Spin" else "BEZIER"
    except Exception:
        pass
    track = obj.animation_data.nla_tracks.new()
    track.name = clip
    strip = track.strips.new(clip, int(keys[0][0]), act)
    try:
        strip.action_slot = act.slots[0]
    except Exception:
        pass
    obj.animation_data.action = None
    # reset to rest pose
    for f, val in keys[:1]:
        if index >= 0:
            v = list(getattr(obj, path)); v[index] = val; setattr(obj, path, v)
        else:
            setattr(obj, path, val)

DOOR_CLIPS = [
    (door_fl, "DoorFL_Open", "rotation_euler", [(1, 0.0), (30, math.radians(-65))], 2),
    (door_fr, "DoorFR_Open", "rotation_euler", [(1, 0.0), (30, math.radians(65))], 2),
    (door_rl, "DoorRL_Open", "rotation_euler", [(1, 0.0), (30, math.radians(-95))], 2),
    (door_rr, "DoorRR_Open", "rotation_euler", [(1, 0.0), (30, math.radians(95))], 2),
]
for ob, clip, path, keys, idx in DOOR_CLIPS:
    add_clip(ob, clip, path, keys, idx)
    add_clip(ob, "AllDoors_Open", path, keys, idx)
slide_keys = [(1, (door_sl.location.x, door_sl.location.y, door_sl.location.z)),
              (8, (door_sl.location.x - 0.10, door_sl.location.y, door_sl.location.z)),
              (30, (door_sl.location.x - 0.10, door_sl.location.y + 1.05, door_sl.location.z))]
add_clip(door_sl, "DoorSlide_Open", "location", slide_keys)
add_clip(door_sl, "AllDoors_Open", "location", slide_keys)
for wh in wheels:
    add_clip(wh, "Wheels_Spin", "rotation_euler", [(1, 0.0), (31, math.radians(360))], 0)

scene.frame_start, scene.frame_end = 1, 30
bpy.context.view_layer.update()

# ---------------------------------------------------------------- export
bpy.ops.object.select_all(action="DESELECT")
glb = os.path.join(EXPORT, "clerk_van_procedural.glb")
bpy.ops.export_scene.gltf(
    filepath=glb, export_format="GLB", export_apply=True, export_lights=True,
    export_animations=True, export_animation_mode="NLA_TRACKS", export_image_format="AUTO",
    export_yup=True, use_selection=False, export_extras=True, export_cameras=False,
    export_materials="EXPORT", export_normals=True, export_texcoords=True,
)
# After export: mute the NLA tracks and stop strips from holding their last frame, so the
# .blend opens (and renders) in the rest pose. Unmute a track in the NLA editor to preview a clip.
for ob in bpy.data.objects:
    if ob.animation_data:
        for tr in ob.animation_data.nla_tracks:
            tr.mute = True
            for st in tr.strips:
                st.extrapolation = "NOTHING"
try:
    bpy.ops.file.pack_all()
except Exception:
    pass
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(EXPORT, "clerk_van_procedural.blend"))

# copy the GLB next to the web test page and into the Godot project
import shutil
for dst in ():  # the Crafter-based build (build_crafter_van.py) is the one shipped to web/ and godot/
    if os.path.isdir(dst):
        shutil.copy(glb, os.path.join(dst, "clerk_van.glb"))

# stats
tris = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
print(f"BUILD OK  objects={len(bpy.data.objects)} faces={tris}  glb={glb} size={os.path.getsize(glb)/1e6:.2f} MB")
