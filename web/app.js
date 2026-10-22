// Clerk Van glTF test rig (Three.js). Loads ./clerk_van.glb (exported from Blender,
// Y-up, front = +Z... see README) and drives the named pivots directly:
//   Door_FL / Door_FR / Door_RL / Door_RR  -> rotate about local Y (hinge)
//   Door_Slide                             -> translate out (-X) then back (-Z)
//   Wheel_FL/FR/RL/RR                      -> rotate about local X (rolling)
//   Steer_L / Steer_R                      -> rotate about local Y (steering)
//   Light_HeadL/R (spot), Light_TailL/R (point), materials Headlight_Lens / Taillight_Lens
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const params = new URLSearchParams(location.search);
const WHEEL_R = 0.356;
const DOOR = {
  Door_FL: { kind: 'hinge', angle: THREE.MathUtils.degToRad(-65) },
  Door_FR: { kind: 'hinge', angle: THREE.MathUtils.degToRad(65) },
  Door_RL: { kind: 'hinge', angle: THREE.MathUtils.degToRad(-95) },
  Door_RR: { kind: 'hinge', angle: THREE.MathUtils.degToRad(95) },
  Door_Slide: { kind: 'slide', out: new THREE.Vector3(-0.10, 0, 0), back: new THREE.Vector3(0, 0, -1.05) },
};

// ---------------------------------------------------------------- renderer / scene
const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor(0x000000, 0);            // page CSS provides the exact #7CFF00
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 200);
const controls = new OrbitControls(camera, canvas);
controls.target.set(0, 0.95, 0);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI / 2 - 0.02;
controls.minDistance = 3; controls.maxDistance = 40;

scene.add(new THREE.HemisphereLight(0xffffff, 0xb8ff66, 0.9));
const sun = new THREE.DirectionalLight(0xffffff, 2.6);
sun.position.set(6, 9, 7);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.left = -5; sun.shadow.camera.right = 5; sun.shadow.camera.top = 5; sun.shadow.camera.bottom = -5;
sun.shadow.camera.near = 1; sun.shadow.camera.far = 40; sun.shadow.bias = -0.0005; sun.shadow.normalBias = 0.02;
scene.add(sun);
const fill = new THREE.DirectionalLight(0xffffff, 0.9); fill.position.set(-7, 4, -5); scene.add(fill);

const ground = new THREE.Mesh(new THREE.PlaneGeometry(80, 80), new THREE.ShadowMaterial({ opacity: 0.22 }));
ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; scene.add(ground);

// Turntable pivot: the van rotates, camera + lights stay fixed.
const pivot = new THREE.Group(); scene.add(pivot);

// ---------------------------------------------------------------- state
const S = {
  drive: false, speed: 6, throttle: 0, steer: 0, turntable: false, head: false, tail: false,
  doorsOpen: { Door_FL: false, Door_FR: false, Door_Slide: false, Door_RL: false, Door_RR: false },
  doorT: { Door_FL: 0, Door_FR: 0, Door_Slide: 0, Door_RL: 0, Door_RR: 0 },
  distance: 0,
};
const nodes = {};         // name -> Object3D
const rest = {};          // name -> { pos, rot }
const mats = {};          // material name -> Material
let mixer = null, clips = [], activeAction = null, van = null;

const status = document.getElementById('status');
const log = (s) => { status.textContent = s; };

