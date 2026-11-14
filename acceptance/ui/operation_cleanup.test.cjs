const {test}=require('node:test'),assert=require('node:assert/strict');
const {operationCleanup,ownsCleanup}=require('./operation_cleanup.cjs');
const guard={contract:'owned-config',submission:{path:'/own/begin',method:'POST'}};
const proof=[{action:'capturedJson',contract:'owned-config',bodySha256:'a'.repeat(64)},{action:'submitValues',path:'/own/begin',method:'POST'}];
test('cleanup requires this operation configuration proof and exact own start target',()=>{
 assert.equal(ownsCleanup({functionalRawObservations:proof},guard),true);
 for(const observations of [[],proof.slice(0,1),[proof[0],{...proof[1],path:'/other/begin'}]])assert.equal(ownsCleanup({functionalRawObservations:observations},guard),false);
});
test('cleanup preserves original failure and records stop proof separately',async()=>{
 let clicked=false,called=false;const page={locator:()=>({count:async()=>1,isEnabled:async()=>true,click:async()=>{clicked=true}})};
 const evidence={engine:'java',http:[{}],errors:['original failure'],functionalObservations:[{original:true}],functionalRawObservations:proof};
 await operationCleanup(page,{guard,steps:[{action:'clickWhenEnabled',selector:'#stop'},{action:'capturedJson'}]},evidence,async(p,s,o,e)=>{called=true;assert.equal(e.jsonResponseFloor,0);e.functionalRawObservations.push({stopped:true})});
 assert.ok(clicked&&called);assert.equal(evidence.cleanup.complete,true);assert.deepEqual(evidence.errors,['original failure']);assert.deepEqual(evidence.functionalObservations,[{original:true}]);
 await operationCleanup(page,{guard,steps:[{action:'capturedJson'}]},evidence,async()=>{throw Error('cannot stop')});
 assert.equal(evidence.cleanup.complete,false);assert.deepEqual(evidence.errors,['original failure','Operation cleanup failed: cannot stop']);
});
test('cleanup does not touch an unowned run',async()=>{
 const evidence={errors:[],functionalRawObservations:[]};await operationCleanup({locator:()=>{throw Error('must not touch')}},{guard,steps:[{action:'clickWhenEnabled',selector:'#stop'}]},evidence,()=>{});
 assert.equal(evidence.cleanup.authorized,false);assert.equal(evidence.cleanup.complete,false);
});
test('owned cleanup waits for the stop control instead of skipping its initial disabled state',async()=>{
 let clicked=false;const page={locator:()=>({count:async()=>1,click:async options=>{assert.equal(options.timeout,30000);await new Promise(resolve=>setImmediate(resolve));clicked=true;}})};
 const evidence={engine:'java',http:[],requestSequence:8,errors:['count assertion failed'],functionalObservations:[],functionalRawObservations:proof};
 await operationCleanup(page,{guard,steps:[{action:'clickWhenEnabled',selector:'#stop'},{action:'capturedJson'}]},evidence,async(p,s,o,e)=>{assert.equal(clicked,true);assert.equal(e.jsonRequestFloor,8);});
 assert.equal(evidence.cleanup.complete,true);assert.equal(evidence.errors[0],'count assertion failed');
});
