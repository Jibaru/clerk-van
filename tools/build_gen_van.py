"""
Clerk Van, high-fidelity build: body generated from the four reference views with Hunyuan3D-2mv
(references/gen/<GEN>.glb), scaled to Transit metres, doors + wheels separated and rigged, the Clerk livery
atlas (tools/profiles/gen.json) box-projected on the painted panels, and the reference photographs projected
on everything else (grille, lamps, glass, mirrors, cladding, bumpers). Wheels come from the Crafter parts library.

Same runtime contract as the other builds: Door_FL/FR/Slide/RL/RR, Wheel_*, Steer_L/R, Light_*, *_Lens
materials, clips Door*_Open / AllDoors_Open / Wheels_Spin.   blender --background --python tools/build_gen_van.py -- <root>
"""
import bpy, bmesh, math, os, sys, json, shutil
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = os.path.abspath(argv[0]) if argv else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = argv[1] if len(argv) > 1 else "hunyuan_mv_s7_o512"
SRC = os.path.join(ROOT, "references", "gen", GEN + ".glb")
TEX = os.path.join(ROOT, "textures", "clerk_van_atlas_gen.png")
LAYOUT = json.load(open(os.path.join(ROOT, "textures", "atlas_layout_gen.json")))
PROF = json.load(open(os.path.join(ROOT, "tools", "profiles", "gen.json")))
BBOX = json.load(open(os.path.join(ROOT, "references", "views", "bboxes.json")))
PARTS = os.path.join(ROOT, "references", "crafter", "crafter_parts.blend")
EXPORT = os.path.join(ROOT, "export")
os.makedirs(EXPORT, exist_ok=True)
ATLAS = LAYOUT["size"]; R = LAYOUT["regions"]

L_TARGET, W_TARGET, H_TARGET, Y_UNIFORM = 5.45, 2.03, 2.12, 1.15
DECIMATE = 0.35
Y_B, Z_BELT, Z_SILL = PROF["Y_B"], PROF["Z_BELT"], PROF["Z_SILL"]
Y_AXLE_F, Y_AXLE_R, WHEEL_R = PROF["Y_AXLE_F"], PROF["Y_AXLE_R"], PROF["WHEEL_R"]
Y_DF = -1.36                 # cab door front edge
Z_DOOR0, Z_DOOR1 = 0.57, 1.98
SLIDE_Y0, SLIDE_Y1 = Y_B + 0.02, Y_B + 1.30

# ---------------------------------------------------------------- helpers
def link(ob):
    bpy.context.scene.collection.objects.link(ob); return ob

def parent(child, par, keep=True):
    bpy.context.view_layer.update()
    child.parent = par
    child.matrix_parent_inverse = par.matrix_world.inverted() if keep else Matrix()

def bounds(ob):
    vs = ob.data.vertices
    xs = [v.co.x for v in vs]; ys = [v.co.y for v in vs]; zs = [v.co.z for v in vs]
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))

def set_origin(ob, pivot):
    pv = Vector(pivot); ob.data.transform(Matrix.Translation(-pv)); ob.location = pv

