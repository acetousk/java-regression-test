const {test}=require('node:test'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {rejectionMatches,readToken}=require('./csrf_probe.cjs');
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
test('rejection proof requires exact request/response, status, target and unchanged persisted value',()=>{
 const item={key:'/save',method:'POST',status:401,requestBody:Buffer.from('token=invalid'),body:Buffer.from('refused')};
 const proof={kind:'invalid',path:'/save',method:'POST',status:401,unchanged:true,requestSha256:sha(item.requestBody),responseSha256:sha(item.body)};
 assert.equal(rejectionMatches(item,[proof]),true);
 for(const changed of [{...proof,unchanged:false},{...proof,path:'/other'},{...proof,method:'GET'},
  {...proof,status:403},{...proof,requestSha256:'wrong'},{...proof,responseSha256:'wrong'},{...proof,kind:'expected'}])assert.equal(rejectionMatches(item,[changed]),false);
 assert.equal(rejectionMatches({...item,status:500},[{...proof,status:500}]),false);
});
test('token discovery fails on absent or conflicting current values',async()=>{
 const page=values=>({locator:()=>({evaluateAll:async()=>values})});
 assert.equal(await readToken(page(['one']),'input'),'one');
 await assert.rejects(readToken(page([]),'input'));await assert.rejects(readToken(page(['one','two']),'input'));
});
test('token workflow refuses mutated records and always closes the peer session',async()=>{
 const {runCsrfProbe}=require('./csrf_probe.cjs');
 function fixture(mutateRejected){
  let persisted='before',draft='before',closed=false;
  const peerLocator={fill:async()=>{},click:async()=>{},first(){return this;},evaluateAll:async()=>['peer-token']};
  const other={setDefaultTimeout(){},goto:async()=>{},waitForURL:async()=>{},locator:()=>peerLocator};
  const peer={newPage:async()=>other,close:async()=>{closed=true;}};
  const page={url:()=> 'http://127.0.0.1:1234/record?id=one',context:()=>({browser:()=>({newContext:async()=>peer})}),
   goto:async()=>{},waitForLoadState:async()=>{},locator:selector=>({inputValue:async()=>persisted,fill:async value=>{draft=value;},
    click:async()=>{persisted=draft;},evaluateAll:async()=>['main-token']}),
   evaluate:async(fn,args)=>{if(mutateRejected)persisted=args.fieldValue;return {status:401,request:[...Buffer.from('token='+args.token)],response:[...Buffer.from('token refused')]};}};
  return {page,closed:()=>closed};
 }
 const step={selector:'#form',fieldSelector:'#value',submitSelector:'#submit',tokenSelector:'#token',tokenField:'token',path:'/record/save',validValue:'after',rejectedValue:'forbidden',peerUsername:'fixture',peerPassword:'fixture',rejectionStatus:401,rejectionText:'token refused'};
 const good=fixture(false),evidence={functionalObservations:[]};await runCsrfProbe(good.page,step,evidence);
 assert.equal(evidence.securityChecks.length,2);assert.equal(good.closed(),true);
 const bad=fixture(true),failed={functionalObservations:[]};await assert.rejects(runCsrfProbe(bad.page,step,failed),/Persisted value/);
 assert.equal(bad.closed(),true);assert.equal(failed.securityChecks.length,0);
});
