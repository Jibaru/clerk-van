extends Node3D
## Clerk Van test scene (Godot 4.3+).
## Drives the named pivots of clerk_van.glb directly, the same way the web rig does:
##   Door_FL/FR/RL/RR rotate about local Y (hinge), Door_Slide translates (-X out, then -Z back),
##   Wheel_* rotate about local X, Steer_L/R rotate about local Y,
##   Light_HeadL/R (SpotLight3D) + Light_TailL/R (OmniLight3D) toggle, lens materials get emission.
## The GLB also carries AnimationPlayer clips (DoorFL_Open, ..., AllDoors_Open, Wheels_Spin).

const WHEEL_R := 0.356
const DOOR_ANGLE := {"Door_FL": -65.0, "Door_FR": 65.0, "Door_RL": -95.0, "Door_RR": 95.0}
const SLIDE_OUT := Vector3(-0.10, 0, 0)
const SLIDE_BACK := Vector3(0, 0, -1.15)

@onready var van: Node3D = $Pivot/Van
@onready var pivot: Node3D = $Pivot
@onready var ui: VBoxContainer = $UI/Panel/VBox

var nodes := {}
var rest_rot := {}
var rest_pos := {}
var door_t := {"Door_FL": 0.0, "Door_FR": 0.0, "Door_Slide": 0.0, "Door_RL": 0.0, "Door_RR": 0.0}
var door_open := {"Door_FL": false, "Door_FR": false, "Door_Slide": false, "Door_RL": false, "Door_RR": false}
var speed := 6.0
var steer_deg := 0.0
var drive := false
var turntable := false
var head_mats: Array[StandardMaterial3D] = []
var tail_mats: Array[StandardMaterial3D] = []


func _ready() -> void:
	$Camera3D.look_at(Vector3(0, 0.95, 0), Vector3.UP)
	$Sun.look_at(Vector3.ZERO, Vector3.UP)
	$Fill.look_at(Vector3.ZERO, Vector3.UP)
	for name in ["Door_FL", "Door_FR", "Door_Slide", "Door_RL", "Door_RR", "Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR",
			"Steer_L", "Steer_R", "Light_HeadL", "Light_HeadR", "Light_TailL", "Light_TailR"]:
		var n := van.find_child(name, true, false)
		if n:
			nodes[name] = n
			if n is Node3D:
				rest_rot[name] = n.rotation
				rest_pos[name] = n.position
	head_mats = _collect_materials(["Headlight_Lens", "Headlight_L", "Headlight_R"], Color(1.0, 0.96, 0.85))
	tail_mats = _collect_materials(["Taillight_Lens", "Taillight_L", "Taillight_R", "BrakeLight"], Color(1.0, 0.1, 0.06))
	_set_lights("head", false)
	_set_lights("tail", false)
	for mi in van.find_children("*", "MeshInstance3D", true, false):
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON

	ui.get_node("Drive").toggled.connect(func(on): drive = on)
	ui.get_node("Turntable").toggled.connect(func(on): turntable = on)
	ui.get_node("Headlights").toggled.connect(func(on): _set_lights("head", on))
	ui.get_node("Taillights").toggled.connect(func(on): _set_lights("tail", on))
	for d in door_open.keys():
		ui.get_node(d).toggled.connect(func(on): door_open[d] = on)
	ui.get_node("Steer").value_changed.connect(func(v): steer_deg = v)

	var missing := []
	for n in ["Door_FL", "Door_FR", "Door_Slide", "Door_RL", "Door_RR", "Wheel_FL", "Light_HeadL"]:
		if not nodes.has(n):
			missing.append(n)
	var ap: AnimationPlayer = van.find_child("AnimationPlayer", true, false)
	var clips := ap.get_animation_list() if ap else PackedStringArray()
	ui.get_node("Status").text = "nodes: %d  clips: %s%s" % [nodes.size(), ", ".join(clips),
			("\nMISSING: " + ", ".join(missing)) if missing.size() else "\nall pivots found"]


