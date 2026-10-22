"""
Clerk Van on the "Ford Transit With Light Bar" asset (circlegent, Sketchfab, CC-BY):
references/transit/transit.glb -> export/clerk_van.glb + .blend (+ copies in web/ and godot/).

What this does to the asset: strips the roof light bar, roof rails and the interior shelving of the
conversion, closes the sliding door, scales the model to metres (wheelbase 3.75 m), centres it, repaints
every body-colour panel with the Clerk livery atlas (textures/clerk_van_atlas_transit.png, box projection
in metres, no photo projection), fills the rear-door glass, and rigs doors / wheels / lights / clips with
the same node names as the other builds.   blender --background --python tools/build_transit_van.py -- <root>
"""
import bpy, bmesh, math, os, sys, json, shutil
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = os.path.abspath(argv[0]) if argv else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "references", "transit", "transit.glb")
TEX = os.path.join(ROOT, "textures", "clerk_van_atlas_transit.png")
LAYOUT = json.load(open(os.path.join(ROOT, "textures", "atlas_layout_transit.json")))
PROF = json.load(open(os.path.join(ROOT, "tools", "profiles", "transit.json")))
EXPORT = os.path.join(ROOT, "export")
os.makedirs(EXPORT, exist_ok=True)
ATLAS = LAYOUT["size"]; R = LAYOUT["regions"]

# asset units -> metres (wheelbase 4.449 units = 3.75 m), centre of the body in asset units
S = 3.75 / 4.449
CX, CY = 1.51, 3.53
def M(x, y, z):
    return Vector(((x - CX) * S, (y - CY) * S, z * S))

# ---------------------------------------------------------------- helpers
def link(ob):
    bpy.context.scene.collection.objects.link(ob); return ob

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

def centre(ob):
    (x0, x1), (y0, y1), (z0, z1) = bounds(ob)
    return Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))

def select(objs, active=None):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or objs[0]

def join(objs, name):
    select(objs, objs[0]); bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active; ob.name = name; return ob

def new_mat(name, color=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, image=None, alpha=1.0, emissive=None, coat=0.0):
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
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            m.blend_method = "BLEND"
        m.show_transparent_back = False
    if emissive is not None:
        bsdf.inputs["Emission Color"].default_value = (*emissive, 1.0); bsdf.inputs["Emission Strength"].default_value = 0.0
    return m

def uv_rect(region):
    x0, y0, x1, y1 = R[region]
    return (x0 / ATLAS, 1 - y1 / ATLAS, x1 / ATLAS, 1 - y0 / ATLAS)

def project_uv(obj, mat_indices):
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = me.uv_layers.active.data
    ext = LAYOUT["extents"]
    mw = obj.matrix_world; nm = mw.to_3x3().inverted().transposed()
    for poly in me.polygons:
        if poly.material_index not in mat_indices:
            continue
        n = (nm @ poly.normal).normalized()
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        c = mw @ poly.center
        if c.z > ROOF_Z - 0.10 and az > 0.4:
            mode = "top"
        elif abs(c.x) > 0.74 and c.z < ROOF_Z - 0.05:
            mode = "side"
        elif c.y > YR_Z - 0.45 and c.z > 0.3:
            mode = "rear"
        elif c.y < YF_Z + 0.9 and c.z < 1.45 and n.z > 0.3:
            mode = "top"
        elif c.y < YF_Z + 0.7:
            mode = "front"
        else:
            mode = "side" if ax >= ay and ax >= az else ("front" if n.y < 0 else "rear") if ay >= az else ("top" if n.z > 0 else "bottom")
        sx = 1 if (c.x > 0 if mode == "side" else n.x > 0) else -1
        for li in poly.loop_indices:
            p = mw @ me.vertices[me.loops[li].vertex_index].co
            if mode == "side":
                a0, a1, b0, b1 = ext["side"]; v = (p.z - b0) / (b1 - b0)
                if sx > 0:
                    u = (p.y - a0) / (a1 - a0); reg = "side_left"
                else:
                    u = (a1 - p.y) / (a1 - a0); reg = "side_right"
            elif mode == "front":
                a0, a1, b0, b1 = ext["front"]; v = (p.z - b0) / (b1 - b0); u = (p.x - a0) / (a1 - a0); reg = "front"
            elif mode == "rear":
                a0, a1, b0, b1 = ext["front"]; v = (p.z - b0) / (b1 - b0); u = (a1 - p.x) / (a1 - a0); reg = "rear"
            elif mode == "top":
                a0, a1, b0, b1 = ext["top"]; u = (a1 - p.x) / (a1 - a0); v = (b1 - p.y) / (b1 - b0); reg = "top"
            else:
                u, v, reg = 0.5, 0.5, "bottom"
            u0, v0, u1, v1 = uv_rect(reg)
            uv[li].uv = (u0 + u * (u1 - u0), v0 + v * (v1 - v0))
            continue
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
            uv[li].uv = (u0 + u * (u1 - u0), v0 + v * (v1 - v0))

