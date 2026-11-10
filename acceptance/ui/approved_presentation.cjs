// Change 7: presentation approval is scoped and cannot turn absent functional evidence into a pass.
const {isDeepStrictEqual}=require('node:util');
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
  Array.isArray(observations)&&observations.length>0&&isDeepStrictEqual(observations,rust.functionalObservations);
 // Only markup bodies may differ. Request targets, order, methods, status and non-markup bytes stay strict.
 const http=java.http.length===rust.http.length&&java.http.every((a,i)=>{
  const b=rust.http[i];
  const markup=/^(text\/html|application\/x-qvt)(?:;|$)/i;
  return a.key===b.key&&a.method===b.method&&a.status===b.status&&
   (a.body.equals(b.body)||(rule.channels.includes('htmlMarkup')&&markup.test(a.contentType||'')&&markup.test(b.contentType||'')));
 });
 const qvt=java.qvt.length===rust.qvt.length&&java.qvt.every((a,i)=>{
  const b=rust.qvt[i];return a.key===b.key&&(a.body.equals(b.body)||rule.channels.includes('htmlMarkup'));
 });
 const presentationPassed=functionalPassed&&http&&qvt&&raw.downloads.equal&&
  (raw.dom.equal||rule.channels.includes('domMarkup'))&&(raw.rgba.equal||rule.channels.includes('rgba'));
 return {applicable:true,ruleId:rule.id,functionalPassed,presentationPassed,
  passed:presentationPassed&&raw.database.passed,rawPassed:raw.passed,
  contract:'Reviewed markup/pixels only; exact content-text assertions, semantic control labels, submitted values, request targets, downloads and database verdict remain required. Raw label whitespace is retained separately.'};
}
module.exports={approvedPresentation};
