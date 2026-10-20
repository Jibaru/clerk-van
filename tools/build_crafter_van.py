"""
Clerk Van on a real van mesh: takes the Sketchfab VW Crafter (references/crafter/source/crafter_custom.glb,
by geyges, Sketchfab Free Standard licence), rescales it to Transit-like dimensions, repaints every exterior
panel with the Clerk livery atlas (textures/clerk_van_atlas_crafter.png), fills the side/rear windows, strips
the roof gear and passenger seats, and rigs it with the same node names as the procedural model:
  Door_FL, Door_FR, Door_Slide, Door_RL, Door_RR, Wheel_FL/FR/RL/RR, Steer_L/R,
  Light_HeadL/R, Light_TailL/R, materials Headlight_Lens / Taillight_Lens, clips Door*_Open, AllDoors_Open, Wheels_Spin.

Exports export/clerk_van.glb + export/clerk_van.blend (also copied to web/ and godot/).
Run:  blender --background --python tools/build_crafter_van.py -- <project root>
"""
import bpy, bmesh, math, os, sys, json, shutil
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = os.path.abspath(argv[0]) if argv else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "references", "crafter", "source", "crafter_custom.glb")
TEX = os.path.join(ROOT, "textures", "clerk_van_atlas_crafter.png")
LAYOUT = json.load(open(os.path.join(ROOT, "textures", "atlas_layout_crafter.json")))
EXPORT = os.path.join(ROOT, "export")
os.makedirs(EXPORT, exist_ok=True)
ATLAS = LAYOUT["size"]
R = LAYOUT["regions"]

SCALE = Vector((1.28, 1.06, 1.06))     # file units -> metres (Transit-like width, Crafter length kept)
WHEEL_UP = 1.18                        # wheels enlarged to 235/65R16-ish
DECIMATE_ABOVE = 25000                 # faces; heavier meshes get a 0.5 collapse for the web/Godot build

# ---------------------------------------------------------------- helpers

def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def parent(child, par, keep=True):
    bpy.context.view_layer.update()
    child.parent = par
    child.matrix_parent_inverse = par.matrix_world.inverted() if keep else Matrix()


def bounds(ob):
    vs = ob.data.vertices
    if not len(vs):
        return (0, 0), (0, 0), (0, 0)
    xs = [v.co.x for v in vs]; ys = [v.co.y for v in vs]; zs = [v.co.z for v in vs]
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def select(objs, active=None):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or objs[0]


def join(objs, name):
    select(objs, objs[0])
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    return ob


def keep_side(ob, sign):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.x * sign < 0], context="VERTS")
    bm.to_mesh(ob.data); bm.free()


def dup(ob, name):
    n = ob.copy(); n.data = ob.data.copy(); n.name = name
    link(n)
    return n


def set_origin(ob, pivot):
    pv = Vector(pivot)
    ob.data.transform(Matrix.Translation(-pv))
    ob.location = pv


def uv_rect(region):
    x0, y0, x1, y1 = R[region]
    return (x0 / ATLAS, 1 - y1 / ATLAS, x1 / ATLAS, 1 - y0 / ATLAS)


def project_uv(obj, mat_indices):
    """Box-project every face whose material slot is in mat_indices into the livery atlas (object must be in world space)."""
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = me.uv_layers.active.data
    ext = LAYOUT["extents"]
    for poly in me.polygons:
        if poly.material_index not in mat_indices:
            continue
        n = poly.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        for li in poly.loop_indices:
            p = me.vertices[me.loops[li].vertex_index].co
            if ax >= ay and ax >= az:
                a0, a1, b0, b1 = ext["side"]
                v = (p.z - b0) / (b1 - b0)
                if n.x > 0:
                    u = (p.y - a0) / (a1 - a0); reg = "side_left"
                else:
                    u = (a1 - p.y) / (a1 - a0); reg = "side_right"
            elif ay >= az:
                a0, a1, b0, b1 = ext["front"]
                v = (p.z - b0) / (b1 - b0)
                if n.y < 0:
                    u = (p.x - a0) / (a1 - a0); reg = "front"
                else:
                    u = (a1 - p.x) / (a1 - a0); reg = "rear"
            else:
                if n.z > 0:
                    a0, a1, b0, b1 = ext["top"]
                    u = (a1 - p.x) / (a1 - a0)
                    v = (b1 - p.y) / (b1 - b0); reg = "top"
                else:
                    u, v, reg = 0.5, 0.5, "bottom"
            u0, v0, u1, v1 = uv_rect(reg)
            uv[li].uv = (u0 + u * (u1 - u0), v0 + v * (v1 - v0))