def set_origin(ob, pivot):
    pv = Vector(pivot); ob.data.transform(Matrix.Translation(-pv)); ob.location = pv

# ---------------------------------------------------------------- import + normalise
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
scene = bpy.context.scene; scene.render.fps = 30
bpy.context.view_layer.update()
for ob in list(bpy.data.objects):
    if ob.type != "MESH":
        continue
    ob.data = ob.data.copy()
    mw = ob.matrix_world.copy(); ob.parent = None; ob.matrix_world = Matrix(); ob.data.transform(mw)
    ob.rotation_mode = "XYZ"
for ob in list(bpy.data.objects):
    if ob.type != "MESH":
        bpy.data.objects.remove(ob, do_unlink=True)
for ob in bpy.data.objects:
    ob.animation_data_clear()

def O(n):
    return bpy.data.objects[n]

# ---- strip roof light bar / rails / beacon and the conversion's interior shelving (asset units)
ROOF_CLUTTER = {"3DGeom-32", "3DGeom-92", "3DGeom-108", "3DGeom-185", "3DGeom-84", "3DGeom-154", "3DGeom-164", "3DGeom-5", "3DGeom-186", "3DGeom-87",
                "3DGeom-187", "3DGeom-188", "3DGeom-189", "3DGeom-190",   # + roof clearance-lamp boxes
                "3DGeom-184", "3DGeom-91", "3DGeom-111", "3DGeom-63"}   # + chrome TRANSIT lettering on the rear door                    # + conversion decals/strips + floor sill plate
for ob in list(bpy.data.objects):
    if ob.name == "3DGeom-1":
        continue
    (x0, x1), (y0, y1), (z0, z1) = bounds(ob)
    cx_, cy_, cz_ = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    inside = 0.5 < cx_ < 2.5 and 2.8 < cy_ < 6.75 and cz_ > 0.55 and (x1 - x0) < 1.9 and (y1 - y0) < 3.5   # shelving / partitions inside the cargo box
    if ob.name in ROOF_CLUTTER or inside:
        bpy.data.objects.remove(ob, do_unlink=True)

# ---- sliding door: the asset ships it slid open, raised, with an open window aperture and an open step well.
# Instead of repairing it, the closed door is rebuilt later by mirroring the driver-side flank (see "mirrored sliding door").
for n in ("3DGeom-7", "3DGeom-6"):
    if n in bpy.data.objects:
        bpy.data.objects.remove(O(n), do_unlink=True)
_c3 = O("3DGeom-3")                                   # drop the door's lower cladding exported at the open position
_bm = bmesh.new(); _bm.from_mesh(_c3.data)
bmesh.ops.delete(_bm, geom=[f for f in _bm.faces if f.calc_center_median().y > CY - 0.9 and f.calc_center_median().x < CX], context="FACES")
_bm.to_mesh(_c3.data); _bm.free()

