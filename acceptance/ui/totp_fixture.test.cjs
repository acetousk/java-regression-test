const {test}=require('node:test'),assert=require('node:assert/strict');
const {codeAt,fillTotp}=require('./totp_fixture.cjs');
const secret='GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ';
test('TOTP uses RFC6238 SHA1 vectors and rejects malformed material',()=>{
 assert.equal(codeAt(secret,59),'287082');assert.equal(codeAt(secret,1111111109),'081804');
 assert.equal(codeAt(secret,1234567890),'005924');assert.throws(()=>codeAt('not base32',59));
});
test('setup secrets remain engine-scoped and refusal codes avoid the accepted window',async()=>{
 let filled;const page={locator:s=>({innerText:async()=>`Secret: ${secret}`,fill:async value=>filled=value})};
 const evidence={engine:'java',functionalRawObservations:[],functionalObservations:[]};
 await fillTotp(page,{binding:'fixture-one',secretSelector:'#setup',selector:'#code'},evidence,()=>1234567890000);
 assert.equal(filled,'005924');assert.equal(evidence.functionalRawObservations[0].timeSource,'wall-clock');
 await assert.rejects(fillTotp(page,{binding:'fixture-one',selector:'#code'},{...evidence,engine:'rust'},()=>1234567890000),/earlier real setup/);
 await fillTotp(page,{binding:'fixture-one',selector:'#code',mode:'incorrect'},evidence,()=>1234567890000);
 for(const n of [-2,-1,0,1,2])assert.notEqual(filled,codeAt(secret,1234567890+n*30));
 await fillTotp(page,{binding:'fixture-one',selector:'#code',mode:'expired'},evidence,()=>1234567890000);
 assert.equal(filled,codeAt(secret,1234567590));
});
test('cross-account probes require independent bindings and reject accidental valid-code collisions',async()=>{
 let filled;const evidence={engine:'rust',functionalRawObservations:[],functionalObservations:[]};
 const page={locator:()=>({innerText:async()=>`Secret: ${secret}`,fill:async value=>filled=value})};
 for(const binding of ['cross-source','cross-target'])await fillTotp(page,{binding,secretSelector:'#setup',selector:'#code'},evidence,()=>1234567890000);
 await assert.rejects(fillTotp(page,{binding:'cross-source',targetBinding:'cross-source',selector:'#code',mode:'crossAccount'},evidence,()=>1234567890000),/another factor/);
 await assert.rejects(fillTotp(page,{binding:'cross-source',targetBinding:'cross-target',selector:'#code',mode:'crossAccount'},evidence,()=>1234567890000),/collided/);
 await assert.rejects(fillTotp(page,{binding:'cross-source',targetBinding:'missing',selector:'#code',mode:'crossAccount'},evidence,()=>1234567890000),/provisioned/);
 const other={locator:()=>({innerText:async()=>`Secret: JBSWY3DPEHPK3PXP`,fill:async value=>filled=value})};
 await fillTotp(other,{binding:'other-factor',secretSelector:'#setup',selector:'#code'},evidence,()=>1234567890000);
 await fillTotp(other,{binding:'other-factor',targetBinding:'cross-target',selector:'#code',mode:'crossAccount'},evidence,()=>1234567890000);
 assert.notEqual(filled,codeAt(secret,1234567890));
});
