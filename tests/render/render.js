// node render.js <datadir> <out.png> '<params json>'
const { chromium } = require('playwright'); const fs=require('fs'); const path=require('path');
(async()=>{
  const [dir,out,pj]=process.argv.slice(2); const P=JSON.parse(pj);
  const b=await chromium.launch({args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const pg=await b.newPage({viewport:{width:P.w,height:P.h}});
  const three=process.env.THREE_JS;
  await pg.route('http://x/**', async r=>{ const u=new URL(r.request().url()); let f;
    if(u.pathname=='/'||u.pathname=='/render.html') f=path.join(__dirname,'render.html');
    else if(u.pathname=='/three.module.js') f=three;
    else if(u.pathname.startsWith('/data/')) f=path.join(dir,u.pathname.slice(6));
    if(!f||!fs.existsSync(f)) return r.fulfill({status:404,body:''});
    const ct=f.endsWith('.js')?'application/javascript':f.endsWith('.html')?'text/html':f.endsWith('.json')?'application/json':'application/octet-stream';
    r.fulfill({status:200,body:fs.readFileSync(f),contentType:ct}); });
  pg.on('console',m=>{ if(m.type()=='error') console.log('console:',m.text()); });
  pg.on('pageerror',e=>console.log('pageerror',e.message));
  await pg.addInitScript(p=>{window.__params=p;},P);
  await pg.goto('http://x/render.html');
  await pg.waitForFunction(()=>window.__done===true,null,{timeout:240000});
  await pg.locator('#c').screenshot({path:out}); await b.close();
})();
