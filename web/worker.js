// 웹 워커: Pyodide(브라우저 속 파이썬)로 그래스호퍼 흉내 검사기를 돌린다. 화면이 멈추지 않게 따로 돈다.
const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/';
importScripts(PYODIDE + 'pyodide.js');
const FILES = ['GH_AI_builder.py', 'ghsim.py', 'export_tris.py', 'check_examples_real.py', 'sim_web.py'];
let py = null;

async function boot() {
  postMessage({ type: 'status', text: '파이썬 엔진 받는 중… (처음 한 번 10~30초)' });
  py = await loadPyodide({ indexURL: PYODIDE });
  postMessage({ type: 'status', text: '계산 도구(numpy, shapely) 받는 중…' });
  await py.loadPackage(['numpy', 'shapely']);
  py.FS.mkdirTree('/app');
  for (const f of FILES) {
    const t = await (await fetch('py/' + f, { cache: 'no-cache' })).text();
    py.FS.writeFile('/app/' + f, t);
  }
  const cat = await (await fetch('real_catalog_rhino8.txt')).text();
  py.globals.set('CAT', cat);
  await py.runPythonAsync(`
import sys; sys.path.insert(0, '/app')
import sim_web
N_CAT = sim_web.load_catalog(CAT)
`);
  postMessage({ type: 'ready', catalog: py.globals.get('N_CAT') });
}
const booting = boot().catch(e => postMessage({ type: 'fatal', text: String(e) }));

onmessage = async (ev) => {
  await booting;
  const { id, text, overrides } = ev.data;
  const t0 = performance.now();
  try {
    py.globals.set('TXT', text);
    py.globals.set('OV', JSON.stringify(overrides || {}));
    const out = py.runPython('sim_web.run_web(TXT, OV)');
    const meta = JSON.parse(out.get(0));
    const list = out.get(1);
    const bufs = [];
    for (let i = 0; i < list.length; i++) {
      const p = list.get(i); const b = p.getBuffer('f32');
      bufs.push(new Float32Array(b.data)); b.release(); p.destroy();
    }
    list.destroy(); out.destroy();
    meta.seconds = (performance.now() - t0) / 1000;
    postMessage({ type: 'result', id, meta, bufs }, bufs.map(b => b.buffer));
  } catch (e) {
    postMessage({ type: 'error', id, text: String(e.message || e).split('\n').slice(-3).join('\n') });
  }
};
