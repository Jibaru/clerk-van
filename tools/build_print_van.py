"""
Printable Clerk Van: one watertight shell of the exterior with every livery graphic
(logos, wordmarks, text, QR codes) raised as relief so it shows on a 3D print, coloured
like the display model (livery atlas on the shell, white / purple relief, dark glass and tyres).

Runs in Blender 4.2 headless on the shipped build, after print_mask_polys.py:
  python tools/print_mask_polys.py --profile transit
  blender --background export/clerk_van.blend --python tools/build_print_van.py -- <repo root> [relief_mm] [scale_denominator]

Steps
  1. drop interior / never-visible objects, join the exterior meshes (doors and wheels in the rest pose)
  2. Solidify (closed slabs) + voxel Remesh + Smooth: a closed shell WALL metres thick around every
     exterior surface (an open surface fed straight to the remesher is discarded, hence the slabs)
  3. colours: each shell face takes the material of the nearest original surface (glass, tyre, rim,
     lamp, chrome, dark plastic) or the livery atlas by the same box projection as the display model
  4. relief: the polygons vectorised from the livery masks are built as filled 2-D curves in panel
     metres, extruded, and every vertex is ray-cast onto the shell so the letters follow the body
     (top at surface + RELIEF, base embedded into the shell). Closed solids, unioned by the slicer.
  5. export: export/clerk_van_print.stl (all, mm at 1:SCALE), _body.stl + _relief.stl (two-colour print),
     clerk_van_print.glb (metres, textured) for the web viewer; the GLB is copied to web/.
"""
import bpy, bmesh, os, sys, json, time, shutil
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = os.path.abspath(argv[0]) if argv else os.getcwd()
RELIEF = (float(argv[1]) if len(argv) > 1 else 15.0) / 1000.0   # relief height, metres at full scale (15 mm = 0.6 mm at 1:24)
DENOM = float(argv[2]) if len(argv) > 2 else 24.0                 # STL scale 1:DENOM
WALL = 0.04          # shell thickness, metres at full scale: 1.7 mm at 1:24
VOXEL = 0.0065       # shell voxel size (m): 0.27 mm at 1:24 (5 mm doubles the file sizes)
ADAPT = 0.5          # voxel remesh adaptivity (flat panels collapse to few triangles)
SMOOTH = (0.5, 4)    # Smooth modifier factor, iterations: removes the voxel stair-stepping
TARGET_FACES = 0        # optional edge-collapse decimation; off: it leaves holes the fill step cannot close
EMBED = WALL * 0.5   # how deep the relief solids sink into the shell
TEX = os.path.join(ROOT, "textures")
OUT = os.path.join(ROOT, "export")
LAYOUT = json.load(open(os.path.join(TEX, "atlas_layout_transit.json")))
ATLAS = LAYOUT["size"]; R = LAYOUT["regions"]; EXT = LAYOUT["extents"]
T0 = time.time()


def log(*a):
    print(f"[print {time.time() - T0:6.1f}s]", *a, flush=True)


def open_edges(me):
    """Edges with other than two faces: 0 means watertight."""
    b = bmesh.new()
    b.from_mesh(me)
    n = sum(1 for e in b.edges if len(e.link_faces) != 2)
    b.free()
    return n


scene = bpy.context.scene
for o in bpy.data.objects:            # rest pose, no NLA influence
    if o.animation_data:
        for t in o.animation_data.nla_tracks:
            t.mute = True
scene.frame_set(0)
bpy.context.view_layer.update()
body = bpy.data.objects["Body"]
bb = [body.matrix_world @ Vector(c) for c in body.bound_box]
YF_Z, YR_Z, ROOF_Z = min(v.y for v in bb), max(v.y for v in bb), max(v.z for v in bb)

# ------------------------------------------------------------------ 1. exterior selection
INTERIOR_MATS = ("interior", "seat_fabric", "mat_carpet", "plastic_dash", "transit_lod0", "Metal Steel", "DoorInner")
DROP_NAMES = {"RearBlankInner"}
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
depsgraph = bpy.context.evaluated_depsgraph_get()
DIRS = [Vector(v).normalized() for v in ((1, 0, 0), (-1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, 1),
                                         (0.7, 0, 0.7), (-0.7, 0, 0.7), (0, -0.7, 0.7), (0, 0.7, 0.7), (0.7, 0.7, 0), (-0.7, -0.7, 0))]