def paint(ob, which="carpaint", y_min=None):
    """Replace material slots with the livery. which='carpaint': only slots named Car Paint; 'all': every slot.
    y_min: only faces whose centre y > y_min (used to keep the windscreen glass of a combined glass mesh)."""
    me = ob.data
    if which == "all" and y_min is None:
        me.materials.clear()
        me.materials.append(M_LIVERY)
        for p in me.polygons:
            p.material_index = 0
        project_uv(ob, {0})
        return
    if y_min is not None:
        me.materials.append(M_LIVERY)
        idx = len(me.materials) - 1
        for p in me.polygons:
            if p.center.y > y_min:
                p.material_index = idx
        project_uv(ob, {idx})
        return
    idxs = set()
    for i, m in enumerate(me.materials):
        if m and m.name.startswith("Car Paint"):
            me.materials[i] = M_LIVERY
            idxs.add(i)
    if idxs:
        project_uv(ob, idxs)


def new_mat(name, color=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, image=None, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
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
        tex = m.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.location = (-400, 300)
        m.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return m


def make_lens(src_name, new_name, color, emissive):
    m = bpy.data.materials.get(src_name)
    if not m:
        return
    m.name = new_name
    bs = m.node_tree.nodes.get("Principled BSDF")
    if bs:
        bs.inputs["Base Color"].default_value = (*color, 1)
        bs.inputs["Alpha"].default_value = 1.0
        bs.inputs["Roughness"].default_value = 0.25
        bs.inputs["Emission Color"].default_value = (*emissive, 1)
        bs.inputs["Emission Strength"].default_value = 0.0
    try:
        m.surface_render_method = "DITHERED"
    except Exception:
        m.blend_method = "OPAQUE"


# ---------------------------------------------------------------- import + normalise
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
scene = bpy.context.scene
scene.render.fps = 30
bpy.context.view_layer.update()

for ob in list(bpy.data.objects):
    if ob.type != "MESH":
        continue
    ob.data = ob.data.copy()
    mw = ob.matrix_world.copy()
    ob.parent = None
    ob.matrix_world = Matrix()
    ob.data.transform(mw)
    ob.rotation_mode = "XYZ"
for ob in list(bpy.data.objects):
    if ob.type != "MESH":
        bpy.data.objects.remove(ob, do_unlink=True)
for ob in bpy.data.objects:
    ob.animation_data_clear()
for act in list(bpy.data.actions):
    bpy.data.actions.remove(act)

# drop passenger-bus fittings and roof gear
DROP_PREFIX = ("4_Salon", "interiorBase_seat", "i_interior_curtains", "i_lights", "e_the_hatch", "e_hatch_glassShape",
               "e_cooler", "e_parkinglights", "e_logo_chrome", "wheelLogo")
for ob in list(bpy.data.objects):
    if ob.name.startswith(DROP_PREFIX):
        bpy.data.objects.remove(ob, do_unlink=True)

# scale to Transit-like metres
SM = Matrix.Diagonal((SCALE.x, SCALE.y, SCALE.z, 1.0))
for ob in bpy.data.objects:
    ob.data.transform(SM)

def O(name):
    return bpy.data.objects[name]

# ---------------------------------------------------------------- wheels (enlarged, split per side) + ground lift
def build_wheels(names, tag, y_center_hint):
    w = join([O(n) for n in names if n in bpy.data.objects], "wheels_" + tag)
    out = []
    for sx, side in ((1, "L"), (-1, "R")):
        half = dup(w, "Wheel_" + tag + side)
        keep_side(half, sx)
        (x0, x1), (y0, y1), (z0, z1) = bounds(half)
        c = Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
        half.data.transform(Matrix.Translation(-c))
        half.data.transform(Matrix.Scale(WHEEL_UP, 4))
        half.location = c
        out.append(half)
    bpy.data.objects.remove(w, do_unlink=True)
    return out

front = build_wheels(["wheel_front_rimShape", "wheel_front_tyre_tyreShape", "wheel_front_brakeDisk", "wheel_front_plasticBlack_matteShape"], "F", -2.17)
rear = build_wheels(["wheel_1_back", "wheel_2_back"], "R", 1.38)
wheels = front + rear
WHEEL_R = (bounds(front[0])[2][1] - bounds(front[0])[2][0]) / 2
lift = WHEEL_R - front[0].location.z
print("wheel radius", round(WHEEL_R, 3), "lift", round(lift, 3))
for ob in bpy.data.objects:
    if ob in wheels:
        ob.location.z += lift
    else:
        ob.data.transform(Matrix.Translation((0, 0, lift)))

# remove roof-mounted clutter hidden inside combined meshes (AC box, rack, antenna): split loose parts, drop high ones
ROOF_Z = bounds(O("2_Exterior_color"))[2][1] - 0.06
for name in ("e_plasticBlack_matteShape", "2_Exterior_color", "metaltBlackShape", "i_blackRubberShape"):
    if name not in bpy.data.objects:
        continue
    ob = O(name)
    select([ob], ob)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")
    pieces = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    keep_parts = []
    for o in pieces:
        (_, _, (z0, z1)) = bounds(o)
        if z0 > ROOF_Z:
            bpy.data.objects.remove(o, do_unlink=True)
        else:
            keep_parts.append(o)
    if keep_parts:
        merged = join(keep_parts, name)

# ---------------------------------------------------------------- livery
img = bpy.data.images.load(TEX)
img.colorspace_settings.name = "sRGB"
M_LIVERY = new_mat("Livery", image=img, rough=0.30, coat=0.35)
for ob in bpy.data.objects:
    if any(m and m.name.startswith("Car Paint") for m in ob.data.materials):
        paint(ob, "carpaint")
# fill the side and rear windows with body panels
for n in ("e_windowsShape", "e_sideDoor_windowsShape", "e_backLeftDoor_windowsShape", "e_backRightDoor_windowsShape",
          "e_sideDoor_glassClear", "e_sideDoor_glassTint", "e_backLeftDoor_glassClear", "e_backLeftDoor_glassTint",
          "e_backRightDoor_glassClear", "e_backRightDoor_glassTint"):
    if n in bpy.data.objects:
        paint(O(n), "all")
for n in ("e_glassClear", "e_glassTint"):             # windscreen + long side windows share one mesh
    if n in bpy.data.objects:
        paint(O(n), "all", y_min=-0.95)
make_lens("glow_white", "Headlight_Lens", (0.9, 0.9, 0.93), (1.0, 0.98, 0.9))


def map_planar(obj, region, mat_index, a_axis, bounds_ab, flip_u=False):
    """Planar UVs for faces of one material slot: u from a_axis ('x' or 'y'), v from z."""
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = me.uv_layers.active.data
    u0, v0, u1, v1 = uv_rect(region)
    a0, a1, b0, b1 = bounds_ab
    for poly in me.polygons:
        if poly.material_index != mat_index:
            continue
        for li in poly.loop_indices:
            pt = me.vertices[me.loops[li].vertex_index].co
            a = pt.x if a_axis == "x" else pt.y
            u = (a - a0) / (a1 - a0)
            if flip_u:
                u = 1 - u
            v = (pt.z - b0) / (b1 - b0)
            uv[li].uv = (u0 + u * (u1 - u0), v0 + v * (v1 - v0))


# number plates: swap the Crafter sign texture for the California plate
M_PLATE = new_mat("Plate", image=img, rough=0.5)
for name, flip in (("e_signShape", False), ("e_signShape_back", True)):
    if name in bpy.data.objects:
        ob = O(name)
        for i, m in enumerate(ob.data.materials):
            if m and "sign" in m.name.lower():
                ob.data.materials[i] = M_PLATE
                (x0, x1), _, (z0, z1) = bounds(ob)
                map_planar(ob, "plate_eu", i, "x", (x0, x1, z0, z1), flip_u=flip)

# Ford oval on the grille centre (replaces the VW badge position)
M_FORD = new_mat("FordBadge", image=img, rough=0.25, metal=0.3)
bmf = bmesh.new()
gy = bounds(O("radiatorGrille_6KA"))[1][0] - 0.012 if "radiatorGrille_6KA" in bpy.data.objects else bounds(O("2_Exterior_color"))[1][0] - 0.01
gz = sum(bounds(O("radiatorGrille_6KA"))[2]) / 2 if "radiatorGrille_6KA" in bpy.data.objects else 0.8
vs = [bmf.verts.new((x, gy, z)) for x, z in ((-0.11, gz - 0.044), (0.11, gz - 0.044), (0.11, gz + 0.044), (-0.11, gz + 0.044))]
bmf.faces.new(vs)
bmesh.ops.recalc_face_normals(bmf, faces=bmf.faces)
for f in bmf.faces:
    if f.normal.y > 0:
        bmesh.ops.reverse_faces(bmf, faces=[f])
me_f = bpy.data.meshes.new("FordBadge"); bmf.to_mesh(me_f); bmf.free()
ford = bpy.data.objects.new("FordBadge", me_f); link(ford)
me_f.materials.append(M_FORD)
map_planar(ford, "ford", 0, "x", (-0.11, 0.11, gz - 0.044, gz + 0.044))
# strip the VW roundel and the "CRAFTER" lettering from the rear doors (chrome faces in those regions)
for ob in bpy.data.objects:
    if ob.type != "MESH" or not ob.data.materials:
        continue
    chrome_idx = {i for i, m in enumerate(ob.data.materials) if m and ("chrome" in m.name.lower() or "metalgrey" in m.name.lower()
                  or (ob.name.startswith("e_back") and "plasticblack" in m.name.lower()))}
    if not chrome_idx:
        continue
    bmr = bmesh.new(); bmr.from_mesh(ob.data)
    kill = []
    for f in bmr.faces:
        if f.material_index not in chrome_idx:
            continue
        c = f.calc_center_median()
        if c.y > 2.55 and ((abs(c.x) < 0.14 and 0.85 < c.z < 1.32) or (0.40 < c.x < 0.80 and 0.80 < c.z < 0.95)):
            kill.append(f)
    if kill:
        bmesh.ops.delete(bmr, geom=kill, context="FACES")
        bmr.to_mesh(ob.data)
        print("stripped", len(kill), "badge faces from", ob.name)
    bmr.free()
# hide whatever VW emblem geometry sits on the grille centre
for ob in list(bpy.data.objects):
    if ob.type == "MESH" and ("logo" in ob.name.lower() or "emblem" in ob.name.lower() or "znachok" in ob.name.lower()):
        bpy.data.objects.remove(ob, do_unlink=True)
make_lens("glow_red", "Taillight_Lens", (0.6, 0.05, 0.05), (1.0, 0.08, 0.05))

# ---------------------------------------------------------------- hierarchy + door pivots
root = bpy.data.objects.new("ClerkVan", None); link(root)
body = O("2_Exterior_color"); body.name = "Body"

def group(key):
    return [o for o in bpy.data.objects if o.type == "MESH" and key in o.name]

def door_pivot(name, key, hinge):
    piv = bpy.data.objects.new(name, None); link(piv)
    piv.location = hinge
    parent(piv, body)
    for o in group(key):
        parent(o, piv)
    return piv

(bx, by, bz) = bounds(O("e_driveDoor_Exterior_color"))
door_fl = door_pivot("Door_FL", "driveDoor", (bx[1] - 0.02, by[0], 1.0))
(bx, by, bz) = bounds(O("e_passengerDoor_Exterior_color"))
door_fr = door_pivot("Door_FR", "passengerDoor", (bx[0] + 0.02, by[0], 1.0))
(bx, by, bz) = bounds(O("e_sideDoor_Exterior_color"))
door_sl = door_pivot("Door_Slide", "sideDoor", (bx[0], (by[0] + by[1]) / 2, 1.0))
(bx, by, bz) = bounds(O("e_backLeftDoor_Exterior_color"))
door_rl = door_pivot("Door_RL", "backLeftDoor", (bx[1] - 0.01, by[1] - 0.02, 1.0))
(bx, by, bz) = bounds(O("e_backRightDoor_Exterior_color"))
door_rr = door_pivot("Door_RR", "backRightDoor", (bx[0] + 0.01, by[1] - 0.02, 1.0))
for d in (door_fl, door_fr, door_sl, door_rl, door_rr):
    d.rotation_mode = "XYZ"

# wheels under steer pivots / root
for w in wheels:
    w.rotation_mode = "XYZ"
    if w.name.startswith("Wheel_F"):
        st = bpy.data.objects.new("Steer_" + w.name[-1], None); link(st)
        st.location = w.location.copy(); parent(st, root)
        w.location = (0, 0, 0); w.parent = st
    else:
        parent(w, root)
parent(body, root)
for ob in list(bpy.data.objects):
    if ob.parent is None and ob is not root:
        parent(ob, body)

# ---------------------------------------------------------------- lights (KHR_lights_punctual)
def add_light(name, kind, loc, energy, color, rot=None):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy; ld.color = color
    if kind == "SPOT":
        ld.spot_size = math.radians(70); ld.spot_blend = 0.6
    ob = bpy.data.objects.new(name, ld); link(ob)
    ob.location = loc
    if rot:
        ob.rotation_euler = rot
    parent(ob, body)

yF = bounds(body)[1][0]; yR = bounds(body)[1][1]
for sx, nm in ((1, "Light_HeadL"), (-1, "Light_HeadR")):
    add_light(nm, "SPOT", (sx * 0.70, yF - 0.05, 0.80), 60.0, (1.0, 0.97, 0.88), rot=(math.radians(-85), 0, 0))
for sx, nm in ((1, "Light_TailL"), (-1, "Light_TailR")):
    add_light(nm, "POINT", (sx * 0.90, yR + 0.08, 1.05), 8.0, (1.0, 0.08, 0.05))

# ---------------------------------------------------------------- decimate heavy meshes (web / Godot friendliness)
for ob in bpy.data.objects:
    if ob.type == "MESH" and len(ob.data.polygons) > DECIMATE_ABOVE:
        m = ob.modifiers.new("decimate", "DECIMATE")
        m.ratio = 0.5
        m.use_collapse_triangulate = True

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
    track.strips.new(clip, int(keys[0][0]), act)
    obj.animation_data.action = None
    f, val = keys[0]
    if index >= 0:
        v = list(getattr(obj, path)); v[index] = val; setattr(obj, path, v)
    else:
        setattr(obj, path, val)

for ob, clip, keys in ((door_fl, "DoorFL_Open", [(1, 0.0), (30, math.radians(-65))]),
                       (door_fr, "DoorFR_Open", [(1, 0.0), (30, math.radians(65))]),
                       (door_rl, "DoorRL_Open", [(1, 0.0), (30, math.radians(-95))]),
                       (door_rr, "DoorRR_Open", [(1, 0.0), (30, math.radians(95))])):
    add_clip(ob, clip, "rotation_euler", keys, 2)
    add_clip(ob, "AllDoors_Open", "rotation_euler", keys, 2)
L0 = door_sl.location.copy()
slide_keys = [(1, tuple(L0)), (8, (L0.x - 0.10, L0.y, L0.z)), (30, (L0.x - 0.10, L0.y + 1.10, L0.z))]
add_clip(door_sl, "DoorSlide_Open", "location", slide_keys)
add_clip(door_sl, "AllDoors_Open", "location", slide_keys)
for w in wheels:
    add_clip(w, "Wheels_Spin", "rotation_euler", [(1, 0.0), (31, math.radians(360))], 0)
scene.frame_start, scene.frame_end = 1, 30
bpy.context.view_layer.update()

# ---------------------------------------------------------------- export
bpy.ops.object.select_all(action="DESELECT")
glb = os.path.join(EXPORT, "clerk_van.glb")
bpy.ops.export_scene.gltf(
    filepath=glb, export_format="GLB", export_apply=True, export_lights=True,
    export_animations=True, export_animation_mode="NLA_TRACKS", export_image_format="AUTO",
    export_yup=True, use_selection=False, export_extras=True, export_cameras=False,
    export_materials="EXPORT", export_normals=True, export_texcoords=True,
)
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
print(f"BUILD OK  objects={len(bpy.data.objects)} faces={tris}  glb={glb} size={os.path.getsize(glb)/1e6:.2f} MB  wheel_r={WHEEL_R:.3f}")
