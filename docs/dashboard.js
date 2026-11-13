/* Research and operational scores have separate provenance and histories. */
(() => {
  const el=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=v=>Number.isFinite(v)?v.toFixed(1):'—';
  const names={hy:'高收益債利差',ig:'投資級債利差',vix:'VIX',indices:'Nasdaq 100 回撤',nfci:'金融情勢',us10y:'美國十年債',breadth:'市場廣度'};
  let data,globalArchive=null;
  function factors(list){return '<table><thead><tr><th>風險因子</th><th>強度 / 100</th><th>貢獻分數</th><th>有效權重</th></tr></thead><tbody>'+list.map(c=>'<tr><td>'+esc(c.label||names[c.metric]||c.metric)+(c.eligible?'':'<div class="muted small">'+esc(c.reason==='signal_not_yet_calibrated'?'尚未校準':c.reason==='quality_gate_not_passed'?'品質門檻未通過':c.reason)+'</div>')+'</td><td>'+num(c.signal)+'</td><td>'+num(c.contribution)+'</td><td>'+(c.eligible?num(c.effective_weight!=null?c.effective_weight*100:c.weight/data.global.coverage)+'%':'—')+'</td></tr>').join('')+'</tbody></table>';}
  function chart(rows,threshold){
    const points=rows.filter(r=>Number.isFinite(r.score));
    if(!points.length)return '<p class="muted">此期間尚無符合品質條件的分數，缺值不以零分替代。</p>';
    if(points.length===1)return '<p class="muted">目前只有 1 筆已留存分數（'+esc(points[0].date)+'：'+num(points[0].score)+'）。累積第二筆後顯示趨勢。</p>';
    const width=960,height=260,left=44,right=12,top=18,bottom=34;
    const times=rows.map(r=>Date.parse(r.date)), start=Math.min(...times),end=Math.max(...times);
    const x=r=>left+(Date.parse(r.date)-start)/(end-start||1)*(width-left-right), y=v=>top+(100-v)/100*(height-top-bottom);
    let paths=[],segment=[];
    rows.forEach(r=>{if(Number.isFinite(r.score)){segment.push(`${x(r)},${y(r.score)}`);}else if(segment.length){paths.push(segment);segment=[];}});if(segment.length)paths.push(segment);
    return '<svg viewBox="0 0 960 260" role="img" aria-label="風險分數歷史趨勢，縱軸零至一百分">'+[0,25,50,75,100].map(v=>`<line x1="${left}" x2="948" y1="${y(v)}" y2="${y(v)}" stroke="#2d3b56"/><text x="5" y="${y(v)+4}" fill="#a7b5ce" font-size="12">${v}</text>`).join('')+(threshold==null?'':`<line x1="${left}" x2="948" y1="${y(threshold)}" y2="${y(threshold)}" stroke="#ffd181" stroke-dasharray="6 5"/>`)+paths.map(p=>`<polyline fill="none" stroke="#6ce2ce" stroke-width="2" points="${p.join(' ')}"/>`).join('')+points.map(r=>`<circle cx="${x(r)}" cy="${y(r.score)}" r="2" fill="#6ce2ce"><title>${esc(r.date)}：${num(r.score)}</title></circle>`).join('')+`<text x="44" y="250" fill="#a7b5ce" font-size="12">${esc(rows[0].date.slice(0,10))}</text><text x="948" y="250" text-anchor="end" fill="#a7b5ce" font-size="12">${esc(rows[rows.length-1].date.slice(0,10))}</text></svg>`;
  }
  function renderHistory(){
    const kind=el('risk-series').value;
    let rows=kind==='global_archive'?(globalArchive?.records||[]):kind==='global'?data.global_history:kind==='forward'?data.prospective_history:data.taiwan_history;
    const limit=el('risk-range').value;
    if(limit!=='all')rows=rows.slice(-Number(limit));
    el('risk-chart').innerHTML=chart(rows,kind.startsWith('global')?null:data.taiwan.research_threshold);
    el('risk-chart-note').textContent=kind==='global_archive'?(globalArchive?'三年描述性重建：'+globalArchive.valid_scores+' / '+globalArchive.sessions+' 筆有效分數；按觀測日配對，可能包含後續修訂，非當時已知訊號。最高覆蓋率 90%（早期利率暖機期為 85%），不與實際留存紀錄混接。':'全球歷史資料無法取得，不能視為零風險。'):kind==='global'?'按實際執行時間留存；不將事後重建值混入。':kind==='forward'?'僅顯示已事前留存的研究預測；缺資料期間不補發。':'歷史重建使用凍結的全期間參考分布；不是無前視回測或前瞻績效。虛線為研究門檻 '+data.taiwan.research_threshold+'。';
    el('risk-date').innerHTML=rows.filter(r=>Number.isFinite(r.score)).slice().reverse().map(r=>'<option value="'+esc(r.date)+'">'+esc(r.date)+'</option>').join('');
    el('risk-date').onchange=()=>showDetail(rows);showDetail(rows);
  }
  function showDetail(rows){const row=rows.find(r=>r.date===el('risk-date').value);el('risk-factors').innerHTML=row?'<p class="small muted">所選日期：'+esc(row.date)+(row.signal_date?'｜訊號資料日：'+esc(row.signal_date):'')+'｜分數 '+num(row.score)+'</p>'+factors(row.components||[]):'<p class="muted">尚無可檢視的因子紀錄。</p>';}
  async function load(){try{
    const response=await fetch('./risk_dashboard.json?'+Date.now(),{cache:'no-store'});if(!response.ok)throw Error('評分資料暫時無法取得');data=await response.json();
    try{const archive=await fetch('./global_history.json?'+Date.now(),{cache:'no-store'});globalArchive=archive.ok?await archive.json():null;}catch(e){globalArchive=null;}
    const g=data.global,t=data.taiwan.latest_research;
    el('global-score').textContent=num(g.score);el('global-score-info').textContent='品質覆蓋 '+num(g.coverage*100)+'%｜最低 '+num(g.min_coverage*100)+'%';
    el('global-score-date').textContent='資料擷取：'+(g.as_of||'未知');
    el('taiwan-score').textContent=num(t?.score);el('taiwan-score-info').textContent=t?'評分日 '+t.date+'｜訊號日 '+t.signal_date:'等待合格資料';
    el('taiwan-score-date').textContent=t?.status==='prospective_research'?'已留存前瞻研究預測':'歷史重建分數 · 非今日訊號';
    el('risk-gate').textContent='正式模型 '+data.formal_model_status;
    el('formal-score').textContent=Number.isFinite(data.taiwan.score)?num(data.taiwan.score):'尚未符合條件';
    el('formal-reason').textContent=data.taiwan.reason||('評分日 '+data.taiwan.as_of);
    el('gate-checks').innerHTML='<ul>'+ (data.taiwan.quality_gate?.checks||[]).map(c=>'<li class="'+(c.passed?'':'warn')+'">'+esc(c.label)+'：'+(c.passed?'通過':'待完成')+'</li>').join('')+'</ul><a href="model_readiness.json">查看品質關卡報告</a>';

    el('risk-count').textContent=data.historical_sessions+' 個交易日已整合 · '+data.valid_historical_scores+' 筆歷史研究分數';
    el('risk-limitations').innerHTML=data.limitations.map(s=>'<li>'+esc(s)+'</li>').join('');
    el('risk-error').textContent='';renderHistory();
  }catch(e){el('risk-error').textContent=e.message+'；請勿將空白解讀為低風險。';}}
  el('risk-series').onchange=renderHistory;el('risk-range').onchange=renderHistory;
  async function forwardHealth(){try{
    const r=await fetch('./forward_health.json?'+Date.now(),{cache:'no-store'});if(!r.ok)throw Error();
    const h=await r.json();const labels={captured:'當日快照已保存',capture_incomplete:'當日擷取未完整',capture_due_no_current_attempt:'晚間應擷取但未見當日紀錄',outside_capture_window:'目前不在擷取時段'};
    el('forward-health').textContent=h.taipei_date+'｜'+(labels[h.status]||h.status)+'｜累積快照 '+h.snapshots+'、預測 '+h.predictions+'、結果 '+h.outcomes+'｜檢查時間 '+h.checked_at_utc;
  }catch(e){el('forward-health').textContent='無法取得前瞻健康報告，不能視為正常執行。';}}
  load();forwardHealth();setInterval(()=>{load();forwardHealth();},60000);
})();
