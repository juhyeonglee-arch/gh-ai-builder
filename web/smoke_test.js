// 웹 미리보기 자동 확인: node web/smoke_test.js <사이트폴더> <결과폴더>
// 사이트를 띄우고 예제마다 실제 브라우저로 계산 → 오류 없음·Bake 개수 확인 → 화면 그림 저장.
// (로컬 시험용) 환경변수 LOCAL_CDN=<폴더> 를 주면 jsdelivr 요청을 그 폴더의 파일로 대신한다.
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const [site, out] = process.argv.slice(2).map(p => path.resolve(p));
fs.mkdirSync(out, { recursive: true });
const TYPES = { '.html': 'text/html', '.js': 'application/javascript', '.mjs': 'application/javascript', '.css': 'text/css', '.json': 'application/json', '.wasm': 'application/wasm', '.txt': 'text/plain; charset=utf-8', '.py': 'text/plain; charset=utf-8' };
const srv = http.createServer((q, r) => {
  const f = path.join(site, decodeURIComponent(new URL(q.url, 'http://x').pathname).replace(/\/$/, '/index.html'));
  if (!f.startsWith(site) || !fs.existsSync(f)) { r.writeHead(404); return r.end(); }
  r.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream' }); fs.createReadStream(f).pipe(r);
}).listen(0);
const base = `http://127.0.0.1:${srv.address().port}/`;
const manifest = JSON.parse(fs.readFileSync(path.join(site, 'examples', 'manifest.json'), 'utf8'));
const expect = JSON.parse(process.env.EXPECT || '{}'); // {"08": 80081}

(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const ctx = await b.newContext({ viewport: { width: 1400, height: 900 } });
  if (process.env.LOCAL_CDN) {
    const L = process.env.LOCAL_CDN;
    await ctx.route('https://cdn.jsdelivr.net/**', async (rt) => {
      const u = new URL(rt.request().url()).pathname;
      let f = null;
      if (u.startsWith('/pyodide/')) f = path.join(L, 'pyodide', u.split('/').slice(4).join('/'));
      else if (u.startsWith('/npm/three@')) f = path.join(L, 'three', u.split('/').slice(3).join('/'));
      if (!f || !fs.existsSync(f)) return rt.fulfill({ status: 404, body: '' });
      rt.fulfill({ status: 200, body: fs.readFileSync(f), contentType: TYPES[path.extname(f)] || 'application/octet-stream', headers: { 'Access-Control-Allow-Origin': '*' } });
    });
  }
  let failed = 0; const rows = [];
  for (const e of manifest) {
    const key = e.file.slice(0, 2);
    const pg = await ctx.newPage(); const logs = [];
    pg.on('console', m => { if (m.type() === 'error') logs.push(m.text()); });
    pg.on('pageerror', er => logs.push(String(er)));
    const t0 = Date.now();
    await pg.goto(base + '?ex=' + key);
    let res = null;
    try {
      await pg.waitForFunction(() => window.__result, null, { timeout: 300000 });
      res = await pg.evaluate(() => window.__result);
    } catch (er) { res = { error: 'timeout: ' + (await pg.locator('#status').innerText().catch(() => '')) }; }
    await pg.waitForTimeout(500);
    await pg.screenshot({ path: path.join(out, `웹_${e.file.replace(/\.json$/, '')}.png`) });
    const errs = res.error ? [res.error] : res.problems.filter(p => p.startsWith('ERROR')).concat(res.names);
    const bakeOk = !(key in expect) || (res.bake === expect[key]);
    const ok = !errs.length && res.bake > 0 && bakeOk && !logs.length;
    if (!ok) failed++;
    rows.push(`| ${e.file} | ${ok ? '✅' : '❌'} | ${res.bake ?? '-'} | ${res.seconds ? res.seconds.toFixed(1) : '-'} | ${((Date.now() - t0) / 1000).toFixed(0)} | ${[...errs, ...logs, bakeOk ? '' : 'Bake 기대값 ' + expect[key]].filter(Boolean).join('; ').slice(0, 200)} |`);
    console.log(rows.at(-1));
    await pg.close();
  }
  const md = `## 웹 미리보기 확인 — ${failed ? '실패 있음 ❌' : '모두 통과 ✅'}\n\n| 예제 | 결과 | Bake | 계산(초) | 전체(초) | 메모 |\n|---|---|---|---|---|---|\n${rows.join('\n')}\n`;
  fs.writeFileSync(path.join(out, 'web_summary.md'), md); console.log(md);
  await b.close(); srv.close(); process.exit(failed ? 1 : 0);
})();
