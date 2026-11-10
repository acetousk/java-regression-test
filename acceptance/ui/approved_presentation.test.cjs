const {test}=require('node:test'),assert=require('node:assert/strict');
const {approvedPresentation}=require('./approved_presentation.cjs');
const context={screen:'screen',mode:'html',route:'/apps/screen',suiteId:'functional'};
const rules=[{id:'reviewed',screen:'screen',mode:'html',path:'/apps/screen',functionalSuiteId:'functional',channels:['htmlMarkup','domMarkup','rgba']}];
function args(){return [{issues:[],downloads:{equal:true},dom:{equal:false},rgba:{equal:false},database:{passed:true},passed:false},
 {functionalComplete:true,functionalObservations:[{text:'Save'}],http:[{key:'/save',method:'POST',status:200,contentType:'text/html',body:Buffer.from('java')}],qvt:[]},
 {functionalComplete:true,functionalObservations:[{text:'Save'}],http:[{key:'/save',method:'POST',status:200,contentType:'text/html',body:Buffer.from('rust')}],qvt:[]},context,rules];}
test('separate presentation result retains raw failure',()=>{const r=approvedPresentation(...args());assert.equal(r.passed,true);assert.equal(r.rawPassed,false);});
test('scope, observations, requests, errors, downloads and database fail closed',()=>{
 for(const change of [a=>a[3]={...context,mode:'qapps'},a=>a[2].functionalComplete=false,a=>a[1].functionalObservations=[],a=>a[2].functionalObservations=[{text:'Delete'}],a=>a[2].http[0].key='/delete',a=>a[2].http[0].status=201,a=>a[2].http[0].contentType='application/json',a=>a[0].issues=['error'],a=>a[0].downloads.equal=false,a=>a[0].database.passed=false]){const a=args();change(a);assert.equal(approvedPresentation(...a).passed,false);}
});
