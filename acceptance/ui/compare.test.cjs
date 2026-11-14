const {test}=require('node:test');
const assert=require('node:assert/strict');
// Change 1: exact comparison and rejection of matching failure pages.
const {bytes,pixels,contentErrors}=require('./compare.cjs');
test('whitespace and a single byte are raw HTML differences',()=>{
 assert.equal(bytes(Buffer.from('<p>x</p>'),Buffer.from('<p>x</p>\n')).equal,false);
 assert.equal(bytes(Buffer.from('a'),Buffer.from('b')).firstDifferentOffset,0);
});
test('RGBA compares alpha and a single channel without a threshold',()=>{
 const a={width:1,height:1,data:Buffer.from([0,0,0,255])};
 assert.equal(pixels(a,{...a,data:Buffer.from([0,0,1,255])}).differentPixels,1);
 assert.equal(pixels(a,{...a,data:Buffer.from([0,0,0,254])}).equal,false);
 assert.equal(pixels(a,a).equal,true);
});
test('identical pixel buffers with different dimensions are unequal',()=>{
 const a={width:1,height:2,data:Buffer.alloc(8)};
 assert.equal(pixels(a,{...a,width:2,height:1}).equal,false);
});
const {parityPassed}=require('./compare.cjs');
test('matching error or redirected pages cannot pass coverage',()=>{
 const clean=()=>({complete:true,unroutable:[],captures:[{sides:{java:{status:200},rust:{status:200}},html:{equal:true},dom:{equal:true},pixels:{equal:true}}]});
 assert.equal(parityPassed(clean()),true);
 for(const error of [{pageErrors:['exception']},{httpErrors:[{status:404}]},{unexpectedRedirect:true},{parameterError:true},{renderError:true},{errorPage:true},{error:'failed'},{status:500},{readinessError:'timeout'}]){
  const s=clean();Object.assign(s.captures[0].sides.rust,error);assert.equal(parityPassed(s),false);
 }
 const s=clean();s.captures[0].missingParameters=['userId'];assert.equal(parityPassed(s),false);
});
test('HTTP 200 shell cannot hide rendered or parameter errors in the live DOM',()=>{
 assert.equal(contentErrors(Buffer.from('<html>shell</html>'),'<div>Error rendering screen</div>').renderError,true);
 assert.equal(contentErrors(Buffer.from('Exception in render'),'<html></html>').renderError,true);
 assert.equal(contentErrors(Buffer.from('shell'),'Required parameter missing').parameterError,true);
 assert.deepEqual(contentErrors(Buffer.from('screen'),'<div>ready</div>'),{renderError:false,parameterError:false});
});
