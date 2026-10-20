"""
Opens export/clerk_van.blend, builds a lime-green studio (#7CFF00) with a fixed
camera and fixed lights, and renders either preview stills or the 360 turntable.

  blender --background export/clerk_van.blend --python tools/render_turntable.py -- <root> preview
  blender --background export/clerk_van.blend --python tools/render_turntable.py -- <root> turntable [frames]

Preview stills  -> renders/preview_*.png
Turntable frames-> renders/turntable/frame_0001.png ...  (encode with tools/encode_turntable.ps1 / ffmpeg)
"""
import bpy, math, os, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
ROOT = os.path.abspath(argv[0])
MODE = argv[1] if len(argv) > 1 else "preview"
FRAMES = int(argv[2]) if len(argv) > 2 else 120
OUT = os.path.join(ROOT, "renders")
os.makedirs(OUT, exist_ok=True)

LIME = (0.2013, 1.0, 0.0)   # #7CFF00 in linear (sRGB 124/255 = 0.4863 -> 0.2013)

scene = bpy.context.scene
root = bpy.data.objects["ClerkVan"]

# rest pose: make sure no clip plays while the turntable runs
for ob in bpy.data.objects:
    if ob.animation_data:
        ob.animation_data.action = None
        for tr in ob.animation_data.nla_tracks:
            tr.mute = True

# headlights/taillights off for the reference look
for n in ("Light_HeadL", "Light_HeadR", "Light_TailL", "Light_TailR"):
    if n in bpy.data.objects:
        bpy.data.objects[n].hide_render = True

# ---------------------------------------------------------------- world: lime for camera rays, neutral for lighting
world = bpy.data.worlds.new("Studio")
scene.world = world
world.use_nodes = True
nt = world.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
out = nt.nodes.new("ShaderNodeOutputWorld")
mix = nt.nodes.new("ShaderNodeMixShader")
lp = nt.nodes.new("ShaderNodeLightPath")
bg_cam = nt.nodes.new("ShaderNodeBackground")
bg_cam.inputs["Color"].default_value = (*LIME, 1)
bg_cam.inputs["Strength"].default_value = 1.0
bg_env = nt.nodes.new("ShaderNodeBackground")
bg_env.inputs["Strength"].default_value = 1.0
tc = nt.nodes.new("ShaderNodeTexCoord")
sep_w = nt.nodes.new("ShaderNodeSeparateXYZ")
grad = nt.nodes.new("ShaderNodeValToRGB")
grad.color_ramp.elements[0].position = 0.0; grad.color_ramp.elements[0].color = (0.30, 0.31, 0.33, 1)
grad.color_ramp.elements[1].position = 1.0; grad.color_ramp.elements[1].color = (1.15, 1.17, 1.22, 1)
e = grad.color_ramp.elements.new(0.5); e.color = (0.62, 0.64, 0.68, 1)
mr = nt.nodes.new("ShaderNodeMapRange")
mr.inputs["From Min"].default_value = -1.0; mr.inputs["From Max"].default_value = 1.0
nt.links.new(tc.outputs["Generated"], sep_w.inputs["Vector"])
nt.links.new(sep_w.outputs["Z"], mr.inputs["Value"])
nt.links.new(mr.outputs["Result"], grad.inputs["Fac"])
nt.links.new(grad.outputs["Color"], bg_env.inputs["Color"])
nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
nt.links.new(bg_env.outputs["Background"], mix.inputs[1])
nt.links.new(bg_cam.outputs["Background"], mix.inputs[2])
nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])

# ---------------------------------------------------------------- floor: exact lime, darkened only where the van shadows it
# Diffuse -> Shader to RGB gives the lit floor value (with shadows); it is normalised against a
# calibration render so fully lit floor == exactly #7CFF00.
floor_mat = bpy.data.materials.new("LimeFloor")
floor_mat.use_nodes = True
fnt = floor_mat.node_tree
for n in list(fnt.nodes):
    fnt.nodes.remove(n)
