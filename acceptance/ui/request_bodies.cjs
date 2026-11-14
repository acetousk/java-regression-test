// Phase 3, Change 20: retain request content bytes without token or encoding normalization.
const crypto=require('node:crypto');
const {bytes}=require('./compare.cjs');
function captureRequestBody(request){
 try{
  const value=request.postDataBuffer();
  if(value!==null&&!Buffer.isBuffer(value))throw Error('Unexpected request body representation');
  const requestBody=value===null?Buffer.alloc(0):value;
  return {requestBody,requestBodyComplete:true,requestBodyPresent:value!==null,
   requestBodyBytes:requestBody.length,requestBodySha256:crypto.createHash('sha256').update(requestBody).digest('hex')};
 }catch(error){return {requestBody:null,requestBodyComplete:false,requestBodyPresent:null,requestBodyError:error.message};}
}
function compareRequestBodies(left,right,targetEqual=(a,b)=>a===b){
 if(!Array.isArray(left)||!Array.isArray(right))return {complete:false,equal:false,entries:[]};
 const complete=left.length>0&&right.length>0&&[...left,...right].every(e=>e?.requestBodyComplete===true&&
  typeof e.key==='string'&&e.key.length>0&&typeof e.method==='string'&&e.method.length>0&&
  Buffer.isBuffer(e.requestBody)&&typeof e.requestBodyPresent==='boolean'&&(e.requestBodyPresent||e.requestBody.length===0));
 const entries=[];
 for(let i=0;i<Math.max(left.length,right.length);i++){
  const a=left[i],b=right[i];
  const identity=!!a&&!!b&&a.method===b.method&&targetEqual(a.key,b.key);
  const body=Buffer.isBuffer(a?.requestBody)&&Buffer.isBuffer(b?.requestBody)?bytes(a.requestBody,b.requestBody):{equal:false,missing:true};
  entries.push({index:i,left:{method:a?.method,target:a?.key,present:a?.requestBodyPresent},right:{method:b?.method,target:b?.key,present:b?.requestBodyPresent},body,
   equal:identity&&a.requestBodyPresent===b.requestBodyPresent&&body.equal});
 }
 return {complete,equal:complete&&left.length===right.length&&entries.every(e=>e.equal),entries,
  scope:'Request content bytes for captured document, XHR, and fetch responses; no wire-frame or header identity claim'};
}
module.exports={captureRequestBody,compareRequestBodies};
