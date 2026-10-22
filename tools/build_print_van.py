"""
Printable Clerk Van: one watertight shell of the exterior with every livery graphic
(logos, wordmarks, text, QR codes) raised as relief so it shows on a 3D print.

Runs in Blender 4.2 headless on the shipped build, after print_mask_polys.py:
  python tools/print_mask_polys.py --profile transit
  blender --background export/clerk_van.blend --python tools/build_print_van.py -- <repo root> [relief_mm] [scale_denominator]

Steps
  1. drop interior / never-visible objects, join the exterior meshes (doors and wheels in the rest pose)
  2. Geometry Nodes Mesh to Volume -> Volume to Mesh: a closed shell WALL metres thick around
     every exterior surface (single-sided game panels become solid walls)
  3. relief: the polygons vectorised from the livery masks are built as filled 2-D curves in panel
     metres, extruded, and every vertex is ray-cast onto the shell so the letters follow the body
     (top at surface + RELIEF, base embedded into the shell). Closed solids, unioned by the slicer.
  4. export export/clerk_van_print.stl (millimetres at 1:SCALE) and clerk_van_print.glb (metres)
     for the web viewer; the GLB is copied to web/.
"""
import bpy, bmesh, os, sys, json, time, shutil
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = os.path.abspath(argv[0]) if argv else os.getcwd()
RELIEF = (float(argv[1]) if len(argv) > 1 else 15.0) / 1000.0   # relief height, metres at full scale (15 mm = 0.6 mm at 1:24)
DENOM = float(argv[2]) if len(argv) > 2 else 24.0                 # STL scale 1:DENOM
WALL = 0.04          # shell thickness, metres at full scale: 1.7 mm at 1:24
VOXEL = 0.008        # shell voxel size (m): 0.33 mm at 1:24
ADAPT = 0.4          # voxel remesh adaptivity (flat panels collapse to few triangles)
EMBED = WALL * 0.5   # how deep the relief solids sink into the shell
TEX = os.path.join(ROOT, "textures")
OUT = os.path.join(ROOT, "export")
T0 = time.time()


def log(*a):
    print(f"[print {time.time() - T0:6.1f}s]", *a, flush=True)


scene = bpy.context.scene
for o in bpy.data.objects:            # rest pose, no NLA influence
    if o.animation_data:
        for t in o.animation_data.nla_tracks:
            t.mute = True
scene.frame_set(0)
bpy.context.view_layer.update()

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
        log("drop (interior material)", o.name)
        continue
    if not visible_from_outside(o):
        log("drop (never visible)", o.name)
        continue
    keep.append(o)
log("keeping", len(keep), "objects")

bm = bmesh.new()
for o in keep:
    ev = o.evaluated_get(depsgraph)
    me = ev.to_mesh()
    me.transform(o.matrix_world)
    bm.from_mesh(me)
    ev.to_mesh_clear()
ext_me = bpy.data.meshes.new("Exterior")
bm.to_mesh(ext_me)
bm.free()
ext = bpy.data.objects.new("Exterior", ext_me)
scene.collection.objects.link(ext)
log("exterior mesh", len(ext_me.polygons), "faces")

# ------------------------------------------------------------------ 2. watertight shell
# Single-sided game panels first become closed slabs (Solidify, centred), then the voxel remesher
# (OpenVDB level set) unions every slab into one watertight surface.  An open surface fed straight to
# Mesh to Volume / voxel remesh is discarded by the level-set builder, which is why the slabs are needed.
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
log("solidified", len(ext.data.polygons), "faces")
rm = ext.modifiers.new("Shell", "REMESH")
rm.mode = "VOXEL"
rm.voxel_size = VOXEL
rm.adaptivity = ADAPT
rm.use_smooth_shade = True
bpy.ops.object.modifier_apply(modifier="Shell")
ext.name = ext.data.name = "PrintShell"
log("shell", len(ext.data.polygons), "faces")

shell_bvh = BVHTree.FromPolygons([v.co[:] for v in ext.data.vertices], [p.vertices[:] for p in ext.data.polygons])
# diagnostics: wall thickness through a flat flank and the roof
for label, o, d in (("flank", Vector((3, 1.0, 1.6)), Vector((-1, 0, 0))), ("roof", Vector((0, 1.0, 6)), Vector((0, 0, -1)))):
    hits = []
    p = o
    for _ in range(6):
        loc, nrm, idx, dist = shell_bvh.ray_cast(p, d, 20)
        if loc is None:
            break
        hits.append(round((loc - o).length, 4))
        p = loc + d * 1e-4
    log(f"{label} hits along ray: {hits}")

# ------------------------------------------------------------------ 3. relief from the livery masks
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
    me = bm.to_mesh(co.data) if closed else None
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
    log(f"relief {name}: {len(shapes)} shapes, {len(me.polygons)} faces, {lost} vertices off-body")
    relief_objs.append(co)

# ------------------------------------------------------------------ 4. export
mat = bpy.data.materials.new("PrintResin")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.86, 0.86, 0.88, 1)
bsdf.inputs["Roughness"].default_value = 0.55
for o in [ext] + relief_objs:
    o.data.materials.clear()
    o.data.materials.append(mat)

bpy.ops.object.select_all(action="DESELECT")
for o in [ext] + relief_objs:
    o.select_set(True)
bpy.context.view_layer.objects.active = ext
bpy.ops.object.join()
final = ext
final.name = final.data.name = "ClerkVanPrint"
zmin = min(v.co.z for v in final.data.vertices)
final.location.z -= zmin
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
log("final mesh", len(final.data.polygons), "faces", len(final.data.vertices), "verts")

for o in list(bpy.data.objects):
    if o is not final:
        bpy.data.objects.remove(o, do_unlink=True)
glb = os.path.join(OUT, "clerk_van_print.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=False, export_apply=True,
                          export_animations=False, export_lights=False, export_cameras=False,
                          export_texcoords=False, export_normals=True, export_materials="EXPORT", export_yup=True)
shutil.copy(glb, os.path.join(ROOT, "web", "clerk_van_print.glb"))

stl = os.path.join(OUT, "clerk_van_print.stl")
bpy.ops.wm.stl_export(filepath=stl, global_scale=1000.0 / DENOM, apply_modifiers=True, ascii_format=False, export_selected_objects=False)
dims = final.dimensions * 1000.0 / DENOM
log(f"STL {stl}  {os.path.getsize(stl)/1e6:.1f} MB  size {dims.x:.0f} x {dims.y:.0f} x {dims.z:.0f} mm at 1:{DENOM:.0f}")
log(f"GLB {glb}  {os.path.getsize(glb)/1e6:.1f} MB")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "clerk_van_print.blend"))
print("PRINT BUILD OK")
