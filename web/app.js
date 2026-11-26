import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const $ = (id) => document.getElementById(id);
const MAT = {
  steel:    { label: '강철',     color: 0x3d4148, metalness: 0.35, roughness: 0.55 },
  concrete: { label: '콘크리트', color: 0xcfccc4, roughness: 0.95 },
  glass:    { label: '유리',     color: 0x7fa7c4, transparent: true, opacity: 0.45, roughness: 0.1, metalness: 0.2, depthWrite: false },
  aluminum: { label: '알루미늄', color: 0xb9bcc0, metalness: 0.5, roughness: 0.4 },
  spandrel: { label: '스팬드럴', color: 0x2f343b, roughness: 0.6 },
  wood:     { label: '목재',     color: 0xb0805a, roughness: 0.8 },
  stone:    { label: '석재',     color: 0xcdc6b9, roughness: 0.9 },
  none:     { label: '재료 없음', color: 0x9a9a9a, roughness: 0.7 },
  line:     { label: '선',       color: 0x2a5ab8 },
};

// ---------------- 3D 화면 ----------------
const canvas = $('c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor(0xf4f4f2);
const scene = new THREE.Scene();
scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8070, 1.1));
const dl = new THREE.DirectionalLight(0xffffff, 1.6); dl.position.set(0.5, -0.8, 0.9); scene.add(dl);
const dl2 = new THREE.DirectionalLight(0xffffff, 0.5); dl2.position.set(-0.7, 0.6, 0.3); scene.add(dl2);
const camera = new THREE.PerspectiveCamera(35, 1, 10, 1e7); camera.up.set(0, 0, 1); camera.position.set(1, -1.3, 0.8);
const controls = new OrbitControls(camera, canvas);
const root = new THREE.Group(); scene.add(root);
const layerGroups = {}; // 재료 → [Object3D]
let bbox = null;

function resize() {
  const r = canvas.parentElement.getBoundingClientRect();
  renderer.setSize(r.width, r.height, false); camera.aspect = r.width / r.height; camera.updateProjectionMatrix(); draw();
}
// 큰 모델은 한 장 그리는 데 오래 걸려서, 계속 그리지 않고 바뀔 때만 그린다.
let drawQueued = false;
function draw() { if (drawQueued) return; drawQueued = true; requestAnimationFrame(() => { drawQueued = false; renderer.render(scene, camera); }); }
controls.addEventListener('change', draw);
addEventListener('resize', resize); resize();

function material(m) {
  const { label, ...p } = MAT[m] || MAT.none;
  return new THREE.MeshStandardMaterial({ ...p, side: THREE.DoubleSide, flatShading: true });
}
function geom(arr) {
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(arr, 3)); g.computeVertexNormals(); return g;
}
function addLayer(m, obj) { (layerGroups[m] ||= []).push(obj); if (m === 'glass') obj.renderOrder = 2; root.add(obj); }

function clearScene() {
  for (const o of [...root.children]) { root.remove(o); o.geometry?.dispose(); o.material?.dispose(); }
  for (const k in layerGroups) delete layerGroups[k];
}

function buildScene(meta, bufs) {
  clearScene();
  for (const [m, i] of Object.entries(meta.meshes)) if (bufs[i].length) addLayer(m, new THREE.Mesh(geom(bufs[i]), material(m)));
  if (bufs[meta.lines].length) {
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(bufs[meta.lines], 3));
    addLayer('line', new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: MAT.line.color })));
  }
  for (const b of meta.blocks) {
    const M = bufs[b.matrices]; const mtx = new THREE.Matrix4();
    for (const [m, i] of Object.entries(b.tris)) {
      const im = new THREE.InstancedMesh(geom(bufs[i]), material(m), b.count);
      for (let k = 0; k < b.count; k++) { mtx.fromArray(M, k * 16); im.setMatrixAt(k, mtx); }
      im.instanceMatrix.needsUpdate = true; im.computeBoundingBox(); im.computeBoundingSphere();
      addLayer(m, im);
    }
  }
  const box = new THREE.Box3();
  root.traverse(o => { if (o.isMesh || o.isLineSegments) { if (o.isInstancedMesh) { o.computeBoundingBox(); box.union(o.boundingBox); } else { o.geometry.computeBoundingBox(); box.union(o.geometry.boundingBox); } } });
  const first = !bbox; bbox = box.isEmpty() ? null : box;
  renderLayers();
  if (first || !keepView) fit();
  draw();
}