# ---- rear-door glass: paint it like the doors (the captures have blind rear doors)
glass = O("3DGeom-8")
bm = bmesh.new(); bm.from_mesh(glass.data)
rear = [f for f in bm.faces if f.calc_center_median().y > 6.5]
if rear:
    me_r = bpy.data.meshes.new("RearBlank"); nb = bmesh.new(); vm = {}
    for f in rear:
        vs_ = []
        for v in f.verts:
            if v.index not in vm:
                vm[v.index] = nb.verts.new(v.co)
            vs_.append(vm[v.index])
        try:
            nb.faces.new(vs_)
        except ValueError:
            pass
    nb.to_mesh(me_r); nb.free()
    rb = bpy.data.objects.new("RearBlank", me_r); link(rb)
    ib = bmesh.new(); ib.from_mesh(me_r); bmesh.ops.translate(ib, vec=(0, -0.015, 0), verts=ib.verts); bmesh.ops.reverse_faces(ib, faces=ib.faces)
    me_ri = bpy.data.meshes.new("RearBlankInner"); ib.to_mesh(me_ri); ib.free()
    rbi = bpy.data.objects.new("RearBlankInner", me_ri); link(rbi)
    bmesh.ops.delete(bm, geom=rear, context="FACES")
bm.to_mesh(glass.data); bm.free()

# ---- scale to metres and centre
SM = Matrix.Diagonal((S, S, S, 1.0)) @ Matrix.Translation((-CX, -CY, 0))
for ob in bpy.data.objects:
    ob.data.transform(SM)
body = O("3DGeom-1"); body.name = "Body"
(BX, BY, BZ) = bounds(body)
YF, YR, ROOF = BY[0], BY[1], BZ[1]
ROOF_Z, YF_Z, YR_Z = ROOF, YF, YR

# ---- roof patch: the light-bar mount left a hole in the roof skin; cover it with a plate following the roof curve
_mwb = body.matrix_world; _nmb = _mwb.to_3x3().inverted().transposed()
_top = [(_mwb @ p.center) for p in body.data.polygons if (_nmb @ p.normal).z > 0.5 and (_mwb @ p.center).z > 2.45 and 0.6 < (_mwb @ p.center).y < 1.6 and abs((_mwb @ p.center).x) < 0.78]
_prof = []
for x in [i / 10 for i in range(-7, 8)]:
    zs = [c.z for c in _top if abs(c.x - x) < 0.08]
    if zs:
        _prof.append((x, max(zs) - 0.010))     # just under the rib crests so the patch never pokes through the skin
_rb = bmesh.new()
_ys = (-0.02, 0.54)                    # the mount cut-out spans y 0.03..0.48, x -0.32..0.08 (ray-cast); patch only that strip
_prof = [(x, z) for x, z in _prof if -0.45 <= x <= 0.25]
_grid = [[_rb.verts.new((x, y, z)) for (x, z) in _prof] for y in _ys]
for i in range(len(_prof) - 1):
    _rb.faces.new([_grid[0][i], _grid[0][i + 1], _grid[1][i + 1], _grid[1][i]])
bmesh.ops.recalc_face_normals(_rb, faces=_rb.faces)
for f in _rb.faces:
    if f.normal.z < 0:
        bmesh.ops.reverse_faces(_rb, faces=[f])
_mr = bpy.data.meshes.new("RoofPatch"); _rb.to_mesh(_mr); _rb.free()
roof_patch = bpy.data.objects.new("RoofPatch", _mr); link(roof_patch)
print("roof patch profile", [(x, round(z, 3)) for x, z in _prof])


# ---- mirrored sliding door: copy the driver-side flank over the passenger-side opening (x -> -x)
def _boundary_pts(ob, pred):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    pts = [ob.matrix_world @ ((e.verts[0].co + e.verts[1].co) / 2) for e in bm.edges if len(e.link_faces) == 1]
    bm.free()
    return [p for p in pts if pred(p)]
_mw = body.matrix_world; _nm = _mw.to_3x3().inverted().transposed()
_ys = sorted((_mw @ p.center).y for p in body.data.polygons
             if (_mw @ p.center).x < -0.8 and (_nm @ p.normal).x < -0.6 and 0.9 < (_mw @ p.center).z < 2.2 and -1.6 < (_mw @ p.center).y < 1.6)