def new_mat(name, color=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, image=None, coat=0.0, emissive=None, uv=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough; bsdf.inputs["Metallic"].default_value = metal
    if coat:
        try:
            bsdf.inputs["Coat Weight"].default_value = coat; bsdf.inputs["Coat Roughness"].default_value = 0.08
        except KeyError:
            pass
    if image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = image; tex.location = (-400, 300)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if uv:
            uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = uv; uvn.location = (-650, 300)
            nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
    if emissive is not None:
        bsdf.inputs["Emission Color"].default_value = (*emissive, 1.0); bsdf.inputs["Emission Strength"].default_value = 0.0
        if image is not None:
            nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    return m

def uv_rect(region):
    x0, y0, x1, y1 = R[region]
    return (x0 / ATLAS, 1 - y1 / ATLAS, x1 / ATLAS, 1 - y0 / ATLAS)

def load_part(name, new_name):
    with bpy.data.libraries.load(PARTS, link=False) as (src, dst):
        dst.objects = [name]
    ob = dst.objects[0]; ob.name = new_name; link(ob); return ob

# ---------------------------------------------------------------- import + scale (same policy as gen_measure.py)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
scene = bpy.context.scene; scene.render.fps = 30
body = [o for o in bpy.data.objects if o.type == "MESH"][0]
body.name = "Body"; body.data.name = "Body"
bpy.context.view_layer.update()
body.data.transform(body.matrix_world); body.matrix_world = Matrix()
body.rotation_mode = "XYZ"
for o in list(bpy.data.objects):
    if o is not body:
        bpy.data.objects.remove(o, do_unlink=True)

vs = body.data.vertices
ys = [v.co.y for v in vs]; zs = [v.co.z for v in vs]
y0, y1, z0, z1 = min(ys), max(ys), min(zs), max(zs)
side = sorted(abs(v.co.x) for v in vs if -0.3 < v.co.y < 0.3 and -0.2 < v.co.z < 0.3)
hw = side[int(len(side) * 0.98)]
s_xz = ((W_TARGET / 2) / hw + H_TARGET / (z1 - z0)) / 2
front = [v.co.y for v in vs if v.co.z < z0 + 0.15 and v.co.y < 0]; rear = [v.co.y for v in vs if v.co.z < z0 + 0.15 and v.co.y > 0]
a, b = max(front) + 0.02, min(rear) - 0.02
s_y = s_xz * Y_UNIFORM
extra = (L_TARGET - (y1 - y0) * s_y) / s_y
for v in vs:
    y = v.co.y
    if y > b:
        y += extra
    elif y > a:
        y = a + (y - a) * (b - a + extra) / (b - a)
    v.co = Vector((v.co.x * s_xz, y * s_y, (v.co.z - z0) * s_xz))
ys = [v.co.y for v in vs]
body.data.transform(Matrix.Translation((0, -(min(ys) + max(ys)) / 2, 0)))
body.data.update()
(BX, BY, BZ) = bounds(body)
YF, YR, ROOF = BY[0], BY[1], BZ[1]
print(f"body bounds x={BX} y={BY} z={BZ}")

# decimate for a web/Godot-friendly count, then smooth
m = body.modifiers.new("dec", "DECIMATE"); m.ratio = DECIMATE; m.use_collapse_triangulate = True
bpy.ops.object.select_all(action="DESELECT"); body.select_set(True); bpy.context.view_layer.objects.active = body
bpy.ops.object.modifier_apply(modifier="dec")
for p in body.data.polygons:
    p.use_smooth = True
bm = bmesh.new(); bm.from_mesh(body.data)
for e in bm.edges:
    if len(e.link_faces) == 2:
        e.smooth = e.calc_face_angle(None) < math.radians(35)
bm.to_mesh(body.data); bm.free()
print("body faces after decimate", len(body.data.polygons))

# ---------------------------------------------------------------- materials
img = bpy.data.images.load(TEX); img.colorspace_settings.name = "sRGB"
photos = {}
for n in ("front", "back", "left", "right"):
    im = bpy.data.images.load(os.path.join(ROOT, "references", "views", n + "_keyed.png")); im.colorspace_settings.name = "sRGB"
    photos[n] = im
M_LIVERY = new_mat("Livery", image=img, rough=0.32, coat=0.15, uv="LiveryUV")
M_PHOTO = {n: new_mat("Photo_" + n, image=photos[n], rough=0.35, coat=0.2, uv="PhotoUV") for n in photos}
M_HEAD = new_mat("Headlight_Lens", image=photos["front"], rough=0.15, uv="PhotoUV", emissive=(1, 1, 1))
M_TAIL = new_mat("Taillight_Lens", image=photos["back"], rough=0.2, uv="PhotoUV", emissive=(1, 1, 1))
M_UNDER = new_mat("Underbody", (0.05, 0.05, 0.055), rough=0.9)
M_INTERIOR = new_mat("Interior", (0.10, 0.10, 0.11), rough=0.85)
SLOTS = ["Livery", "Photo_front", "Photo_back", "Photo_left", "Photo_right", "Headlight_Lens", "Taillight_Lens", "Underbody"]
MATS = {"Livery": M_LIVERY, "Headlight_Lens": M_HEAD, "Taillight_Lens": M_TAIL, "Underbody": M_UNDER, **{"Photo_" + n: M_PHOTO[n] for n in photos}}
body.data.materials.clear()
for s_ in SLOTS:
    body.data.materials.append(MATS[s_])
SI = {s_: i for i, s_ in enumerate(SLOTS)}

ext = LAYOUT["extents"]
MIRROR_X = 1.06

def classify(c, n):
    """face centre c, normal n (world) -> material slot name"""
    ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
    mirror = abs(c.x) > 0.97 and 0.95 < c.z < 1.65 and -1.55 < c.y < -0.85
    if mirror or abs(c.x) > MIRROR_X:
        return "Photo_front"                        # mirrors: the side photo only shows background behind them
    if ax >= ay and ax >= az:
        side_photo = "Photo_left" if n.x > 0 else "Photo_right"
        if c.z < Z_SILL or c.y < -2.15:
            return side_photo                       # cladding, and the nose corners (lamps wrap around)
        if c.y < Y_B - 0.03 and c.y > Y_DF - 0.1 and 1.22 < c.z < 1.96:
            return side_photo                       # cab door glass
        if c.y < Y_DF - 0.1 and c.z > 1.2:
            return side_photo                       # A-pillar / windscreen edge
        return "Livery"
    if ay >= az:
        if n.y < 0:
            if c.y > -2.12 and c.z > 1.12 and c.z < 1.42:
                return "Livery"                     # cowl step at the back of the hood stays white
            if 0.55 < abs(c.x) < 1.02 and 0.84 < c.z < 1.17:
                return "Headlight_Lens"
            return "Photo_front"
        if c.z < 0.72 or abs(c.x) > 0.86:
            return "Taillight_Lens" if (abs(c.x) > 0.86 and 0.74 < c.z < 1.42) else "Photo_back"
        return "Livery"
    if n.z > 0:
        if c.y < -1.0 and c.z >= 1.40:
            return "Photo_front"                    # windscreen seen from above
        return "Livery"                             # hood (below 1.40) and roof
    return "Underbody"

def livery_uv(c, n, p):
    ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
    if ax >= ay and ax >= az:
        a0, a1, b0, b1 = ext["side"]; v = (p.z - b0) / (b1 - b0)
        if n.x > 0:
            u = (p.y - a0) / (a1 - a0); reg = "side_left"
        else:
            u = (a1 - p.y) / (a1 - a0); reg = "side_right"
    elif ay >= az:
        a0, a1, b0, b1 = ext["front"]; v = (p.z - b0) / (b1 - b0)
        if n.y < 0:
            u = (p.x - a0) / (a1 - a0); reg = "front"
        else:
            u = (a1 - p.x) / (a1 - a0); reg = "rear"
    else:
        if n.z > 0:
            a0, a1, b0, b1 = ext["top"]; u = (a1 - p.x) / (a1 - a0); v = (b1 - p.y) / (b1 - b0); reg = "top"
        else:
            u, v, reg = 0.5, 0.5, "bottom"
    u0, v0, u1, v1 = uv_rect(reg)
    return (u0 + u * (u1 - u0), v0 + v * (v1 - v0))

XM = 1.26   # mirror-to-mirror half width used for the front/rear photos

def photo_uv(slot, p):
    """Orthographic projection of the reference photo: van bbox in the photo <-> van extents in metres."""
    if slot in ("Photo_left",):
        bb = BBOX["left"]; u = (p.y - YF) / (YR - YF); v = p.z / ROOF
    elif slot == "Photo_right":
        bb = BBOX["right"]; u = (YR - p.y) / (YR - YF); v = p.z / ROOF
    elif slot in ("Photo_front", "Headlight_Lens"):
        bb = BBOX["front"]; u = (p.x + XM) / (2 * XM); v = p.z / ROOF
    else:
        bb = BBOX["back"]; u = (XM - p.x) / (2 * XM); v = p.z / ROOF
    x0, y0, x1, y1 = bb["bbox"]; W, H = bb["w"], bb["h"]
    px = x0 + u * (x1 - x0); py = y1 - v * (y1 - y0)
    return (px / W, 1 - py / H)

def assign(ob):
    me = ob.data
    if "LiveryUV" not in me.uv_layers:
        me.uv_layers.new(name="LiveryUV")
    if "PhotoUV" not in me.uv_layers:
        me.uv_layers.new(name="PhotoUV")
    luv = me.uv_layers["LiveryUV"].data; puv = me.uv_layers["PhotoUV"].data
    mw = ob.matrix_world; nm = mw.to_3x3().inverted().transposed()
    for poly in me.polygons:
        c = mw @ poly.center; n = (nm @ poly.normal).normalized()
        slot = classify(c, n)
        poly.material_index = SI[slot]
        for li in poly.loop_indices:
            p = mw @ me.vertices[me.loops[li].vertex_index].co
            luv[li].uv = livery_uv(c, n, p)
            puv[li].uv = photo_uv(slot, p)
    me.uv_layers.active = me.uv_layers["LiveryUV"]

# ---------------------------------------------------------------- separate doors and wheels by region (face level)
def separate(ob, name, pred):
    """Move faces satisfying pred(centre) into a new object `name` (world space kept)."""
    bm = bmesh.new(); bm.from_mesh(ob.data)
    sel = [f for f in bm.faces if pred(f.calc_center_median())]
    if not sel:
        bm.free(); return None
    new_bm = bmesh.new()
    vmap = {}
    for f in sel:
        vs_ = []
        for v in f.verts:
            if v.index not in vmap:
                vmap[v.index] = new_bm.verts.new(v.co)
            vs_.append(vmap[v.index])
        try:
            nf = new_bm.faces.new(vs_); nf.smooth = f.smooth
        except ValueError:
            pass
    bmesh.ops.delete(bm, geom=sel, context="FACES")
    bm.to_mesh(ob.data); bm.free()
    me = bpy.data.meshes.new(name); new_bm.to_mesh(me); new_bm.free()
    n = bpy.data.objects.new(name, me); link(n)
    for s_ in SLOTS:
        me.materials.append(MATS[s_])
    n.rotation_mode = "XYZ"
    return n

HWB = BX[1]
door_fl = separate(body, "Door_FL", lambda c: c.x > 0.80 and Y_DF < c.y < Y_B and Z_DOOR0 < c.z < Z_DOOR1)
door_fr = separate(body, "Door_FR", lambda c: c.x < -0.80 and Y_DF < c.y < Y_B and Z_DOOR0 < c.z < Z_DOOR1)
door_sl = separate(body, "Door_Slide", lambda c: c.x < -0.80 and SLIDE_Y0 < c.y < SLIDE_Y1 and Z_DOOR0 < c.z < Z_DOOR1)
door_rl = separate(body, "Door_RL", lambda c: c.y > YR - 0.30 and 0.0 < c.x < 0.88 and 0.72 < c.z < 2.0)
door_rr = separate(body, "Door_RR", lambda c: c.y > YR - 0.30 and -0.88 < c.x < 0.0 and 0.72 < c.z < 2.0)
for ya, tag in ((Y_AXLE_F, "F"), (Y_AXLE_R, "R")):
    for sx, sd in ((1, "L"), (-1, "R")):
        gone = separate(body, f"gen_wheel_{tag}{sd}", lambda c, ya=ya, sx=sx: c.x * sx > 0.62 and (c.y - ya) ** 2 + (c.z - WHEEL_R) ** 2 < 0.44 ** 2 and c.z < 0.55)
        if gone:
            bpy.data.objects.remove(gone, do_unlink=True)

for ob in (body, door_fl, door_fr, door_sl, door_rl, door_rr):
    assign(ob)

# interior box + wheel wells (simple dark geometry so open doors / arches do not show the shell's backfaces)
def box(name, x0, x1, y0, y1, z0, z1, mat):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(x1 - x0, y1 - y0, z1 - z0), verts=bm.verts)
    bmesh.ops.translate(bm, vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), verts=bm.verts)
    for f in bm.faces:
        f.normal_flip()
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(mat)
    return link(bpy.data.objects.new(name, me))

