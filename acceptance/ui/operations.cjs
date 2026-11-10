// Change 6: sampled operations retain exact evidence and fail closed on coverage gaps.
const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');

const {contentErrors}=require('./compare.cjs');
const functional=require('./functional_actions.cjs');
const {approvedPresentation}=require('./approved_presentation.cjs');
const isAssertion=action=>['visible','text','value'].includes(action)||functional.assertions.has(action);
const {compareOperation,compareRepeatability,operationReport}=require('./operations_compare.cjs');
let out,plan,selection;
const write=(p,data)=>fs.writeFileSync(p,Buffer.isBuffer(data)||typeof data==='string'?data:JSON.stringify(data,null,2));
const bases={java:'http://127.0.0.1:38080',rust:'http://127.0.0.1:38081'};
const comparisons=[],repeatability=[];
let expected=[];
function buildCases(selection,plan){
 const cases=[];
 for(const selected of selection.selected||[]){
  const screen=plan.screens?.find(s=>s.key===selected.key);
  const operations=screen?.operations?.length?screen.operations:[{id:'missing-inventory',unverifiedReason:'No operation inventory'}];
  for(const route of selected.routes?.length?selected.routes:['']){
   const mode=route.startsWith('/qapps')?'qapps':'html';
   const applicable=operations.filter(op=>!op.modes||op.modes.includes(mode));
   if(!applicable.length)applicable.push({id:'missing-mode-inventory',unverifiedReason:'No operation inventory for selected mode'});
   for(const op of applicable)cases.push({id:selected.key+':'+mode+':'+op.id,route,op:{...op,selectedScreenKey:selected.key,selectedMode:mode,selectedRoute:route,...(!route?{unverifiedReason:'Missing selected route'}:{})}});
  }
 }
 return cases;
}
function operationIssues(op,metadata){
 const issues=[];
 if(op.unverifiedReason)issues.push(op.unverifiedReason);
 if(!Array.isArray(op.steps))issues.push('missing explicit steps');
 const steps=op.steps||[],lastAction=steps.findLastIndex(s=>!isAssertion(s.action));
 const assertions=[...steps.slice(lastAction+1),...(op.postconditions||[])].filter(s=>isAssertion(s.action)&&!(s.action==='visible'&&['body','html',':root'].includes(s.selector)));
 if(lastAction>=0&&!assertions.length)issues.push('interactive operation has no success postcondition');
 if(op.postconditions&&!op.postconditions.every(s=>isAssertion(s.action)))issues.push('unsupported postcondition');
 if(op.functionalSuiteId){
  const scope=op.functionalScope;
  if(!scope||scope.screen!==op.selectedScreenKey||scope.mode!==op.selectedMode||scope.path!==new URL(operationRoute(op.selectedRoute||'/',op),'http://local.invalid').pathname)issues.push('functional suite scope does not match selected screen/mode/route');
  if(!(op.steps||[]).some(s=>isAssertion(s.action)))issues.push('functional suite has no explicit assertion');
 }
 for(const fixture of op.fixturePrerequisites||[])for(const side of ['java','rust'])
  if(!metadata?.sides?.[side]?.fixtures?.some(f=>f.name===fixture&&f.status==='verified'))issues.push(side+': fixture not verified: '+fixture);
 return issues;
}
function operationRoute(route,op){
 const u=new URL(op.route||route,'http://operation.invalid');
 if(u.origin!=='http://operation.invalid')throw Error('operation route must stay on the local engine');
 if((u.pathname.startsWith('/qapps'))!==(route.startsWith('/qapps')))throw Error('operation route changes render mode');
 for(const [key,value] of Object.entries(op.routeParameters||{}))u.searchParams.set(key,String(value));
 return u.pathname+u.search;
}
async function perform(page,step){
 const locator=step.selector?page.locator(step.selector):null;
 let responseWait;
 if(step.response){
  const spec=step.response;
  if(!spec.path||!spec.method||!Number.isInteger(spec.status))throw Error('incomplete expected response');
  responseWait=page.waitForResponse(r=>{const u=new URL(r.url());return u.pathname+u.search===spec.path&&r.request().method()===spec.method;},{timeout:10000});
  responseWait.catch(()=>{});
 }
 const action=async()=>{
  if(step.action==='fill')await locator.fill(step.value);
  else if(step.action==='click')await locator.click();
  else if(step.action==='select')await locator.selectOption(step.value);
  else if(step.action==='check')await locator.check();
  else if(step.action==='uncheck')await locator.uncheck();
  else if(step.action==='press')await locator.press(step.value);
  else if(step.action==='goto'){const u=new URL(step.route,page.url());if(u.origin!==new URL(page.url()).origin)throw Error('external navigation refused');await page.goto(u.href,{waitUntil:'load',timeout:25000});}
  else if(step.action==='download')await Promise.all([page.waitForEvent('download',{timeout:10000}),locator.click()]);
  else if(step.action==='visible')await locator.waitFor({state:'visible'});
  else if(step.action==='value'){if(await locator.inputValue()!==String(step.value))throw Error('postcondition value mismatch');}
  else if(step.action==='text')await page.waitForFunction(({selector,value})=>[...document.querySelectorAll(selector)].some(n=>n.innerText.includes(value)),{selector:step.selector,value:step.value},{timeout:6000});
  else throw Error('unsupported action '+step.action);
 };
 await action();
 if(responseWait){const response=await responseWait;if(response.status()!==step.response.status)throw Error('unexpected action response status');const error=await response.finished();if(error)throw error;}
 // Includes the triggering request's completed body; success is still checked separately by postconditions.
 if(!['visible','text','value','fill'].includes(step.action))await page.waitForLoadState('networkidle',{timeout:10000});
}

