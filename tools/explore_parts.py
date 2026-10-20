"""Colour every object of references/transit/transit.glb with a distinct flat colour, render ortho views and
write a legend (index -> name, colour, bounds, material) so parts can be identified by eye.
blender --background --python tools/explore_parts.py -- <root>"""
import bpy, os, sys, json, math, random
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
ROOT = os.path.abspath(argv[0])
SRC = os.path.join(ROOT, "references", "transit", "transit.glb")
OUT = os.path.join(ROOT, "references", "transit", "parts")
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
scene = bpy.context.scene
bpy.context.view_layer.update()
meshes = sorted([o for o in bpy.data.objects if o.type == "MESH"], key=lambda o: -len(o.data.polygons))
random.seed(3)
legend = []
for i, ob in enumerate(meshes):
    h = (i * 0.618033988) % 1.0
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h, 0.75 if i % 2 else 0.45, 0.95 if i % 3 else 0.6)
    m = bpy.data.materials.new(f"idx_{i}"); m.use_nodes = True
    bs = m.node_tree.nodes["Principled BSDF"]; bs.inputs["Base Color"].default_value = (r, g, b, 1); bs.inputs["Roughness"].default_value = 0.8
    ob.data = ob.data.copy(); ob.data.materials.clear(); ob.data.materials.append(m)
    for p in ob.data.polygons:
        p.material_index = 0
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    legend.append({"i": i, "name": ob.name, "tris": len(ob.data.polygons), "rgb": [round(r * 255), round(g * 255), round(b * 255)],
                   "min": [round(min(p[k] for p in pts), 3) for k in range(3)], "max": [round(max(p[k] for p in pts), 3) for k in range(3)]})
json.dump(legend, open(os.path.join(OUT, "legend.json"), "w"), indent=1)

gmin = Vector([min(l["min"][k] for l in legend) for k in range(3)]); gmax = Vector([max(l["max"][k] for l in legend) for k in range(3)])
c = (gmin + gmax) / 2
sun = bpy.data.lights.new("Sun", "SUN"); sun.energy = 2.0
so = bpy.data.objects.new("Sun", sun); scene.collection.objects.link(so); so.rotation_euler = (math.radians(35), 0, math.radians(25))
world = bpy.data.worlds.new("W"); scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1); world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
cam_data = bpy.data.cameras.new("Cam"); cam_data.type = "ORTHO"
cam = bpy.data.objects.new("Cam", cam_data); scene.collection.objects.link(cam); scene.camera = cam
scene.render.engine = "BLENDER_EEVEE_NEXT"; scene.eevee.taa_render_samples = 4
L = (gmax - gmin).length
for name, dirv, up, ortho, res in (("sideL", Vector((1, 0, 0)), 8.0, (1800, 900)), ("sideR", Vector((-1, 0, 0)), 8.0, (1800, 900)),
                                   ("front", Vector((0, -1, 0)), 4.0, (900, 900)), ("rear", Vector((0, 1, 0)), 4.0, (900, 900)),
                                   ("top", Vector((0, 0.0001, 1)), 8.0, (900, 1800)), ("bottom", Vector((0, 0.0001, -1)), 8.0, (900, 1800))) if False else (
                                   ("sideL", Vector((1, 0, 0)), None, 8.0, (1800, 900)), ("sideR", Vector((-1, 0, 0)), None, 8.0, (1800, 900)),
                                   ("front", Vector((0, -1, 0)), None, 4.0, (900, 900)), ("rear", Vector((0, 1, 0)), None, 4.0, (900, 900)),
                                   ("top", Vector((0, 0.0001, 1)), None, 8.0, (900, 1800)), ("bottom", Vector((0, 0.0001, -1)), None, 8.0, (900, 1800))):
    scene.render.resolution_x, scene.render.resolution_y = res
    cam_data.ortho_scale = ortho
    cam.location = c + dirv.normalized() * L
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(OUT, f"parts_{name}.png")
    bpy.ops.render.render(write_still=True)
print("PARTS done", len(legend))