interior = box("Interior", -0.78, 0.78, -1.10, YR - 0.20, 0.50, 1.80, M_INTERIOR)   # must stay inside the tapering upper body
cab_int = box("Interior_Cab", -0.78, 0.78, -1.85, -1.10, 0.50, 1.20, M_INTERIOR)
for ya, tag in ((Y_AXLE_F, "F"), (Y_AXLE_R, "R")):
    for sx, sd in ((1, "L"), (-1, "R")):
        bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=0.46, radius2=0.46, depth=0.50)
        bm.transform(Matrix.Rotation(math.radians(90), 4, "Y")); bm.transform(Matrix.Translation((sx * 0.72, ya, WHEEL_R)))
        for f in bm.faces:
            f.normal_flip()
        me = bpy.data.meshes.new("Well"); bm.to_mesh(me); bm.free(); me.materials.append(M_UNDER)
        link(bpy.data.objects.new("Well_" + tag + sd, me))

# ---------------------------------------------------------------- hierarchy / pivots
root = bpy.data.objects.new("ClerkVan", None); link(root)
parent(body, root)
set_origin(door_fl, (HWB - 0.02, Y_DF, 1.28)); set_origin(door_fr, (-(HWB - 0.02), Y_DF, 1.28))
set_origin(door_sl, (-(HWB - 0.03), (SLIDE_Y0 + SLIDE_Y1) / 2, 1.28))
set_origin(door_rl, (0.88, YR - 0.02, 1.28)); set_origin(door_rr, (-0.88, YR - 0.02, 1.28))
for d in (door_fl, door_fr, door_sl, door_rl, door_rr):
    parent(d, body)
