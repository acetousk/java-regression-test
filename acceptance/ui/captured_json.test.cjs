const {test}=require('node:test'),assert=require('node:assert/strict');
const {capturedJson,field}=require('./captured_json.cjs');
const response=body=>({key:'/run/status',method:'GET',status:200,contentType:'application/json',body:Buffer.from(JSON.stringify(body))});
const evidence=http=>({engine:'java',http,functionalObservations:[],functionalRawObservations:[]});
const contract={path:'/run/status',method:'GET',status:200,contract:'one-call',readyWhen:[{path:['count'],op:'atLeast',value:1}],checks:[{path:['count'],value:1},{path:['output'],value:{text:'echo'}}]};
test('ready output requires exact count and the complete expected output object',async()=>{
 const e=evidence([response({count:0}),response({count:1,output:{text:'echo'}})]);await capturedJson(null,contract,e);assert.equal(e.functionalObservations[0].responseIndex,1);
 await assert.rejects(capturedJson(null,contract,evidence([response({count:2,output:{text:'echo'}})])),/field count/);
 await assert.rejects(capturedJson(null,contract,evidence([response({count:1,output:{text:'echo',unexpected:true}})])),/field output/);
});
test('wrong target/method/query and stale responses cannot satisfy a new assertion',async()=>{
 for(const change of [{key:'/other/status'},{key:'/run/status?extra=1'},{method:'POST'}]){
  let t=0;await assert.rejects(capturedJson(null,contract,evidence([{...response({count:1,output:{text:'echo'}}),...change}]),{now:()=>t,wait:async ms=>{t+=ms;}}),/readiness/);assert.equal(t,30000);
 }
 const e=evidence([response({count:1,output:{text:'echo'}})]);await capturedJson(null,contract,e);let t=0;
 await assert.rejects(capturedJson(null,contract,e,{now:()=>t,wait:async ms=>{t+=ms;}}),/readiness/);
});
test('dynamic request ID is bound to an earlier captured response and exact query bytes',async()=>{
 const e=evidence([{key:'/start',method:'POST',status:200,contentType:'application/json',body:Buffer.from('{"started":true,"runId":"one-id"}') }]);
 await capturedJson(null,{path:'/start',method:'POST',status:200,contract:'start',checks:[{path:['started'],value:true}],bind:[{name:'test-run',path:['runId']}]},e);
 e.http.push({...response({count:1,output:{text:'echo'}}),key:'/run/status?runId=one-id&details=true'});
 await capturedJson(null,{...contract,queries:[[['runId',{binding:'test-run'}],['details','true']]]},e);
 assert.equal(e.functionalObservations[1].targetPath,'/run/status?runId=one-id&details=true');
 await assert.rejects(capturedJson(null,{...contract,queries:[[['runId',{binding:'test-run'}]]]}, {...e,engine:'rust'}),/Missing captured/);
 assert.throws(()=>field({},['__proto__']),/Invalid/);
});
test('cleanup response floor excludes pre-stop state and counts require actual arrays',async()=>{
 assert.equal(field({items:{length:1,0:'wrong'}},['items','length']),undefined);assert.equal(field({items:{0:'wrong'}},['items',0]),undefined);
 const e=evidence([response({count:1,output:{text:'echo'}})]);e.jsonResponseFloor=0;let t=0;
 await capturedJson(null,contract,e,{now:()=>t,wait:async ms=>{t+=ms;e.http.push(response({count:1,output:{text:'echo'}}));}});
 assert.equal(e.functionalObservations[0].responseIndex,1);
});
test('exact start response keys reject additional output fields',async()=>{
 await assert.rejects(capturedJson(null,{path:'/run/status',method:'GET',status:200,contract:'start',checks:[],exactKeys:['runId'],bind:[{name:'strict-start',path:['runId']}]},evidence([response({runId:'one',unexpected:'other run'})])),/exact object keys/);
});
test('a late response from a pre-mutation request cannot prove the mutation result',async()=>{
 const e=evidence([{...response({count:1,output:{text:'echo'}}),requestSequence:4}]);e.jsonRequestFloor=5;let t=0;
 await capturedJson(null,contract,e,{now:()=>t,wait:async ms=>{t+=ms;e.http.push({...response({count:1,output:{text:'echo'}}),requestSequence:6});}});
 assert.equal(e.functionalObservations[0].responseIndex,1);
});