_gap = max(zip(_ys, _ys[1:]), key=lambda t: t[1] - t[0])
SL_Y0, SL_Y1 = _gap
SL_Z0, SL_Z1 = 0.26, max(p.z for p in _boundary_pts(body, lambda p: p.x < -0.7 and SL_Y0 + 0.2 < p.y < SL_Y1 - 0.2)) + 0.01
print(f"slide opening y=({SL_Y0:.3f},{SL_Y1:.3f}) z top={SL_Z1:.3f}")


def mirror_strip(src, name, y0, y1, z0, z1, xmin=0.3):
    """Faces of src with centre in the box (driver side) -> new object mirrored to the passenger side."""
    bm = bmesh.new(); bm.from_mesh(src.data)
    mw = src.matrix_world
    sel = [f for f in bm.faces if (lambda c: c.x > xmin and y0 < c.y < y1 and z0 < c.z < z1)(mw @ f.calc_center_median())]
    nb = bmesh.new(); vm = {}
    for f in sel:
        vs_ = []
        for v in f.verts:
            if v.index not in vm:
                w = mw @ v.co
                vm[v.index] = nb.verts.new((-w.x, w.y, w.z))
            vs_.append(vm[v.index])
        try:
            nf = nb.faces.new(list(reversed(vs_))); nf.material_index = f.material_index; nf.smooth = f.smooth
        except ValueError:
            pass
    bm.free()
    me = bpy.data.meshes.new(name); nb.to_mesh(me); nb.free()
    for m in src.data.materials:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me); link(ob); ob.rotation_mode = "XYZ"
    return ob


sl = mirror_strip(body, "Door_Slide_skin", SL_Y0 + 0.006, SL_Y1 - 0.006, SL_Z0, SL_Z1 - 0.004)
sl_clad = []
for n in ("3DGeom-2", "3DGeom-3"):
    if n in bpy.data.objects:
        c = mirror_strip(O(n), "Door_Slide_clad_" + n[-1], SL_Y0 + 0.006, SL_Y1 - 0.006, 0.2, 1.0)
        if len(c.data.polygons):
            sl_clad.append(c)
        else:
            bpy.data.objects.remove(c, do_unlink=True)
print("mirrored door faces", len(sl.data.polygons), "cladding pieces", [len(c.data.polygons) for c in sl_clad])


# ---------------------------------------------------------------- materials
img = bpy.data.images.load(TEX); img.colorspace_settings.name = "sRGB"
M_LIVERY = new_mat("Livery", image=img, rough=0.30, coat=0.25)
M_CLAD = new_mat("Cladding", (0.045, 0.047, 0.052), rough=0.6)
M_INNER = new_mat("DoorInner", (0.03, 0.03, 0.034), rough=0.85)
if "RearBlankInner" in bpy.data.objects:
    bpy.data.objects["RearBlankInner"].data.materials.append(M_INNER)

def inner_faces_to_interior(ob, livery_idx):
    """Faces of livery slots whose normal points into the vehicle (door inner skins) get the dark interior material."""
    me = ob.data
    if M_INNER.name not in [m.name for m in me.materials if m]:
        me.materials.append(M_INNER)
    inner = [i for i, m in enumerate(me.materials) if m and m.name == M_INNER.name][0]
    mw = ob.matrix_world; nm = mw.to_3x3().inverted().transposed()
    n_in = 0
    for p in me.polygons:
        if p.material_index not in livery_idx:
            continue
        c = mw @ p.center; n = (nm @ p.normal).normalized()
        d = Vector((c.x, 0.0, c.z - 1.3)); d.y = 0.0
        if c.y > 2.6:
            d = Vector((0.0, 1.0, 0.0))
        elif c.y < -2.6:
            d = Vector((0.0, -1.0, 0.0))
        if d.length > 0.2 and n.dot(d.normalized()) < -0.35:
            p.material_index = inner; n_in += 1
    return n_in