for ob in list(bpy.data.objects):
    if ob.type == "MESH" and ob.parent is None and ob is not body:
        parent(ob, body)

# ---------------------------------------------------------------- wheels (Crafter parts)
wheels = []
wheel_src = load_part("Crafter_Wheel", "Crafter_Wheel_src")
wheel_src.data.transform(Matrix.Scale(WHEEL_R / 0.348, 4))
for ya, tag in ((Y_AXLE_F, "F"), (Y_AXLE_R, "R")):
    for sx, sd in ((1, "L"), (-1, "R")):
        center = Vector((sx * (HWB - 0.03), ya, WHEEL_R))
        tire = wheel_src.copy(); tire.data = wheel_src.data.copy(); tire.name = "Wheel_" + tag + sd; link(tire)
        tire.rotation_mode = "XYZ"
        if sx < 0:
            tire.data.transform(Matrix.Rotation(math.pi, 4, "Z"))
        if tag == "F":
            st = bpy.data.objects.new("Steer_" + sd, None); link(st); st.location = center; parent(st, root)
            tire.location = (0, 0, 0); tire.parent = st
        else:
            tire.location = center; parent(tire, root)
        wheels.append(tire)
bpy.data.objects.remove(wheel_src, do_unlink=True)

# ---------------------------------------------------------------- lights
def add_light(name, kind, loc, energy, color, rot=None):
    ld = bpy.data.lights.new(name, kind); ld.energy = energy; ld.color = color
    if kind == "SPOT":
        ld.spot_size = math.radians(70); ld.spot_blend = 0.6
    ob = bpy.data.objects.new(name, ld); link(ob); ob.location = loc
    if rot:
        ob.rotation_euler = rot
    parent(ob, body)
