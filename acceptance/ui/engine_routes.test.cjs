const {test}=require('node:test'),assert=require('node:assert/strict');
const {resolveEngineOperation}=require('./engine_routes.cjs');
test('explicit engine mappings retain queries, suffixes, expected values and stable assertion IDs',()=>{
 const op={route:'/apps/old/item/rows?id=one',engineRoutes:{rust:{html:'/apps/new/item?stored=Y'}},engineSelectors:{rust:{'#old':'#new'}},
  steps:[{action:'value',selector:'#old',value:'exact '},{action:'clickResponse',selector:'#old',path:'/apps/old/item/run',method:'POST',parameters:{id:'one'},status:200}],postconditions:[]};
 const result=resolveEngineOperation('/apps/old/item',op,'rust');
 assert.equal(result.route,'/apps/new/item/rows?id=one&stored=Y');
 assert.equal(result.operation.steps[0].selector,'#new');assert.equal(result.operation.steps[0].id,'#old');
 assert.equal(result.operation.steps[0].value,'exact ');assert.equal(result.operation.steps[1].path,'/apps/new/item/run');
 assert.equal(op.steps[0].selector,'#old');assert.equal(resolveEngineOperation('/apps/old/item',op,'java').route,op.route);
});
test('mapping rejects external destinations, fragments and changed modes',()=>{
 for(const mapped of ['https://example.invalid/new','//example.invalid/new','/apps/new#fragment','/qapps/new'])
  assert.throws(()=>resolveEngineOperation('/apps/old',{engineRoutes:{rust:{html:mapped}},steps:[]},'rust'));
});
test('mapping does not replace an unrelated path sharing only a partial prefix',()=>{
 const result=resolveEngineOperation('/apps/old',{route:'/apps/older',engineRoutes:{rust:{html:'/apps/new'}},steps:[]},'rust');
 assert.equal(result.route,'/apps/older');
});

test('transition targets resolve to exact engine paths and preserve expected methods and queries',()=>{
 const op={engineRoutes:{rust:{html:'/apps/new'}},steps:[],coveredTransitions:[{name:'save',path:'/apps/old/save?id=one',method:'POST'}]};
 assert.deepEqual(resolveEngineOperation('/apps/old',op,'rust').operation.coveredTransitions,[{name:'save',path:'/apps/new/save?id=one',method:'POST'}]);
 assert.equal(op.coveredTransitions[0].path,'/apps/old/save?id=one');
});
test('submission targets map their full path and retain exact query values',()=>{
 const op={engineRoutes:{rust:{html:'/apps/new'}},steps:[{action:'submitValues',path:'/apps/old/save?id=one',method:'POST',values:{field:'value'}}]};
 const step=resolveEngineOperation('/apps/old',op,'rust').operation.steps[0];
 assert.equal(step.path,'/apps/new/save?id=one');assert.equal(step.method,'POST');
 assert.deepEqual(step.values,{field:'value'});
});

test('explicit engine actions retain exact confirmation and shared postconditions',()=>{
 const op={engineStepContract:'save-control-v1',engineRoutes:{rust:{html:'/apps/new'}},
  engineSteps:{java:[{action:'click',selector:'#save'}],rust:[{action:'confirmClick',selector:'#commit',message:'Save this record?',accept:true}]},
  postconditions:[{action:'value',selector:'#record',value:'unchanged'}]};
 const original=structuredClone(op),java=resolveEngineOperation('/apps/old',op,'java').operation,rust=resolveEngineOperation('/apps/old',op,'rust').operation;
 assert.equal(java.steps[0].action,'click');assert.equal(rust.steps[0].action,'confirmClick');
 assert.equal(rust.steps[0].message,'Save this record?');assert.equal(rust.steps[0].accept,true);
 assert.deepEqual(java.postconditions,rust.postconditions);assert.deepEqual(op,original);
 assert.notDeepEqual(java.steps,rust.steps);
});
test('engine-specific plans reject missing or empty counterpart contracts',()=>{
 const valid={engineStepContract:'save-v1',engineSteps:{java:[{action:'click'}],rust:[{action:'click'}]}};
 for(const op of [{...valid,engineStepContract:''},{...valid,engineStepContract:undefined},
  {...valid,engineSteps:{java:[{action:'click'}]}},{...valid,engineSteps:{java:[],rust:[{action:'click'}]}},
  {...valid,engineSteps:{...valid.engineSteps,other:[{action:'click'}]}},
  {...valid,engineSteps:{java:[null],rust:[{action:'click'}]}}])
  assert.throws(()=>resolveEngineOperation('/apps/old',op,'java'));
});

test('qapps exports use explicit HTML mappings and preserve exact POST contracts',()=>{
 const path='/apps/old/DocumentExport.json?id=one';
 const op={engineRoutes:{rust:{qapps:'/qapps/new',html:'/apps/new'}},coveredTransitions:[{name:'export',path,method:'POST'}],steps:[]};
 const resolved=resolveEngineOperation('/qapps/old',op,'rust').operation;
 assert.deepEqual(resolved.coveredTransitions,[{name:'export',path:'/apps/new/DocumentExport.json?id=one',method:'POST'}]);
 assert.equal(op.coveredTransitions[0].path,path);
 assert.equal(resolveEngineOperation('/qapps/old',{...op,coveredTransitions:[{name:'other',path:'/apps/older/export',method:'POST'}]},'rust').operation.coveredTransitions[0].path,'/apps/older/export');
 assert.equal(resolveEngineOperation('/qapps/old',{...op,engineRoutes:{rust:{qapps:'/qapps/new'}}},'rust').operation.coveredTransitions[0].path,path);
 assert.throws(()=>resolveEngineOperation('/qapps/old',{...op,engineRoutes:{rust:{qapps:'/qapps/new',html:'https://example.invalid/'}}},'rust'));
});
