"""Import the Sketchfab Crafter GLB, normalise transforms, dump world-space bounds per object
and render two quick previews.  blender --background --python tools/inspect_crafter.py -- <root>"""
import bpy, os, sys, json, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
ROOT = os.path.abspath(argv[0])
SRC = os.path.join(ROOT, "references", "crafter", "source", "crafter_custom.glb")
OUT = os.path.join(ROOT, "references", "crafter")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
scene = bpy.context.scene
bpy.context.view_layer.update()

rows = []
gmin = Vector((1e9,) * 3); gmax = Vector((-1e9,) * 3)
for ob in bpy.data.objects:
    if ob.type != "MESH":
        continue
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    rows.append({"name": ob.name, "tris": len(ob.data.polygons), "min": [round(v, 3) for v in mn], "max": [round(v, 3) for v in mx],
                 "mats": [m.name for m in ob.data.materials if m]})
    for i in range(3):
        gmin[i] = min(gmin[i], mn[i]); gmax[i] = max(gmax[i], mx[i])
rows.sort(key=lambda r: -r["tris"])
json.dump({"global_min": list(gmin), "global_max": list(gmax), "objects": rows}, open(os.path.join(OUT, "crafter_bounds.json"), "w"), indent=1)
print("GLOBAL", [round(v, 3) for v in gmin], [round(v, 3) for v in gmax])
for r in rows[:45]:
    print(r["tris"], r["name"], r["min"], r["max"], r["mats"][:2])

# quick previews
center = (gmin + gmax) / 2
size = (gmax - gmin).length
cam_data = bpy.data.cameras.new("Cam"); cam_data.lens = 40
cam = bpy.data.objects.new("Cam", cam_data); scene.collection.objects.link(cam); scene.camera = cam
sun = bpy.data.lights.new("Sun", "SUN"); sun.energy = 3.0
so = bpy.data.objects.new("Sun", sun); scene.collection.objects.link(so); so.rotation_euler = (math.radians(50), 0, math.radians(30))
world = bpy.data.worlds.new("W"); scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.6, 0.6, 0.6, 1)
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
scene.eevee.taa_render_samples = 16
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
for name, dirv in (("front34", Vector((0.7, -0.8, 0.45))), ("side", Vector((1, 0, 0.12))), ("front", Vector((0, -1, 0.15)))):
    cam.location = center + dirv.normalized() * size * 1.1
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(OUT, f"crafter_{name}.png")
    bpy.ops.render.render(write_still=True)
print("done")