// ---------------------------------------------------------------- load
const loader = new GLTFLoader();
const MODELS = { display: './clerk_van.glb', print: './clerk_van_print.glb' };
let currentModel = null;
function loadModel(kind) {
  if (kind === currentModel) return;
  currentModel = kind;
  for (const b of document.querySelectorAll('[data-model]')) b.classList.toggle('on', b.dataset.model === kind);
  if (van) { stopClip(); pivot.remove(van); van.traverse((o) => { if (o.isMesh) o.geometry.dispose(); }); van = null; }
  for (const k of Object.keys(nodes)) delete nodes[k];
  for (const k of Object.keys(rest)) delete rest[k];
  for (const k of Object.keys(mats)) delete mats[k];
  mixer = null; clips = []; activeAction = null;
  const file = MODELS[kind];
  log(`loading ${file}…`);
  loader.load(file, (gltf) => {
  van = gltf.scene;
  pivot.add(van);
  van.traverse((o) => {
    if (o.name) nodes[o.name] = o;
    if (o.isMesh) {
      o.castShadow = true; o.receiveShadow = true;
      const ms = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of ms) if (m && m.name) mats[m.name] = m;
    }
    if (o.isLight) { o.castShadow = false; }
  });
  for (const n of Object.keys(DOOR).concat(['Wheel_FL', 'Wheel_FR', 'Wheel_RL', 'Wheel_RR', 'Steer_L', 'Steer_R'])) {
    const o = nodes[n];
    if (o) rest[n] = { pos: o.position.clone(), rot: o.rotation.clone() };
  }
  // lens emissive colours (exported with strength 0, so set the colour here)
  if (mats.Headlight_Lens) { mats.Headlight_Lens.emissive.set(0xfff6e0); mats.Headlight_Lens.emissiveIntensity = 0; }
  if (mats.Taillight_Lens) { mats.Taillight_Lens.emissive.set(0xff1a10); mats.Taillight_Lens.emissiveIntensity = 0; }
  for (const n of ['Light_HeadL', 'Light_HeadR', 'Light_TailL', 'Light_TailR']) {
    const l = nodes[n]; if (!l) continue;
    l.userData.onIntensity = n.startsWith('Light_Head') ? 60 : 6;
    l.intensity = 0; l.visible = false;
    if (l.isSpotLight) { l.angle = THREE.MathUtils.degToRad(38); l.penumbra = 0.6; l.distance = 30; l.decay = 1.2; }
    if (l.isPointLight) { l.distance = 4; l.decay = 1.5; }
  }
  // exported animation clips
  clips = gltf.animations || [];
  mixer = new THREE.AnimationMixer(van);
  const sel = document.getElementById('clipSelect');
  sel.innerHTML = clips.length ? clips.map((c) => `<option>${c.name}</option>`).join('') : '<option>(no clips)</option>';
  mixer.addEventListener('finished', () => { stopClip(); });

  const missing = Object.keys(DOOR).concat(['Wheel_FL', 'Wheel_FR', 'Wheel_RL', 'Wheel_RR', 'Light_HeadL', 'Light_TailL']).filter((n) => !nodes[n]);
  let tris = 0; van.traverse((o) => { if (o.isMesh) { const g = o.geometry; tris += (g.index ? g.index.count : g.attributes.position.count) / 3; } });
  if (kind === 'print') {
    // matte grey "resin" so the relief reads in the viewer
    const resin = new THREE.MeshStandardMaterial({ color: 0xc9cad0, roughness: 0.7, metalness: 0 });
    van.traverse((o) => { if (o.isMesh) o.material = resin; });
    log(`${file} loaded\n${Math.round(tris)} tris · one watertight shell, livery raised 15 mm` +
        `\nno rigs in this model (doors, wheels, lights are static)\nSTL at 1:24 in the Download section`);
  } else {
    log(`${file} loaded\n${Object.keys(nodes).length} nodes · ${Math.round(tris)} tris · ${clips.length} clips` +
        `\nmaterials: ${Object.keys(mats).length}` + (missing.length ? `\nMISSING: ${missing.join(', ')}` : '\nall pivots found'));
  }
  document.getElementById('loading')?.remove();
  applyUrlParams();
  }, (ev) => { if (ev.total) log(`loading ${file} ${(100 * ev.loaded / ev.total).toFixed(0)}%`); },
     (err) => { log(`Failed to load ${file}: ` + err.message + '\nServe this folder over http (see README).'); console.error(err); });
}
loadModel(params.get('model') === 'print' ? 'print' : 'display');