for sx, nm in ((1, "Light_HeadL"), (-1, "Light_HeadR")):
    add_light(nm, "SPOT", (sx * 0.72, YF - 0.05, 1.0), 60.0, (1.0, 0.97, 0.88), rot=(math.radians(-85), 0, 0))
for sx, nm in ((1, "Light_TailL"), (-1, "Light_TailR")):
    add_light(nm, "POINT", (sx * 0.95, YR + 0.08, 1.05), 8.0, (1.0, 0.08, 0.05))

# ---------------------------------------------------------------- clips
def add_clip(obj, clip, path, keys, index=-1):
    if obj.animation_data is None:
        obj.animation_data_create()
    obj.animation_data.action = None
    for f, val in keys:
        if index >= 0:
            v = list(getattr(obj, path)); v[index] = val; setattr(obj, path, v)
        else:
            setattr(obj, path, val)
        obj.keyframe_insert(data_path=path, frame=f, index=index)
    act = obj.animation_data.action; act.name = f"{clip}.{obj.name}"
    for fc in act.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR" if clip == "Wheels_Spin" else "BEZIER"
    track = obj.animation_data.nla_tracks.new(); track.name = clip
    track.strips.new(clip, int(keys[0][0]), act)
    obj.animation_data.action = None
    f, val = keys[0]
    if index >= 0:
        v = list(getattr(obj, path)); v[index] = val; setattr(obj, path, v)
    else:
        setattr(obj, path, val)