fout = fnt.nodes.new("ShaderNodeOutputMaterial")
emis = fnt.nodes.new("ShaderNodeEmission")
diff = fnt.nodes.new("ShaderNodeBsdfDiffuse")
diff.inputs["Color"].default_value = (1, 1, 1, 1)
s2rgb = fnt.nodes.new("ShaderNodeShaderToRGB")
sep = fnt.nodes.new("ShaderNodeSeparateColor")
ramp = fnt.nodes.new("ShaderNodeMapRange")
ramp.clamp = True
ramp.inputs["To Min"].default_value = 0.45
ramp.inputs["To Max"].default_value = 1.0
mult = fnt.nodes.new("ShaderNodeMix")
mult.data_type = "RGBA"
mult.blend_type = "MULTIPLY"
mult.inputs["Factor"].default_value = 1.0
mult.inputs[6].default_value = (*LIME, 1)
fnt.links.new(diff.outputs["BSDF"], s2rgb.inputs["Shader"])
fnt.links.new(s2rgb.outputs["Color"], sep.inputs["Color"])
fnt.links.new(sep.outputs["Green"], ramp.inputs["Value"])
fnt.links.new(ramp.outputs["Result"], mult.inputs[7])
fnt.links.new(mult.outputs[2], emis.inputs["Color"])
emis.inputs["Strength"].default_value = 1.0
# lime only for camera rays; reflections / bounce see a neutral grey floor so the white paint stays white
lp2 = fnt.nodes.new("ShaderNodeLightPath")
grey = fnt.nodes.new("ShaderNodeBsdfDiffuse")
grey.inputs["Color"].default_value = (0.35, 0.35, 0.35, 1)
mix2 = fnt.nodes.new("ShaderNodeMixShader")
fnt.links.new(lp2.outputs["Is Camera Ray"], mix2.inputs["Fac"])
fnt.links.new(grey.outputs["BSDF"], mix2.inputs[1])
fnt.links.new(emis.outputs["Emission"], mix2.inputs[2])
fnt.links.new(mix2.outputs["Shader"], fout.inputs["Surface"])
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
floor = bpy.context.active_object
floor.name = "Floor"
floor.data.materials.append(floor_mat)


def calibrate_floor():
    """Render a tiny frame with the raw lit value and set the Map Range so open floor maps to 1.0."""
    link_raw = fnt.links.new(s2rgb.outputs["Color"], emis.inputs["Color"])
    rx, ry, pct, smp = scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage, scene.eevee.taa_render_samples
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 192, 108, 100
    scene.eevee.taa_render_samples = 8
    vt = scene.view_settings.view_transform
    scene.view_settings.view_transform = "Raw"
    fmt, depth = scene.render.image_settings.file_format, scene.render.image_settings.color_depth
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_depth = "32"
    tmp = os.path.join(OUT, "_calib.exr")
    scene.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(tmp)
    px = list(im.pixels)
    w, h = im.size
    def val(x, y):
        i = (y * w + x) * 4
        return px[i + 1]
    lit = max(val(x, 4) for x in range(4, w - 4, 8))          # bottom row of the frame = open floor near the camera
    bpy.data.images.remove(im)
    os.remove(tmp)
    fnt.links.remove(link_raw)
    fnt.links.new(mult.outputs[2], emis.inputs["Color"])
    ramp.inputs["From Min"].default_value = lit * 0.30
    ramp.inputs["From Max"].default_value = lit * 0.72   # light falloff across the floor stays exact lime; only real shadows darken
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage, scene.eevee.taa_render_samples = rx, ry, pct, smp
    scene.view_settings.view_transform = vt
    scene.render.image_settings.file_format, scene.render.image_settings.color_depth = fmt, depth
    print("floor calibration: lit value =", lit)


