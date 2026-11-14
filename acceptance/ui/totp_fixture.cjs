// Phase 3, Change 25: derive disposable factor codes from actual setup-screen secrets.
const assert=require('node:assert/strict'),crypto=require('node:crypto');
const secrets=new Map();
function keyBytes(secret){
 assert.match(secret,/^[A-Z2-7]+={0,6}$/,'Expected a base32 setup secret');
 let bits=0,value=0;const output=[];
 for(const char of secret.replace(/=+$/,'')){value=(value<<5)|'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'.indexOf(char);bits+=5;if(bits>=8){bits-=8;output.push((value>>>bits)&255);}}
 return Buffer.from(output);
}
function codeAt(secret,seconds){
 assert.ok(Number.isSafeInteger(seconds)&&seconds>=0,'Invalid factor clock');
 const counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(seconds/30)));
 const digest=crypto.createHmac('sha1',keyBytes(secret)).update(counter).digest(),offset=digest[19]&15;
 return String((digest.readUInt32BE(offset)&0x7fffffff)%1000000).padStart(6,'0');
}
async function fillTotp(page,step,evidence,now=()=>Date.now()){
 assert.ok(['java','rust'].includes(evidence.engine),'Unknown factor engine');
 assert.equal(typeof step.binding,'string');assert.ok(step.binding.trim(),'Factor binding required');
 const id=evidence.engine+':'+step.binding;
 if(step.secretSelector){
  const text=await page.locator(step.secretSelector).innerText();
  const matches=[...text.matchAll(/\bSecret:\s*([A-Z2-7]+={0,6})\b/g)];
  assert.equal(matches.length,1,'Expected exactly one displayed setup secret');keyBytes(matches[0][1]);
  if(secrets.has(id))assert.equal(secrets.get(id),matches[0][1],'Factor binding cannot change');
  secrets.set(id,matches[0][1]);
 }
 const secret=secrets.get(id);assert.ok(secret,'Factor requires an earlier real setup capture');
 const epoch=Math.floor(now()/1000),mode=step.mode||'current';assert.ok(['current','incorrect','expired','crossAccount'].includes(mode));
 let code=codeAt(secret,epoch);
 if(mode==='expired')code=codeAt(secret,epoch-300);
 if(mode==='incorrect'){
  const accepted=new Set([-2,-1,0,1,2].map(n=>codeAt(secret,epoch+n*30)));
  code='000000';while(accepted.has(code))code=String(Number(code)+1).padStart(6,'0');
 }
 if(mode==='crossAccount'){
  assert.notEqual(step.targetBinding,step.binding,'Cross-account code must use another factor');
  const target=secrets.get(evidence.engine+':'+step.targetBinding);assert.ok(target,'Target factor must be provisioned');
  assert.ok(![-2,-1,0,1,2].some(n=>codeAt(target,epoch+n*30)===code),'Cross-account code collided with target window');
 }
 if(mode==='expired')assert.ok(![-2,-1,0,1,2].some(n=>codeAt(secret,epoch+n*30)===code),'Expired code collided with current window');
 await page.locator(step.selector).fill(code);
 const observation={id:step.id||step.binding,action:'totpFill',binding:step.binding,mode,epochSeconds:epoch,timeSource:'wall-clock',secretSha256:crypto.createHash('sha256').update(secret).digest('hex'),codeSha256:crypto.createHash('sha256').update(code).digest('hex')};
 evidence.functionalRawObservations.push(observation);evidence.functionalObservations.push(observation);
}
module.exports={codeAt,fillTotp};
