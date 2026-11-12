// Phase 3, Change 21: valid and rejected token probes require persisted-state postconditions.
const assert=require('node:assert/strict'),crypto=require('node:crypto');
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
function rejectionMatches(item,checks){
 return [401,403].includes(item.status)&&Buffer.isBuffer(item.body)&&Buffer.isBuffer(item.requestBody)&&
  (checks||[]).some(c=>['invalid','cross-session'].includes(c.kind)&&c.unchanged===true&&c.status===item.status&&
   c.path===item.key&&c.method===item.method&&c.requestSha256===sha(item.requestBody)&&c.responseSha256===sha(item.body));
}
async function readToken(page,selector){
 const values=await page.locator(selector).evaluateAll(nodes=>[...new Set(nodes.map(n=>n.value).filter(Boolean))]);
 assert.equal(values.length,1,'Exactly one current token value');return values[0];
}
async function runCsrfProbe(page,step,evidence,hooks={}){
 assert.ok([401,403].includes(step.rejectionStatus),'Explicit authentication rejection status');
 const initialUrl=page.url(),target=new URL(step.path,initialUrl);
 assert.equal(target.origin,new URL(initialUrl).origin,'Probe target must stay on the engine');
 assert.ok(step.validValue!==step.rejectedValue,'Distinct rejected mutation value');
 const assertPersisted=async()=>{
  await page.goto(initialUrl,{waitUntil:'networkidle'});
  assert.equal(await page.locator(step.fieldSelector).inputValue(),step.validValue,'Persisted value after request');
 };
 assert.notEqual(await page.locator(step.fieldSelector).inputValue(),step.validValue,'Valid probe must change the persisted value');
 await page.locator(step.fieldSelector).fill(step.validValue);
 await page.locator(step.submitSelector).click();await page.waitForLoadState('networkidle');await assertPersisted();
 const validToken=await readToken(page,step.tokenSelector);
 const peer=await page.context().browser().newContext({viewport:{width:1440,height:900},locale:'en-US',timezoneId:'UTC'});
 let detachPeer;
 try{
  const other=await peer.newPage();other.setDefaultTimeout(6000);detachPeer=hooks.attachPeer?.(other);
  await other.goto(new URL('/Login',initialUrl).href);
  await other.locator('#login_form input[name="username"]').fill(step.peerUsername);
  await other.locator('#login_form input[name="password"]').fill(step.peerPassword);
  await Promise.all([other.waitForURL(u=>u.pathname!=='/Login',{timeout:10000}),other.locator('#login_form button[type="submit"]').first().click()]);
  await other.goto(initialUrl,{waitUntil:'networkidle'});
  const peerToken=await readToken(other,step.tokenSelector);assert.notEqual(peerToken,validToken,'Sessions must use distinct tokens');
  evidence.securityChecks=evidence.securityChecks||[];
  for(const [kind,token] of [['invalid','invalid-token-fixture'],['cross-session',peerToken]]){
   assert.notEqual(token,validToken);
   const result=await page.evaluate(async({selector,fieldSelector,fieldValue,tokenField,token,url})=>{
    const form=document.querySelector(selector);if(!(form instanceof HTMLFormElement))throw Error('Probe requires the actual rendered form');
    const field=document.querySelector(fieldSelector);if(!field?.name)throw Error('Probe field lacks submitted name');
    const params=new URLSearchParams();for(const [key,value] of new FormData(form)){if(typeof value!=='string')throw Error('Token probe cannot serialize file fields');params.append(key,value);}
    params.set(field.name,fieldValue);params.set(tokenField,token);const body=params.toString();
    const response=await fetch(url,{method:'POST',credentials:'same-origin',redirect:'error',headers:{'Content-Type':'application/x-www-form-urlencoded'},body});
    return {status:response.status,request:Array.from(new TextEncoder().encode(body)),response:Array.from(new Uint8Array(await response.arrayBuffer()))};
   },{selector:step.selector,fieldSelector:step.fieldSelector,fieldValue:step.rejectedValue,tokenField:step.tokenField,token,url:target.href});
   assert.equal(result.status,step.rejectionStatus,kind+' token refusal status');
   const response=Buffer.from(result.response);assert.ok(response.toString('utf8').includes(step.rejectionText),kind+' token refusal message');
   await assertPersisted();
   evidence.securityChecks.push({kind,status:result.status,path:target.pathname+target.search,method:'POST',requestSha256:sha(Buffer.from(result.request)),responseSha256:sha(response),unchanged:true});
  }
  evidence.functionalObservations.push({id:step.id||step.selector,action:'csrfProbe',validPersistedValue:step.validValue,
   rejections:evidence.securityChecks.map(c=>({kind:c.kind,status:c.status,unchanged:c.unchanged}))});
 }finally{detachPeer?.();await peer.close();}
}
module.exports={runCsrfProbe,rejectionMatches,readToken};
