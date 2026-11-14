// Change 6: sampled operations retain exact evidence and fail closed on coverage gaps.
const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');

const {contentErrors}=require('./compare.cjs');
// Change 7: functional evidence qualifies only explicitly reviewed presentation scopes.
const functional=require('./functional_actions.cjs');
const {resolveEngineOperation}=require('./engine_routes.cjs');
const {approvedPresentation}=require('./approved_presentation.cjs');
const {fixtureHook}=require('./fixture_hooks.cjs');
const {captureRequestBody}=require('./request_bodies.cjs');
const {runCsrfProbe,rejectionMatches}=require('./csrf_probe.cjs');
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
   for(const op of applicable)cases.push({id:selected.key+':'+mode+':'+op.id,route,op:{...op,engineRoutes:screen?.engineRoutes||{},selectedScreenKey:selected.key,selectedMode:mode,selectedRoute:route,...(!route?{unverifiedReason:'Missing selected route'}:{})}});
  }
 }
 return cases;
}
function operationIssues(op,metadata){
 const issues=[];
 // Phase 3, Change 24: every engine-specific sequence must satisfy the same evidence rules.
 if(op.engineSteps!==undefined){
  if(typeof op.engineStepContract!=='string'||!op.engineStepContract.trim()||!op.engineSteps||Object.keys(op.engineSteps).sort().join(',')!=='java,rust')
   issues.push('Explicit engine steps require both engines and a named contract');
  for(const side of ['java','rust']){
   const {engineSteps,...base}=op;
   if(!Array.isArray(engineSteps?.[side])||!engineSteps[side].length||engineSteps[side].some(s=>!s||typeof s.action!=='string')){issues.push(side+': invalid engine step list');continue;}
   issues.push(...operationIssues({...base,steps:engineSteps?.[side]},metadata).map(issue=>side+': '+issue));
  }
  return issues;
 }
 if(op.unverifiedReason)issues.push(op.unverifiedReason);
 if(!Array.isArray(op.steps))issues.push('missing explicit steps');
 const steps=op.steps||[],lastAction=steps.findLastIndex(s=>!isAssertion(s.action));
 const assertions=[...steps.slice(lastAction+1),...(op.postconditions||[])].filter(s=>isAssertion(s.action)&&!(s.action==='visible'&&['body','html',':root'].includes(s.selector)));
 if(lastAction>=0&&!assertions.length)issues.push('interactive operation has no success postcondition');
 if(op.postconditions&&!op.postconditions.every(s=>isAssertion(s.action)))issues.push('unsupported postcondition');
 if(op.functionalSuiteId){
  const scope=op.functionalScope;
  if(!scope||scope.screen!==op.selectedScreenKey||scope.mode!==op.selectedMode||scope.path!==new URL(operationRoute(op.selectedRoute||'/',op),'http://local.invalid').pathname)issues.push('functional suite scope does not match selected screen/mode/route');
  if(![...(op.steps||[]),...(op.postconditions||[])].some(s=>isAssertion(s.action)))issues.push('functional suite has no explicit assertion');
 }
 for(const step of steps)if(step.action==='submitValues'&&(!validTransition(step)||step.method!=='POST'))issues.push('Submission requires an exact local path and POST method');
 for(const spec of op.coveredTransitions||[])if(!validTransition(spec))issues.push('Transition coverage requires an exact local path and method');
 for(const fixture of op.fixturePrerequisites||[])for(const side of ['java','rust'])
  if(!metadata?.sides?.[side]?.fixtures?.some(f=>f.name===fixture&&f.status==='verified'))issues.push(side+': fixture not verified: '+fixture);
 return issues;
}
// Phase 3, Change 24: safety and evidence requirements inspect the executed sequences.
function actualSteps(op){return op.engineSteps?['java','rust'].flatMap(side=>op.engineSteps[side]||[]):op.steps||[];}
function repeatabilityAllowed(op){return !op.session&&op.readOnly===true&&actualSteps(op).length>0&&actualSteps(op).every(s=>isAssertion(s.action));}
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
 for(const failure of bodyFailures){const download=evidence.downloads.find(d=>d.key===failure.item.key);if(download){failure.item.body=download.body;if(failure.qvt)failure.qvt.body=download.body;}
  // Phase 3, Change 29: Chromium withholds redirect bodies; retain the gap after proven completion.
  else if([301,302,303,307,308].includes(failure.item.status)&&failure.error==='response.body: Response body is unavailable for redirect responses'&&
   (evidence.http||[]).some(item=>item.status>=200&&item.status<300&&Buffer.isBuffer(item.body)&&Array.isArray(item.redirectChain)&&item.redirectChain.every(prior=>prior.sameOrigin===true)&&item.redirectChain.some(prior=>prior.key===failure.item.key&&prior.method===failure.item.method))) {
   failure.item.responseBodyUnavailable='browser-redirect';failure.item.responseBodyError=failure.error;
  }else evidence.errors.push('response body: '+failure.error);}
 for(const failure of failedRequests)if(!(failure.error==='net::ERR_ABORTED'&&evidence.downloads.some(d=>d.key===failure.key)))evidence.errors.push('request failed: '+failure.error);
 if(op.expectedDownloadUtf8!==undefined&&!evidence.downloads.some(d=>d.body.equals(Buffer.from(op.expectedDownloadUtf8))))evidence.errors.push('download content does not match expected fixture bytes');
}
// Phase 3, Change 15: every claimed transition needs an observed successful response.
function validTransition(spec){
 return spec&&typeof spec==='object'&&typeof spec.path==='string'&&spec.path.startsWith('/')&&
  !spec.path.startsWith('//')&&!spec.path.includes('#')&&['GET','POST','PUT','PATCH','DELETE'].includes(spec.method);
}
function transitionCoverage(evidence,op){
 const coverage=(op.coveredTransitions||[]).map(spec=>{
  const valid=Boolean(validTransition(spec));
  const name=typeof spec==='string'?spec:spec?.name,method=spec?.method,target=spec?.path;
  const candidates=valid?evidence.http.filter(item=>item.key===target&&item.method===method):[];
  const responses=candidates.filter(item=>item.status>=200&&item.status<300&&Buffer.isBuffer(item.body));
  const redirects=candidates.filter(item=>[301,302,303,307,308].includes(item.status));
  const terminal=evidence.http.filter(item=>item.status>=200&&item.status<300&&Buffer.isBuffer(item.body)&&
   Array.isArray(item.redirectChain)&&item.redirectChain.some(prior=>prior.key===target&&prior.method===method&&prior.sameOrigin===true));
  const observed=responses.length>0||(redirects.length>0&&terminal.length>0);
  return {name,method,target,valid,observed,responses:[...responses,...redirects,...terminal].map(item=>({key:item.key,method:item.method,status:item.status,redirectChain:item.redirectChain||[]}))};
 });
 for(const item of coverage)if(!item.observed)evidence.errors.push('Claimed transition was not observed: '+item.name);
 return coverage;
}
async function performStep(page,step,op,evidence,hooks={}){
 // Phase 3, Change 27: responses started before this action cannot prove its result.
 if(!isAssertion(step.action)){evidence.jsonRequestFloor=evidence.requestSequence||0;evidence.jsonResponseFloor=evidence.http.length-1;}
 if(step.action==='csrfProbe')return runCsrfProbe(page,step,evidence,hooks);
 // Phase 3, Change 25: real setup captures feed factor inputs without fixed shared secrets.
 if(step.action==='totpFill')return require('./totp_fixture.cjs').fillTotp(page,step,evidence);
 // Phase 3, Change 26: delivered code inputs bind to the owned fixture and account recipient.
 if(step.action==='fixtureValueFill')return require('./fixture_values.cjs').fixtureValueFill(page,step,evidence);
 // Phase 3, Change 27: assert retained JSON responses without sending extra application requests.
 if(step.action==='capturedJson')return require('./captured_json.cjs').capturedJson(page,step,evidence);
 if(op.functionalSuiteId||functional.actions.has(step.action))
  return functional.performFunctional(page,step,perform,evidence.functionalObservations,evidence.functionalRawObservations);
 return perform(page,step);
}
async function capture(page,side,route,op,id,dir){
 const evidence={id,engine:side,exercised:false,complete:false,errors:[],http:[],qvt:[],downloads:[],functionalSuiteId:op.functionalSuiteId||null,functionalComplete:false,functionalObservations:[],functionalRawObservations:[]},jobs=[],failedRequests=[],bodyFailures=[];
 let expectedConfirmation=false;
 const requestOrder=new WeakMap();evidence.requestSequence=0;
 const onRequest=request=>{if(new URL(request.url()).origin===bases[side])requestOrder.set(request,++evidence.requestSequence);};
 const onError=e=>evidence.errors.push(e.message);
 const onResponse=r=>{
  const u=new URL(r.url()),type=r.request().resourceType();
  if(u.origin!==bases[side])return;
  if(!['document','xhr','fetch'].includes(type)){if(r.status()>=400)evidence.errors.push('HTTP '+r.status()+' '+u.pathname);return;}
  const redirectChain=[];for(let prior=r.request().redirectedFrom();prior;prior=prior.redirectedFrom()){const target=new URL(prior.url());redirectChain.unshift({key:target.pathname+target.search,method:prior.method(),sameOrigin:target.origin===u.origin});}
  const item={key:u.pathname+u.search,method:r.request().method(),status:r.status(),contentType:r.headers()['content-type']||'',body:null,redirectChain,requestSequence:requestOrder.get(r.request())??null,requestContentType:r.request().headers()['content-type']||'',...captureRequestBody(r.request())};evidence.http.push(item);
  const qvt=u.pathname.endsWith('.qvt')?{key:item.key,contentType:item.contentType,body:null}:null;if(qvt)evidence.qvt.push(qvt);
  jobs.push(r.body().then(body=>{item.body=body;if(qvt)qvt.body=body;}).catch(e=>bodyFailures.push({item,qvt,error:e.message})));
 };
 const onRequestFailed=r=>failedRequests.push({key:new URL(r.url()).pathname+new URL(r.url()).search,error:r.failure()?.errorText});
 const onDialog=d=>{if(expectedConfirmation)return;evidence.errors.push('unexpected dialog: '+d.type());d.dismiss().catch(e=>evidence.errors.push(e.message));};
 const onDownload=d=>jobs.push((async()=>{const file=await d.path();if(!file)throw Error('download unavailable');evidence.downloads.push({key:d.url().replace(bases[side],''),filename:d.suggestedFilename(),body:fs.readFileSync(file)});})().catch(e=>evidence.errors.push(e.message)));
 page.on('request',onRequest);page.on('requestfailed',onRequestFailed);page.on('dialog',onDialog);page.on('response',onResponse);page.on('pageerror',onError);page.on('download',onDownload);
 try{
  await page.goto(bases[side]+route,{waitUntil:'load',timeout:25000});await ready(page,route);
  const requested=new URL(route,bases[side]),landed=new URL(page.url());
  if(!initialTargetMatches(requested,landed))throw Error('unexpected initial screen redirect');
  for(const step of [...(op.steps||[]),...(op.postconditions||[])]){
    expectedConfirmation=step.action==='confirmClick';
    try{await performStep(page,step,op,evidence,{attachPeer:peer=>{peer.on('response',onResponse);peer.on('requestfailed',onRequestFailed);return ()=>{peer.off('response',onResponse);peer.off('requestfailed',onRequestFailed);};}});}finally{expectedConfirmation=false;}
  }
  evidence.functionalComplete=Boolean(op.functionalSuiteId&&evidence.functionalObservations.length);
  await page.waitForLoadState('networkidle',{timeout:10000});await ready(page,route);evidence.exercised=true;
  evidence.dom=Buffer.from(await page.content());
  const screenshot=await page.screenshot({fullPage:true,caret:'initial',animations:'allow',timeout:15000});
  evidence.rgba=require('pngjs').PNG.sync.read(screenshot);write(path.join(dir,side+'.png'),screenshot);
  write(path.join(dir,side+'.dom.html'),evidence.dom);
  const errorContent=contentErrors('',evidence.dom.toString());
  if(errorContent.renderError||errorContent.parameterError)evidence.errors.push('rendering or required-parameter error');
  if(op.expectedFinalPath&&new URL(page.url()).pathname!==op.expectedFinalPath)evidence.errors.push('unexpected final screen path');
  if(/ - Login$/.test(await page.title())&&op.expectedFinalPath!=='/Login')evidence.errors.push('unexpected login page');
  evidence.complete=true;
 }catch(e){evidence.errors.push(e.message);
  try{write(path.join(dir,side+'.failure.dom.html'),await page.content());await page.screenshot({path:path.join(dir,side+'.failure.png'),fullPage:true,timeout:5000});}catch(captureError){evidence.errors.push('failure evidence: '+captureError.message);}
 }
 finally{await require('./operation_cleanup.cjs').operationCleanup(page,op.cleanup,evidence,performStep);
 try{await bounded((async()=>{let consumed=0;while(consumed<jobs.length){const batch=jobs.slice(consumed);consumed=jobs.length;await Promise.all(batch);}})(),15000);}catch(e){evidence.errors.push(e.message);
  try{write(path.join(dir,side+'.failure.dom.html'),await page.content());await page.screenshot({path:path.join(dir,side+'.failure.png'),fullPage:true,timeout:5000});}catch(captureError){evidence.errors.push('failure evidence: '+captureError.message);}
 }page.off('request',onRequest);page.off('requestfailed',onRequestFailed);page.off('dialog',onDialog);page.off('response',onResponse);page.off('pageerror',onError);page.off('download',onDownload);}
 finalizeDownloadEvidence(evidence,failedRequests,bodyFailures,op);
 for(const item of evidence.http)if(item.status>=400){
  if(rejectionMatches(item,evidence.securityChecks))item.expectedRejection=true;
  else evidence.errors.push('HTTP '+item.status+' '+item.key);
 }
 evidence.transitionCoverage=transitionCoverage(evidence,op);
 evidence.http.forEach((item,i)=>{if(Buffer.isBuffer(item.requestBody))write(path.join(dir,side+'.http.'+i+'.request.body'),item.requestBody);});
 for(const [kind,items] of [['http',evidence.http],['qvt',evidence.qvt],['downloads',evidence.downloads]])items.forEach((item,i)=>{if(item.body)write(path.join(dir,side+'.'+kind+'.'+i+'.body'),item.body);});
 write(path.join(dir,side+'.metadata.json'),{...evidence,dom:undefined,rgba:undefined,http:evidence.http.map(({body,requestBody,...r})=>r),qvt:evidence.qvt.map(({body,...r})=>r),downloads:evidence.downloads.map(({body,...r})=>r)});
 return evidence;
}
// Phase 3, Change 12: authentication scenarios never reuse the administrator session.
async function casePage(browser,sharedPage,side,op,dir){
 if(!op.session)return {page:sharedPage,close:async()=>{}};
 if(op.session!=='anonymous'&&(typeof op.session!=='object'||!op.session.username||!op.session.password||!op.session.expectedPath))
  throw Error('An isolated login needs credentials and an exact expected path');
 const context=await browser.newContext({viewport:{width:1440,height:900},locale:'en-US',timezoneId:'UTC',deviceScaleFactor:1,acceptDownloads:true});
 const page=await context.newPage();page.setDefaultTimeout(6000);
 try{
  if(op.session!=='anonymous'){
   await page.goto(bases[side]+'/Login');
   await page.locator('#login_form input[name="username"]').fill(op.session.username);
   await page.locator('#login_form input[name="password"]').fill(op.session.password);
   await Promise.all([page.waitForURL(url=>url.pathname===op.session.expectedPath,{timeout:10000}),page.locator('#login_form button[type="submit"]').first().click()]);
   write(path.join(dir,side+'.session-preparation.json'),{username:op.session.username,expectedPath:op.session.expectedPath,actualPath:new URL(page.url()).pathname,isolated:true});
   write(path.join(dir,side+'.session-preparation.html'),await page.content());
  }
  return {page,close:()=>context.close()};
 }catch(error){await context.close();throw error;}
}
async function main(){
 out=process.argv[2];
 const ports=JSON.parse(fs.readFileSync(path.join(out,'ports.json')));for(const side of ['java','rust'])bases[side]='http://127.0.0.1:'+ports[side];
 plan=JSON.parse(fs.readFileSync(path.join(out,'operation-plan.json')));selection=JSON.parse(fs.readFileSync(path.join(out,'selection.json')));
 const rulesFile=path.join(out,'comparison-differences.json');
 const approvalRules=fs.existsSync(rulesFile)?JSON.parse(fs.readFileSync(rulesFile)).ui_presentation||[]:[];
 write(path.join(out,'approved-differences.json'),{ui_presentation:approvalRules});
 const crypto=require('node:crypto');
 write(path.join(out,'functional-provenance.json'),Object.fromEntries(['functional_actions.cjs','approved_presentation.cjs','comparison-differences.json'].map(name=>{const file=name==='comparison-differences.json'?rulesFile:path.join(__dirname,name);return [name,fs.existsSync(file)?crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'):null];})));
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
     const resolved=Object.fromEntries(['java','rust'].map(side=>[side,resolveEngineOperation(route,op,side)]));
     write(path.join(dir,'resolved-engines.json'),resolved);
     const captured={};
     for(const side of ['java','rust']){
      await fixtureHook(op.fixtureControl,'before',side,dir,id);
      const isolated=await casePage(browser,pages[side],side,op,dir);
      try{captured[side]=await capture(isolated.page,side,operationRoute(route,resolved[side].operation),resolved[side].operation,id,dir);}
      finally{try{await fixtureHook(op.fixtureControl,'after',side,dir,id);}finally{await isolated.close();}}
     }
     const {java,rust}=captured;
     const after=snapshot(path.join(dir,'after'));
     result=compareOperation(java,rust,after,{qvtRequired:route.startsWith('/qapps')||op.qvtRequired===true,downloadsRequired:op.downloadsRequired===true||actualSteps(op).some(s=>s.action==='download')});result.beforeDatabase=before;result.approvedDatabase=after.approvedStructured;result.evidence=path.relative(out,dir);
     if(before.complete!==true||before.equal!==true)result.passed=false;
     result.approvedPresentation=approvedPresentation(result,java,rust,{screen:op.selectedScreenKey,mode:op.selectedMode,route:operationRoute(route,op),suiteId:op.functionalSuiteId,beforeRawDatabase:before,
       beforeDatabaseCompatibility:before.approvedStructured,databaseCompatibility:after.approvedStructured,
       rulesSha256:crypto.createHash('sha256').update(fs.readFileSync(rulesFile)).digest('hex')},approvalRules);
     if(op.repeatability===true){
      if(!repeatabilityAllowed(op))
       repeatability.push({kind:'same-engine',id,passed:false,issues:['repeatability requires explicit readOnly and assertion-only steps']});
      else for(const [side,first] of [['java',java],['rust',rust]]){
       const repeatDir=path.join(dir,'repeat-'+side);fs.mkdirSync(repeatDir,{recursive:true});
       const baseline=snapshot(path.join(repeatDir,'before'));
       const second=await capture(pages[side],side,operationRoute(route,resolved[side].operation),resolved[side].operation,id,repeatDir);
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
module.exports={buildCases,operationIssues,operationRoute,perform,performStep,transitionCoverage,finalizeDownloadEvidence,initialTargetMatches,actualSteps,repeatabilityAllowed};
if(require.main===module)main().catch(e=>{if(out){write(path.join(out,'operations-error.txt'),e.stack);const report=operationReport(expected,comparisons,repeatability);report.passed=false;report.error=e.message;write(path.join(out,'operations-result.json'),report);}process.exitCode=1;});
