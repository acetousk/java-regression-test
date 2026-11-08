// Change 1: compare raw bytes. No normalization, tolerance, masks or approvals.
const crypto = require('node:crypto');
function bytes(a, b) {
  let first = -1, different = 0;
  for (let i=0; i<Math.max(a.length,b.length); i++) if(a[i]!==b[i]) { if(first<0) first=i; different++; }
  return {equal:a.equals(b), leftBytes:a.length, rightBytes:b.length, differentBytes:different, firstDifferentOffset:first,
    leftSha256:crypto.createHash('sha256').update(a).digest('hex'), rightSha256:crypto.createHash('sha256').update(b).digest('hex')};
}
function pixels(a,b) {
  const sameDimensions=a.width===b.width && a.height===b.height;
  const raw=bytes(a.data,b.data);
  let differentPixels=null;
  if(sameDimensions) {
    differentPixels=0;
    for(let i=0;i<a.data.length;i+=4) if(!a.data.subarray(i,i+4).equals(b.data.subarray(i,i+4))) differentPixels++;
  }
  return {...raw,equal:sameDimensions&&raw.equal,sameDimensions,leftDimensions:[a.width,a.height],rightDimensions:[b.width,b.height],differentPixels};
}
function contentErrors(body,dom) {
  const text=body.toString('utf8')+'\n'+dom;
  return {parameterError:text.includes('Required parameter missing'),
    renderError:/Error rendering|Exception in render/.test(text)};
}
function captureValid(c) {
  return !c.missingParameters?.length && ['java','rust'].every(side=>{
    const s=c.sides[side];
    return s && s.status===200 && !s.error && !s.readinessError && !s.unexpectedRedirect && !s.parameterError && !s.renderError && !s.errorPage
      && !s.pageErrors?.length && !s.httpErrors?.length;
  });
}
function parityPassed(summary) {
 return summary.complete===true && summary.captures.length>0 && summary.unroutable.length===0 &&
   summary.captures.every(c=>captureValid(c)&&c.html?.equal&&c.dom?.equal&&c.pixels?.equal&&(!c.route?.startsWith('/qapps')||c.qvt?.equal===true));
}
module.exports={bytes,pixels,contentErrors,captureValid,parityPassed};