function snapshot(dir){
 const result=spawnSync(process.env.OPERATION_PYTHON||'python3',[path.join(__dirname,'operation_database.py'),out,dir],{encoding:'utf8',timeout:180000,maxBuffer:1024*1024});
 if(result.status!==0){write(dir+'.error.txt',String(result.stderr||result.error));return {status:'error',complete:false,equal:false,exclusions:[],evidencePath:dir};}
 return JSON.parse(result.stdout.trim());
}
async function ready(page,route){
 if(route.startsWith('/qapps')) await page.waitForFunction(()=>{const v=window.moqui?.webrootVue,p=v?.currentPathList||[],a=v?.activeSubscreens||[];return v&&v.loading===0&&p.length>0&&a.length>=p.length&&p.every((n,i)=>a[i]?.pathName===n)&&!document.querySelector('#current-page-root > .spinner');},null,{timeout:10000});
 await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>i.decode().catch(()=>{})));});
}
async function bounded(promise,millis){
 let timer;
 try{return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('response evidence completion timed out')),millis);})]);}
 finally{clearTimeout(timer);}
}
function initialTargetMatches(requested,landed){
 return landed.origin===requested.origin&&landed.pathname===requested.pathname&&[...requested.searchParams].every(([k,v])=>landed.searchParams.get(k)===v);
}
function finalizeDownloadEvidence(evidence,failedRequests,bodyFailures,op){
 // Chromium reports a download navigation as aborted; positive downloaded bytes are the body evidence.
 for(const failure of bodyFailures){const download=evidence.downloads.find(d=>d.key===failure.item.key);if(download){failure.item.body=download.body;if(failure.qvt)failure.qvt.body=download.body;}else evidence.errors.push('response body: '+failure.error);}
 for(const failure of failedRequests)if(!(failure.error==='net::ERR_ABORTED'&&evidence.downloads.some(d=>d.key===failure.key)))evidence.errors.push('request failed: '+failure.error);
 if(op.expectedDownloadUtf8!==undefined&&!evidence.downloads.some(d=>d.body.equals(Buffer.from(op.expectedDownloadUtf8))))evidence.errors.push('download content does not match expected fixture bytes');
}
async function capture(page,side,route,op,id,dir){
 const evidence={id,engine:side,exercised:false,complete:false,errors:[],http:[],qvt:[],downloads:[],functionalSuiteId:op.functionalSuiteId||null,functionalComplete:false,functionalObservations:[],functionalRawObservations:[]},jobs=[],failedRequests=[],bodyFailures=[];
 let expectedConfirmation=false;
 const onError=e=>evidence.errors.push(e.message);
 const onResponse=r=>{
  const u=new URL(r.url()),type=r.request().resourceType();
  if(u.origin!==bases[side])return;
  if(r.status()>=400)evidence.errors.push('HTTP '+r.status()+' '+u.pathname);
  if(!['document','xhr','fetch'].includes(type))return;
  const item={key:u.pathname+u.search,method:r.request().method(),status:r.status(),contentType:r.headers()['content-type']||'',body:null};evidence.http.push(item);
  const qvt=u.pathname.endsWith('.qvt')?{key:item.key,contentType:item.contentType,body:null}:null;if(qvt)evidence.qvt.push(qvt);
  jobs.push(r.body().then(body=>{item.body=body;if(qvt)qvt.body=body;}).catch(e=>bodyFailures.push({item,qvt,error:e.message})));
 };
 const onRequestFailed=r=>failedRequests.push({key:new URL(r.url()).pathname+new URL(r.url()).search,error:r.failure()?.errorText});
 const onDialog=d=>{if(expectedConfirmation)return;evidence.errors.push('unexpected dialog: '+d.type());d.dismiss().catch(e=>evidence.errors.push(e.message));};
 const onDownload=d=>jobs.push((async()=>{const file=await d.path();if(!file)throw Error('download unavailable');evidence.downloads.push({key:d.url().replace(bases[side],''),filename:d.suggestedFilename(),body:fs.readFileSync(file)});})().catch(e=>evidence.errors.push(e.message)));
 page.on('requestfailed',onRequestFailed);page.on('dialog',onDialog);page.on('response',onResponse);page.on('pageerror',onError);page.on('download',onDownload);
 try{
  await page.goto(bases[side]+route,{waitUntil:'load',timeout:25000});await ready(page,route);
  const requested=new URL(route,bases[side]),landed=new URL(page.url());
  if(!initialTargetMatches(requested,landed))throw Error('unexpected initial screen redirect');
  for(const step of [...(op.steps||[]),...(op.postconditions||[])]){
    expectedConfirmation=step.action==='confirmClick';
    try{if(op.functionalSuiteId)await functional.performFunctional(page,step,perform,evidence.functionalObservations,evidence.functionalRawObservations);else await perform(page,step);}finally{expectedConfirmation=false;}
  }
  evidence.functionalComplete=Boolean(op.functionalSuiteId&&evidence.functionalObservations.length);
  await page.waitForLoadState('networkidle',{timeout:10000});await ready(page,route);evidence.exercised=true;
  evidence.dom=Buffer.from(await page.content());
  const screenshot=await page.screenshot({fullPage:true,caret:'initial',animations:'allow',timeout:15000});
  evidence.rgba=require('pngjs').PNG.sync.read(screenshot);write(path.join(dir,side+'.png'),screenshot);
  write(path.join(dir,side+'.dom.html'),evidence.dom);
  const errorContent=contentErrors('',evidence.dom.toString());
  if(errorContent.renderError||errorContent.parameterError)evidence.errors.push('rendering or required-parameter error');
  if(/ - Login$/.test(await page.title()))evidence.errors.push('unexpected login page');
  evidence.complete=true;
 }catch(e){evidence.errors.push(e.message);
  try{write(path.join(dir,side+'.failure.dom.html'),await page.content());await page.screenshot({path:path.join(dir,side+'.failure.png'),fullPage:true,timeout:5000});}catch(captureError){evidence.errors.push('failure evidence: '+captureError.message);}
 }
 finally{try{await bounded((async()=>{let consumed=0;while(consumed<jobs.length){const batch=jobs.slice(consumed);consumed=jobs.length;await Promise.all(batch);}})(),15000);}catch(e){evidence.errors.push(e.message);
  try{write(path.join(dir,side+'.failure.dom.html'),await page.content());await page.screenshot({path:path.join(dir,side+'.failure.png'),fullPage:true,timeout:5000});}catch(captureError){evidence.errors.push('failure evidence: '+captureError.message);}
 }page.off('requestfailed',onRequestFailed);page.off('dialog',onDialog);page.off('response',onResponse);page.off('pageerror',onError);page.off('download',onDownload);}
 finalizeDownloadEvidence(evidence,failedRequests,bodyFailures,op);
 for(const [kind,items] of [['http',evidence.http],['qvt',evidence.qvt],['downloads',evidence.downloads]])items.forEach((item,i)=>{if(item.body)write(path.join(dir,side+'.'+kind+'.'+i+'.body'),item.body);});
 write(path.join(dir,side+'.metadata.json'),{...evidence,dom:undefined,rgba:undefined,http:evidence.http.map(({body,...r})=>r),qvt:evidence.qvt.map(({body,...r})=>r),downloads:evidence.downloads.map(({body,...r})=>r)});
 return evidence;
}
async function main(){
 out=process.argv[2];
 const ports=JSON.parse(fs.readFileSync(path.join(out,'ports.json')));for(const side of ['java','rust'])bases[side]='http://127.0.0.1:'+ports[side];
 plan=JSON.parse(fs.readFileSync(path.join(out,'operation-plan.json')));selection=JSON.parse(fs.readFileSync(path.join(out,'selection.json')));
 const rulesFile=path.join(__dirname,'../../approved-differences.json');
 const approvalRules=fs.existsSync(rulesFile)?JSON.parse(fs.readFileSync(rulesFile)).ui_presentation||[]:[];
 write(path.join(out,'approved-differences.json'),{ui_presentation:approvalRules});
 const crypto=require('node:crypto');
 write(path.join(out,'functional-provenance.json'),Object.fromEntries(['functional_actions.cjs','approved_presentation.cjs','../../approved-differences.json'].map(name=>{const file=path.join(__dirname,name);return [name,fs.existsSync(file)?crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'):null];})));
 const cases=buildCases(selection,plan);expected=cases.map(c=>c.id);
 write(path.join(out,'operations-result.json'),operationReport(expected,comparisons,repeatability));
 const metadata=JSON.parse(fs.readFileSync(path.join(out,'operation-fixtures/metadata.json')));
 const browser=await require('@playwright/test').chromium.launch({headless:true}),pages={};
 write(path.join(out,'browser-provenance.json'),{browser:browser.version(),viewport:{width:1440,height:900},locale:'en-US',timezoneId:'UTC',deviceScaleFactor:1});
 try{
  for(const side of ['java','rust']){
   const context=await browser.newContext({viewport:{width:1440,height:900},locale:'en-US',timezoneId:'UTC',deviceScaleFactor:1,acceptDownloads:true});
   const page=pages[side]=await context.newPage();page.setDefaultTimeout(6000);
   // Unexpected dialogs fail captures; the plan cannot silently confirm destructive actions.

   await page.goto(bases[side]+'/Login');await page.locator('#login_form input[name="username"]').fill('john.doe');await page.locator('#login_form input[name="password"]').fill('moqui');
   await Promise.all([page.waitForURL(u=>!u.pathname.endsWith('/Login'),{timeout:30000}),page.locator('#login_form button[type="submit"]').first().click()]);
  }
  let index=0;
  for(const {id,route,op} of cases){
    const dir=path.join(out,'operations',String(index++).padStart(4,'0'));fs.mkdirSync(dir,{recursive:true});write(path.join(dir,'case.json'),{id,route,operation:op});
    let result;
    const problems=operationIssues(op,metadata);
    if(problems.length){result={id,kind:'cross-engine',passed:false,issues:problems};}
    else{try{
     const before=snapshot(path.join(dir,'before'));
     const java=await capture(pages.java,'java',operationRoute(route,op),op,id,dir);
     const rust=await capture(pages.rust,'rust',operationRoute(route,op),op,id,dir);
     const after=snapshot(path.join(dir,'after'));
     result=compareOperation(java,rust,after,{qvtRequired:route.startsWith('/qapps')||op.qvtRequired===true,downloadsRequired:op.downloadsRequired===true||(op.steps||[]).some(s=>s.action==='download')});result.beforeDatabase=before;result.evidence=path.relative(out,dir);
     result.approvedPresentation=approvedPresentation(result,java,rust,{screen:op.selectedScreenKey,mode:op.selectedMode,route:operationRoute(route,op),suiteId:op.functionalSuiteId},approvalRules);
     if(before.complete!==true||before.equal!==true){result.passed=false;result.approvedPresentation.passed=false;}
     if(op.repeatability===true){
      if(op.readOnly!==true||(op.steps||[]).some(s=>!isAssertion(s.action)))
       repeatability.push({kind:'same-engine',id,passed:false,issues:['repeatability requires explicit readOnly and assertion-only steps']});
      else for(const [side,first] of [['java',java],['rust',rust]]){
       const repeatDir=path.join(dir,'repeat-'+side);fs.mkdirSync(repeatDir,{recursive:true});
       const baseline=snapshot(path.join(repeatDir,'before'));
       const second=await capture(pages[side],side,operationRoute(route,op),op,id,repeatDir);
       const final=snapshot(path.join(repeatDir,'after'));
       const complete=baseline.complete===true&&final.complete===true;
       const db={status:complete?'compared':'error',complete,equal:complete&&fs.readFileSync(path.join(repeatDir,'before',side+'.sql')).equals(fs.readFileSync(path.join(repeatDir,'after',side+'.sql'))),exclusions:[],evidencePath:repeatDir};
       const diagnostic=compareRepeatability(first,second,db,{qvtRequired:route.startsWith('/qapps')});
       diagnostic.scope='same-session reload; database snapshots bracket only the repeated GET, not a restored-state replay';
       repeatability.push(diagnostic);
      }
     }
    }catch(e){result={id,kind:'cross-engine',passed:false,issues:[e.message],evidence:path.relative(out,dir)};}}
    comparisons.push(result);write(path.join(out,'operations-result.json'),operationReport(expected,comparisons,repeatability));
    console.log(index,id,result.passed===true?'PASS':'FAIL');
  }
 }finally{await browser.close();}
 const report=operationReport(expected,comparisons,repeatability);write(path.join(out,'operations-result.json'),report);process.exitCode=report.passed?0:1;
}
module.exports={buildCases,operationIssues,operationRoute,perform,finalizeDownloadEvidence,initialTargetMatches};
if(require.main===module)main().catch(e=>{if(out){write(path.join(out,'operations-error.txt'),e.stack);const report=operationReport(expected,comparisons,repeatability);report.passed=false;report.error=e.message;write(path.join(out,'operations-result.json'),report);}process.exitCode=1;});