function fit() {
  if (!bbox) return;
  const c = bbox.getCenter(new THREE.Vector3()); const r = bbox.getSize(new THREE.Vector3()).length() / 2 || 1;
  const dir = camera.position.clone().sub(controls.target).normalize();
  if (!isFinite(dir.x) || dir.length() < 0.5) dir.set(0.6, -0.75, 0.35).normalize();
  const d = r / Math.sin(THREE.MathUtils.degToRad(camera.fov) / 2) * 1.05;
  controls.target.copy(c); camera.position.copy(c).addScaledVector(dir, d);
  camera.near = d / 1000; camera.far = d * 20; camera.updateProjectionMatrix(); controls.update(); draw();
}

function renderLayers() {
  const el = $('layers'); el.innerHTML = '';
  for (const m of Object.keys(layerGroups)) {
    const lab = document.createElement('label');
    const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = layerGroups[m][0].visible;
    cb.onchange = () => { layerGroups[m].forEach(o => o.visible = cb.checked); draw(); };
    const sw = document.createElement('span'); sw.className = 'sw'; sw.style.background = '#' + (MAT[m] || MAT.none).color.toString(16).padStart(6, '0');
    lab.append(cb, sw, (MAT[m] || MAT.none).label); el.append(lab);
  }
}

// ---------------- 계산 (워커) ----------------
const worker = new Worker('worker.js');
let ready = false, reqId = 0, srcText = '', overrides = {}, keepView = false;
const pending = new Map();
worker.onmessage = (ev) => {
  const d = ev.data;
  if (d.type === 'status') setStatus(d.text);
  else if (d.type === 'ready') { ready = true; $('go').disabled = false; $('go').textContent = '계산하고 보기'; setStatus(`준비됐어요. Rhino 8 컴포넌트 목록 ${d.catalog}개로 이름도 검사해요.`); maybeAuto(); }
  else if (d.type === 'fatal') setStatus('엔진을 불러오지 못했어요: ' + d.text, true);
  else if (pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); }
};
function compute(text, ov) {
  return new Promise((res) => { const id = ++reqId; pending.set(id, res); worker.postMessage({ id, text, overrides: ov }); });
}
function setStatus(t, err) { const s = $('status'); s.textContent = t; s.classList.toggle('err', !!err); }

async function run(text, { keep = false, sliders = !keep } = {}) {
  if (!ready || !text.trim()) return;
  keepView = keep; $('busy').hidden = false; $('go').disabled = true;
  $('busyText').textContent = '계산 중… (큰 정의는 20초쯤 걸려요)';
  const d = await compute(text, overrides);
  $('busy').hidden = true; $('go').disabled = false;
  if (d.type === 'error') { setStatus('계산하지 못했어요:\n' + d.text, true); window.__result = { error: d.text }; return; }
  const m = d.meta;
  buildScene(m, d.bufs); showResult(m); if (sliders) showSliders(m);
  setStatus(`계산 ${m.seconds.toFixed(1)}초 · 노드 ${m.nodes}개 · 선 ${m.wires}개`);
  window.__result = { bake: m.bake, problems: m.problems, names: m.names, seconds: m.seconds };
}

function showResult(m) {
  $('resCard').hidden = false; $('title').textContent = m.title || '(제목 없음)'; $('summary').textContent = m.summary || '';
  const errs = m.problems.filter(p => p.startsWith('ERROR')), warns = m.problems.filter(p => !p.startsWith('ERROR'));
  const b = $('badges'); b.innerHTML = '';
  const badge = (t, c) => { const s = document.createElement('span'); s.className = 'badge ' + c; s.textContent = t; b.append(s); };
  badge(m.names.length ? `이름 오류 ${m.names.length}` : '이름 검사 통과', m.names.length ? 'err' : 'ok');
  badge(errs.length ? `계산 오류 ${errs.length}` : '계산 오류 없음', errs.length ? 'err' : 'ok');
  if (warns.length) badge(`경고 ${warns.length}`, 'warn');
  badge(`Bake ${m.bake.toLocaleString()}개`, '');
  for (const bl of m.blocks) badge(`블록 ${bl.name} ×${bl.count}`, '');
  const ul = $('msgs'); ul.innerHTML = '';
  for (const t of [...m.names.map(x => 'ERROR 이름: ' + x), ...errs, ...warns]) {
    const li = document.createElement('li'); li.textContent = t; li.className = t.startsWith('ERROR') ? 'err' : 'warn'; ul.append(li);
  }
}