for ob, clip, keys in ((door_fl, "DoorFL_Open", [(1, 0.0), (30, math.radians(-65))]), (door_fr, "DoorFR_Open", [(1, 0.0), (30, math.radians(65))]),
                       (door_rl, "DoorRL_Open", [(1, 0.0), (30, math.radians(-95))]), (door_rr, "DoorRR_Open", [(1, 0.0), (30, math.radians(95))])):
    add_clip(ob, clip, "rotation_euler", keys, 2); add_clip(ob, "AllDoors_Open", "rotation_euler", keys, 2)
L0 = door_sl.location.copy()
slide_keys = [(1, tuple(L0)), (8, (L0.x - 0.10, L0.y, L0.z)), (30, (L0.x - 0.10, L0.y + 1.05, L0.z))]
add_clip(door_sl, "DoorSlide_Open", "location", slide_keys); add_clip(door_sl, "AllDoors_Open", "location", slide_keys)
for w in wheels:
    add_clip(w, "Wheels_Spin", "rotation_euler", [(1, 0.0), (31, math.radians(360))], 0)
scene.frame_start, scene.frame_end = 1, 30
bpy.context.view_layer.update()

# ---------------------------------------------------------------- export
bpy.ops.object.select_all(action="DESELECT")
glb = os.path.join(EXPORT, "clerk_van.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", export_apply=True, export_lights=True, export_animations=True,
                          export_animation_mode="NLA_TRACKS", export_image_format="AUTO", export_yup=True, use_selection=False,
                          export_extras=True, export_cameras=False, export_materials="EXPORT", export_normals=True, export_texcoords=True)
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
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(EXPORT, "clerk_van.blend"))
for dst in (os.path.join(ROOT, "web"), os.path.join(ROOT, "godot")):
    if os.path.isdir(dst):
        shutil.copy(glb, os.path.join(dst, "clerk_van.glb"))
tris = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
print(f"BUILD OK  objects={len(bpy.data.objects)} faces={tris}  glb={glb} size={os.path.getsize(glb)/1e6:.2f} MB")
