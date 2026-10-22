"""
Printable Clerk Van: the exterior of the display model, exactly as it looks (same geometry, same
materials and livery atlas), given a 4 cm wall and with every livery graphic (logos, wordmarks,
text, QR codes) raised as closed relief solids so it shows on a 3D print.

Runs in Blender 4.2 headless on the shipped build, after print_mask_polys.py:
  python tools/print_mask_polys.py --profile transit
  blender --background export/clerk_van.blend --python tools/build_print_van.py -- <repo root> [relief_mm] [scale_denominator]

Steps
  1. drop interior / never-visible objects, join evaluated copies of the exterior (doors and wheels in
     the rest pose), materials kept
  2. Solidify, centred, WALL thick: every single-sided game panel becomes a closed slab; the slabs
     overlap each other and the slicer unions them (PrusaSlicer / Bambu Studio / Cura all merge
     overlapping closed shells of one object). No voxel remesh: that melted the detail and repainted
     the faces, which is what the user rejected.
  3. relief: the polygons vectorised from the livery masks are built as filled 2-D curves in panel
     metres, extruded, and every vertex is ray-cast onto the solidified body so the letters follow the
     surface (top at surface + RELIEF, base embedded WALL/2). Each glyph is a verified closed solid.
  4. export: export/clerk_van_print.stl (all), _body.stl + _relief.stl (two-colour print), mm at
     1:SCALE; clerk_van_print.glb (metres, original materials) for the web viewer, copied to web/.
"""
import bpy, bmesh, os, sys, json, time, shutil
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = os.path.abspath(argv[0]) if argv else os.getcwd()
RELIEF = (float(argv[1]) if len(argv) > 1 else 15.0) / 1000.0   # relief height, metres at full scale (15 mm = 0.6 mm at 1:24)
DENOM = float(argv[2]) if len(argv) > 2 else 24.0                 # STL scale 1:DENOM
WALL = 0.04          # wall thickness, metres at full scale: 1.7 mm at 1:24
EMBED = WALL * 0.5   # how deep the relief solids sink into the wall (= back to the original surface)
TEX = os.path.join(ROOT, "textures")
OUT = os.path.join(ROOT, "export")
T0 = time.time()


def log(*a):
    print(f"[print {time.time() - T0:6.1f}s]", *a, flush=True)


def open_edges(me):
    """Edges with other than two faces: 0 means every shell in the mesh is closed."""
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
YF_Z = min(v.y for v in bb)

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

# the display window glass is transparent; with the interior gone it would show the far wall's relief, so
# the windows get an opaque dark glass (what a print looks like). The headlamp covers (3DGeom-8) keep the
# clear glass so the lamps inside stay visible.
PRINT_GLASS = None


def print_glass(m):
    global PRINT_GLASS
    if PRINT_GLASS is None:
        PRINT_GLASS = m.copy()
        PRINT_GLASS.name = "PrintGlass"
        bsdf = PRINT_GLASS.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Alpha"].default_value = 1.0
            bsdf.inputs["Base Color"].default_value = (0.02, 0.025, 0.035, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.15
        PRINT_GLASS.surface_render_method = "DITHERED"
    return PRINT_GLASS


bpy.ops.object.select_all(action="DESELECT")
copies = []
for o in keep:
    ev = o.evaluated_get(depsgraph)
    me = bpy.data.meshes.new_from_object(ev)
    me.transform(o.matrix_world)
    if o.name != "3DGeom-8":
        for i, m in enumerate(me.materials):
            if m and m.name.startswith("Glass"):
                me.materials[i] = print_glass(m)
    c = bpy.data.objects.new("c_" + o.name, me)
    scene.collection.objects.link(c)
    c.select_set(True)
    copies.append(c)
bpy.context.view_layer.objects.active = copies[0]
bpy.ops.object.join()
ext = copies[0]
ext.name = ext.data.name = "PrintBody"
# the glTF import split most vertices (per-corner normals / UVs), so nearly every edge is a boundary and
# Solidify would rim each triangle; welding the vertices (UVs stay per corner) reconnects the panels
bm = bmesh.new()
bm.from_mesh(ext.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
bm.to_mesh(ext.data)
bm.free()
log("exterior", len(ext.data.polygons), "faces,", len(ext.data.materials), "materials, open edges", open_edges(ext.data))

# ------------------------------------------------------------------ 2. walls
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
bm = bmesh.new()
bm.from_mesh(ext.data)
bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges)
# Solidify cannot rim the few edges the game mesh shares between three or more faces; it leaves 4 cm
# slits between rim quads there. Welding the rim vertices closes most, a hole fill the rest (edges shared
# by overlapping slabs are fine for a slicer).
holes = [e for e in bm.edges if len(e.link_faces) == 1]
bmesh.ops.remove_doubles(bm, verts=[v for e in holes for v in e.verts], dist=2e-3)
bmesh.ops.holes_fill(bm, edges=bm.edges, sides=12)
# the slits that remain are pairs of facing rim edges a few mm apart: bridge each pair with one quad
from mathutils.kdtree import KDTree
slits = [e for e in bm.edges if len(e.link_faces) == 1]
kd = KDTree(len(slits))
for i, e in enumerate(slits):
    kd.insert((e.verts[0].co + e.verts[1].co) / 2, i)
kd.balance()
used = set()
for i, e in enumerate(slits):
    if i in used:
        continue
    for co, j, d in kd.find_n((e.verts[0].co + e.verts[1].co) / 2, 4):
        if j == i or j in used or d > 0.012:
            continue
        f = slits[j]
        a, b = e.verts
        c, d2 = (f.verts[0], f.verts[1]) if (f.verts[0].co - b.co).length < (f.verts[1].co - b.co).length else (f.verts[1], f.verts[0])
        try:
            bm.faces.new((a, b, c, d2))
            used.update((i, j))
            break
        except ValueError:
            continue
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
bm.to_mesh(ext.data)
bm.free()
ext.data.validate(verbose=False, clean_customdata=False)
b = bmesh.new()
b.from_mesh(ext.data)
left = sum(1 for e in b.edges if len(e.link_faces) == 1)
shared = sum(1 for e in b.edges if len(e.link_faces) > 2)
b.free()
log(f"solidified {len(ext.data.polygons)} faces; boundary edges {len(holes)} -> {left} after hole fill; {shared} edges shared by overlapping slabs")

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


# ------------------------------------------------------------------ 3. relief from the livery masks
def new_mat(name, color, rough=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    return m


M_WHITE = new_mat("ReliefWhite", (0.95, 0.95, 0.96), 0.4)
M_PURPLE = new_mat("ReliefPurple", (0.147, 0.058, 1.0), 0.4)     # #6C47FF

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
    me.materials.clear()
    me.materials.append(M_WHITE)
    me.materials.append(M_PURPLE)
    for p in me.polygons:      # the hood lockup (top panel, ahead of the windscreen) is purple like the atlas
        p.material_index = 1 if (name == "top" and p.center.y < YF_Z + 1.2) else 0
    log(f"relief {name}: {len(shapes)} shapes, {len(me.polygons)} faces, {lost} vertices off-body, open edges {open_edges(me)}")
    relief_objs.append(co)

# ------------------------------------------------------------------ 4. export
for o in list(bpy.data.objects):
    if o is not ext and o not in relief_objs:
        bpy.data.objects.remove(o, do_unlink=True)
zmin = min(v.co.z for v in ext.data.vertices)
for o in [ext] + relief_objs:
    o.location.z -= zmin
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

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
    "open edges", open_edges(final.data))

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