func _collect_materials(material_names: Array, emission: Color) -> Array[StandardMaterial3D]:
	## The lenses are MATERIALS on the lamp meshes (Headlight_Lens / Taillight_Lens in the Transit build),
	## shared between several meshes; duplicate them per surface so we can drive emission.
	var out: Array[StandardMaterial3D] = []
	for mi in van.find_children("*", "MeshInstance3D", true, false):
		if mi.mesh == null:
			continue
		for s in range(mi.mesh.get_surface_count()):
			var m := mi.get_active_material(s)
			if m is StandardMaterial3D and (material_names.has(m.resource_name) or material_names.has(mi.name)):
				var dup: StandardMaterial3D = m.duplicate()
				dup.emission_enabled = true
				dup.emission = emission
				dup.emission_energy_multiplier = 0.0
				mi.set_surface_override_material(s, dup)
				out.append(dup)
	return out


func _set_lights(kind: String, on: bool) -> void:
	var names := ["Light_HeadL", "Light_HeadR"] if kind == "head" else ["Light_TailL", "Light_TailR"]
	for n in names:
		if nodes.has(n):
			var l: Light3D = nodes[n]
			l.visible = on
			l.light_energy = (12.0 if kind == "head" else 3.0) if on else 0.0
			if l is SpotLight3D:
				l.spot_range = 30.0
				l.spot_angle = 38.0
				l.shadow_enabled = true
			elif l is OmniLight3D:
				l.omni_range = 4.0
	for m in (head_mats if kind == "head" else tail_mats):
		m.emission_energy_multiplier = (4.0 if kind == "head" else 3.0) if on else 0.0


func _apply_door(name: String, t: float) -> void:
	if not nodes.has(name):
		return
	var n: Node3D = nodes[name]
	var e := 2.0 * t * t if t < 0.5 else 1.0 - pow(-2.0 * t + 2.0, 2) / 2.0
	if name == "Door_Slide":
		var a := minf(1.0, t / 0.2)
		var b := maxf(0.0, (t - 0.2) / 0.8)
		n.position = rest_pos[name] + SLIDE_OUT * a + SLIDE_BACK * b
	else:
		var r: Vector3 = rest_rot[name]
		n.rotation = Vector3(r.x, r.y + deg_to_rad(DOOR_ANGLE[name]) * e, r.z)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_L: ui.get_node("Headlights").button_pressed = not ui.get_node("Headlights").button_pressed
			KEY_K: ui.get_node("Taillights").button_pressed = not ui.get_node("Taillights").button_pressed
			KEY_T: ui.get_node("Turntable").button_pressed = not ui.get_node("Turntable").button_pressed
			KEY_1: ui.get_node("Door_FL").button_pressed = not ui.get_node("Door_FL").button_pressed
			KEY_2: ui.get_node("Door_FR").button_pressed = not ui.get_node("Door_FR").button_pressed
			KEY_3: ui.get_node("Door_Slide").button_pressed = not ui.get_node("Door_Slide").button_pressed
			KEY_4: ui.get_node("Door_RL").button_pressed = not ui.get_node("Door_RL").button_pressed
			KEY_5: ui.get_node("Door_RR").button_pressed = not ui.get_node("Door_RR").button_pressed


func _process(dt: float) -> void:
	var throttle := 0.0
	if Input.is_key_pressed(KEY_W):
		throttle += 1.0
	if Input.is_key_pressed(KEY_S):
		throttle -= 1.0
	if Input.is_key_pressed(KEY_A):
		steer_deg = clampf(steer_deg + 60.0 * dt, -30.0, 30.0)
		ui.get_node("Steer").set_value_no_signal(steer_deg)
	if Input.is_key_pressed(KEY_D):
		steer_deg = clampf(steer_deg - 60.0 * dt, -30.0, 30.0)
		ui.get_node("Steer").set_value_no_signal(steer_deg)
	var v := (speed if drive else 0.0) + throttle * speed
	var d_ang := v * dt / WHEEL_R
	for w in ["Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR"]:
		if nodes.has(w):
			nodes[w].rotate_object_local(Vector3.RIGHT, d_ang)
	for s in ["Steer_L", "Steer_R"]:
		if nodes.has(s):
			var r: Vector3 = rest_rot[s]
			nodes[s].rotation = Vector3(r.x, r.y + deg_to_rad(steer_deg), r.z)
	for d in door_open.keys():
		var target := 1.0 if door_open[d] else 0.0
		var t: float = move_toward(door_t[d], target, dt / 0.9)
		if t != door_t[d]:
			door_t[d] = t
			_apply_door(d, t)
	if turntable:
		pivot.rotate_y(dt * 0.5)
