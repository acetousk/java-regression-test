// Phase 3, Change 27: assert exact output and counts in captured responses; never execute code.
const assert=require('node:assert/strict'),crypto=require('node:crypto'),{isDeepStrictEqual}=require('node:util');
const bindings=new Map(),cursors=new WeakMap();
function field(object,path){
 assert.ok(Array.isArray(path)&&path.length&&path.every(k=>(typeof k==='string'||Number.isSafeInteger(k))&&!['__proto__','prototype','constructor'].includes(k)),'Invalid JSON field path');
 let value=object;for(const key of path){if(value===null||typeof value!=='object'||((typeof key==='number'||key==='length')&&!Array.isArray(value))||!Object.hasOwn(value,key))return undefined;value=value[key];}return value;
}
function targets(step,engine){
 assert.match(step.path,/^\/(?!\/)/);const url=new URL(step.path,'http://capture.invalid');assert.ok(url.origin==='http://capture.invalid'&&!url.search&&!url.hash,'Exact local pathname required');
 const alternatives=step.queries||[[]];assert.ok(Array.isArray(alternatives)&&alternatives.length>0&&alternatives.length<=4);
 return alternatives.map(entries=>{
  assert.ok(Array.isArray(entries));const names=new Set(),query=new URLSearchParams();
  for(const pair of entries){assert.ok(Array.isArray(pair)&&pair.length===2);const [name,spec]=pair;assert.equal(typeof name,'string');assert.ok(!names.has(name),'Duplicate query name');names.add(name);
   let value=spec;if(spec&&typeof spec==='object'){assert.deepEqual(Object.keys(spec),['binding']);value=bindings.get(engine+':'+spec.binding);assert.equal(typeof value,'string','Missing captured response binding');}
   assert.equal(typeof value,'string','Exact query value required');query.append(name,value);
  }
  return url.pathname+(query.size?'?'+query.toString():'');
 });
}
function ready(body,conditions){
 assert.ok(Array.isArray(conditions));return conditions.every(check=>{
  const actual=field(body,check.path);
  if(check.op==='equal')return isDeepStrictEqual(actual,check.value);
  if(check.op==='atLeast'){assert.ok(typeof check.value==='number'&&Number.isFinite(check.value));return typeof actual==='number'&&Number.isFinite(actual)&&actual>=check.value;}
  if(check.op==='nonemptyString')return typeof actual==='string'&&actual.length>0;
  throw Error('Unsupported JSON readiness operation');
 });
}
async function capturedJson(page,step,evidence,timing={}){
 assert.ok(['java','rust'].includes(evidence.engine));assert.ok(['GET','POST'].includes(step.method));assert.equal(step.status,200,'Explicit successful response status required');
 assert.ok(typeof step.contract==='string'&&step.contract.trim(),'Named JSON contract required');assert.ok(Array.isArray(step.checks)&&(step.checks.length>0||Array.isArray(step.exactKeys)),'Exact JSON checks required');
 const accepted=targets(step,evidence.engine),now=timing.now||(()=>performance.now()),wait=timing.wait||(ms=>new Promise(resolve=>setTimeout(resolve,ms))),deadline=now()+30000;
 const first=Math.max(cursors.get(evidence)??-1,evidence.jsonResponseFloor??-1)+1;
 while(now()<deadline){
  for(let index=first;index<evidence.http.length;index++){
   const response=evidence.http[index];if(response.method!==step.method||!accepted.includes(response.key)||!Buffer.isBuffer(response.body))continue;
   if(evidence.jsonRequestFloor!==undefined&&(!Number.isSafeInteger(response.requestSequence)||response.requestSequence<=evidence.jsonRequestFloor))continue;
   assert.equal(response.status,step.status,'Captured JSON status');assert.match(response.contentType||'',/^application\/json(?:;|$)/i,'Captured JSON content type');
   const body=JSON.parse(response.body.toString('utf8'));if(!ready(body,step.readyWhen||[]))continue;
   if(step.exactKeys!==undefined){assert.ok(body&&typeof body==='object'&&!Array.isArray(body));assert.deepEqual(Object.keys(body).sort(),[...step.exactKeys].sort(),'Captured JSON exact object keys');}
   const observed=step.checks.map(check=>{const actual=field(body,check.path);assert.deepEqual(actual,check.value,'Captured JSON field '+check.path.join('.'));return {path:check.path,value:actual};});
   const stored={};for(const binding of step.bind||[]){assert.ok(typeof binding.name==='string'&&binding.name.trim());const value=field(body,binding.path);assert.ok(typeof value==='string'&&value.length>0&&value.length<=256,'Captured binding must be a bounded nonempty string');const key=evidence.engine+':'+binding.name;if(bindings.has(key))assert.equal(bindings.get(key),value,'Captured binding cannot change');bindings.set(key,value);stored[binding.name]=value;}
   assert.ok(now()<deadline,'Captured JSON exceeded total deadline');cursors.set(evidence,index);
   const observation={id:step.id||step.contract,action:'capturedJson',contract:step.contract,targetPath:response.key,method:response.method,status:response.status,responseIndex:index,bodySha256:crypto.createHash('sha256').update(response.body).digest('hex'),checks:observed,bindings:stored};
   evidence.functionalObservations.push(observation);evidence.functionalRawObservations.push(observation);return;
  }
  const delay=Math.min(100,deadline-now());if(delay>0)await wait(delay);
 }
 throw Error('No captured response satisfied JSON readiness within 30 seconds');
}
module.exports={capturedJson,field,targets};