def visible_from_outside(o, samples=300):
    """True if a ray from any sampled face escapes the vehicle without hitting another surface."""
    mw = o.matrix_world
    polys = o.data.polygons
    if not polys:
        return False
    step = max(1, len(polys) // samples)
    for i in range(0, len(polys), step):
        p = polys[i]
        c = mw @ p.center
        n = (mw.to_3x3() @ p.normal).normalized()
        for d in DIRS:
            if d.dot(n) < -0.2:
                continue
            hit = scene.ray_cast(depsgraph, c + d * 0.01, d, distance=20)[0]
            if not hit:
                return True
    return False


keep = []
for o in meshes:
    only_inner = bool(o.data.materials) and all((m is None) or any(k in m.name for k in INTERIOR_MATS) for m in o.data.materials)
    if o.name in DROP_NAMES or only_inner:
        continue
    if not visible_from_outside(o):
        continue
    keep.append(o)
log("keeping", len(keep), "objects")


# material class of an original face, used to colour the shell
def mat_class(obj, mat):
    n = mat.name if mat else ""
    if obj.name == "3DGeom-8":            # headlamp cover glass: light like the lamp, not window-dark
        return "lens"
    if "Glass" in n:
        return "glass"
    if "Tyres" in n:
        return "tyre"
    if obj.name.startswith("Wheel_"):
        return "rim"
    if "Lens" in n or "tcm_red" in n:
        return "lens"
    if "chrome" in n:
        return "chrome"
    if any(k in n for k in ("Cladding", "gum1", "brakes", "brushed_metal", "smallspecmap", "ford_logo")):
        return "dark"
    return "livery"


CLASSES = ("glass", "tyre", "rim", "lens", "chrome", "dark", "livery")
class_tris = {c: ([], []) for c in CLASSES}     # verts, tris per class (world space)
bm = bmesh.new()
for o in keep:
    ev = o.evaluated_get(depsgraph)
    me = ev.to_mesh()
    me.transform(o.matrix_world)
    me.calc_loop_triangles()
    mats = o.data.materials
    for lt in me.loop_triangles:
        cls = mat_class(o, mats[lt.material_index] if lt.material_index < len(mats) else None)
        vs, ts = class_tris[cls]
        base = len(vs)
        vs.extend(me.vertices[i].co.copy() for i in lt.vertices)
        ts.append((base, base + 1, base + 2))
    bm.from_mesh(me)
    ev.to_mesh_clear()
ext_me = bpy.data.meshes.new("Exterior")
bm.to_mesh(ext_me)
bm.free()
ext = bpy.data.objects.new("Exterior", ext_me)
scene.collection.objects.link(ext)
class_bvh = {c: BVHTree.FromPolygons(vs, ts) for c, (vs, ts) in class_tris.items() if ts}
log("exterior mesh", len(ext_me.polygons), "faces; classes:", {c: len(t[1]) for c, t in class_tris.items()})

# ------------------------------------------------------------------ 2. watertight shell
bpy.ops.object.select_all(action="DESELECT")
bpy.context.view_layer.objects.active = ext
ext.select_set(True)
sol = ext.modifiers.new("Wall", "SOLIDIFY")
sol.thickness = WALL
sol.offset = 0.0
sol.use_rim = True
sol.use_even_offset = False
sol.nonmanifold_thickness_mode = "FIXED"
bpy.ops.object.modifier_apply(modifier="Wall")
rm = ext.modifiers.new("Shell", "REMESH")
rm.mode = "VOXEL"
rm.voxel_size = VOXEL
rm.adaptivity = ADAPT
rm.use_smooth_shade = True
bpy.ops.object.modifier_apply(modifier="Shell")
log("remeshed", len(ext.data.polygons), "faces")
sm = ext.modifiers.new("Smooth", "SMOOTH")
sm.factor, sm.iterations = SMOOTH
bpy.ops.object.modifier_apply(modifier="Smooth")
if TARGET_FACES and len(ext.data.polygons) > TARGET_FACES:      # keep the STL / GLB downloadable
    tr = ext.modifiers.new("Tri", "TRIANGULATE")  # collapse on the remesher's n-gons opens holes; triangles stay closed
    bpy.ops.object.modifier_apply(modifier="Tri")
    backup = ext.data.copy()
    dm = ext.modifiers.new("Decimate", "DECIMATE")
    dm.ratio = TARGET_FACES / len(ext.data.polygons)
    dm.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier="Decimate")
    # collapse leaves a few hundred triangle-sized holes on thin parts (tyre bottoms, mirrors); fill them
    # Collapse also leaves degenerate (zero-area / duplicate-vertex) triangles that Blender drops when the
    # file is saved or exported, which opens holes: dissolve them, fill, validate, and count on the
    # validated mesh (what the STL will contain).
    left, before = -1, -1
    for _ in range(3):
        bm = bmesh.new()
        bm.from_mesh(ext.data)
        if before < 0:
            before = sum(1 for e in bm.edges if len(e.link_faces) != 2)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=bm.edges)
        bmesh.ops.holes_fill(bm, edges=bm.edges, sides=0)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.to_mesh(ext.data)
        bm.free()
        ext.data.validate(verbose=False, clean_customdata=False)
        left = open_edges(ext.data)
        if left == 0:
            break
    if left == 0:
        log(f"decimated to {len(ext.data.polygons)} faces, {before} open edges filled")
        bpy.data.meshes.remove(backup)
    else:
        log(f"decimation left {left} open edges after filling: keeping the undecimated shell")
        old = ext.data
        ext.data = backup
        bpy.data.meshes.remove(old)
    bm.free()
