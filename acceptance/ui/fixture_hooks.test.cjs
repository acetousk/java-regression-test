const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {fixtureHook}=require('./fixture_hooks.cjs');
function setup(){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'fixture-hook-')),readyFile=path.join(dir,'ready.json');fs.writeFileSync(readyFile,JSON.stringify({url:'http://127.0.0.1:18361',token:'test-capability'}));return {dir,readyFile};}
test('typed fixture control limits endpoints, rejects redirects and retains exact assertions',async()=>{
 const {dir,readyFile}=setup();try{
  const config={readyFile,reset:{counter:0},assertions:[{path:['counter'],value:1}]};
  const before=await fixtureHook(config,'before','java',dir,'case',async(url,options)=>{
   assert.equal(url,'http://127.0.0.1:18361/__fixture/reset');assert.equal(options.redirect,'error');
   assert.equal(options.method,'POST');assert.deepEqual(JSON.parse(options.body),{counter:0,label:'case:java'});
   return {status:200,text:async()=>'{}'};
  });assert.equal(before.status,200);
  await fixtureHook(config,'after','java',dir,'case',async(url,options)=>{
   assert.equal(url,'http://127.0.0.1:18361/__fixture/state');assert.equal(options.method,'GET');
   return {status:200,text:async()=>'{"counter":1}'};
  });
  const saved=fs.readFileSync(path.join(dir,'java.fixture-after.json'),'utf8');assert.ok(!saved.includes('test-capability'));assert.equal(JSON.parse(saved).assertions[0].actual,1);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('fixture controls reject other hosts and fail on bad status or effects',async()=>{
 const {dir,readyFile}=setup();try{
  const config={readyFile,assertions:[{path:['counter'],value:1}]};
  for(const response of [{status:403,text:async()=>'{}'},{status:200,text:async()=>'{"counter":2}'}])
   await assert.rejects(fixtureHook(config,'after','rust',dir,'case',async()=>response));
  for(const url of ['http://localhost:1','http://127.0.0.2:1','https://127.0.0.1:1','http://127.0.0.1:1/engine','http://user@127.0.0.1:1']){
   fs.writeFileSync(readyFile,JSON.stringify({url,token:'test'}));await assert.rejects(fixtureHook(config,'before','java',dir,'case'),/loopback/);
  }
  await assert.rejects(fixtureHook(['shell'],'before','java',dir,'case'),/typed/);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
