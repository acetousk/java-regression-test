// Phase 3, Change 27: cleanup owns only a run configured and started by this operation.
const assert=require('node:assert/strict');
function ownsCleanup(evidence,guard){
 assert.ok(guard&&typeof guard.contract==='string'&&guard.contract&&guard.submission?.method==='POST'&&typeof guard.submission.path==='string');
 const observations=evidence.functionalRawObservations||[];
 const ownStart=observations.some(o=>o.action==='submitValues'&&o.path===guard.submission.path&&o.method===guard.submission.method)||
  (evidence.functionalObservations||[]).some(o=>o.action==='clickResponse'&&o.value?.path===guard.submission.path&&o.value?.method===guard.submission.method&&o.value?.status===200);
 return observations.some(o=>o.action==='capturedJson'&&o.contract===guard.contract&&/^[a-f0-9]{64}$/.test(o.bodySha256||''))&&ownStart;
}
async function operationCleanup(page,config,evidence,performStep){
 if(config===undefined)return;
 const report={authorized:false,complete:false,observations:[],errors:[]};evidence.cleanup=report;
 try{
  report.authorized=ownsCleanup(evidence,config.guard);
  if(!report.authorized){report.reason='No matching configuration proof and start submission; no cleanup action taken';evidence.errors.push('Operation cleanup skipped: ownership not proven');return;}
  assert.ok(Array.isArray(config.steps)&&config.steps.length>0&&config.steps.at(-1).action==='capturedJson','Cleanup must end with captured stop proof');
  const cleanupEvidence={...evidence,jsonResponseFloor:evidence.http.length-1,jsonRequestFloor:evidence.requestSequence||0,functionalObservations:[],functionalRawObservations:[]};
  report.observations=cleanupEvidence.functionalRawObservations;
  for(const step of config.steps){
   if(step.action==='clickWhenEnabled'){
    const control=page.locator(step.selector);assert.equal(await control.count(),1,'Cleanup requires one owned control');
    await control.click({timeout:30000});
    cleanupEvidence.functionalRawObservations.push({action:step.action,selector:step.selector,clicked:true});
   }else{
    assert.equal(step.action,'capturedJson','Cleanup permits a guarded click and captured stop proof only');
    await performStep(page,step,{},cleanupEvidence);
   }
  }
  report.observations=cleanupEvidence.functionalRawObservations;report.complete=true;
 }catch(error){report.errors.push(error.message);evidence.errors.push('Operation cleanup failed: '+error.message);}
}
module.exports={ownsCleanup,operationCleanup};
