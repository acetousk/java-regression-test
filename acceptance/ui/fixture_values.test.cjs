const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {fixtureValueFill}=require('./fixture_values.cjs');
test('delivered code inputs bind recipient, raw hash, capability origin, and engine',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'fixture-code-')),ready=path.join(dir,'ready.json');
 fs.writeFileSync(ready,JSON.stringify({url:'http://127.0.0.1:18363/',token:'private-test'}));
 let filled;const page={locator:()=>({fill:async value=>filled=value})},evidence={engine:'java',functionalRawObservations:[],functionalObservations:[]};
 const raw=Buffer.from('Your single use code is: 123456');const message={singleUseCode:'123456',recipients:['recipient@example.invalid'],rawBase64:raw.toString('base64'),sha256:crypto.createHash('sha256').update(raw).digest('hex')};
 const response=async(url,options)=>{assert.equal(options.redirect,'error');assert.equal(options.headers.Authorization,'Bearer private-test');return {status:200,text:async()=>JSON.stringify({messages:[message]})};};
 const step={binding:'delivery-one',readyFile:ready,messageIndex:0,recipient:'recipient@example.invalid',selector:'#code'};
 try{
  await fixtureValueFill(page,step,evidence,response);assert.equal(filled,'123456');assert.ok(evidence.functionalRawObservations[0].body);
  await fixtureValueFill(page,{binding:'delivery-one',selector:'#code',incorrect:true},evidence);assert.notEqual(filled,'123456');
  await assert.rejects(fixtureValueFill(page,{binding:'delivery-one',selector:'#code'},{...evidence,engine:'rust'}),/Earlier fixture/);
  await assert.rejects(fixtureValueFill(page,{...step,recipient:'other@example.invalid'},evidence,response),/recipient/);
  message.sha256='0'.repeat(64);await assert.rejects(fixtureValueFill(page,step,evidence,response),/MIME hash/);
  fs.writeFileSync(ready,JSON.stringify({url:'http://example.invalid/',token:'test'}));await assert.rejects(fixtureValueFill(page,step,evidence,response),/loopback/);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('delivery has a total monotonic deadline without a real timeout sleep',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'fixture-deadline-')),ready=path.join(dir,'ready.json');fs.writeFileSync(ready,JSON.stringify({url:'http://127.0.0.1:18363/',token:'test'}));
 const step={binding:'deadline',readyFile:ready,messageIndex:0,recipient:'recipient@example.invalid',selector:'#code'};
 let elapsed=0,calls=0;const timing={now:()=>elapsed,wait:async ms=>{elapsed+=ms;}};
 const response=async()=>{calls++;return {status:200,text:async()=>'{"messages":[]}'}};
 const evidence={engine:'java',functionalRawObservations:[],functionalObservations:[]};
 try{
  await assert.rejects(fixtureValueFill({},step,evidence,response,timing),/did not arrive/);
  assert.equal(elapsed,30000);assert.equal(calls,300);
  elapsed=0;const slow=async()=>{elapsed=30001;return {status:200,text:async()=>'{"messages":[]}'}};
  await assert.rejects(fixtureValueFill({},step,evidence,slow,timing),/total deadline/);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('the same code cannot replace recipient, MIME, or fixture identity of an existing binding',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'fixture-identity-')),ready=path.join(dir,'ready.json');
 const writeReady=token=>fs.writeFileSync(ready,JSON.stringify({url:'http://127.0.0.1:18363/',token}));writeReady('first');
 const makeMessage=(recipient,text)=>({singleUseCode:'123456',recipients:[recipient],rawBase64:Buffer.from(text).toString('base64'),sha256:crypto.createHash('sha256').update(text).digest('hex')});
 let message=makeMessage('one@example.invalid','original MIME');const response=async()=>({status:200,text:async()=>JSON.stringify({messages:[message]})});
 const evidence={engine:'java',functionalRawObservations:[],functionalObservations:[]},page={locator:()=>({fill:async()=>{}})},step={binding:'immutable-delivery',readyFile:ready,messageIndex:0,recipient:'one@example.invalid',selector:'#code'};
 try{
  await fixtureValueFill(page,step,evidence,response);
  message=makeMessage('two@example.invalid','different MIME');await assert.rejects(fixtureValueFill(page,{...step,recipient:'two@example.invalid'},evidence,response),/delivery identity/);
  message=makeMessage('one@example.invalid','different MIME');await assert.rejects(fixtureValueFill(page,step,evidence,response),/delivery identity/);
  message=makeMessage('one@example.invalid','original MIME');writeReady('replacement');await assert.rejects(fixtureValueFill(page,step,evidence,response),/delivery identity/);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
