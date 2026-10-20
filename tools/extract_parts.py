"""Extract reusable high-detail parts from the Sketchfab VW Crafter GLB (geyges, Sketchfab Free
Standard licence) into references/crafter/crafter_parts.blend, normalised to metres at Transit scale:
  Crafter_Wheel      one wheel assembly (rim, tyre, brake disc, hub), centred at the origin, axis X, outer face +X
  Crafter_HeadlightL / Crafter_HeadlightR   lamp cluster incl. clear glass, world position as on the Crafter (scaled)
  Crafter_MirrorL / Crafter_MirrorR         housing + arm + glass
blender --background --python tools/extract_parts.py -- <root>
"""
import bpy, bmesh, os, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:]
ROOT = os.path.abspath(argv[0])
SRC = os.path.join(ROOT, "references", "crafter", "source", "crafter_custom.glb")
DST = os.path.join(ROOT, "references", "crafter", "crafter_parts.blend")
S = 2.03 / 1.51          # Crafter body width in the file -> Transit body width

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
bpy.context.view_layer.update()

# bake world transforms into mesh data, flatten hierarchy
for ob in list(bpy.data.objects):
    if ob.type != "MESH":
        continue
    ob.data = ob.data.copy()
    mw = ob.matrix_world.copy()
    ob.parent = None
    ob.matrix_world = Matrix()
    ob.data.transform(mw)
for ob in list(bpy.data.objects):
    if ob.type != "MESH":
        bpy.data.objects.remove(ob, do_unlink=True)


def O(name):
    return bpy.data.objects[name]


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


def bounds(ob):
    xs = [v.co.x for v in ob.data.vertices]; ys = [v.co.y for v in ob.data.vertices]; zs = [v.co.z for v in ob.data.vertices]
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def dup(ob, name):
    n = ob.copy(); n.data = ob.data.copy(); n.name = name
    bpy.context.scene.collection.objects.link(n)
    return n


keep = []

# ---- headlamps (both sides are in one object each) -> split
lamp = join([O("e_frontLights1_1L1"), O("e_frontLights2_1L2"), O("frontLight_glass1_1L1"), O("frontLight_glass")], "lamp_both")
def keep_above(ob, zmin):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < zmin], context="VERTS")
    bm.to_mesh(ob.data); bm.free()


keep_above(lamp, 0.59)          # drop the fog-lamp glass below the cluster
lampL = dup(lamp, "Crafter_HeadlightL"); keep_side(lampL, +1)
lampR = dup(lamp, "Crafter_HeadlightR"); keep_side(lampR, -1)
bpy.data.objects.remove(lamp, do_unlink=True)
keep += [lampL, lampR]

# ---- front wheel assembly -> one wheel centred at the origin
wheel = join([O("wheel_front_rimShape"), O("wheel_front_tyre_tyreShape"), O("wheel_front_brakeDisk"), O("wheel_front_plasticBlack_matteShape")], "wheel_both")
keep_side(wheel, +1)
(x0, x1), (y0, y1), (z0, z1) = bounds(wheel)
cy, cz = (y0 + y1) / 2, (z0 + z1) / 2
wheel.data.transform(Matrix.Translation((-x1, -cy, -cz)))     # outer face at x = 0, centred
wheel.name = "Crafter_Wheel"
print("wheel tyre radius (file units)", (z1 - z0) / 2, "width", x1 - x0)
keep.append(wheel)

# ---- mirrors: loose parts of the driver-door plastics that stick out beyond the door skin; the right one is mirrored
for side, door_obj, glass_obj, sign in (("L", "e_driveDoor_plasticBlack_matteShape", "e_driveDoor_Mirror_mirrorShape", +1),):
    d = O(door_obj)
    select([d], d)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")
    pieces = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    mirror_bits = []
    for o in pieces:
        (bx0, bx1), _, (bz0, bz1) = bounds(o)
        if (bx1 if sign > 0 else -bx0) > 0.79 and bz0 > 0.9:
            mirror_bits.append(o)
    m = join(mirror_bits + [O(glass_obj)], "Crafter_Mirror" + side)
    keep.append(m)
    mr = dup(m, "Crafter_MirrorR")
    mr.data.transform(Matrix.Scale(-1, 4, Vector((1, 0, 0))))
    mr.data.flip_normals()
    keep.append(mr)

# ---- drop everything else, scale to Transit size
for ob in list(bpy.data.objects):
    if ob not in keep:
        bpy.data.objects.remove(ob, do_unlink=True)
for ob in keep:
    ob.data.transform(Matrix.Scale(S, 4))
    (bx, by, bz) = bounds(ob)
    print(ob.name, len(ob.data.polygons), "x", [round(v, 3) for v in bx], "y", [round(v, 3) for v in by], "z", [round(v, 3) for v in bz])

bpy.ops.outliner.orphans_purge(do_recursive=True)
try:
    bpy.ops.file.pack_all()
except Exception as e:
    print("pack:", e)
bpy.ops.wm.save_as_mainfile(filepath=DST)
print("saved", DST)
