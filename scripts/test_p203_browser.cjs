/* P2-03 actual browser acceptance, local HTTP and real Chromium. */
const { chromium }=require('playwright');
const { spawn }=require('node:child_process');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ROOT=path.resolve(__dirname,'..'), DOCS=path.join(ROOT,'docs');
const read=p=>JSON.parse(fs.readFileSync(path.join(DOCS,p),'utf8'));
const pct=x=>(x*100).toFixed(1)+'%';
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  const server=spawn('python3',['-m','http.server','8765','--bind','127.0.0.1','--directory',DOCS],{stdio:'ignore'});
  let browser;
  try{
    await delay(900);
    browser=await chromium.launch({headless:true});
    const page=await browser.newPage({viewport:{width:1366,height:900}});
    const errors=[],failed=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('requestfailed',r=>failed.push(r.url()+':'+r.failure()?.errorText));
    const response=await page.goto('http://127.0.0.1:8765/',{waitUntil:'networkidle',timeout:30000});
    assert.equal(response.status(),200);
    await page.waitForFunction(()=>document.getElementById('p203-research')?.dataset.status==='loaded',{timeout:30000});
    assert.deepEqual(errors,[],'JS exceptions');
    assert.deepEqual(failed,[],'failed HTTP requests');
    const text=await page.locator('#p203-research').innerText();
    const ext=read('p2_02_extended_validation.json');
    const mu=read('p2_02_failure_and_multiplicity.json');
    const up=read('p2_03_uptrend_early_warning_research.json');
    for(const h of ['5d','20d']){
      for(const f of ext.holdout[h].walk_forward_folds)
        assert(text.includes(pct(f.metrics.precision)),h+' walk-forward fold');
      assert(text.includes(pct(ext.holdout[h].walk_forward_aggregate.precision)),h+' aggregate');
      for(const f of Object.values(mu.factor_comparisons[h]))
        assert(text.includes(pct(f.full_minus_removed_precision)),h+' factor delta');
      assert(text.includes(pct(up.results[h].aggregate.precision)),h+' uptrend precision');
      assert(text.includes(pct(up.results[h].aggregate.base_rate)),h+' uptrend base');
      assert(text.includes(up.results[h].bonferroni_two_horizons_p.toFixed(2)),h+' p value');
    }
    assert(text.includes('BLOCKED'));
    assert(text.includes('研究版｜不可作為交易訊號'));
    assert(text.includes('未達顯著'));
    // Legacy operational dashboard must still populate from its own JSON.
    await page.waitForFunction(()=>document.getElementById('risk-count')?.textContent.includes('交易日'),{timeout:30000});
    assert(await page.locator('#risk-chart').innerHTML(),'legacy chart');
    assert(await page.locator('#risk-factors').innerText(),'legacy factors');
    assert(await page.locator('#cards .card').count()>=4,'legacy metric cards');
    const before=await page.locator('#p203-research').innerText();
    await page.selectOption('#risk-series','global');
    await page.selectOption('#risk-range','60');
    assert(await page.locator('#risk-chart').innerHTML(),'legacy interaction');
    assert.equal(await page.locator('#p203-research').innerText(),before,'research panel isolation');
    await page.screenshot({path:path.join(ROOT,'p203_browser_acceptance.png'),fullPage:true});
    console.log(JSON.stringify({status:'PASS',research_json_checks:true,legacy_dashboard:true,controls:true,blocked:true,js_errors:errors,failed_requests:failed,screenshot:'p203_browser_acceptance.png'}));
  }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
