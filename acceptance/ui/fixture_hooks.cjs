// Phase 3, Change 18: typed external fixture control cannot execute commands or follow redirects.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const assert=require('node:assert/strict');
async function fixtureHook(config,stage,side,directory,id,request=fetch){
 if(config===undefined)return;
 if(!config||Array.isArray(config)||typeof config.readyFile!=='string'||!['before','after'].includes(stage)||!['java','rust'].includes(side))
  throw Error('Invalid typed fixture control configuration');
 const readyBytes=fs.readFileSync(config.readyFile),ready=JSON.parse(readyBytes);
 const url=new URL(ready.url);
 if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||!url.port||url.username||url.password||url.search||url.hash||url.pathname!=='/'||typeof ready.token!=='string'||!ready.token)
  throw Error('Fixture control requires a capability-protected loopback origin');
 const target=url.origin+'/__fixture/'+(stage==='before'?'reset':'state');
 const payload=stage==='before'?{...(config.reset||{}),label:id+':'+side}:undefined;
 const record={stage,side,caseId:id,url:target,method:stage==='before'?'POST':'GET',request:payload,
  readySha256:crypto.createHash('sha256').update(readyBytes).digest('hex'),status:null,body:null,assertions:[],error:null};
 try{
  const response=await request(target,{method:record.method,headers:{Authorization:'Bearer '+ready.token,'Content-Type':'application/json'},
   body:payload?JSON.stringify(payload):undefined,redirect:'error',signal:AbortSignal.timeout(30000)});
  record.status=response.status;record.body=await response.text();
  assert.equal(response.status,200,'Fixture control response');const state=JSON.parse(record.body);
  if(stage==='after')for(const check of config.assertions||[]){
   if(!Array.isArray(check.path)||!check.path.length||check.path.some(k=>!['string','number'].includes(typeof k)))throw Error('Invalid fixture assertion path');
   const actual=check.path.reduce((node,key)=>node?.[key],state);
   record.assertions.push({path:check.path,expected:check.value,actual});assert.deepEqual(actual,check.value,'External fixture effect '+check.path.join('.'));
  }
 }catch(error){record.error=error.message;throw error;}
 finally{fs.writeFileSync(path.join(directory,side+'.fixture-'+stage+'.json'),JSON.stringify(record,null,2));}
 return record;
}
module.exports={fixtureHook};