M_GLASS = new_mat("Glass", (0.05, 0.06, 0.08), rough=0.03, alpha=0.45)
BODY_MATS = ("[Color M00]", "[Color M00]1")
for ob in bpy.data.objects:
    if ob.type != "MESH":
        continue
    me = ob.data
    idx = set()
    for i, m in enumerate(me.materials):
        if m and m.name in BODY_MATS:
            me.materials[i] = M_LIVERY; idx.add(i)
        elif m and m.name in ("[Color M09]", "[Color M07]"):
            me.materials[i] = M_CLAD
        elif m and m.name.endswith("_windows"):
            me.materials[i] = M_GLASS
    if ob.name in ("RearBlank", "SlideHeader", "RoofPatch"):
        me.materials.clear(); me.materials.append(M_LIVERY)
        for p in me.polygons:
            p.material_index = 0
        idx = {0}
    if idx:
        project_uv(ob, idx)
        inner_faces_to_interior(ob, idx)

# front-door window frames come with their own white texture; paint them with the livery so the black band
# starts at the B-pillar exactly as in the captures
for n in ("3DGeom-66", "3DGeom-73"):
    if n in bpy.data.objects:
        ob = O(n); ob.data.materials.clear(); ob.data.materials.append(M_LIVERY)
        for p in ob.data.polygons:
            p.material_index = 0
        project_uv(ob, {0}); inner_faces_to_interior(ob, {0})


def retag(src, new_name, color, emissive):
    m = bpy.data.materials.get(src)
    if not m:
        return
    m.name = new_name
    bs = m.node_tree.nodes.get("Principled BSDF")
    if bs:
        bs.inputs["Alpha"].default_value = 1.0
        bs.inputs["Emission Color"].default_value = (*emissive, 1); bs.inputs["Emission Strength"].default_value = 0.0
        if not bs.inputs["Base Color"].is_linked:
            bs.inputs["Base Color"].default_value = (*color, 1)
    try:
        m.surface_render_method = "DITHERED"
    except Exception:
        pass
retag("Lights", "Headlight_Lens", (0.72, 0.75, 0.82), (1.0, 0.98, 0.9))
hl = bpy.data.materials.get("Headlight_Lens")
if hl:
    bs = hl.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Roughness"].default_value = 0.08
    bs.inputs["Metallic"].default_value = 0.6
    try:
        bs.inputs["Coat Weight"].default_value = 1.0
    except KeyError:
        pass
for ob in bpy.data.objects:                           # roof clearance lamps / roof-side bits: painted over like the wrap
    if ob.type != "MESH" or ob is body:
        continue
    (x0, x1), (y0, y1), (z0, z1) = bounds(ob)
    small = (x1 - x0) < 0.35 and (y1 - y0) < 0.5 and (z1 - z0) < 0.35
    if (z0 > 2.1 and small and abs((x0 + x1) / 2) > 0.7) or not any(m for m in ob.data.materials):
        ob.data.materials.clear(); ob.data.materials.append(M_LIVERY)
        for p in ob.data.polygons:
            p.material_index = 0
        project_uv(ob, {0})
retag("2019  Ford Transit Hightop_tcm_redglass", "Taillight_Lens", (0.6, 0.05, 0.05), (1.0, 0.08, 0.05))

# ---------------------------------------------------------------- doors
def separate(ob, name, pred):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    sel = [f for f in bm.faces if pred(f.calc_center_median())]
    if not sel:
        bm.free(); return None
    nb = bmesh.new(); vm = {}
    for f in sel:
        vs_ = []
        for v in f.verts:
            if v.index not in vm:
                vm[v.index] = nb.verts.new(v.co)
            vs_.append(vm[v.index])
        try:
            nf = nb.faces.new(vs_); nf.material_index = f.material_index; nf.smooth = f.smooth
        except ValueError:
            pass
    bmesh.ops.delete(bm, geom=sel, context="FACES"); bm.to_mesh(ob.data); bm.free()
    me = bpy.data.meshes.new(name); nb.to_mesh(me); nb.free()
    for m in ob.data.materials:
        me.materials.append(m)
    if ob.data.uv_layers:
        pass
    n = bpy.data.objects.new(name, me); link(n); n.rotation_mode = "XYZ"
    liv = {i for i, m in enumerate(me.materials) if m is M_LIVERY}
    project_uv(n, liv)
    inner_faces_to_interior(n, liv)
    return n

