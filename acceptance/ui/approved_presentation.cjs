// Change 7: presentation approval is scoped and cannot turn absent functional evidence into a pass.
const {isDeepStrictEqual}=require('node:util');
const {compareRequestBodies}=require('./request_bodies.cjs');
// Phase 3, Change 16: exact reviewed route pairs preserve raw targets and every query byte.
function pairedTarget(java,rust,pairs=[]) {
 if(java===rust)return true;
 const local=value=>typeof value==='string'&&value.startsWith('/')&&!value.startsWith('//')&&!value.includes('#');
 if(!local(java)||!local(rust)||!Array.isArray(pairs))return false;
 const matches=pairs.filter(p=>p&&p.java===java&&p.rust===rust&&local(p.java)&&local(p.rust));
 if(matches.length!==1)return false;
 return pairs.filter(p=>p?.java===java).length===1&&pairs.filter(p=>p?.rust===rust).length===1;
}
function pairedObservations(java,rust,pairs) {
 if(!Array.isArray(java)||!Array.isArray(rust)||java.length!==rust.length)return false;
 return java.every((a,i)=>{
  const b=rust[i];
  if(isDeepStrictEqual(a,b))return true;
  if(!a||!b||!Object.hasOwn(a,'targetPath')||!Object.hasOwn(b,'targetPath'))return false;
  const {targetPath:ja,...otherJava}=a,{targetPath:ru,...otherRust}=b;
  return isDeepStrictEqual(otherJava,otherRust)&&pairedTarget(ja,ru,pairs);
 });
}
function approvedPresentation(raw,java,rust,context,rules=[]) {
 const {screen,mode,route,suiteId}=context;
 const pathname=new URL(route,'http://local.invalid').pathname;
 const rule=rules.find(r=>r.screen===screen&&r.mode===mode&&r.path===pathname&&r.functionalSuiteId===suiteId);
 if(!rule)return {applicable:false,passed:false,reason:'No matching reviewed presentation scope'};
 if(raw.issues.length||![java,rust].every(c=>Array.isArray(c.http)&&Array.isArray(c.qvt)&&
   [...c.http,...c.qvt].every(e=>Buffer.isBuffer(e.body))))
  return {applicable:true,ruleId:rule.id,functionalPassed:false,presentationPassed:false,passed:false,reason:'Incomplete capture'};
 const observations=java.functionalObservations;
 const functionalPassed=raw.issues.length===0&&java.functionalComplete===true&&rust.functionalComplete===true&&
  Array.isArray(observations)&&observations.length>0&&pairedObservations(observations,rust.functionalObservations,rule.requestTargets);
 // Only markup bodies may differ. Request targets, order, methods, status and non-markup bytes stay strict.
 const http=java.http.length===rust.http.length&&java.http.every((a,i)=>{
  const b=rust.http[i];
  const markup=/^(text\/html|application\/x-qvt)(?:;|$)/i;
  return pairedTarget(a.key,b.key,rule.requestTargets)&&a.method===b.method&&a.status===b.status&&
   (a.body.equals(b.body)||(rule.channels.includes('htmlMarkup')&&markup.test(a.contentType||'')&&markup.test(b.contentType||'')));
 });
 const qvt=java.qvt.length===rust.qvt.length&&java.qvt.every((a,i)=>{
  const b=rust.qvt[i];return pairedTarget(a.key,b.key,rule.requestTargets)&&(a.body.equals(b.body)||rule.channels.includes('htmlMarkup'));
 });
 const requestBodies=compareRequestBodies(java.http,rust.http,(a,b)=>pairedTarget(a,b,rule.requestTargets));
 const presentationPassed=functionalPassed&&http&&qvt&&requestBodies.equal&&raw.downloads.equal&&
  (raw.dom.equal||rule.channels.includes('domMarkup'))&&(raw.rgba.equal||rule.channels.includes('rgba'));
 // Phase 3, Change 13: reviewed database rules have a separate, explicit verdict.
 const databaseMode=rule.database==='reviewedStructured'?'reviewedStructured':'raw';
 const structuredValid=value=>value?.status==='compared'&&value.complete===true&&value.passed===true&&
  typeof context.rulesSha256==='string'&&context.rulesSha256.length===64&&value.rulesSha256===context.rulesSha256;
 const databasePassed=databaseMode==='reviewedStructured'?
  structuredValid(context.beforeDatabaseCompatibility)&&structuredValid(context.databaseCompatibility):
  raw.database.passed&&(!context.beforeRawDatabase||(context.beforeRawDatabase.complete===true&&context.beforeRawDatabase.equal===true));
 return {applicable:true,ruleId:rule.id,functionalPassed,presentationPassed,databaseMode,databasePassed,requestBodies,
  passed:presentationPassed&&databasePassed,rawPassed:raw.passed,
  comparisonKind:'exception-adjusted',reviewedRequestTargets:rule.requestTargets||[],
  contract:'Reviewed markup/pixels only; exact content-text assertions, semantic control labels, submitted values, request targets, downloads and database verdict remain required. Raw label whitespace is retained separately.'};
}
module.exports={approvedPresentation,pairedTarget,pairedObservations};
