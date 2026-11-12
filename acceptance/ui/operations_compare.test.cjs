const {test}=require('node:test');
const assert=require('node:assert/strict');
const {compareOperation,compareRepeatability,operationReport}=require('./operations_compare.cjs');
const B=Buffer.from;
const capture=engine=>({id:'save',engine,exercised:true,complete:true,errors:[],
 http:[{key:'POST /save',method:'POST',status:200,requestBodyComplete:true,requestBodyPresent:true,requestBody:Buffer.from('value=one'),body:B('saved')}],dom:B('<p>saved</p>'),
 rgba:{width:1,height:1,data:B([1,2,3,255])},qvt:[],downloads:[]});
const database=()=>({status:'compared',complete:true,equal:true,exclusions:[],evidencePath:'private/db.json'});
const pair=()=>[capture('java'),capture('rust'),database()];
test('complete exercised matching operation passes without serializing captured content',()=>{
 const result=compareOperation(...pair());assert.equal(result.passed,true);
 assert.equal(JSON.stringify(result).includes('<p>saved</p>'),false);
});
test('each required channel or completion status fails closed when absent',()=>{
 for(const key of ['id','engine','exercised','complete','errors','http','dom','rgba','qvt','downloads']) {
  const p=pair();delete p[1][key];assert.equal(compareOperation(...p).passed,false,key);
 }
 for(const value of [null,{},undefined]) assert.equal(compareOperation(value,value,null).passed,false);
});
test('matching unexercised, failed and error pages never pass',()=>{
 for(const patch of [{exercised:false},{complete:false},{errors:['timeout']},{error:'timeout'},{pageErrors:['exception']},{unexpectedRedirect:true},{http:[]},
  {http:[{key:'GET /',method:'GET',status:500,body:B('same')}]},{dom:B('Required parameter missing')}]) {
  const p=pair();Object.assign(p[0],patch);Object.assign(p[1],patch);assert.equal(compareOperation(...p).passed,false);
 }
});
test('HTTP method/status, whitespace, DOM, alpha and dimensions are exact',()=>{
 const changes=[c=>c.http[0].body=B('saved\n'),c=>c.http[0].method='GET',c=>c.http[0].status=201,
  c=>c.dom=B('<p>saved</p> '),c=>c.rgba.data[3]=254,c=>c.rgba.width=2];
 for(const change of changes){const p=pair();change(p[1]);assert.equal(compareOperation(...p).passed,false);}
});
test('QVT and downloads require matching occurrence order, names and bytes',()=>{
 for(const channel of ['qvt','downloads']) {
  const p=pair();const entry=()=>({key:'one',filename:'file.txt',body:B('bytes')});
  p[0][channel]=[entry()];p[1][channel]=[entry()];assert.equal(compareOperation(...p).passed,true);
  p[1][channel][0].key='two';assert.equal(compareOperation(...p).passed,false);
  p[1][channel]=[];assert.equal(compareOperation(...p).passed,false);
  p[1][channel]=[entry()];p[1][channel][0].body=B('other');assert.equal(compareOperation(...p).passed,false);
 }
 const p=pair();p[0].downloads=[{key:'one',filename:'a',body:B('same')}];p[1].downloads=[{key:'one',filename:'b',body:B('same')}];
 assert.equal(compareOperation(...p).passed,false);
 assert.equal(compareOperation(...pair(),{qvtRequired:true}).passed,false);
 assert.equal(compareOperation(...pair(),{downloadsRequired:true}).passed,false);
});
test('database equality requires complete evidence without exclusions',()=>{
 for(const db of [null,{}, {equal:true}, {...database(),status:'unexercised'}, {...database(),complete:false},
  {...database(),equal:false},{...database(),error:'capture failed'},{...database(),errors:['query failed']},{...database(),exclusions:['timestamps']},{...database(),evidencePath:''}])
  assert.equal(compareOperation(capture('java'),capture('rust'),db).passed,false);
});
test('coverage rejects missing, duplicate, extra and same-engine results; diagnostics do not waive parity',()=>{
 const good=compareOperation(...pair()),repeat=compareRepeatability(capture('java'),capture('java'),database());
 assert.equal(repeat.passed,true);assert.equal(operationReport(['save'],[good],[repeat]).passed,true);
 for(const [ids,results] of [[[],[]],[['save'],[]],[['save'],[repeat]],[['save','other'],[good]],
  [['save'],[good,good]],[['other'],[good]],[['save','save'],[good,good]]])
  assert.equal(operationReport(ids,results,[repeat]).passed,false);
 const p=pair();p[1].dom=B('different');assert.equal(operationReport(['save'],[compareOperation(...p)],[repeat]).passed,false);
 assert.equal(operationReport(['save'],[good]).repeatability.passed,false);
 assert.equal(compareRepeatability(capture('java'),capture('rust'),database()).passed,false);
});

test('multiple QVT responses compare occurrence order rather than matching a set',()=>{
 const p=pair();const entry=x=>({key:'/page.qvt',body:B(x)});
 p[0].qvt=[entry('first'),entry('second')];p[1].qvt=[entry('second'),entry('first')];
 assert.equal(compareOperation(...p).passed,false);
});