YRD = M(0, 6.75, 0).y           # rear door faces are behind this
rl = separate(body, "Door_RL_skin", lambda c: c.y > YRD and 0.0 < c.x < 1.0 and 0.42 < c.z < 2.5)
rr = separate(body, "Door_RR_skin", lambda c: c.y > YRD and -1.0 < c.x < 0.0 and 0.42 < c.z < 2.5)

def door_pivot(name, hinge, members):
    piv = bpy.data.objects.new(name, None); link(piv); piv.location = hinge; piv.rotation_mode = "XYZ"
    parent(piv, body)
    for o in members:
        parent(o, piv)
    return piv

def members(pred):
    out = []
    for o in bpy.data.objects:
        if o.type != "MESH" or o is body:
            continue
        (x0, x1), (y0, y1), (z0, z1) = bounds(o)
        if pred(Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)), x1 - x0, y1 - y0, z1 - z0):
            out.append(o)
    return out

# ---- mirror housings: white paint (not the livery), grey indicator pods untouched
M_WHITE = new_mat("MirrorPaint", (0.90, 0.90, 0.92), rough=0.35, coat=0.3)
mir_l = separate(body, "Mirror_L_housing", lambda c: c.x > 1.02 and -1.95 < c.y < -0.75 and 0.85 < c.z < 1.65)
mir_r = separate(body, "Mirror_R_housing", lambda c: c.x < -1.02 and -1.95 < c.y < -0.75 and 0.85 < c.z < 1.65)
for ob in (mir_l, mir_r, bpy.data.objects.get("3DGeom-76")):
    if ob is None:
        continue
    ob.data.materials.clear(); ob.data.materials.append(M_WHITE)
    for pl in ob.data.polygons:
        pl.material_index = 0

# ---- window surround: the driver side has a separate frame mesh (3DGeom-76, now white); the passenger
# frame is plain door skin, so paint a band of skin faces around the glass white with the same width
def _boundary_segments(ob):
    bm = bmesh.new(); bm.from_mesh(ob.data); mw = ob.matrix_world
    segs = [((mw @ e.verts[0].co), (mw @ e.verts[1].co)) for e in bm.edges if len(e.link_faces) == 1]
    bm.free()
    return [((a.y, a.z), (b.y, b.z)) for a, b in segs]


def _dist_to_segs(pt, segs):
    px, py = pt; best = 1e9
    for (ax, ay), (bx, by) in segs:
        dx, dy = bx - ax, by - ay
        t = 0.0 if dx == 0 and dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        qx, qy = ax + t * dx, ay + t * dy
        best = min(best, ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5)
    return best


def _frame_width(frame_ob, glass_ob):
    segs = _boundary_segments(glass_ob); mw = frame_ob.matrix_world
    ds = sorted(_dist_to_segs(((mw @ p.center).y, (mw @ p.center).z), segs) for p in frame_ob.data.polygons
                if abs((mw @ p.center).x) < 1.03 and 1.2 < (mw @ p.center).z < 2.05)
    return ds[int(len(ds) * 0.9)] if ds else 0.06


