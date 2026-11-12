// Change 1 acceptance: response bodies, live serialized DOM and decoded RGBA independently.
const fs=require('node:fs'), path=require('node:path');
const {chromium}=require('@playwright/test');
const {PNG}=require('pngjs');
const {bytes,pixels,contentErrors,parityPassed}=require('./compare.cjs');
const out=process.argv[2], inventory=JSON.parse(fs.readFileSync(path.join(out,'inventory.json')));
const write=(name,data)=>fs.writeFileSync(path.join(out,name),typeof data==='string'||Buffer.isBuffer(data)?data:JSON.stringify(data,null,2));
async function main(){
 const browser=await chromium.launch({headless:true});
 const contexts={}, pages={}, parameterValues={java:{},rust:{}};
 // Change 5: only verified records created in these two isolated databases enter selection.
 const fixtures=JSON.parse(fs.readFileSync(path.join(out,'fixture-parameters.json')));
 for(const side of ['java','rust']) for(const [name,values] of Object.entries(fixtures)) parameterValues[side][name]=new Set(values);
 const summary={contract:'raw equality; no normalization, masks, tolerance or approvals',browser:browser.version(),viewport:{width:1440,height:900},captures:[],unroutable:[]};
 try {
 for(const side of ['java','rust']) {
  contexts[side]=await browser.newContext({viewport:summary.viewport,locale:'en-US',timezoneId:'UTC',deviceScaleFactor:1});
  pages[side]=await contexts[side].newPage();
 }
 const bases={java:'http://127.0.0.1:38080',rust:'http://127.0.0.1:38081'};
 async function capture(key,route,index){
  const dir=path.join(out,'captures',String(index).padStart(4,'0'));fs.mkdirSync(dir,{recursive:true});
  const item={key,route,sides:{}}, qvtBodies={java:{},rust:{}};
  for(const side of ['java','rust']) {
   const page=pages[side], errors=[], httpErrors=[], responseJobs=[];
   const onResponse=r=>{
    if(r.status()>=400) httpErrors.push({url:r.url(),status:r.status()});
    const u=new URL(r.url());
    if(u.origin===bases[side] && u.pathname.endsWith('.qvt')) {
     const key=u.pathname+u.search, values=(qvtBodies[side][key]??=[]), n=values.length;values.push(null);
     responseJobs.push(r.body().then(body=>{values[n]=body;}).catch(e=>errors.push('QVT body capture: '+e.message)));
    }
   };
   page.on('response',onResponse);
   const onError=e=>errors.push(e.message);page.on('pageerror',onError);
   try {
    const response=await page.goto(bases[side]+route,{waitUntil:'load',timeout:20000});
    const body=await response.body();fs.writeFileSync(path.join(dir,side+'.response.html'),body);
    let readinessError=null;
    if(route.startsWith('/qapps')) {
     try { await page.waitForFunction(()=>{const v=window.moqui?.webrootVue; const paths=v?.currentPathList||[], active=v?.activeSubscreens||[]; return v && v.loading===0 && paths.length>0 && active.length>=paths.length && paths.every((name,i)=>active[i]?.pathName===name) && !document.querySelector('#current-page-root > .spinner');},null,{timeout:10000}); } catch(e) {readinessError=e.message;}
    }
    await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>i.decode().catch(()=>{})));});
    // Record the live page; no injected CSS, clock freezing or DOM rewriting.
    for(const href of await page.locator('a[href]').evaluateAll(nodes=>nodes.map(n=>n.href))) {
     try {const u=new URL(href); if(u.origin!==bases[side]) continue;
      for(const [k,v] of u.searchParams) {if(v) (parameterValues[side][k]??=new Set()).add(v);}
     } catch {}
    }
    const dom=await page.content();fs.writeFileSync(path.join(dir,side+'.dom.html'),dom);
    await page.screenshot({path:path.join(dir,side+'.png'),fullPage:true,caret:'initial',animations:'allow',timeout:15000});
    await Promise.all(responseJobs);
    for(const [key,values] of Object.entries(qvtBodies[side])) for(let n=0;n<values.length;n++) if(values[n]) {
     const name=require('node:crypto').createHash('sha256').update(key).digest('hex').slice(0,16);
     fs.writeFileSync(path.join(dir,side+'.qvt.'+name+'.'+n+'.html'),values[n]);
    }
    const title=await page.title();
    item.sides[side]={status:response.status(),url:page.url(),title,errorPage:/^Error\s*[-:]/i.test(title)||(/ - Login$/.test(title)&&new URL(route,bases[side]).pathname!=='/Login'),pageErrors:errors,bodyBytes:body.length,readinessError,httpErrors,...contentErrors(body,dom),unexpectedRedirect:new URL(page.url()).pathname!==new URL(route,bases[side]).pathname};
   }catch(e){item.sides[side]={error:e.message,pageErrors:errors};}
   finally{page.off('pageerror',onError);page.off('response',onResponse);}
  }
  if(['java','rust'].every(s=>!item.sides[s].error)){
   item.html=bytes(fs.readFileSync(path.join(dir,'java.response.html')),fs.readFileSync(path.join(dir,'rust.response.html')));
   item.dom=bytes(fs.readFileSync(path.join(dir,'java.dom.html')),fs.readFileSync(path.join(dir,'rust.dom.html')));
   item.pixels=pixels(PNG.sync.read(fs.readFileSync(path.join(dir,'java.png'))),PNG.sync.read(fs.readFileSync(path.join(dir,'rust.png'))));
  }
  if(route.startsWith('/qapps')) {
   const keys=[...new Set([...Object.keys(qvtBodies.java),...Object.keys(qvtBodies.rust)])].sort();
   const resources=keys.map(key=>{const a=qvtBodies.java[key]||[],b=qvtBodies.rust[key]||[];
    return {key,leftResponses:a.length,rightResponses:b.length,comparisons:Array.from({length:Math.max(a.length,b.length)},(_,i)=>a[i]&&b[i]?bytes(a[i],b[i]):{equal:false,missing:true})};});
   item.qvt={equal:resources.length>0&&resources.every(r=>r.leftResponses===r.rightResponses&&r.comparisons.every(c=>c.equal)),resources};
  }
  item.evidence=path.relative(out,dir); summary.captures.push(item);write('summary.json',summary);
  console.log(index,route,item.html?.equal,item.dom?.equal,item.pixels?.equal);
 }
 await capture('webroot/webroot/Login.xml','/Login',0);
 for(const side of ['java','rust']){
  const page=pages[side];
  await page.locator('#login_form input[name="username"]').fill('john.doe');
  await page.locator('#login_form input[name="password"]').fill('moqui');
  await Promise.all([page.waitForURL(u=>!u.pathname.endsWith('/Login'),{timeout:30000}),page.locator('#login_form button[type="submit"]').first().click()]);
  summary[side+'LoginURL']=page.url();
 }
 let index=1;
 const ordered=[...inventory.shared].sort((a,b)=>Number(inventory.screens.rust[a].required_parameters.length>0)-Number(inventory.screens.rust[b].required_parameters.length>0));
 for(const key of ordered){
  const record=inventory.screens.rust[key];
  if(record.route==='/Login') continue;
  if(!record.route || record.route.startsWith('/error') || ['/rest','/sso','/emailOAuth','/ChangePassword','/SecondFactor'].includes(record.route)) {
   summary.unroutable.push({key,reason:!record.route?'not a mapped browser screen':'special-purpose endpoint; requires dedicated scenario'}); continue;
  }
  const params=new URLSearchParams();
  const missing=[];
  for(const name of record.required_parameters){
   // Change 5: directories are not callable service definitions.
   const common=name==='serviceName' ? inventory.shared_services : [...(parameterValues.java[name]||[])].filter(v=>parameterValues.rust[name]?.has(v)).sort();
   if(common.length) params.set(name,common[0]); else missing.push(name);
  }
  const route=record.route+(params.size?'?'+params:'');
  if(missing.length) {summary.unroutable.push({key,reason:'no common record parameter in rendered links',missing});continue;}
  // Change 2: unsupported HTML is uncovered, never a successful error-page capture.
  const htmlSides=['java','rust'].filter(side=>{const modes=inventory.screens[side][key].render_modes;return modes?.[0] && !modes.includes('html');});
  if(htmlSides.length) summary.unroutable.push({key,route,reason:'HTML render mode unsupported',sides:htmlSides});
  else {await capture(key,route,index++);summary.captures.at(-1).missingParameters=missing;}
  if(record.route.startsWith('/apps/')) {await capture(key,route.replace('/apps/','/qapps/'),index++);summary.captures.at(-1).missingParameters=missing;}
 }
 summary.parameterValues=Object.fromEntries(Object.entries(parameterValues).map(([side,values])=>[side,Object.fromEntries(Object.entries(values).map(([k,v])=>[k,[...v].sort()]))]));
 summary.complete=true;
 summary.rawParityPassed=parityPassed(summary);
 process.exitCode=summary.rawParityPassed?0:1;
 write('summary.json',summary);
 }finally{await browser.close();write('summary.json',summary);}
}
main().catch(e=>{write('fatal.json',{error:e.stack});console.error(e);process.exitCode=1;});
