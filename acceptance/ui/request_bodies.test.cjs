const {test}=require('node:test'),assert=require('node:assert/strict');
const {captureRequestBody,compareRequestBodies}=require('./request_bodies.cjs');
const entry=value=>({key:'/save',method:'POST',...captureRequestBody({postDataBuffer:()=>value})});
test('request capture preserves arbitrary bytes, absence, hashes and extraction failures',()=>{
 const bytes=Buffer.from([0,255,32,38]);const saved=entry(bytes);
 assert.ok(saved.requestBody.equals(bytes));assert.equal(saved.requestBodyBytes,4);assert.match(saved.requestBodySha256,/^[a-f0-9]{64}$/);
 assert.equal(entry(null).requestBodyPresent,false);assert.equal(entry(Buffer.alloc(0)).requestBodyPresent,true);
 assert.equal(captureRequestBody({postDataBuffer:()=>{throw Error('unavailable');}}).requestBodyComplete,false);
});
test('raw request equality rejects missing historical capture, token changes and encoding changes',()=>{
 const base=entry(Buffer.from('value=a+b&token=one'));
 assert.equal(compareRequestBodies([base],[{...base}]).equal,true);
 for(const other of [{...base,requestBodyComplete:false},entry(Buffer.from('value=a%20b&token=one')),entry(Buffer.from('value=a+b&token=two')),
  {...base,key:'/other'},{...base,method:'GET'},{key:'/save',method:'POST'}])assert.equal(compareRequestBodies([base],[other]).equal,false);
 assert.equal(compareRequestBodies([entry(null)],[entry(Buffer.alloc(0))]).equal,false);
 assert.equal(compareRequestBodies([],[]).complete,false);
 assert.ok(!JSON.stringify(compareRequestBodies([base],[base])).includes('token=one'));
});