function showSliders(m) {
  const box = $('sliders'); box.innerHTML = '';
  $('sliderCard').hidden = !m.sliders.length;
  const glabel = Object.fromEntries((m.groups || []).map(g => [g.id, g.label]));
  let lastG = null;
  for (const s of m.sliders) {
    if (s.group !== lastG) { lastG = s.group; const h = document.createElement('div'); h.className = 'grp'; h.textContent = glabel[s.group] || s.group || ''; box.append(h); }
    if ('toggle' in s) {
      const l = document.createElement('label'); l.className = 'tg';
      const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = s.toggle;
      cb.onchange = () => { overrides[s.id] = cb.checked; run(srcText, { keep: true }); };
      l.append(cb, s.name); box.append(l); continue;
    }
    const w = document.createElement('div'); w.className = 'sl';
    const name = document.createElement('span'); name.textContent = s.name;
    const num = document.createElement('input'); num.type = 'number'; num.value = s.value;
    const r = document.createElement('input'); r.type = 'range'; r.min = s.min; r.max = s.max; r.value = s.value;
    r.step = s.int ? 1 : (s.max - s.min) / 200 || 0.01; num.step = r.step;
    r.oninput = () => num.value = r.value;
    const commit = (v) => { overrides[s.id] = Number(v); r.value = v; num.value = v; run(srcText, { keep: true }); };
    r.onchange = () => commit(r.value); num.onchange = () => commit(num.value);
    w.append(name, num, r); box.append(w);
  }
}

// ---------------- 입력 ----------------
function load(text, label) {
  srcText = text; overrides = {}; $('txt').value = text;
  setStatus(label + ' 불러옴'); run(text);
}
$('go').onclick = () => { const t = $('txt').value; if (t !== srcText) { srcText = t; overrides = {}; } run(srcText); };
$('reset').onclick = () => { overrides = {}; run(srcText, { keep: true, sliders: true }); };
$('file').onchange = async (e) => { const f = e.target.files[0]; if (f) load(await f.text(), f.name); e.target.value = ''; };
$('fit').onclick = fit;
$('shot').onclick = () => { const a = document.createElement('a'); a.href = canvas.toDataURL('image/png'); a.download = 'gh_ai_미리보기.png'; a.click(); };
$('copy').onclick = async () => {
  try {
    const g = JSON.parse(srcText.trim().replace(/^```(json)?|```$/g, ''));
    for (const n of g.nodes || []) if (n.id in overrides) { if (n.slider) n.slider[2] = overrides[n.id]; else if ('toggle' in n) n.toggle = overrides[n.id]; }
    await navigator.clipboard.writeText(JSON.stringify(g, null, 1)); setStatus('지금 값이 담긴 JSON을 복사했어요. 빌더에 붙여 넣으세요.');
  } catch (e) { setStatus('복사하지 못했어요: ' + e.message, true); }
};

let examples = [];
fetch('examples/manifest.json').then(r => r.json()).then(list => {
  examples = list;
  for (const e of list) { const o = document.createElement('option'); o.value = e.file; o.textContent = e.name; $('ex').append(o); }
  maybeAuto();
}).catch(() => {});
$('ex').onchange = async () => { const f = $('ex').value; if (!f) return; load(await (await fetch('examples/' + encodeURIComponent(f))).text(), f); };

let autoDone = false;
async function maybeAuto() {
  if (autoDone || !ready || !examples.length) return; autoDone = true;
  const q = new URLSearchParams(location.search).get('ex');
  const e = q ? examples.find(x => x.file.startsWith(q)) : examples.find(x => x.file.startsWith('01'));
  if (e) { $('ex').value = e.file; load(await (await fetch('examples/' + encodeURIComponent(e.file))).text(), e.name); }
}
