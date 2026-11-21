/* P2-03 actual browser acceptance, local HTTP and real Chromium. */
const { chromium }=require('playwright');
const { spawn }=require('node:child_process');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ROOT=path.resolve(__dirname,'..'), DOCS=path.join(ROOT,'docs');
const site=process.env.RADAR_ACCEPTANCE_URL;
const read=async (page,p)=>site
  ? (await page.request.get(new URL(p,site).href)).json()
  : JSON.parse(fs.readFileSync(path.join(DOCS,p),'utf8'));
const pct=x=>(x*100).toFixed(1)+'%';
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  const server=site?null:spawn('python3',['-m','http.server','8765','--bind','127.0.0.1','--directory',DOCS],{stdio:'ignore'});
  let browser;
  try{
    if(server)await delay(900);
    browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
    const page=await browser.newPage({viewport:{width:1366,height:900}});
    const errors=[],failed=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('requestfailed',r=>failed.push(r.url()+':'+r.failure()?.errorText));
    const response=await page.goto(site||'http://127.0.0.1:8765/',{waitUntil:'networkidle',timeout:30000});
    assert.equal(response.status(),200);
    await page.waitForFunction(()=>document.getElementById('p203-research')?.dataset.status==='loaded',{timeout:30000});
    assert.deepEqual(errors,[],'JS exceptions');
    assert.deepEqual(failed,[],'failed HTTP requests');
    const readiness=await read(page,'model_readiness.json');
    const text=await page.locator('#p203-research').innerText();
    const ext=await read(page,'p2_02_extended_validation.json');
    const mu=await read(page,'p2_02_failure_and_multiplicity.json');
    const up=await read(page,'p2_03_uptrend_early_warning_research.json');
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
    assert(text.includes(readiness.status));
    assert(text.includes('研究版｜不可作為交易訊號'));
    assert(text.includes('未達顯著'));
    // Legacy operational dashboard must still populate from its own JSON.
    await page.waitForFunction(()=>document.getElementById('risk-count')?.textContent.includes('交易日'),{timeout:30000});
    assert(await page.locator('#risk-chart').innerHTML(),'legacy chart');
    assert(await page.locator('#risk-factors').innerText(),'legacy factors');
    assert(await page.locator('#cards .card').count()>=4,'legacy metric cards');
    assert.equal(await page.locator('#strategy-title').count(),0,'3C scenario removed');
    const snapshot=await read(page,'data.json');
    assert.equal(Object.hasOwn(snapshot,'strategy'),false,'3C strategy state removed');
    const crash = page.locator('#taiwan-crash-watch');
    await page.waitForFunction(()=>document.querySelector('.crash-research')?.dataset.status==='loaded');
    const watch = snapshot.taiwan_crash_watch;
    if (site || watch) {
      assert.equal(await crash.locator('article').count(),3,'selloff dashboard has three market phases');
      assert.equal(watch.schema_version,1);
      const tw = snapshot.metrics.taiex;
      if (Number.isFinite(tw.official_close)) {
        assert.equal(tw.provider,'TWSE','Taiwan headline uses the exchange close');
        assert.equal(tw.value,tw.official_close);
        assert.equal(tw.date,tw.official_close_date);
      }
      if (watch.market?.tse?.down_pct != null)
        assert((await crash.innerText()).includes(`${watch.market.tse.down}/${watch.market.tse.compared}`));
      if (watch.leverage?.five_day_pct != null)
        assert((await crash.innerText()).includes(watch.leverage.five_day_prior_date));
    } else {
      assert((await crash.locator('.crash-cards').textContent()).includes('暫時不可用'));
    }
    await crash.locator('summary').click();
    const validation = await read(page,'taiwan_crash_watch_validation.json');
    const comparison = validation.blocks[0].targets['1'];
    assert((await crash.innerText()).includes(`${comparison.multisource.hits}/${comparison.events}`));
    assert((await crash.innerText()).includes('11/20 盤前回放'));
    const market = page.locator('#market-analysis');
    await page.waitForFunction(()=>!document.getElementById('market-analysis').textContent.includes('正在核對'));
    if (site) {
      assert.equal(await market.locator('article').count(), 4);
      assert((await market.textContent()).includes('資料日'));
    }
    const foreign = page.locator('#foreign-cash-ranking');
    await foreign.locator('select').waitFor();
    await page.waitForFunction(()=>!document.querySelector('#foreign-cash-ranking select').disabled);
    const ranking = await read(page,'foreign_cash_ranking.json');
    assert.equal(await foreign.locator('.foreign-top tr').count(),25);
    const events = foreign.locator('.foreign-events tr');
    assert.equal(await events.count(),12);
    const latest = ranking.entries.at(-1);
    assert((await events.first().textContent()).includes(latest.date));
    assert((await events.first().textContent()).includes('前 '));
    await foreign.locator('.foreign-next').click();
    assert((await events.first().textContent()).includes(ranking.entries.at(-13).date));
    await foreign.locator('select').selectOption('25');
    assert.equal(await foreign.locator('.foreign-events tr:not([data-rank="25"])').count(),0);
    assert.equal(await events.count(),Math.min(12,ranking.entries.filter(item=>item.rank===25).length));
    assert(await foreign.locator('.foreign-prev').isDisabled());
    await foreign.locator('select').selectOption('0');
    const before=await page.locator('#p203-research').innerText();
    await page.selectOption('#risk-series','global');
    await page.selectOption('#risk-range','60');
    assert(await page.locator('#risk-chart').innerHTML(),'legacy interaction');
    assert.equal(await page.locator('#p203-research').innerText(),before,'research panel isolation');
    const dashboard=await read(page,'risk_dashboard.json');
    const archive=await read(page,'global_history.json');
    const counts=await page.locator('#data-integrity').textContent();
    assert(counts.includes(dashboard.valid_historical_scores+' / '+dashboard.historical_sessions));
    assert(counts.includes(archive.valid_scores+' / '+archive.sessions));
    assert.equal(await page.locator('#global-score').textContent(),(dashboard.global.score?.toFixed(1)??'—'));
    assert.equal(await page.locator('#taiwan-score').textContent(),(dashboard.taiwan.latest_research?.score?.toFixed(1)??'—'));
    if(readiness.status==='BLOCKED')assert.equal(await page.locator('#formal-score').textContent(),'尚未符合條件');
    await page.selectOption('#risk-series','global_archive');
    assert.equal(await page.locator('#risk-chart svg').count(),1);
    await page.selectOption('#risk-series','forward');
    if(!dashboard.prospective_history.some(row=>Number.isFinite(row.score))){
      assert(await page.locator('#risk-date').isDisabled());
      assert((await page.locator('#risk-chart').textContent()).includes('尚無'));
    }
    await page.selectOption('#risk-series','taiwan');
    await page.setViewportSize({width:360,height:800});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile viewport overflow');
    assert.equal(await page.locator('#risk-chart svg').count(),1);
    assert.deepEqual(errors,[],'JS exceptions after interaction');
    assert.deepEqual(failed,[],'failed requests after interaction');
    await page.screenshot({path:path.join(ROOT,'p203_browser_acceptance.png'),fullPage:true});
    // Simulate an unavailable snapshot and confirm the normal refresh recovers.
    const testPage=await browser.newPage();
    await testPage.clock.install();
    testPage.on('pageerror',e=>errors.push(e.message));
    await testPage.goto(site||'http://127.0.0.1:8765/',{waitUntil:'networkidle'});
    await testPage.waitForFunction(()=>!document.querySelector('#risk-series').disabled);
    await testPage.route('**/risk_dashboard.json?*',route=>route.fulfill({status:200,json:{schema_version:1}}));
    await testPage.route('**/data.json?*',route=>route.fulfill({status:503}));
    await testPage.clock.fastForward(61000);
    await testPage.waitForFunction(()=>document.querySelector('#risk-error').textContent.includes('格式不一致'));
    assert(await testPage.locator('#risk-series').isDisabled());
    assert.equal(await testPage.locator('#global-score').textContent(),'—');
    await testPage.waitForFunction(()=>document.querySelectorAll('#cards .card').length===0);
    assert((await testPage.locator('#alerts').textContent()).includes('不可用'));
    assert.equal(await testPage.locator('#market-analysis article').count(),0);
    assert.equal(await testPage.locator('#taiwan-crash-watch article').count(),0);
    assert((await testPage.locator('.crash-cards').textContent()).includes('暫時不可用'));
    assert.equal(await testPage.locator('#p203-research').getAttribute('data-status'),'loaded');
    await testPage.unroute('**/risk_dashboard.json?*');
    await testPage.unroute('**/data.json?*');
    await testPage.clock.fastForward(61000);
    await testPage.waitForFunction(()=>!document.querySelector('#risk-series').disabled);
    await testPage.waitForFunction(()=>document.querySelectorAll('#cards .card').length>=4);
    assert.equal(await testPage.locator('#taiwan-crash-watch article').count(),watch ? 3 : 0);
    assert.deepEqual(errors,[],'JS exceptions after recovery');
    console.log(JSON.stringify({status:'PASS',research_json_checks:true,legacy_dashboard:true,controls:true,blocked:true,js_errors:errors,failed_requests:failed,screenshot:'p203_browser_acceptance.png'}));
  }finally{if(browser)await browser.close();server?.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