if "3DGeom-76" in bpy.data.objects:
    # the driver mesh 3DGeom-76 = mirror housing + window surround; mirror just the surround (x < 1.03) onto the
    # passenger door, which has no frame mesh of its own
    src = O("3DGeom-76"); mw = src.matrix_world
    bm = bmesh.new(); bm.from_mesh(src.data)
    sel = [f for f in bm.faces if (mw @ f.calc_center_median()).x < 1.03]
    nb = bmesh.new(); vm = {}
    for f in sel:
        vs_ = []
        for v in f.verts:
            if v.index not in vm:
                w = mw @ v.co; vm[v.index] = nb.verts.new((-w.x, w.y, w.z))
            vs_.append(vm[v.index])
        try:
            nf = nb.faces.new(list(reversed(vs_))); nf.smooth = f.smooth
        except ValueError:
            pass
    bm.free()
    me_f = bpy.data.meshes.new("Mirror_R_frame"); nb.to_mesh(me_f); nb.free(); me_f.materials.append(M_WHITE)
    frame_r = bpy.data.objects.new("Mirror_R_frame", me_f); link(frame_r); frame_r.rotation_mode = "XYZ"
    print("passenger window frame faces", len(me_f.polygons))
    # door handles: black on both sides (the captures show body-colour handles on the black band).
    # driver lever lives in 3DGeom-76 -> black paint slot; the passenger skin already has its own lever,
    # so drop the mirrored copy to avoid two coincident levers
    M_HANDLE = new_mat("HandlePaint", (0.03, 0.03, 0.034), rough=0.45, coat=0.3)
    src.data.materials.append(M_HANDLE); hi = len(src.data.materials) - 1
    n_h = 0
    for pl in src.data.polygons:
        c = mw @ pl.center
        if 0.9 < c.x < 1.01 and -1.05 < c.y < -0.72 and 1.1 < c.z < 1.26:
            pl.material_index = hi; n_h += 1
    bm2 = bmesh.new(); bm2.from_mesh(me_f)
    kill = [f for f in bm2.faces if (lambda c: -1.01 < c.x < -0.9 and -1.05 < c.y < -0.72 and 1.1 < c.z < 1.26)(f.calc_center_median())]
    bmesh.ops.delete(bm2, geom=kill, context="FACES"); bm2.to_mesh(me_f); bm2.free()
    print("handle faces: driver painted", n_h, "passenger copies removed", len(kill))

# ---- black trim: wiper arms and the antenna are part of the Body mesh and were taking the livery
# (white hood, black band). Wipers = small mesh islands lying on the cowl; antenna = the thin column
# ahead of the passenger A-pillar.
M_TRIM = new_mat("BlackTrim", (0.02, 0.02, 0.022), rough=0.6)
body.data.materials.append(M_TRIM); ti = len(body.data.materials) - 1
me_b = body.data; mw_b = body.matrix_world
uf_par = list(range(len(me_b.polygons))); uf_key = {}
def _find(a):
    while uf_par[a] != a:
        uf_par[a] = uf_par[uf_par[a]]; a = uf_par[a]
    return a
for pl in me_b.polygons:
    for vi in pl.vertices:
        k = tuple(round(c, 5) for c in me_b.vertices[vi].co)
        if k in uf_key:
            ra, rb = _find(uf_key[k]), _find(pl.index)
            if ra != rb: uf_par[ra] = rb
        else:
            uf_key[k] = pl.index
uf_groups = {}
for pl in me_b.polygons: uf_groups.setdefault(_find(pl.index), []).append(pl.index)
WIPER_BOX = ((-0.9, -2.35, 1.27), (0.9, -2.0, 1.45))
n_w = 0
for idx in uf_groups.values():
    if len(idx) > 3000: continue
    pts = [mw_b @ me_b.vertices[vi].co for i in idx for vi in me_b.polygons[i].vertices]
    lo = [min(p[i] for p in pts) for i in range(3)]; hi = [max(p[i] for p in pts) for i in range(3)]
    if all(lo[i] >= WIPER_BOX[0][i] and hi[i] <= WIPER_BOX[1][i] for i in range(3)):
        for i in idx: me_b.polygons[i].material_index = ti
        n_w += len(idx)
n_a = 0
for pl in me_b.polygons:
    c = mw_b @ pl.center
    if -0.9 < c.x < -0.8 and -2.12 < c.y < -2.04 and 1.36 < c.z < 2.25:
        pl.material_index = ti; n_a += 1
