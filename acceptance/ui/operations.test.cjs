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
test('claimed transition coverage requires actual complete successful responses',()=>{
 const {transitionCoverage}=require('./operations.cjs');
 const evidence={errors:[],http:[{key:'/screen/save?id=one',method:'POST',status:200,body:Buffer.from('done')}]};
 assert.equal(transitionCoverage(evidence,{coveredTransitions:[{name:'save',path:'/screen/save?id=one',method:'POST'}]})[0].observed,true);
 for(const entry of [{key:'/screen/not-save',method:'POST',status:200,body:Buffer.from('done')},
  {key:'/screen/save',method:'GET',status:200,body:Buffer.from('done')},
  {key:'/screen/save',method:'POST',status:500,body:Buffer.from('error')},
  {key:'/screen/save',method:'POST',status:200,body:null}]){
  const failed={errors:[],http:[entry]};assert.equal(transitionCoverage(failed,{coveredTransitions:[{name:'save',path:'/screen/save?id=one',method:'POST'}]})[0].observed,false);
  assert.equal(failed.errors.length,1);
 }
});
test('transition proof rejects unrelated targets, methods, query differences and redirects without completion',()=>{
 const {transitionCoverage}=require('./operations.cjs');
 const spec={name:'delete',path:'/apps/intended/delete?id=one',method:'POST'};
 for(const http of [
  [{key:'/apps/unrelated/delete?id=one',method:'POST',status:200,body:Buffer.from('ok')}],
  [{key:spec.path,method:'GET',status:200,body:Buffer.from('ok')}],
  [{key:'/apps/intended/delete?id=two',method:'POST',status:200,body:Buffer.from('ok')}],
  [{key:spec.path,method:'POST',status:302,body:Buffer.alloc(0)}],
  [{key:spec.path,method:'POST',status:302,body:Buffer.alloc(0)},{key:'/apps/intended',method:'GET',status:200,body:Buffer.from('ok')}],
 ]){const evidence={errors:[],http};assert.equal(transitionCoverage(evidence,{coveredTransitions:[spec]})[0].observed,false);}
 const http=[{key:spec.path,method:'POST',status:303,body:Buffer.alloc(0)},
  {key:'/apps/intended',method:'GET',status:200,body:Buffer.from('ok'),redirectChain:[{key:spec.path,method:'POST',sameOrigin:true}]}];
 assert.equal(transitionCoverage({errors:[],http},{coveredTransitions:[spec]})[0].observed,true);
 assert.equal(transitionCoverage({errors:[],http},{coveredTransitions:['delete']})[0].observed,false);
});
test('explicit negative control assertions work without a presentation approval suite',async()=>{
 const {performStep}=require('./operations.cjs');let state;
 const page={locator:selector=>({waitFor:async options=>{assert.equal(selector,'#disabled-action');state=options.state;}})};
 const evidence={functionalObservations:[],functionalRawObservations:[]};
 await performStep(page,{action:'hidden',selector:'#disabled-action'},{},evidence);
 assert.equal(state,'hidden');assert.deepEqual(evidence.functionalObservations,[{id:'#disabled-action',action:'hidden',value:true}]);
});

test('each explicit engine sequence must keep success assertions and exact submission targets',()=>{
 const op={engineStepContract:'save-v1',steps:[{action:'visible',selector:'#saved'}],engineSteps:{java:[{action:'visible',selector:'#saved'}],rust:[{action:'click',selector:'#save'}]}};
 assert.ok(operationIssues(op,{}).some(x=>x.startsWith('rust:')&&x.includes('postcondition')));
 op.engineSteps.rust=[{action:'submitValues',selector:'#save',method:'POST',path:'/save',values:{id:'one'}},{action:'visible',selector:'#saved'}];
 assert.deepEqual(operationIssues(op,{}),[]);
 op.engineSteps.rust[0].path='save';assert.ok(operationIssues(op,{}).some(x=>x.startsWith('rust:')&&x.includes('exact local path')));
});

test('engine-only plans accept shared postconditions without legacy steps',()=>{
 const op={engineStepContract:'save-v1',engineSteps:{java:[{action:'click',selector:'#save'}],rust:[{action:'confirmClick',selector:'#save',accept:true,message:'Save?'}]},postconditions:[{action:'value',selector:'#record',value:'saved'}]};
 assert.deepEqual(operationIssues(op,{}),[]);
 op.engineSteps.rust=[];assert.ok(operationIssues(op,{}).some(x=>x.includes('invalid engine step list')));
});
test('repeatability refuses destructive actions in either actual sequence',()=>{
 const {repeatabilityAllowed,actualSteps}=require('./operations.cjs');
 for(const side of ['java','rust']){
  const op={readOnly:true,steps:[{action:'visible',selector:'#record'}],engineSteps:{java:[{action:'visible',selector:'#record'}],rust:[{action:'visible',selector:'#record'}]}};
  assert.equal(repeatabilityAllowed(op),true);op.engineSteps[side].push({action:'click',selector:'#delete'});
  assert.equal(repeatabilityAllowed(op),false);
  op.engineSteps[side].push({action:'download',selector:'#export'});assert.ok(actualSteps(op).some(s=>s.action==='download'));
 }
});
