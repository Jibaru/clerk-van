"""Scale the chosen Hunyuan mesh to Transit metres (x/z uniform, y stretched only between the wheel arches),
ground it, save references/gen/<name>_scaled.blend and render orthographic side/front/rear/top views with a
0.5 m grid for measuring the livery profile.   blender --background --python tools/gen_measure.py -- <root> <name>"""
import bpy, bmesh, os, sys, math
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:]
ROOT = os.path.abspath(argv[0]); NAME = argv[1]
SRC = os.path.join(ROOT, "references", "gen", NAME + ".glb")
OUT = os.path.join(ROOT, "references", "gen")
L_TARGET, W_TARGET, H_TARGET = 5.45, 2.03, 2.12
Y_UNIFORM = 1.15          # part of the lengthening applied to the whole van (arches become 15% elliptical, wheels are replaced anyway)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
ob = [o for o in bpy.data.objects if o.type == "MESH"][0]
ob.name = "Body"; ob.data.name = "Body"
bpy.context.view_layer.update()
ob.data.transform(ob.matrix_world); ob.matrix_world = Matrix()
vs = ob.data.vertices
xs = [v.co.x for v in vs]; ys = [v.co.y for v in vs]; zs = [v.co.z for v in vs]
y0, y1, z0, z1 = min(ys), max(ys), min(zs), max(zs)
# body half width = median |x| of side-facing vertices in the cargo zone
side = sorted(abs(v.co.x) for v in vs if -0.3 < v.co.y < 0.3 and -0.2 < v.co.z < 0.3)
hw = side[int(len(side) * 0.98)]
s_xz = ((W_TARGET / 2) / hw + H_TARGET / (z1 - z0)) / 2
# wheel arches: tyre vertices
front = [v.co.y for v in vs if v.co.z < z0 + 0.15 and v.co.y < 0]
rear = [v.co.y for v in vs if v.co.z < z0 + 0.15 and v.co.y > 0]
yF, yR = (min(front) + max(front)) / 2, (min(rear) + max(rear)) / 2
a, b = max(front) + 0.02, min(rear) - 0.02           # stretch zone (between the arches)
s_y = s_xz * Y_UNIFORM
L_now = (y1 - y0) * s_y
extra = (L_TARGET - L_now) / s_y
print(f"MEAS hw={hw:.3f} s_xz={s_xz:.3f} s_y={s_y:.3f} L_now={L_now:.2f} extra_units={extra:.3f} stretch_zone=({a:.3f},{b:.3f}) wheels_y=({yF:.3f},{yR:.3f})")
for v in vs:
    y = v.co.y
    if y > b:
        y += extra
    elif y > a:
        y = a + (y - a) * (b - a + extra) / (b - a)
    v.co = Vector((v.co.x * s_xz, y * s_y, (v.co.z - z0) * s_xz))
ob.data.update()
ys = [v.co.y for v in vs]
yc = (min(ys) + max(ys)) / 2
ob.data.transform(Matrix.Translation((0, -yc, 0)))
ob.data.update()
xs = [v.co.x for v in vs]; ys = [v.co.y for v in vs]; zs = [v.co.z for v in vs]
print(f"MEAS final bounds x=({min(xs):.3f},{max(xs):.3f}) y=({min(ys):.3f},{max(ys):.3f}) z=({min(zs):.3f},{max(zs):.3f})")
wf = [v.co.y for v in vs if v.co.z < 0.25 and v.co.y < 0]; wr = [v.co.y for v in vs if v.co.z < 0.25 and v.co.y > 0]
print(f"MEAS wheel centres y: F={(min(wf)+max(wf))/2:.3f} R={(min(wr)+max(wr))/2:.3f}  mirror xmax={max(xs):.3f}")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, NAME + "_scaled.blend"))

# ---- grid renders
scene = bpy.context.scene
mat = bpy.data.materials.new("grey"); mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.75, 0.75, 0.78, 1)
ob.data.materials.clear(); ob.data.materials.append(mat)
sun = bpy.data.lights.new("Sun", "SUN"); sun.energy = 2.5
so = bpy.data.objects.new("Sun", sun); scene.collection.objects.link(so); so.rotation_euler = (math.radians(40), 0, math.radians(20))
world = bpy.data.worlds.new("W"); scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.9, 0.9, 0.9, 1)
cam_data = bpy.data.cameras.new("Cam"); cam_data.type = "ORTHO"
cam = bpy.data.objects.new("Cam", cam_data); scene.collection.objects.link(cam); scene.camera = cam
scene.render.engine = "BLENDER_EEVEE_NEXT"; scene.eevee.taa_render_samples = 8
# grid lines as thin cubes
gm = bpy.data.materials.new("grid"); gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (1, 0, 0, 1)
gm.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 5
def line(x0, x1, y0, y1, z0, z1):
    bpy.ops.mesh.primitive_cube_add()
    c = bpy.context.active_object
    c.scale = ((x1 - x0) / 2 + 0.004, (y1 - y0) / 2 + 0.004, (z1 - z0) / 2 + 0.004)
    c.location = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    c.data.materials.append(gm)
    return c
grid = []
for y in [i * 0.5 for i in range(-6, 7)]:
    grid.append(line(-1.4, 1.4, y, y, 0, 0.0001)); grid.append(line(1.3, 1.3, y, y, 0, 2.4)); grid.append(line(-1.3, -1.3, y, y, 0, 2.4))
for z in [i * 0.5 for i in range(0, 5)]:
    grid.append(line(1.3, 1.3, -3.2, 3.2, z, z)); grid.append(line(-1.3, -1.3, -3.2, 3.2, z, z))
    grid.append(line(-1.4, 1.4, -3.2, -3.2, z, z)); grid.append(line(-1.4, 1.4, 3.2, 3.2, z, z))
for x in [i * 0.5 for i in range(-2, 3)]:
    grid.append(line(x, x, -3.2, -3.2, 0, 2.4)); grid.append(line(x, x, 3.2, 3.2, 0, 2.4)); grid.append(line(x, x, -3.2, 3.2, 0, 0.0001))
def aim(loc, target):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
for name, (loc, target, ortho, res) in {
    "sideL": ((30, 0, 1.2), (0, 0, 1.2), 6.6, (1980, 900)), "sideR": ((-30, 0, 1.2), (0, 0, 1.2), 6.6, (1980, 900)),
    "front": ((0, -30, 1.2), (0, 0, 1.2), 3.0, (1000, 1000)), "rear": ((0, 30, 1.2), (0, 0, 1.2), 3.0, (1000, 1000)),
    "top": ((0, 0, 30), (0, 0.0001, 0), 6.6, (900, 1980)),
}.items():
    scene.render.resolution_x, scene.render.resolution_y = res
    cam_data.ortho_scale = ortho
    aim(loc, target)
    scene.render.filepath = os.path.join(OUT, f"{NAME}_grid_{name}.png")
    bpy.ops.render.render(write_still=True)
print("done")
