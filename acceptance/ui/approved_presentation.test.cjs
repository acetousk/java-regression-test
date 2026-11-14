const {test}=require('node:test'),assert=require('node:assert/strict');
const {approvedPresentation}=require('./approved_presentation.cjs');
const context={screen:'screen',mode:'html',route:'/apps/screen',suiteId:'functional'};
const rules=[{id:'reviewed',screen:'screen',mode:'html',path:'/apps/screen',functionalSuiteId:'functional',channels:['htmlMarkup','domMarkup','rgba']}];
function args(){return [{issues:[],downloads:{equal:true},dom:{equal:false},rgba:{equal:false},database:{passed:true},passed:false},
 {functionalComplete:true,functionalObservations:[{text:'Save'}],http:[{key:'/save',method:'POST',status:200,requestBodyComplete:true,requestBodyPresent:true,requestBody:Buffer.from('value=one'),contentType:'text/html',body:Buffer.from('java')}],qvt:[]},
 {functionalComplete:true,functionalObservations:[{text:'Save'}],http:[{key:'/save',method:'POST',status:200,requestBodyComplete:true,requestBodyPresent:true,requestBody:Buffer.from('value=one'),contentType:'text/html',body:Buffer.from('rust')}],qvt:[]},context,rules];}
test('separate presentation result retains raw failure',()=>{const r=approvedPresentation(...args());assert.equal(r.passed,true);assert.equal(r.rawPassed,false);});
test('scope, observations, requests, errors, downloads and database fail closed',()=>{
 for(const change of [a=>a[3]={...context,mode:'qapps'},a=>a[2].functionalComplete=false,a=>a[1].functionalObservations=[],a=>a[2].functionalObservations=[{text:'Delete'}],a=>a[2].http[0].key='/delete',a=>a[2].http[0].status=201,a=>a[2].http[0].contentType='application/json',a=>a[0].issues=['error'],a=>a[0].downloads.equal=false,a=>a[0].database.passed=false]){const a=args();change(a);assert.equal(approvedPresentation(...a).passed,false);}
});
test('structured approval requires explicit scope, complete before/after and exact rules identity',()=>{
 const make=()=>{const a=args();a[0].database.passed=false;a[4]=[{...rules[0],database:'reviewedStructured'}];
  const db={status:'compared',complete:true,passed:true,rulesSha256:'a'.repeat(64)};
  a[3]={...context,rulesSha256:'a'.repeat(64),databaseCompatibility:{...db},beforeDatabaseCompatibility:{...db}};return a;};
 const result=approvedPresentation(...make());assert.equal(result.passed,true);assert.equal(result.databaseMode,'reviewedStructured');assert.equal(result.rawPassed,false);
 for(const change of [a=>a[4]=rules,a=>delete a[3].beforeDatabaseCompatibility,a=>a[3].databaseCompatibility.complete=false,
  a=>a[3].databaseCompatibility.passed=false,a=>a[3].beforeDatabaseCompatibility.rulesSha256='b'.repeat(64)]){
  const a=make();change(a);assert.equal(approvedPresentation(...a).passed,false);
 }
});
test('exact reviewed route pairs preserve query bytes, methods, observations and raw evidence',()=>{
 const make=()=>{const a=args();a[1].http[0].key='/old/save?id=1';a[2].http[0].key='/new/save?id=1';
  a[1].functionalObservations=[{id:'save',action:'click',targetPath:'/old/save?id=1',value:true}];
  a[2].functionalObservations=[{id:'save',action:'click',targetPath:'/new/save?id=1',value:true}];
  a[4]=[{...rules[0],requestTargets:[{java:'/old/save?id=1',rust:'/new/save?id=1'}]}];return a;};
 const a=make(),before=JSON.stringify(a);assert.equal(approvedPresentation(...a).passed,true);assert.equal(JSON.stringify(a),before);
 for(const change of [a=>a[2].http[0].key='/new/save?id=2',a=>a[2].http[0].method='GET',
  a=>a[2].functionalObservations[0].value=false,a=>a[4][0].requestTargets.push({java:'/old/save?id=1',rust:'/other'}),
  a=>a[4][0].requestTargets=[],a=>a[2].functionalObservations[0].id='different']){
  const a=make();change(a);assert.equal(approvedPresentation(...a).passed,false);
 }
});
test('route pairs reject external, fragment, prefix, and ambiguous correspondence',()=>{
 const {pairedTarget}=require('./approved_presentation.cjs');
 for(const [java,rust,pairs] of [
  ['//host/a','/b',[{java:'//host/a',rust:'/b'}]],
  ['/a#x','/b',[{java:'/a#x',rust:'/b'}]],
  ['/a/child','/b/child',[{java:'/a',rust:'/b'}]],
  ['/a','/b',[{java:'/a',rust:'/b'},{java:'/c',rust:'/b'}]],
 ])assert.equal(pairedTarget(java,rust,pairs),false);
});
