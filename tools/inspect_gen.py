"""Import a generated GLB (references/gen/<name>.glb), report bounds/faces, render 4 quick views.
blender --background --python tools/inspect_gen.py -- <root> <name>"""
import bpy, os, sys, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
ROOT = os.path.abspath(argv[0]); NAME = argv[1]
SRC = os.path.join(ROOT, "references", "gen", NAME + ".glb")
OUT = os.path.join(ROOT, "references", "gen")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
scene = bpy.context.scene
bpy.context.view_layer.update()
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
gmin = Vector((1e9,) * 3); gmax = Vector((-1e9,) * 3)
for ob in meshes:
    for c in ob.bound_box:
        p = ob.matrix_world @ Vector(c)
        for i in range(3):
            gmin[i] = min(gmin[i], p[i]); gmax[i] = max(gmax[i], p[i])
print("GEN objects", len(meshes), "faces", sum(len(o.data.polygons) for o in meshes), "min", [round(v, 3) for v in gmin], "max", [round(v, 3) for v in gmax],
      "mats", [[m.name for m in o.data.materials if m] for o in meshes][:3])
center = (gmin + gmax) / 2; size = (gmax - gmin).length
cam_data = bpy.data.cameras.new("Cam"); cam_data.lens = 45
cam = bpy.data.objects.new("Cam", cam_data); scene.collection.objects.link(cam); scene.camera = cam
for i, (rot, loc) in enumerate(((50, 30), (50, 120), (50, 210), (50, 300))):
    pass
sun = bpy.data.lights.new("Sun", "SUN"); sun.energy = 3.0
so = bpy.data.objects.new("Sun", sun); scene.collection.objects.link(so); so.rotation_euler = (math.radians(50), 0, math.radians(30))
world = bpy.data.worlds.new("W"); scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.7, 0.7, 0.7, 1)
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.eevee.taa_render_samples = 16
scene.render.resolution_x, scene.render.resolution_y = 900, 600
mat = bpy.data.materials.new("grey"); mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.8, 0.82, 1)
for ob in meshes:
    if not ob.data.materials or argv[2:] == ["grey"]:
        ob.data.materials.clear(); ob.data.materials.append(mat)
views = {"a": Vector((0.8, -0.7, 0.45)), "b": Vector((-0.8, 0.7, 0.45)), "side": Vector((1, 0, 0.1)), "front": Vector((0, -1, 0.1)), "top": Vector((0.001, 0.001, 1))}
for name, dirv in views.items():
    cam.location = center + dirv.normalized() * size * 1.15
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(OUT, f"{NAME}_{name}.png")
    bpy.ops.render.render(write_still=True)
print("done")