print("black trim faces: wipers", n_w, "antenna", n_a)

FD = (M(0, 1.29, 0).y, M(0, 2.75, 0).y)       # front door y range
fl = members(lambda c, w, l, h: c.x > 0.75 and FD[0] < c.y < FD[1] and 0.3 < c.z < 2.1 and w < 0.8)
fr = members(lambda c, w, l, h: c.x < -0.75 and FD[0] < c.y < FD[1] and 0.3 < c.z < 2.1 and w < 0.8)
door_fl = door_pivot("Door_FL", (BX[1] - 0.03, FD[0], 1.1), fl)
door_fr = door_pivot("Door_FR", (BX[0] + 0.03, FD[0], 1.1), fr)
slc = centre(sl)
door_sl = door_pivot("Door_Slide", (BX[0] + 0.03, slc.y, 1.1), [sl] + sl_clad)
rlm = [rl] + members(lambda c, w, l, h: c.y > YRD and 0.0 < c.x < 1.0 and 0.42 < c.z < 2.5 and w < 1.2 and "Lens" not in "".join(m.name for m in bpy.data.objects[0].data.materials if m))
rrm = [rr] + members(lambda c, w, l, h: c.y > YRD and -1.0 < c.x < 0.0 and 0.42 < c.z < 2.5 and w < 1.2)
rlm = [o for o in rlm if o is not None and not any(m and m.name == "Taillight_Lens" for m in o.data.materials)]
rrm = [o for o in rrm if o is not None and not any(m and m.name == "Taillight_Lens" for m in o.data.materials)]
door_rl = door_pivot("Door_RL", (0.95, YR - 0.02, 1.1), rlm)
door_rr = door_pivot("Door_RR", (-0.95, YR - 0.02, 1.1), rrm)

# ---------------------------------------------------------------- wheels (the asset's own steel wheels)
root = bpy.data.objects.new("ClerkVan", None); link(root)
WHEELS = {"FL": ("3DGeom-48", "3DGeom-11", "3DGeom-10"), "FR": ("3DGeom-20", "3DGeom-44", "3DGeom-36"),
          "RL": ("3DGeom-15", "3DGeom-26", "3DGeom-49"), "RR": ("3DGeom-55", "3DGeom-58", "3DGeom-22")}
wheels = []
for tag, names in WHEELS.items():
    objs = [O(n) for n in names if n in bpy.data.objects]
    w = join(objs, "Wheel_" + tag)
    c = centre(O("Wheel_" + tag)) if False else None
    tyre_c = centre(w)
    set_origin(w, tyre_c)
    w.rotation_mode = "XYZ"
    if tag.startswith("F"):
        st = bpy.data.objects.new("Steer_" + tag[1], None); link(st); st.location = tyre_c; parent(st, root)
        w.location = (0, 0, 0); w.parent = st
    else:
        parent(w, root)
    wheels.append(w)
WHEEL_R = (bounds(wheels[0])[2][1] - bounds(wheels[0])[2][0]) / 2
print("wheel radius", round(WHEEL_R, 3), "front axle y", round(wheels[0].parent.location.y, 3), "rear axle y", round(wheels[2].location.y, 3))

parent(body, root)
for ob in list(bpy.data.objects):
    if ob.type == "MESH" and ob.parent is None and ob is not body:
        parent(ob, body)

# ---------------------------------------------------------------- lights + clips + export
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
slide_keys = [(1, tuple(L0)), (8, (L0.x - 0.10, L0.y, L0.z)), (30, (L0.x - 0.10, L0.y + 1.15, L0.z))]
add_clip(door_sl, "DoorSlide_Open", "location", slide_keys); add_clip(door_sl, "AllDoors_Open", "location", slide_keys)
for w in wheels:
    add_clip(w, "Wheels_Spin", "rotation_euler", [(1, 0.0), (31, math.radians(360))], 0)
scene.frame_start, scene.frame_end = 1, 30
bpy.context.view_layer.update()

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
