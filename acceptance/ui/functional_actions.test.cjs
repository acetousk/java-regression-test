// Change 7: fail closed on changed labels, submitted values, targets and fixture scope.
const {test}=require('node:test'),assert=require('node:assert/strict');
const {performFunctional,compareFunctional}=require('./functional_actions.cjs');
const {operationIssues,buildCases}=require('./operations.cjs');
test('semantic control labels retain exact raw visible text separately',async()=>{
 const page={locator:()=>({innerText:async()=> 'open_in_new  Add\nCondition ',evaluate:async()=> ' Add\nCondition '})};
 const observations=[],raw=[];await performFunctional(page,{action:'exactLabel',selector:'button',value:'Add Condition'},null,observations,raw);
 assert.equal(observations[0].value,'Add Condition');assert.equal(raw[0].rawVisibleText,'open_in_new  Add\nCondition ');
 await assert.rejects(()=>performFunctional(page,{action:'exactLabel',selector:'button',value:'Add Field'},null,[],[]),/label/);
});
test('exact content text never collapses significant whitespace',async()=>{
 const page={locator:()=>({innerText:async()=> 'A  B'})};
 await assert.rejects(()=>performFunctional(page,{action:'exactText',selector:'p',value:'A B'},null,[]));
});
test('submitted value mismatch fails although a request was sent',async()=>{
 const request={url:()=> 'http://local/create',method:()=> 'POST',headers:()=>({'content-type':'application/x-www-form-urlencoded'}),postData:()=> 'field=wrong'};
 const page={url:()=> 'http://local/page',waitForRequest:async predicate=>{assert.equal(predicate(request),true);return request;},locator:()=>({click:async()=>{}}),waitForLoadState:async()=>{}};
 await assert.rejects(()=>performFunctional(page,{action:'submitValues',selector:'button',path:'/create',method:'POST',values:{field:'expected'}},null,[]),/Submitted field/);
});
test('different operation values or target paths cannot compare equal',()=>{
 assert.equal(compareFunctional([{value:'one'}],[{value:'two'}]).equal,false);
 assert.equal(compareFunctional([{targetPath:'/a'}],[{targetPath:'/b'}]).equal,false);
});
test('functional suite cannot migrate to another selected screen or mode',()=>{
 const op={id:'case',functionalSuiteId:'suite',functionalScope:{screen:'a',mode:'html',path:'/apps/a'},steps:[{action:'exactLabel',selector:'button',value:'Save'}]};
 const cases=buildCases({selected:[{key:'b',routes:['/apps/a']}]},{screens:[{key:'b',operations:[op]}]});
 assert.ok(operationIssues(cases[0].op,{}).some(x=>x.includes('scope')));
 op.functionalScope.screen='b';const fixed=buildCases({selected:[{key:'b',routes:['/apps/a']}]},{screens:[{key:'b',operations:[op]}]});
 assert.deepEqual(operationIssues(fixed[0].op,{}),[]);
});
test('functional suite without observations cannot be justified by empty baseline',()=>{
 const op={functionalSuiteId:'suite',functionalScope:{screen:'a',mode:'html',path:'/apps/a'},selectedScreenKey:'a',selectedMode:'html',selectedRoute:'/apps/a',steps:[]};
 assert.ok(operationIssues(op,{}).some(x=>x.includes('assertion')));
});
test('validation requires an explicit refusal and preserves its exact text',async()=>{
 let messages=[];
 const field={first:()=>({waitFor:async()=>{}}),allInnerTexts:async()=>messages};
 const page={locator:()=>field};
 await assert.rejects(()=>performFunctional(page,{action:'validationText',selector:'.error'},null,[]),/refusal/);
 messages=['Field Path is required.'];const out=[];
 await performFunctional(page,{action:'validationText',selector:'.error'},null,out);
 assert.deepEqual(out[0].value,messages);
 await assert.rejects(()=>performFunctional(page,{action:'validationText',selector:'.error',expected:['Different refusal']},null,[]),/validation/);
});
test('multipart form submission retains exact values including embedded line breaks',async()=>{
 const body=Buffer.from('--fixture\r\nContent-Disposition: form-data; name="field"\r\n\r\none\ntwo\r\n--fixture--\r\n');
 const request={url:()=> 'http://local/create',method:()=> 'POST',headers:()=>({'content-type':'multipart/form-data; boundary=fixture'}),postDataBuffer:()=>body};
 const page={url:()=> 'http://local/page',waitForRequest:async predicate=>{assert.equal(predicate(request),true);return request;},locator:()=>({click:async()=>{}}),waitForLoadState:async()=>{}};
 const observations=[];await performFunctional(page,{action:'submitValues',selector:'button',path:'/create',method:'POST',values:{field:'one\ntwo'}},null,observations);
 assert.equal(observations[0].value.field,'one\ntwo');
});
test('dynamic click verifies actual response target, method and parameter values',async()=>{
 const response={url:()=> 'http://local/tree?fieldPath=wrong&dataDocumentId=Fixture',request:()=>({method:()=> 'GET'}),status:()=>200,finished:async()=>null};
 const page={url:()=> 'http://local/page',waitForResponse:async predicate=>{assert.equal(predicate(response),true);return response;},locator:()=>({click:async()=>{}})};
 await assert.rejects(()=>performFunctional(page,{action:'clickResponse',selector:'a',path:'/tree',method:'GET',status:200,parameters:{dataDocumentId:'Fixture',fieldPath:'enumId'}},null,[]),/parameters/);
});
test('mutation payloads and reloads stay on each scenario document fixture',()=>{
 const plan=require('./approved_functional_plan.json');
 const isolated=new Map();
 for(const screen of plan.screens)for(const op of screen.operations){
  const document=op.routeParameters?.dataDocumentId;if(!document)continue;
  for(const step of op.steps){
   for(const [key,value] of Object.entries(step.values||{}))if(key.startsWith('dataDocumentId'))assert.equal(value,document,op.id);
   if(step.route)assert.equal(new URL(step.route,'http://local').searchParams.get('dataDocumentId'),document,op.id);
  }
  if(op.id.startsWith('invalid-field')){assert.ok(!isolated.has(document));isolated.set(document,op.id);}
 }
 for(const screen of plan.screens)for(const op of screen.operations)if(isolated.has(op.routeParameters?.dataDocumentId))assert.equal(op.id,isolated.get(op.routeParameters.dataDocumentId),'Validation must not poison another scenario');
});
test('native constraint refusal preserves browser text and cannot pass valid input',async()=>{
 const page={locator:()=>({evaluate:async()=>({valid:false,valueMissing:true,message:'Please fill out this field.',value:''})})};
 const out=[];await performFunctional(page,{action:'validationText',selector:'.error',fieldSelector:'input'},null,out,[]);
 assert.deepEqual(out[0].value,['Please fill out this field.']);
 await assert.rejects(()=>performFunctional(page,{action:'validationText',selector:'.error',fieldSelector:'input',expected:['different']},null,[],[]),/validation refusal/);
});
test('keyboard editing requires real focus obtained through visible control',async()=>{
 const page={locator:()=>({click:async()=>{},evaluate:async()=>false}),keyboard:{press:async()=>{throw Error('must not type without focus');}}};
 await assert.rejects(()=>performFunctional(page,{action:'focusFill',selector:'input',control:'label',value:'2'},null,[]),/focus its input/);
});
test('server-search choices type the exact term into the visible widget',async()=>{
 const {searchChoice}=require('./functional_actions.cjs');let filled;
 const page={locator:selector=>({fill:async value=>{filled={selector,value};}})};
 await searchChoice(page,{native:false,select2:true},{search:'fixture.user'});
 assert.deepEqual(filled,{selector:'.select2-search__field:visible',value:'fixture.user'});
 await searchChoice(page,{native:false,select2:false,opener:{fill:async value=>{filled=value;}}},{search:'other.user'});
 assert.equal(filled,'other.user');
 await assert.rejects(searchChoice(page,{native:true},{search:'user'}),/Native options/);
});
test('submission values bind to exact origin, path, query, and explicit method',async()=>{
 const makeRequest=(url,method='POST')=>({url:()=>url,method:()=>method,headers:()=>({'content-type':'application/x-www-form-urlencoded'}),postData:()=> 'field=expected'});
 const step={action:'submitValues',selector:'button',path:'/screen/save?id=one',method:'POST',values:{field:'expected'}};
 for(const request of [makeRequest('http://local/other/save?id=one'),makeRequest('http://local/screen/save?id=two'),makeRequest('http://foreign/screen/save?id=one'),makeRequest('http://local/screen/save?id=one','GET')]){
  const page={url:()=> 'http://local/screen',waitForRequest:async predicate=>{if(!predicate(request))throw Error('No matching submission');return request;},locator:()=>({click:async()=>{}}),waitForLoadState:async()=>{}};
  await assert.rejects(()=>performFunctional(page,step,null,[],[]),/No matching submission/);
 }
 const request=makeRequest('http://local/screen/save?id=one');
 const page={url:()=> 'http://local/screen',waitForRequest:async predicate=>{assert.equal(predicate(request),true);return request;},locator:()=>({click:async()=>{}}),waitForLoadState:async()=>{}};
 const observed=[],raw=[];await performFunctional(page,step,null,observed,raw);
 assert.deepEqual(observed[0].value,{field:'expected'});
 assert.deepEqual(raw[0],{id:'button',action:'submitValues',path:'/screen/save?id=one',method:'POST',values:{field:'expected'}});
 assert.ok(operationIssues({steps:[{...step,path:undefined,transition:'/save'}],postconditions:[{action:'exactText',selector:'p',value:'Saved'}]},{}).some(issue=>issue.includes('Submission requires')));
});
test('response query contracts reject duplicate parameter values',async()=>{
 const response={url:()=> 'http://local/tree?fieldPath=wrong&fieldPath=expected',request:()=>({method:()=> 'GET'}),status:()=>200,finished:async()=>null};
 const page={url:()=> 'http://local/screen',waitForResponse:async predicate=>{assert.equal(predicate(response),true);return response;},locator:()=>({click:async()=>{}})};
 await assert.rejects(()=>performFunctional(page,{action:'clickResponse',selector:'a',path:'/tree',method:'GET',status:200,parameters:{fieldPath:'expected'}},null,[]),/Duplicate action query/);
});
