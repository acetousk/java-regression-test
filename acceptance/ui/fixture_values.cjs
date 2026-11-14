// Phase 3, Change 26: fill inputs only from an owned loopback fixture's retained response.
const fs=require('node:fs'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const bindings=new Map();
async function fixtureValueFill(page,step,evidence,request=fetch,timing={}){
 assert.ok(['java','rust'].includes(evidence.engine));assert.equal(typeof step.binding,'string');assert.ok(step.binding.trim());
 const key=evidence.engine+':'+step.binding;let value=bindings.get(key)?.code;
 if(step.readyFile){
  const readyBytes=fs.readFileSync(step.readyFile),ready=JSON.parse(readyBytes),url=new URL(ready.url);
  assert.ok(url.protocol==='http:'&&url.hostname==='127.0.0.1'&&url.port&&url.pathname==='/'&&!url.search&&!url.hash&&!url.username&&!url.password&&typeof ready.token==='string'&&ready.token,'Owned loopback fixture required');
  assert.ok(Number.isSafeInteger(step.messageIndex)&&step.messageIndex>=0&&typeof step.recipient==='string');
  const target=url.origin+'/__fixture/state';let matched=false;
  const now=timing.now||(()=>performance.now()),wait=timing.wait||(ms=>new Promise(resolve=>setTimeout(resolve,ms)));
  const deadline=now()+30000;
  while(now()<deadline){
   const remaining=Math.ceil(deadline-now());if(remaining<=0)break;
   const response=await request(target,{headers:{Authorization:'Bearer '+ready.token},redirect:'error',signal:AbortSignal.timeout(Math.min(3000,remaining))});
   assert.ok(now()<deadline,'Fixture delivery exceeded the total deadline');
   assert.equal(response.status,200,'Fixture response status');const body=await response.text(),state=JSON.parse(body);
   assert.ok(now()<deadline,'Fixture delivery body exceeded the total deadline');
   const message=state.messages?.[step.messageIndex];
   if(message){
    assert.deepEqual(message.recipients,[step.recipient],'Delivered recipient must match the factor account');
    const raw=Buffer.from(message.rawBase64,'base64');assert.equal(crypto.createHash('sha256').update(raw).digest('hex'),message.sha256,'Delivered MIME hash');
    value=message.singleUseCode;assert.match(value,/^[0-9]{6}$/,'Expected one six-digit delivered code');
    const binding={code:value,recipient:step.recipient,mimeSha256:message.sha256,readySha256:crypto.createHash('sha256').update(readyBytes).digest('hex'),url:target,messageIndex:step.messageIndex};
    if(bindings.has(key))assert.deepEqual(bindings.get(key),binding,'Stored fixture delivery identity cannot change');bindings.set(key,binding);
    evidence.functionalRawObservations.push({action:'fixtureValueFill',binding:step.binding,url:target,status:response.status,body,readySha256:crypto.createHash('sha256').update(readyBytes).digest('hex')});matched=true;break;
   }
   const delay=Math.min(100,deadline-now());if(delay>0)await wait(delay);
  }
  assert.ok(matched,'Expected delivery did not arrive');
 }
 assert.match(value||'',/^[0-9]{6}$/,'Earlier fixture delivery required');
 if(step.incorrect===true){const used=new Set([...bindings].filter(([name])=>name.startsWith(evidence.engine+':')).map(([,binding])=>binding.code));value='000000';while(used.has(value))value=String(Number(value)+1).padStart(6,'0');}
 await page.locator(step.selector).fill(value);
 evidence.functionalObservations.push({id:step.id||step.binding,action:'fixtureValueFill',binding:step.binding,incorrect:step.incorrect===true,valueSha256:crypto.createHash('sha256').update(value).digest('hex')});
}
module.exports={fixtureValueFill};