# ---------------------------------------------------------------- lights (fixed, three-point)
def area(name, loc, target, energy, size, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.size = size
    ld.color = color
    ob = bpy.data.objects.new(name, ld)
    scene.collection.objects.link(ob)
    ob.location = loc
    direction = Vector(target) - Vector(loc)
    ob.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return ob

# Key = sun (uniform over the floor so the lime stays exact away from the van), soft area fills.
sun_d = bpy.data.lights.new("Key", "SUN")
sun_d.energy = 4.6
sun_d.angle = math.radians(9)
sun_d.color = (1.0, 0.98, 0.95)
sun_o = bpy.data.objects.new("Key", sun_d)
scene.collection.objects.link(sun_o)
sun_o.location = (5.5, -7.5, 9.0)
sun_o.rotation_euler = (Vector((0, 0, 1.0)) - Vector(sun_o.location)).to_track_quat("-Z", "Y").to_euler()
area("Fill", (-8.0, -4.0, 4.5), (0, 0, 1.0), 900, 8.0, (0.95, 0.97, 1.0))
area("Rim", (-1.0, 9.0, 6.0), (0, 0, 1.2), 900, 5.0)
area("Top", (0.0, 0.0, 9.0), (0, 0, 0.0), 700, 10.0)

# ---------------------------------------------------------------- camera (fixed)
cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 50
cam = bpy.data.objects.new("Camera", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

def aim(loc, target):
    cam.location = loc
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()

# ---------------------------------------------------------------- render settings
scene.render.engine = "BLENDER_EEVEE_NEXT" if hasattr(bpy.types, "SceneEEVEE") and "BLENDER_EEVEE_NEXT" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
scene.eevee.taa_render_samples = 48
try:
    scene.eevee.use_raytracing = True
    scene.eevee.use_shadows = True
    scene.eevee.ray_tracing_options.resolution_scale = "1"
    scene.eevee.fast_gi_method = "GLOBAL_ILLUMINATION"
except Exception:
    pass
try:
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = 0.6
except Exception:
    pass
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.film_transparent = False
scene.render.dither_intensity = 0.0
scene.view_settings.view_transform = "Standard"   # keep #7CFF00 exact
scene.view_settings.look = "None"
scene.display_settings.display_device = "sRGB"

aim((8.2, -9.2, 3.6), (0, 0, 1.0))
calibrate_floor()

if MODE == "preview":
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.eevee.taa_render_samples = 24
    views = {
        "front34": ((7.6, -8.6, 3.2), (0, 0.1, 0.95)),
        "rear34": ((-7.6, 8.6, 3.2), (0, -0.1, 0.95)),
        "side": ((11.5, 0.0, 1.6), (0, 0, 1.0)),
        "front": ((0, -11.5, 1.6), (0, 0, 1.0)),
        "rear": ((0, 11.5, 1.6), (0, 0, 1.0)),
        "top34": ((5.0, -6.0, 8.0), (0, 0, 0.8)),
    }
    for name, (loc, target) in views.items():
        aim(loc, target)
        scene.render.filepath = os.path.join(OUT, f"preview_{name}.png")
        bpy.ops.render.render(write_still=True)
        print("rendered", scene.render.filepath)

elif MODE == "compare":
    # same viewpoints as the reference grid (long lens, slightly elevated), composited next to the cells
    scene.render.resolution_x, scene.render.resolution_y = 768, 512
    scene.eevee.taa_render_samples = 32
    cam_data.lens = 45
    D = 9.5
    views = {
        "r1c2_front": ((0.0, -D, 1.7), (0, 0, 1.0)),
        "r2c2_rear": ((0.0, D, 1.7), (0, 0, 1.0)),
        "r1c4_sideL": ((D * 1.1, 0.0, 2.3), (0, 0, 1.0)),
        "r2c4_sideR": ((-D * 1.1, 0.0, 2.3), (0, 0, 1.0)),
        "r1c1_front34L": ((D * 0.66, -D * 0.80, 2.2), (0, 0, 1.0)),
        "r1c3_front34R": ((-D * 0.66, -D * 0.80, 2.2), (0, 0, 1.0)),
        "r2c1_rear34L": ((D * 0.66, D * 0.80, 2.2), (0, 0, 1.0)),
        "r2c3_rear34R": ((-D * 0.66, D * 0.80, 2.2), (0, 0, 1.0)),
    }
    cdir = os.path.join(OUT, "compare")
    os.makedirs(cdir, exist_ok=True)
    for name, (loc, target) in views.items():
        aim(loc, target)
        scene.render.filepath = os.path.join(cdir, f"{name}.png")
        bpy.ops.render.render(write_still=True)

elif MODE == "fit":
    # orthographic side / rear / front views for livery fitting
    scene.render.resolution_x, scene.render.resolution_y = 1800, 800
    scene.eevee.taa_render_samples = 16
    cam_data.type = "ORTHO"
    for name, (loc, target, ortho, res) in {
        "sideL": ((30, 0, 1.1), (0, 0, 1.1), 6.6, (1800, 800)), "sideR": ((-30, 0, 1.1), (0, 0, 1.1), 6.6, (1800, 800)),
        "rear": ((0, 30, 1.1), (0, 0, 1.1), 2.6, (1000, 1000)), "front": ((0, -30, 1.1), (0, 0, 1.1), 2.6, (1000, 1000)),
        "top": ((0, 0, 30), (0, 0.0001, 0), 6.6, (800, 1800)),
    }.items():
        scene.render.resolution_x, scene.render.resolution_y = res
        cam_data.ortho_scale = ortho
        aim(loc, target)
        scene.render.filepath = os.path.join(OUT, f"fit_{name}.png")
        bpy.ops.render.render(write_still=True)
    cam_data.type = "PERSP"

elif MODE == "spots":
    scene.render.resolution_x, scene.render.resolution_y = 1024, 768
    scene.eevee.taa_render_samples = 32
    cam_data.lens = 60
    for name, (loc, target) in {"slide_rear": ((-4.0, 2.2, 1.9), (-0.95, 1.0, 1.8)), "roof_rear": ((-3.5, 4.5, 3.2), (-0.9, 2.4, 2.5)),
                                "ws_header": ((-2.5, -5.5, 3.0), (0, -1.9, 2.0)), "slide_full": ((-6.0, 0.4, 1.6), (-0.95, 0.2, 1.4)),
                                "roof_front": ((3.0, -3.5, 3.6), (0.8, -0.6, 2.5)), "low_rear": ((-4.2, 3.2, 0.6), (-0.9, 0.3, 1.5))}.items():
        aim(loc, target)
        scene.render.filepath = os.path.join(OUT, f"spot_{name}.png")
        bpy.ops.render.render(write_still=True)

elif MODE == "closeup":
    scene.render.resolution_x, scene.render.resolution_y = 1024, 768
    scene.eevee.taa_render_samples = 32
    cam_data.lens = 50
    for name, (loc, target) in {"lamp": ((2.6, -4.6, 1.5), (0.7, -2.6, 1.0)), "wheel": ((3.2, -3.4, 1.0), (0.98, -1.9, 0.4)),
                                "mirror": ((3.0, -3.6, 1.9), (1.05, -1.3, 1.4))}.items():
        aim(loc, target)
        scene.render.filepath = os.path.join(OUT, f"closeup_{name}.png")
        bpy.ops.render.render(write_still=True)

elif MODE == "turntable":
    aim((8.2, -9.2, 3.6), (0, 0, 1.0))
    root.rotation_mode = "XYZ"
    root.animation_data_clear()
    root.rotation_euler = (0, 0, 0)
    root.keyframe_insert("rotation_euler", frame=1, index=2)
    root.rotation_euler = (0, 0, math.radians(360))
    root.keyframe_insert("rotation_euler", frame=FRAMES + 1, index=2)
    for fc in root.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    scene.frame_start, scene.frame_end = 1, FRAMES
    scene.render.fps = 30
    tdir = os.path.join(OUT, "turntable")
    os.makedirs(tdir, exist_ok=True)
    scene.render.filepath = os.path.join(tdir, "frame_")
    bpy.ops.render.render(animation=True)
    print("turntable frames in", tdir)

elif MODE == "stills":
    scene.eevee.taa_render_samples = 96
    for name, (loc, target) in {"hero_front": ((8.2, -9.2, 3.6), (0, 0, 1.0)),
                                "hero_rear": ((-8.2, 9.2, 3.6), (0, 0, 1.0)),
                                "hero_side": ((-11.8, -1.5, 2.2), (0, 0, 1.0))}.items():
        aim(loc, target)
        scene.render.filepath = os.path.join(OUT, f"{name}.png")
        bpy.ops.render.render(write_still=True)
