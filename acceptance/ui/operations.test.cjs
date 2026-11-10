const {test}=require('node:test'),assert=require('node:assert/strict');
const {buildCases,operationIssues,operationRoute,perform}=require('./operations.cjs');
test('coverage is frozen for later screens and missing mode inventories before execution',()=>{
 const cases=buildCases({selected:[{key:'one',routes:['/a','/qapps/a']},{key:'two',routes:['/b']}]},
  {screens:[{key:'one',operations:[{id:'save',modes:['html'],steps:[]}]}]});
 assert.equal(cases.length,3);assert.equal(cases[0].id,'one:html:save');
 assert.match(cases[1].op.unverifiedReason,/selected mode/);assert.match(cases[2].op.unverifiedReason,/inventory/);
});
test('fixture prerequisites require positive proof on both engines and mutations need a trailing postcondition',()=>{
 const op={steps:[{action:'click',selector:'button'}],fixturePrerequisites:['record']};
 const metadata={sides:{java:{fixtures:[{name:'record',status:'verified'}]},rust:{fixtures:[]}}};
 assert.equal(operationIssues(op,metadata).length,2);
 op.steps.push({action:'value',selector:'input',value:'saved'});
 assert.equal(operationIssues(op,metadata).length,1);
 metadata.sides.rust.fixtures=[{name:'record',status:'verified'}];assert.deepEqual(operationIssues(op,metadata),[]);
 op.steps.unshift({action:'visible',selector:'body'});op.steps.pop();assert.match(operationIssues(op,metadata)[0],/postcondition/);
});
test('route parameters preserve mode and reject external navigation',()=>{
 assert.equal(operationRoute('/qapps/a?old=x',{routeParameters:{id:'a b'}}),'/qapps/a?old=x&id=a+b');
 assert.throws(()=>operationRoute('/qapps/a',{route:'/vapps/a'}),/mode/);
 assert.throws(()=>operationRoute('/a',{route:'https://external.invalid/a'}),/local/);
});
test('response waiter is registered before click and completion awaited before network idle',async()=>{
 const events=[];let finish;
 const response={url:()=> 'http://local/action',request:()=>({method:()=> 'POST'}),status:()=>200,
  finished:async()=>{events.push('finished');return null;}};
 const page={waitForResponse:predicate=>{events.push('wait');assert.equal(predicate(response),true);return new Promise(resolve=>finish=()=>resolve(response));},
  locator:()=>({click:async()=>{events.push('click');finish();}}),waitForLoadState:async()=>events.push('idle')};
 await perform(page,{action:'click',selector:'button',response:{path:'/action',method:'POST',status:200}});
 assert.deepEqual(events,['wait','click','finished','idle']);
 response.status=()=>500;await assert.rejects(()=>perform(page,{action:'click',selector:'button',response:{path:'/action',method:'POST',status:200}}),/status/);
});
test('input value postcondition compares exact value',async()=>{
 const page={locator:()=>({inputValue:async()=> 'saved '})};
 await assert.rejects(()=>perform(page,{action:'value',selector:'input',value:'saved'}),/mismatch/);
 await perform(page,{action:'value',selector:'input',value:'saved '});
});

test('download navigation abort needs positive matching file evidence; other failures remain failures',()=>{
 const {finalizeDownloadEvidence}=require('./operations.cjs');
 const item={key:'/download',body:null};
 const evidence={errors:[],downloads:[{key:'/download',body:Buffer.from([0,255,10])}]};
 finalizeDownloadEvidence(evidence,[{key:'/download',error:'net::ERR_ABORTED'}],[{item,error:'unavailable'}],{});
 assert.deepEqual(evidence.errors,[]);assert.deepEqual(item.body,Buffer.from([0,255,10]));
 finalizeDownloadEvidence(evidence,[{key:'/different',error:'net::ERR_ABORTED'},{key:'/download',error:'net::ERR_CONNECTION_RESET'}],[],{});
 assert.equal(evidence.errors.length,2);
});
test('download fixture assertion rejects wrong bytes even if paired engines agree',()=>{
 const {finalizeDownloadEvidence}=require('./operations.cjs');
 const evidence={errors:[],downloads:[{key:'/download',body:Buffer.from('wrong')}]};
 finalizeDownloadEvidence(evidence,[],[],{expectedDownloadUtf8:'expected'});
 assert.equal(evidence.errors.length,1);
});
test('a successful wrong screen or changed record cannot pass initial-target validation',()=>{
 const {initialTargetMatches}=require('./operations.cjs');
 const requested=new URL('http://localhost:38080/apps/detail?id=fixture');
 assert.equal(initialTargetMatches(requested,new URL('http://localhost:38080/apps/detail?id=fixture&extra=1')),true);
 for(const url of ['http://localhost:38080/apps/other?id=fixture','http://localhost:38080/apps/detail?id=wrong','http://localhost:38080/apps/detail','http://localhost:38081/apps/detail?id=fixture'])
  assert.equal(initialTargetMatches(requested,new URL(url)),false);
});
test('generic page visibility cannot certify an interactive operation succeeded',()=>{
 const {operationIssues}=require('./operations.cjs');
 assert.ok(operationIssues({steps:[{action:'click',selector:'#save'},{action:'visible',selector:'body'}]},{}).includes('interactive operation has no success postcondition'));
 assert.deepEqual(operationIssues({steps:[{action:'visible',selector:'body'}]},{}),[]);
});
