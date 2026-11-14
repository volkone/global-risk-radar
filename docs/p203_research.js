/* P2-03 research validation view; read-only and fail-closed. */
(() => {
  const root=document.getElementById('p203-research');
  if(!root)return;
  const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pct=x=>typeof x==='number'&&Number.isFinite(x)?(x*100).toFixed(1)+'%':'—';
  const fixed=x=>typeof x==='number'&&Number.isFinite(x)?x.toFixed(2):'—';
  const get=async p=>{const r=await fetch('./'+p+'?'+Date.now(),{cache:'no-store'});if(!r.ok)throw Error(p+' HTTP '+r.status);return r.json();};
  const row=(label,a,b)=>'<tr><td>'+esc(label)+'</td><td>'+esc(a)+'</td><td>'+esc(b)+'</td></tr>';
  const table=(head,body)=>'<div style="overflow-x:auto"><table><thead><tr>'+head.map(x=>'<th>'+esc(x)+'</th>').join('')+'</tr></thead><tbody>'+body+'</tbody></table></div>';
  const link=(p,label)=>'<a href="'+esc(p)+'" target="_blank" rel="noopener">'+esc(label)+'</a>';
  async function render(){
    try{
      const [readiness,p201,p202,extended,multiple,uptrend]=await Promise.all([
        get('model_readiness.json'),get('p2_01_statistical_validation.json'),
        get('p2_02_robustness.json'),get('p2_02_extended_validation.json'),
        get('p2_02_failure_and_multiplicity.json'),get('p2_03_uptrend_early_warning_research.json')
      ]);
      const blocked=readiness.status!=='READY';
      const gates=(readiness.checks||[]).map(c=>'<li>'+esc(c.label)+'：'+(c.passed?'已通過':'未通過')+'</li>').join('');
      const wf=table(['滾動測試','5 日命中率','20 日命中率'],[0,1,2].map(i=>row('第 '+(i+1)+' 段',pct(extended.holdout['5d'].walk_forward_folds[i].metrics.precision),pct(extended.holdout['20d'].walk_forward_folds[i].metrics.precision))).join('')+
        row('合併',pct(extended.holdout['5d'].walk_forward_aggregate.precision),pct(extended.holdout['20d'].walk_forward_aggregate.precision)));
      const factors=[
        ['foreign_tx_short_pressure','外資台指期淨空壓力'],['margin_deleveraging_20d','融資減槓桿'],
        ['institutional_net_selling_5d','法人現貨賣超'],['twd_depreciation_20d','台幣貶值'],
        ['hy_oas_widening_20d','HY 利差擴大'],['prior_us_vix_level','VIX 水準']];
      const ft=table(['因子','5 日完整模型優勢','20 日完整模型優勢','12 項同時校正'],factors.map(([k,name])=>{
        const a=multiple.factor_comparisons['5d'][k],b=multiple.factor_comparisons['20d'][k];
        return '<tr><td>'+esc(name)+'</td><td>'+pct(a.full_minus_removed_precision)+'</td><td>'+pct(b.full_minus_removed_precision)+'</td><td>'+(a.familywise_ci_excludes_zero||b.familywise_ci_excludes_zero?'有區間排除零':'未達顯著')+'</td></tr>';
      }).join(''));
      const early=table(['上漲市場轉弱研究','5 日','20 日'],
        row('警示命中率',pct(uptrend.results['5d'].aggregate.precision),pct(uptrend.results['20d'].aggregate.precision))+
        row('市場事件基準率',pct(uptrend.results['5d'].aggregate.base_rate),pct(uptrend.results['20d'].aggregate.base_rate))+
        row('兩期間校正 p 值',fixed(uptrend.results['5d'].bonferroni_two_horizons_p),fixed(uptrend.results['20d'].bonferroni_two_horizons_p)));
      root.innerHTML='<p class="warn"><strong>研究版｜不可作為交易訊號</strong>。正式品質關卡：'+esc(readiness.status)+'。'+(blocked?'尚未取得正式模型授權，研究分數與門檻不得當作當日預警。':'請另行確認正式授權與當日資料。')+'</p>'+
        '<details open><summary>正式資料與模型品質關卡</summary><ul>'+gates+'</ul></details>'+
        '<h3>Walk-Forward 樣本外穩定性</h3>'+wf+
        '<p class="small muted">依歷史區段逐次評估；同一段歷史已被研究過，不能視為全新、未接觸的獨立確認樣本。</p>'+
        '<h3>六因子成對消融與多重比較</h3>'+ft+
        '<p class="small muted">數值是完整模型命中率減去移除該因子後的命中率。12 項同時信賴區間均包含零；不能據此調整權重。</p>'+
        '<h3>上漲市場轉弱：獨立研究假說</h3>'+early+
        '<p class="small warn">回溯研究未達統計顯著；未接入正式風險分數或警示。</p>'+
        '<p class="small muted">研究來源：'+link('p2_01_statistical_validation.json','P2-01')+' · '+link('p2_02_extended_validation.json','P2-02 滾動驗證')+' · '+link('p2_02_failure_and_multiplicity.json','因子校正')+' · '+link('p2_03_uptrend_early_warning_research.json','轉弱研究')+' · '+link('model_readiness.json','正式品質關卡')+'</p>';
      root.dataset.status='loaded';
    }catch(e){
      root.dataset.status='unavailable';
      root.textContent='研究驗證資料未能完整載入：'+e.message+'。不顯示推測數值，也不提供正式警示。';
    }
  }
  render();
})();