// ---------------------------------------------------------------- controls
function setView(name) {
  const v = { front34: [7.4, 3.0, 7.2], side: [11.0, 1.6, 0.0], rear34: [-7.4, 3.0, -7.2], top: [0.01, 12, 0.01], front: [0, 1.6, 11], rear: [0, 1.6, -11] }[name] || [7.4, 3.0, 7.2];
  camera.position.set(...v); controls.target.set(0, 0.95, 0); controls.update();
}
setView('front34');

function setLights(kind, on) {
  const names = kind === 'head' ? ['Light_HeadL', 'Light_HeadR'] : ['Light_TailL', 'Light_TailR'];
  for (const n of names) { const l = nodes[n]; if (l) { l.visible = on; l.intensity = on ? l.userData.onIntensity : 0; } }
  const m = kind === 'head' ? mats.Headlight_Lens : mats.Taillight_Lens;
  if (m) m.emissiveIntensity = on ? (kind === 'head' ? 3.0 : 2.5) : 0;
  S[kind] = on;
  document.getElementById(kind === 'head' ? 'btnHead' : 'btnTail').classList.toggle('on', on);
}

function setDoor(name, open) {
  if (!nodes[name]) return;
  S.doorsOpen[name] = open;
  document.querySelector(`[data-door="${name}"]`)?.classList.toggle('on', open);
}
function applyDoor(name, t) {
  const o = nodes[name], r = rest[name], d = DOOR[name];
  if (!o || !r) return;
  const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;   // easeInOutQuad
  if (d.kind === 'hinge') {
    o.rotation.set(r.rot.x, r.rot.y + d.angle * e, r.rot.z);
  } else {
    // sliding door: first 20% moves outwards, remaining 80% slides back
    const a = Math.min(1, t / 0.2), b = Math.max(0, (t - 0.2) / 0.8);
    o.position.copy(r.pos).addScaledVector(d.out, a).addScaledVector(d.back, b);
  }
}

function playClip(name) {
  if (!mixer) return;
  const clip = clips.find((c) => c.name === name); if (!clip) return;
  stopClip();
  activeAction = mixer.clipAction(clip);
  activeAction.reset().setLoop(THREE.LoopOnce, 1); activeAction.clampWhenFinished = true; activeAction.play();
  document.getElementById('btnClip').classList.add('on');
}
function stopClip() {
  if (activeAction) { activeAction.stop(); activeAction = null; mixer.stopAllAction(); }
  document.getElementById('btnClip').classList.remove('on');
  // restore the direct-control pose
  for (const n of Object.keys(rest)) { nodes[n].position.copy(rest[n].pos); nodes[n].rotation.copy(rest[n].rot); }
  for (const n of Object.keys(DOOR)) applyDoor(n, S.doorT[n]);
}

function resetAll() {
  for (const n of Object.keys(DOOR)) { setDoor(n, false); }
  setLights('head', false); setLights('tail', false);
  S.drive = false; S.turntable = false; S.steer = 0; S.distance = 0;
  document.getElementById('btnDrive').classList.remove('on'); document.getElementById('btnTurntable').classList.remove('on');
  document.getElementById('steer').value = 0; document.getElementById('steerVal').textContent = '0°';
  pivot.rotation.y = 0;
  stopClip();
  setView('front34');
}

// UI wiring
const q = (id) => document.getElementById(id);
q('btnDrive').onclick = () => { S.drive = !S.drive; q('btnDrive').classList.toggle('on', S.drive); };
q('btnTurntable').onclick = () => { S.turntable = !S.turntable; q('btnTurntable').classList.toggle('on', S.turntable); };
q('btnHead').onclick = () => setLights('head', !S.head);
q('btnTail').onclick = () => setLights('tail', !S.tail);
q('btnAllDoors').onclick = () => { const open = !Object.values(S.doorsOpen).every(Boolean); for (const n of Object.keys(DOOR)) setDoor(n, open); };
for (const b of document.querySelectorAll('[data-door]')) b.onclick = () => setDoor(b.dataset.door, !S.doorsOpen[b.dataset.door]);
for (const b of document.querySelectorAll('[data-view]')) b.onclick = () => setView(b.dataset.view);
for (const b of document.querySelectorAll('[data-model]')) b.onclick = () => loadModel(b.dataset.model);
q('btnReset').onclick = resetAll;
q('btnClip').onclick = () => { if (activeAction) stopClip(); else playClip(q('clipSelect').value); };
q('speed').oninput = (e) => { S.speed = +e.target.value; q('speedVal').textContent = `${S.speed} m/s`; };
q('steer').oninput = (e) => { S.steer = +e.target.value; q('steerVal').textContent = `${S.steer}°`; };
q('btnShot').onclick = () => { renderer.render(scene, camera); const a = document.createElement('a'); a.download = 'clerk_van.png'; a.href = canvas.toDataURL('image/png'); a.click(); };

