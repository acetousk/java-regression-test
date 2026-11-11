// Change 7: approved presentation differences never exempt labels, inputs or outcomes.
const assert = require('node:assert/strict');
const actions = new Set(['exactLabel','exactText','count','hidden','options','choose','submitValues','confirmClick','validationText','clickResponse','focusFill']);
const assertions = new Set(['exactLabel','exactText','count','hidden','options','validationText']);
const labelText = raw => raw.replace(/\s+/g,' ').trim();
async function observedLabel(locator) {
  return locator.evaluate(node => {
    const copy=node.cloneNode(true);
    // Icons are presentation, while every remaining label word is retained.
    copy.querySelectorAll('[aria-hidden="true"], [role="presentation"]').forEach(n=>n.remove());
    return copy.textContent;
  });
}
async function widget(page, step) {
  const field=page.locator(step.selector);
  const count=await field.count();if(count>1)throw Error('Selection requires one uniquely identified backing field');
  if(count===0){const opener=page.locator(step.control);if(await opener.count()!==1)throw Error('Empty selection requires one visible named combobox');return {field,native:false,select2:false,opener};}
  const native=await field.evaluate(n=>n.tagName==='SELECT'&&!n.classList.contains('hidden')&&!n.classList.contains('select2-hidden-accessible'));
  const select2=await field.evaluate(n=>n.classList.contains('select2-hidden-accessible'));
  return {field,native,select2,opener:select2?field.locator('xpath=following-sibling::span[contains(@class,"select2")][1]').locator('[role="combobox"]:visible'):page.locator(step.control)};
}
async function allVirtualOptionLabels(page,options) {
  await options.first().evaluate(node=>{let scroll=node.parentElement;while(scroll&&!(scroll.scrollHeight>scroll.clientHeight&&['auto','scroll'].includes(getComputedStyle(scroll).overflowY)))scroll=scroll.parentElement;if(scroll)scroll.scrollTop=0;});
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const labels=[],seen=new Set();
  for(let attempt=0;attempt<100;attempt++) {
    const current=await options.allTextContents();
    if(new Set(current).size!==current.length)throw Error('Ambiguous duplicate displayed option labels');
    for(const label of current)if(!seen.has(label)){seen.add(label);labels.push(label);}
    const moved=await options.first().evaluate(node=>{
      let scroll=node.parentElement;
      while(scroll&&!(scroll.scrollHeight>scroll.clientHeight&&['auto','scroll'].includes(getComputedStyle(scroll).overflowY)))scroll=scroll.parentElement;
      if(!scroll||scroll.scrollTop+scroll.clientHeight>=scroll.scrollHeight-1)return false;
      scroll.scrollBy({top:Math.max(1,scroll.clientHeight),behavior:'instant'});return true;
    });
    if(!moved)return labels;
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  }
  throw Error('Option enumeration did not reach the end of the menu');
}
async function performFunctional(page,step,basePerform,observations=[],rawObservations=[]) {
  if(!actions.has(step.action)) {
    const locator=step.selector?page.locator(step.selector):null;
    let target=null;
    if(locator&&['click','download'].includes(step.action))target=await locator.evaluate(n=>{
      const href=n.getAttribute('href')||(n.form&&n.form.getAttribute('action'));
      const u=href?new URL(href,location.href):null;
      return {id:n.id||null,name:n.getAttribute('name'),destination:u&&['http:','https:'].includes(u.protocol)?u.pathname+u.search:null,rawHref:href,rawVisibleText:n.innerText};
    });
    await basePerform(page,step);
    let value=step.value===undefined?true:step.value;
    if(locator&&['fill','select','value'].includes(step.action))value=await locator.inputValue();
    if(locator&&step.action==='text')value=await locator.innerText();
    if(target)rawObservations.push({id:step.id||step.selector,action:step.action,target});
    observations.push({id:step.id||step.selector||step.route,action:step.action,value,
      ...(target?{targetPath:target.destination}:{} )});
    return;
  }
  const locator=step.selector?page.locator(step.selector):null;
  const observe=(value)=>observations.push({id:step.id||step.selector,action:step.action,value});
  if(step.action==='exactLabel') {
    const raw=await locator.innerText(),withoutIcons=await observedLabel(locator),actual=labelText(withoutIcons);
    rawObservations.push({id:step.id||step.selector,action:step.action,rawVisibleText:raw,visibleLabelWithoutIcons:withoutIcons,comparison:'Semantic words; presentation whitespace collapsed, raw text retained separately'});
    assert.equal(actual,step.value,'Exact visible control label');observe(actual);
  } else if(step.action==='focusFill') {
    await page.locator(step.control).click();
    assert.equal(await locator.evaluate(node=>document.activeElement===node),true,'Visible label must focus its input');
    await page.keyboard.press('ControlOrMeta+A');await page.keyboard.type(step.value);
    assert.equal(await locator.inputValue(),step.value,'Keyboard-entered value');observe(step.value);
  } else if(step.action==='validationText') {
    if(step.fieldSelector) {
      const state=await page.locator(step.fieldSelector).evaluate(node=>({valid:node.validity.valid,valueMissing:node.validity.valueMissing,message:node.validationMessage,value:node.value}));
      rawObservations.push({id:step.id||step.selector,action:step.action,nativeValidity:state});
      if(!state.valid&&state.message) {assert.equal(state.value,'','Required empty field');if(step.expected)assert.deepEqual([state.message],step.expected,'Exact validation refusal');observe([state.message]);return;}
    }
    await locator.first().waitFor({state:'visible'});const messages=(await locator.allInnerTexts()).filter(text=>text.trim().length);
    assert.ok(messages.length,'Expected explicit visible validation refusal');if(step.expected)assert.deepEqual(messages,step.expected,'Exact validation refusal');observe(messages);
  } else if(step.action==='exactText') {
    const actual=await locator.innerText();assert.equal(actual,step.value,'Exact content text');observe(actual);
  } else if(step.action==='count') {
    await page.waitForFunction(({selector,count})=>document.querySelectorAll(selector).length===count,{selector:step.selector,count:step.value},{timeout:6000});observe(await locator.count());
  } else if(step.action==='hidden') {
    await locator.waitFor({state:'hidden'});observe(true);
  } else if(step.action==='options'||step.action==='choose') {
    const w=await widget(page,step);
    if(w.native) {
      const options=await w.field.locator('option').evaluateAll(nodes=>nodes.map(n=>({value:n.value,label:n.textContent,disabled:n.disabled})));rawObservations.push({id:step.id||step.selector,action:step.action,rawOptions:options});
      if(step.action==='options') {
        if(step.expected)assert.deepEqual(options,step.expected,'Exact native option labels/values/order');if(step.expectedLabels)assert.deepEqual(options.map(o=>labelText(o.label)),step.expectedLabels,'Exact option labels/order');observe({labels:options.map(o=>labelText(o.label)),values:options.map(o=>o.value)});
      } else {
        await w.field.selectOption(step.value);assert.equal(await w.field.inputValue(),step.value);const label=labelText(options.find(o=>o.value===step.value)?.label||'');assert.equal(label,step.label);observe({value:step.value,label});
      }
    } else {
      await w.opener.click();
      const options=page.locator(w.select2?'.select2-results__option[role="treeitem"]:visible':'[role="option"]:visible');
      await options.first().waitFor({state:'visible'});
      if(step.action==='options') {
        const labels=w.select2?await options.allTextContents():await allVirtualOptionLabels(page,options);rawObservations.push({id:step.id||step.selector,action:step.action,rawOptionLabels:labels});
        // Empty-option NBSP is retained: missing/changed labels must not disappear.
        if(step.expectedLabels)assert.deepEqual(labels.map(labelText),step.expectedLabels,'Exact displayed option labels/order');
        if(w.select2){const backing=await w.field.locator('option').evaluateAll(nodes=>nodes.map(n=>({value:n.value,label:n.textContent})));observe({labels:backing.map(o=>labelText(o.label)),values:backing.map(o=>o.value)});}else observe({labels:labels.map(labelText)});if(w.select2)await w.opener.click();else await page.keyboard.press('Escape');
      } else {
        await page.getByRole(w.select2?'treeitem':'option',{name:step.label,exact:true}).click();
        assert.equal(await w.field.inputValue(),step.value,'Selected submitted value');observe({value:await w.field.inputValue(),label:step.label});
      }
    }
  } else if(step.action==='clickResponse') {
    const pending=page.waitForResponse(response=>new URL(response.url()).pathname===step.path&&response.request().method()===step.method,{timeout:10000});pending.catch(()=>{});
    await locator.click();const response=await pending,url=new URL(response.url());
    assert.equal(response.status(),step.status,'Action response status');
    const parameters=Object.fromEntries([...url.searchParams].sort(([a],[b])=>a.localeCompare(b)));assert.deepEqual(parameters,step.parameters,'Action request parameters');
    const error=await response.finished();if(error)throw Error(error);observe({path:url.pathname,method:response.request().method(),status:response.status(),parameters});
  } else if(step.action==='submitValues') {
    const requestPromise=page.waitForRequest(request=>new URL(request.url()).pathname.endsWith(step.transition)&&request.method()==='POST',{timeout:10000});
    requestPromise.catch(()=>{});await locator.click();const request=await requestPromise;
    let data;const type=request.headers()['content-type']||'';
    if(type.includes('application/json'))data=request.postDataJSON();
    else if(type.includes('application/x-www-form-urlencoded'))data=Object.fromEntries(new URLSearchParams(request.postData()||''));
    else if(type.includes('multipart/form-data')){const form=await new Response(request.postDataBuffer(),{headers:{'content-type':type}}).formData();data=Object.fromEntries(form.entries());if(Object.values(data).some(value=>typeof value!=='string'))throw Error('File submission requires an explicit payload assertion');}
    else throw Error('Unsupported submission encoding; cannot verify submitted values');
    const selected={};for(const [key,value] of Object.entries(step.values)){assert.equal(String(data[key]),String(value),'Submitted '+key);selected[key]=String(data[key]);}
    observe(selected);await page.waitForLoadState('networkidle',{timeout:10000});
  } else if(step.action==='confirmClick') {
    // A single explicitly scoped confirmation, never a blanket dialog auto-accept.
    if(step.autoConfirmation) {
      let nativeResolve;const native=new Promise(resolve=>nativeResolve=resolve);
      const listener=dialog=>nativeResolve({kind:'native',dialog});page.once('dialog',listener);
      const selector=step.confirmationSelector||'.q-dialog:has(.q-dialog__message)';
      const box=page.locator(selector);
      const custom=box.waitFor({state:'visible',timeout:6000}).then(()=>({kind:'custom'}));custom.catch(()=>{});
      const click=locator.click();click.catch(()=>{});
      try {
        const found=await Promise.race([native,custom]);
        if(found.kind==='native') {
          const dialog=found.dialog,actual=dialog.message();
          if(dialog.type()!=='confirm'||actual!==step.message){await dialog.dismiss();throw Error('Unexpected native confirmation');}
          if(step.accept)await dialog.accept();else await dialog.dismiss();
          observe({message:actual,accepted:step.accept,buttonLabel:step.accept?'OK':'Cancel'});
        } else {
          const message=labelText(await box.locator('.q-dialog__message').innerText());assert.equal(message,step.message);
          const choice=box.locator(step.accept?'button:has-text("Confirm"), button:has-text("OK")':'button:has-text("Cancel")');
          const buttonLabel=labelText(await observedLabel(choice));await choice.click();observe({message,accepted:step.accept,buttonLabel});
          await box.waitFor({state:'hidden'});
        }
        await click;
      } finally {page.off('dialog',listener);}
      await page.waitForLoadState('networkidle',{timeout:10000});return;
    }
    if(step.confirmationSelector){
      await locator.click();const box=page.locator(step.confirmationSelector);await box.waitFor({state:'visible'});
      assert.equal(labelText(await box.locator(step.messageSelector).innerText()),step.message);
      const button=box.locator(step.accept?step.acceptSelector:step.cancelSelector);
      const buttonLabel=labelText(await observedLabel(button));if(step.buttonLabel)assert.equal(buttonLabel,step.buttonLabel);
      await button.click();observe({message:step.message,accepted:step.accept,buttonLabel});await box.waitFor({state:'hidden'});return;
    }
    const pending=page.waitForEvent('dialog',{timeout:6000});pending.catch(()=>{});
    await Promise.all([locator.click(),pending.then(async dialog=>{
      const actual={type:dialog.type(),message:dialog.message()};
      if(actual.type!=='confirm'||actual.message!==step.message){await dialog.dismiss();throw Error('Unexpected confirmation: '+JSON.stringify(actual));}
      if(step.accept)await dialog.accept();else await dialog.dismiss();observe({message:actual.message,accepted:step.accept});
    })]);
    await page.waitForLoadState('networkidle',{timeout:10000});
  }
}
function compareFunctional(left,right) {
  try{assert.deepEqual(left,right);return {equal:true};}catch(error){return {equal:false,error:error.message};}
}
module.exports={actions,assertions,labelText,performFunctional,compareFunctional};