ext.name = ext.data.name = "PrintShell"
for p in ext.data.polygons:
    p.use_smooth = True
log("shell", len(ext.data.polygons), "faces; open edges:", open_edges(ext.data))

shell_bvh = BVHTree.FromPolygons([v.co[:] for v in ext.data.vertices], [p.vertices[:] for p in ext.data.polygons])
for label, o, d in (("flank", Vector((3, 1.0, 1.6)), Vector((-1, 0, 0))), ("roof", Vector((0, 1.0, 6)), Vector((0, 0, -1)))):
    hits = []
    p = o
    for _ in range(4):
        loc, nrm, idx, dist = shell_bvh.ray_cast(p, d, 20)
        if loc is None:
            break
        hits.append(round((loc - o).length, 4))
        p = loc + d * 1e-4
    log(f"{label} hits along ray: {hits}")


# ------------------------------------------------------------------ 3. colours
def new_mat(name, color, rough=0.5, metal=0.0, image=None, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if coat:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.08
    if image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.location = (-400, 300)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return m


img = bpy.data.images.load(os.path.join(TEX, "clerk_van_atlas_transit.png"))
img.colorspace_settings.name = "sRGB"
MATS = {
    "livery": new_mat("Livery", (1, 1, 1), rough=0.35, image=img, coat=0.2),
    "glass": new_mat("Glass", (0.03, 0.035, 0.05), rough=0.15, coat=0.6),
    "tyre": new_mat("Tyre", (0.03, 0.03, 0.03), rough=0.9),
    "rim": new_mat("Rim", (0.62, 0.63, 0.66), rough=0.35, metal=0.9),
    "lens": new_mat("Lamp", (0.85, 0.86, 0.88), rough=0.1, coat=0.8),
    "chrome": new_mat("Chrome", (0.75, 0.75, 0.78), rough=0.2, metal=1.0),
    "dark": new_mat("DarkPlastic", (0.07, 0.07, 0.075), rough=0.7),
    "white": new_mat("ReliefWhite", (0.95, 0.95, 0.96), rough=0.4),
    "purple": new_mat("ReliefPurple", (0.147, 0.058, 1.0), rough=0.4),     # #6C47FF
}
me = ext.data
for key in ("livery", "glass", "tyre", "rim", "lens", "chrome", "dark"):
    me.materials.append(MATS[key])
IDX = {key: i for i, key in enumerate(("livery", "glass", "tyre", "rim", "lens", "chrome", "dark"))}
counts = {k: 0 for k in IDX}
for poly in me.polygons:
    c = poly.center
    # the shell sits WALL/2 off its source surface; a special class only wins when it is clearly
    # closer than the nearest livery surface (ties at panel edges stay livery, no jagged patches)
    loc, nrm, idx, dl = class_bvh["livery"].find_nearest(c, 0.08)
    best, bd = "livery", (dl if loc is not None else 1e9) - 0.006
    for cls, bvh in class_bvh.items():
        if cls == "livery":
            continue
        loc, nrm, idx, dist = bvh.find_nearest(c, 0.06)
        if loc is not None and dist < bd:
            best, bd = cls, dist
    poly.material_index = IDX[best]
log("classes assigned; open edges:", open_edges(me))
# majority vote over the faces around each vertex removes the jagged fringe where two classes meet
bm = bmesh.new()
bm.from_mesh(me)
bm.faces.ensure_lookup_table()
cur = [f.material_index for f in bm.faces]
for _ in range(2):
    nxt = cur[:]
    for f in bm.faces:
        tally = {}
        for v in f.verts:
            for g in v.link_faces:
                tally[cur[g.index]] = tally.get(cur[g.index], 0) + 1
        nxt[f.index] = max(tally, key=tally.get)
    cur = nxt
for f in bm.faces:
    f.material_index = cur[f.index]
bm.to_mesh(me)
bm.free()
keys = list(IDX)
for poly in me.polygons:
    counts[keys[poly.material_index]] += 1
log("shell face classes:", counts, "open edges:", open_edges(me))


def uv_rect(region):
    x0, y0, x1, y1 = R[region]
    return (x0 / ATLAS, 1 - y1 / ATLAS, x1 / ATLAS, 1 - y0 / ATLAS)


# box projection of the atlas onto livery faces: the same rules as build_transit_van.project_uv
uvl = me.uv_layers.new(name="UVMap")
uv = uvl.data
for poly in me.polygons:
    if poly.material_index != IDX["livery"]:
        continue
    n = poly.normal
    ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
    c = poly.center
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
        p = me.vertices[me.loops[li].vertex_index].co
        if mode == "side":
            a0, a1, b0, b1 = EXT["side"]; v = (p.z - b0) / (b1 - b0)
            if sx > 0:
                u = (p.y - a0) / (a1 - a0); reg = "side_left"
            else:
                u = (a1 - p.y) / (a1 - a0); reg = "side_right"
        elif mode == "front":
            a0, a1, b0, b1 = EXT["front"]; v = (p.z - b0) / (b1 - b0); u = (p.x - a0) / (a1 - a0); reg = "front"
        elif mode == "rear":
            a0, a1, b0, b1 = EXT["front"]; v = (p.z - b0) / (b1 - b0); u = (a1 - p.x) / (a1 - a0); reg = "rear"
        elif mode == "top":
            a0, a1, b0, b1 = EXT["top"]; u = (a1 - p.x) / (a1 - a0); v = (b1 - p.y) / (b1 - b0); reg = "top"
        else:
            u, v, reg = 0.5, 0.5, "bottom"
        u0, v0, u1, v1 = uv_rect(reg)
        uv[li].uv = (u0 + u * (u1 - u0), v0 + v * (v1 - v0))
log("uv projected; open edges:", open_edges(me))

# ------------------------------------------------------------------ 4. relief from the livery masks
polys = json.load(open(os.path.join(TEX, "print_mask", "polys_transit.json")))
# panel -> ray origin on the far side of the body for panel coords (a, b), and the cast direction
PANELS = {
    "side_left":  (lambda a, b: Vector((3.0, a, b)),  Vector((-1, 0, 0))),
    "side_right": (lambda a, b: Vector((-3.0, a, b)), Vector((1, 0, 0))),
    "front":      (lambda a, b: Vector((a, -6.0, b)), Vector((0, 1, 0))),
    "rear":       (lambda a, b: Vector((a, 6.0, b)),  Vector((0, -1, 0))),
    "top":        (lambda a, b: Vector((a, -b, 6.0)), Vector((0, 0, -1))),
}


def extrude_shape(rings, tag):
    """One filled 2-D outline (outer ring + holes) extruded to z = +-0.5 as a closed mesh, or None.
    Blender's curve filler occasionally fails on a glyph whose hole touches its outline (a pinch);
    such a shape is retried without its holes (solid glyph), and dropped if still open."""
    cu = bpy.data.curves.new(tag, "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    cu.extrude = 0.5                      # unit thickness, remapped per vertex later
    cu.resolution_u = 1
    for ring in rings:
        sp = cu.splines.new("POLY")
        sp.points.add(len(ring) - 1)
        for k, (a, b) in enumerate(ring):
            sp.points[k].co = (a, b, 0, 1)
        sp.use_cyclic_u = True
    co = bpy.data.objects.new(tag, cu)
    scene.collection.objects.link(co)
    bpy.ops.object.select_all(action="DESELECT")
    co.select_set(True)
    bpy.context.view_layer.objects.active = co
    bpy.ops.object.convert(target="MESH")
    bm = bmesh.new()
    bm.from_mesh(co.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    closed = bm.faces and all(len(e.link_faces) == 2 for e in bm.edges)
    if closed:
        bm.to_mesh(co.data)
    bm.free()
    if closed:
        return co
    bpy.data.objects.remove(co, do_unlink=True)
    return None


relief_objs = []
for name, (origin, direc) in PANELS.items():
    shapes = polys.get(name, [])
    if not shapes:
        continue
    parts, solid, dropped = [], 0, 0
    for i, sh in enumerate(shapes):
        co = extrude_shape([sh["outer"]] + sh["holes"], f"R_{name}_{i}")
        if co is None and sh["holes"]:
            co = extrude_shape([sh["outer"]], f"R_{name}_{i}")
            solid += co is not None
        if co is None:
            dropped += 1
            continue
        parts.append(co)
    bpy.ops.object.select_all(action="DESELECT")
    for co in parts:
        co.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    co = parts[0]
    co.name = co.data.name = f"Relief_{name}"
    if solid or dropped:
        log(f"relief {name}: {solid} glyphs filled solid, {dropped} dropped (open outline)")
    me = co.data
    lost = 0
    new_co = []
    for v in me.vertices:
        a, b, zz = v.co
        loc, nrm, idx, dist = shell_bvh.ray_cast(origin(a, b), direc, 20.0)
        if loc is None:
            lost += 1
            new_co.append(None)
            continue
        off = RELIEF if zz > 0 else -EMBED
        new_co.append(loc - direc * off)
    for v, c in zip(me.vertices, new_co):
        if c is not None:
            v.co = c
    bm = bmesh.new()
    bm.from_mesh(me)
    if lost:   # shapes that miss the body (mask outside the panel) are dropped with their faces
        bm.verts.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.verts[i] for i, c in enumerate(new_co) if c is None], context="VERTS")
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    # white relief; the hood lockup (top panel, ahead of the windscreen) is purple like the atlas
    me.materials.clear()
    me.materials.append(MATS["white"])
    me.materials.append(MATS["purple"])
    for p in me.polygons:
        p.material_index = 1 if (name == "top" and p.center.y < YF_Z + 1.2) else 0
    log(f"relief {name}: {len(shapes)} shapes, {len(me.polygons)} faces, {lost} vertices off-body")
    relief_objs.append(co)

# ------------------------------------------------------------------ 5. export
for o in list(bpy.data.objects):
    if o is not ext and o not in relief_objs:
        bpy.data.objects.remove(o, do_unlink=True)
zmin = min(v.co.z for v in ext.data.vertices)
for o in [ext] + relief_objs:
    o.location.z -= zmin
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# two-colour STL parts (body / relief), then everything joined
bpy.ops.object.select_all(action="DESELECT")
ext.select_set(True)
bpy.ops.wm.stl_export(filepath=os.path.join(OUT, "clerk_van_print_body.stl"), global_scale=1000.0 / DENOM, export_selected_objects=True, ascii_format=False)
bpy.ops.object.select_all(action="DESELECT")
for o in relief_objs:
    o.select_set(True)
bpy.ops.wm.stl_export(filepath=os.path.join(OUT, "clerk_van_print_relief.stl"), global_scale=1000.0 / DENOM, export_selected_objects=True, ascii_format=False)

bpy.ops.object.select_all(action="SELECT")
bpy.context.view_layer.objects.active = ext
bpy.ops.object.join()
final = ext
final.name = final.data.name = "ClerkVanPrint"
log("final mesh", len(final.data.polygons), "faces", len(final.data.vertices), "verts", "materials", len(final.data.materials),
    "open edges:", open_edges(final.data))

glb = os.path.join(OUT, "clerk_van_print.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=False, export_apply=True,
                          export_animations=False, export_lights=False, export_cameras=False,
                          export_texcoords=True, export_normals=True, export_materials="EXPORT", export_yup=True,
                          export_image_format="AUTO")
shutil.copy(glb, os.path.join(ROOT, "web", "clerk_van_print.glb"))

stl = os.path.join(OUT, "clerk_van_print.stl")
bpy.ops.wm.stl_export(filepath=stl, global_scale=1000.0 / DENOM, apply_modifiers=True, ascii_format=False, export_selected_objects=False)
dims = final.dimensions * 1000.0 / DENOM
log(f"STL {stl}  {os.path.getsize(stl)/1e6:.1f} MB  size {dims.x:.0f} x {dims.y:.0f} x {dims.z:.0f} mm at 1:{DENOM:.0f}")
log(f"GLB {glb}  {os.path.getsize(glb)/1e6:.1f} MB")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "clerk_van_print.blend"))
print("PRINT BUILD OK")
