// Strict operation evidence: no normalization, exemptions, masks or tolerances.
const {bytes,pixels,contentErrors}=require('./compare.cjs');
const {compareRequestBodies}=require('./request_bodies.cjs');
const {rejectionMatches}=require('./csrf_probe.cjs');
const nonempty=x=>typeof x==='string'&&x.length>0;
const list=x=>Array.isArray(x);
function validImage(x) {
 return x&&Number.isSafeInteger(x.width)&&x.width>0&&Number.isSafeInteger(x.height)&&x.height>0&&
  Buffer.isBuffer(x.data)&&x.data.length===x.width*x.height*4;
}
function captureIssues(c,label,requirements) {
 const issues=[];
 if(!c||typeof c!=='object') return [`${label}: missing capture`];
 if(!nonempty(c.id)||!['java','rust'].includes(c.engine)) issues.push(`${label}: missing identity`);
 if(c.exercised!==true||c.complete!==true) issues.push(`${label}: unexercised or incomplete`);
 if(!list(c.errors)||c.errors.length) issues.push(`${label}: capture errors or missing error status`);
 if(['error','readinessError','unexpectedRedirect','parameterError','renderError','errorPage'].some(key=>c[key])||
  ['pageErrors','httpErrors'].some(key=>c[key]&&(!list(c[key])||c[key].length)))
  issues.push(`${label}: operation or page failure`);
 if(!Buffer.isBuffer(c.dom)) issues.push(`${label}: missing DOM bytes`);
 if(!validImage(c.rgba)) issues.push(`${label}: missing or malformed RGBA`);
 for(const channel of ['http','qvt','downloads']) {
  const entries=c[channel];
  if(!list(entries)) {issues.push(`${label}: missing ${channel} evidence`);continue;}
  if((channel==='http'||requirements[`${channel}Required`]===true)&&!entries.length)
   issues.push(`${label}: unexercised ${channel}`);
  for(const entry of entries) {
   if(!entry||!nonempty(entry.key)||!Buffer.isBuffer(entry.body))
    issues.push(`${label}: malformed ${channel} entry`);
   if(channel==='http'&&(!entry||!nonempty(entry.method)||!Number.isInteger(entry.status)||entry.status<200||(entry.status>=400&&!rejectionMatches(entry,c.securityChecks))))
    issues.push(`${label}: failed or malformed HTTP response`);
   if(channel==='downloads'&&(!entry||!nonempty(entry.filename))) issues.push(`${label}: missing download filename`);
  }
 }
 if(Buffer.isBuffer(c.dom)) {
  const bodies=[...(list(c.http)?c.http:[]),...(list(c.qvt)?c.qvt:[])];
  if(bodies.some(e=>Buffer.isBuffer(e?.body)&&Object.values(contentErrors(e.body,c.dom.toString('utf8'))).some(Boolean)))
   issues.push(`${label}: rendered error or missing parameter`);
 }
 return issues;
}
function stream(left,right,channel) {
 if(!list(left)||!list(right)) return {equal:false,missing:true};
 const entries=[];
 for(let i=0;i<Math.max(left.length,right.length);i++) {
  const a=left[i],b=right[i];
  const matched=!!a&&!!b&&a.key===b.key&&nonempty(a.key);
  const metadata=matched&&(channel!=='http'||(a.method===b.method&&a.status===b.status))&&
   (channel!=='downloads'||a.filename===b.filename);
  const body=Buffer.isBuffer(a?.body)&&Buffer.isBuffer(b?.body)?bytes(a.body,b.body):{equal:false,missing:true};
  // Keep identity and offsets/hashes, never response content, tokens, or downloaded bytes.
  entries.push({index:i,matched,metadataEqual:metadata,body,equal:metadata&&body.equal});
 }
 return {equal:left.length===right.length&&entries.every(e=>e.equal),leftCount:left.length,rightCount:right.length,entries};
}
function databaseResult(db) {
 const passed=!!db&&db.status==='compared'&&db.complete===true&&db.equal===true&&
  list(db.exclusions)&&db.exclusions.length===0&&nonempty(db.evidencePath)&&!db.error&&
  (db.errors===undefined||(list(db.errors)&&db.errors.length===0));
 return {passed,status:db?.status??'missing',complete:db?.complete===true,equal:db?.equal===true,
  exclusionCount:list(db?.exclusions)?db.exclusions.length:null,evidencePath:db?.evidencePath??null};
}
function compare(left,right,db,requirements,kind) {
 const issues=[...captureIssues(left,'left',requirements),...captureIssues(right,'right',requirements)];
 if(!nonempty(left?.id)||left?.id!==right?.id) issues.push('unmatched operation identity');
 if(kind==='cross-engine'?(left?.engine!=='java'||right?.engine!=='rust'):
  (!['java','rust'].includes(left?.engine)||left?.engine!==right?.engine)) issues.push('wrong engine pairing');
 const http=stream(left?.http,right?.http,'http'),qvt=stream(left?.qvt,right?.qvt,'qvt');
 const downloads=stream(left?.downloads,right?.downloads,'downloads');
 const dom=Buffer.isBuffer(left?.dom)&&Buffer.isBuffer(right?.dom)?bytes(left.dom,right.dom):{equal:false,missing:true};
 const rgba=validImage(left?.rgba)&&validImage(right?.rgba)?pixels(left.rgba,right.rgba):{equal:false,missing:true};
 const database=databaseResult(db),requestBodies=compareRequestBodies(left?.http,right?.http);
 return {kind,id:nonempty(left?.id)?left.id:null,engines:[left?.engine??null,right?.engine??null],issues,
  http,dom,rgba,qvt,downloads,database,requestBodies,
  passed:requestBodies.equal&&issues.length===0&&[http,dom,rgba,qvt,downloads].every(c=>c.equal)&&database.passed};
}
// Requirements optionally demand a nonempty QVT/download stream, e.g. {qvtRequired:true}.
// HTTP arrays are ordered decoded response bodies, not wire frames or a claim of header equality.
function compareOperation(java,rust,database,requirements={}) {return compare(java,rust,database,requirements,'cross-engine');}
function compareRepeatability(first,second,database,requirements={}) {return compare(first,second,database,requirements,'same-engine');}
function operationReport(expectedIds,comparisons,repeatability=[]) {
 const expected=list(expectedIds)?expectedIds:[],actual=list(comparisons)?comparisons:[];
 const validExpected=expected.length>0&&expected.every(nonempty)&&new Set(expected).size===expected.length;
 const missing=expected.filter(id=>!actual.some(c=>c?.kind==='cross-engine'&&c.id===id));
 const unmatched=actual.filter(c=>!c||c.kind!=='cross-engine'||!expected.includes(c.id)).map(c=>c?.id??null);
 const duplicate=actual.filter((c,i)=>actual.findIndex(x=>x?.id===c?.id)!==i).map(c=>c?.id??null);
 const passed=validExpected&&list(comparisons)&&actual.length===expected.length&&!missing.length&&!unmatched.length&&
  !duplicate.length&&actual.every(c=>c.passed===true);
 return {kind:'operation-parity',passed,expectedCount:expected.length,comparedCount:actual.length,missing,unmatched,duplicate,
  operations:actual,repeatability:{kind:'same-engine-diagnostics',results:list(repeatability)?repeatability:[],
   complete:list(repeatability)&&repeatability.length>0&&repeatability.every(c=>c?.kind==='same-engine'),
   passed:list(repeatability)&&repeatability.length>0&&repeatability.every(c=>c?.kind==='same-engine'&&c.passed===true)}};
}
module.exports={compareOperation,compareRepeatability,operationReport};