const keys = new Set();
addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  keys.add(e.key.toLowerCase());
  const k = e.key.toLowerCase();
  if (k === 'l') setLights('head', !S.head);
  if (k === 'k') setLights('tail', !S.tail);
  if (k === 't') q('btnTurntable').click();
  if (k === 'o') q('btnAllDoors').click();
  if (k === 'r') resetAll();
  if (k === 'p') loadModel(currentModel === 'print' ? 'display' : 'print');
  const dn = { 1: 'Door_FL', 2: 'Door_FR', 3: 'Door_Slide', 4: 'Door_RL', 5: 'Door_RR' }[k];
  if (dn) setDoor(dn, !S.doorsOpen[dn]);
});
addEventListener('keyup', (e) => keys.delete(e.key.toLowerCase()));

function applyUrlParams() {
  if (params.get('view')) setView(params.get('view'));
  if (params.get('lights') === '1') { setLights('head', true); setLights('tail', true); }
  if (params.get('doors') === '1') { for (const n of Object.keys(DOOR)) { setDoor(n, true); S.doorT[n] = 1; applyDoor(n, 1); } }
  if (params.get('spin') === '1') { S.drive = true; }
  if (params.get('turn')) { pivot.rotation.y = THREE.MathUtils.degToRad(+params.get('turn')); }
}

// ---------------------------------------------------------------- loop
function resize() {
  const w = innerWidth, h = innerHeight;
  if (canvas.width !== Math.floor(w * renderer.getPixelRatio()) || canvas.height !== Math.floor(h * renderer.getPixelRatio())) {
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
  }
}
const clock = new THREE.Clock();
function tick() {
  requestAnimationFrame(tick);
  resize();
  const dt = Math.min(clock.getDelta(), 0.05);

  // keyboard driving
  const kb = (keys.has('w') ? 1 : 0) - (keys.has('s') ? 1 : 0);
  const ks = (keys.has('a') ? 1 : 0) - (keys.has('d') ? 1 : 0);
  if (ks) { S.steer = THREE.MathUtils.clamp(S.steer + ks * 60 * dt, -30, 30); q('steer').value = Math.round(S.steer); q('steerVal').textContent = `${Math.round(S.steer)}°`; }
  const v = (S.drive ? S.speed : 0) + kb * S.speed;

  if (van) {
    // wheels roll: Blender +X == glTF +X, positive = forward
    const dAng = (v * dt) / WHEEL_R;
    for (const n of ['Wheel_FL', 'Wheel_FR', 'Wheel_RL', 'Wheel_RR']) if (nodes[n] && !activeAction) nodes[n].rotation.x += dAng;
    for (const n of ['Steer_L', 'Steer_R']) if (nodes[n] && rest[n]) nodes[n].rotation.y = rest[n].rot.y + THREE.MathUtils.degToRad(S.steer);
    // doors ease towards their target
    for (const n of Object.keys(DOOR)) {
      const target = S.doorsOpen[n] ? 1 : 0;
      const t = S.doorT[n] + Math.sign(target - S.doorT[n]) * Math.min(Math.abs(target - S.doorT[n]), dt / 0.9);
      if (t !== S.doorT[n]) { S.doorT[n] = t; if (!activeAction) applyDoor(n, t); }
    }
    if (S.turntable) pivot.rotation.y += dt * 0.5;
    if (activeAction) mixer.update(dt);
  }
  controls.update();
  renderer.render(scene, camera);
}
tick();
