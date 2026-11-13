// Phase 3, Change 11: map explicit engine routes without changing retained raw evidence.
const assert=require('node:assert/strict');
function localRoute(value) {
 const url=new URL(value,'http://operation.invalid');
 if(url.origin!=='http://operation.invalid'||!value.startsWith('/')||value.startsWith('//')||url.hash)
  throw Error('Mapped routes must be local paths without fragments');
 return url;
}
function resolveEngineOperation(route,op,side) {
 // Phase 3, Change 24: execute explicit per-engine controls without equating their observations.
 assert.ok(['java','rust'].includes(side),'Unknown engine');
 let selectedSteps=op.steps||[];
 if(op.engineSteps!==undefined) {
  assert.equal(typeof op.engineStepContract,'string','Per-engine steps require a named contract');
  assert.ok(op.engineStepContract.trim(),'Per-engine steps require a nonempty contract');
  assert.deepEqual(Object.keys(op.engineSteps).sort(),['java','rust'],'Both engine step lists are required');
  for(const steps of Object.values(op.engineSteps))
   assert.ok(Array.isArray(steps)&&steps.length>0&&steps.every(s=>s&&typeof s==='object'&&typeof s.action==='string'),'Invalid engine step list');
  selectedSteps=op.engineSteps[side];
 }
 const mode=route.startsWith('/qapps/')?'qapps':'html';
 const destination=op.engineRoutes?.[side]?.[mode];
 const original=localRoute(route),mapped=localRoute(destination||route);
 if((mapped.pathname.startsWith('/qapps/'))!==(mode==='qapps'))throw Error('Mapped route changes render mode');
 // Phase 3, Change 28: qapps controls submit through the explicitly mapped HTML screen.
 const htmlOriginal=mode==='qapps'?original.pathname.replace(/^\/qapps\//,'/apps/'):null;
 const htmlDestination=mode==='qapps'&&op.engineRoutes?.[side]?.html?localRoute(op.engineRoutes[side].html):null;
 if(htmlDestination&&!htmlDestination.pathname.startsWith('/apps/'))throw Error('HTML action mapping changes render mode');
 const remap=value=>{
  if(typeof value!=='string'||!value.startsWith('/'))return value;
  const url=localRoute(value);
  if(url.pathname===original.pathname||url.pathname.startsWith(original.pathname+'/')) {
   url.pathname=mapped.pathname+url.pathname.slice(original.pathname.length);
   for(const [name,value] of mapped.searchParams)if(!url.searchParams.has(name))url.searchParams.set(name,value);
  }
  else if(htmlDestination&&(url.pathname===htmlOriginal||url.pathname.startsWith(htmlOriginal+'/'))) {
   url.pathname=htmlDestination.pathname+url.pathname.slice(htmlOriginal.length);
   for(const [name,value] of htmlDestination.searchParams)if(!url.searchParams.has(name))url.searchParams.set(name,value);
  }
  return url.pathname+url.search;
 };
 const selectors=op.engineSelectors?.[side]||{};
 const step=value=>{
  const result={...value,id:value.id||value.selector||value.route};
  for(const field of ['selector','control','fieldSelector','submitSelector','tokenSelector','confirmationSelector','messageSelector','acceptSelector','cancelSelector'])
   if(result[field]&&Object.hasOwn(selectors,result[field]))result[field]=selectors[result[field]];
  if(result.route)result.route=remap(result.route);
  if(result.path){const target=localRoute(remap(result.path));result.path=target.pathname+(result.action==='submitValues'?target.search:'');}
  if(result.response)result.response={...result.response,path:remap(result.response.path)};
  return result;
 };
 const coveredTransitions=(op.coveredTransitions||[]).map(spec=>typeof spec==='object'?{...spec,path:remap(spec.path)}:spec);
 const resolved={...op,coveredTransitions,route:remap(op.route||route),steps:selectedSteps.map(step),postconditions:(op.postconditions||[]).map(step)};
 // Phase 3, Change 27: preserve explicit ownership guards for per-engine cleanup.
 const cleanup=op.engineCleanup?.[side];
 if(cleanup)resolved.cleanup={...cleanup,guard:{...cleanup.guard,submission:{...cleanup.guard.submission,path:remap(cleanup.guard.submission.path)}},steps:cleanup.steps.map(step)};
 // Mapping affects where to exercise the contract, never its expected text or submitted values.
 assert.deepEqual(resolved.steps.map(s=>s.value), selectedSteps.map(s=>s.value));
 return {route:resolved.route,operation:resolved,mapping:destination?{side,from:route,to:resolved.route}:null};
}
module.exports={localRoute,resolveEngineOperation};
