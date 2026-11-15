/* Research and operational scores have separate provenance and histories. */
(() => {
  const el=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=v=>Number.isFinite(v)?v.toFixed(1):'—';
  const names={hy:'高收益債利差',ig:'投資級債利差',vix:'VIX',indices:'Nasdaq 100 回撤',nfci:'金融情勢',us10y:'美國十年債',breadth:'市場廣度'};
  let data,globalArchive=null,loading=false;
  const hashKey='storage/phase4_publication_aware_panel.json';
  const validScore=value=>Number.isFinite(value)&&value>=0&&value<=100;
  const validSeries=rows=>Array.isArray(rows)&&rows.every((row,i)=>
    Number.isFinite(Date.parse(row?.date))&&(i===0||Date.parse(row.date)>Date.parse(rows[i-1].date))&&
    (row.score===null||validScore(row.score))&&Array.isArray(row.components)&&row.components.every(c=>c&&typeof c.metric==='string'));
  const countsMatch=(rows,total,valid)=>rows.length===total&&rows.filter(r=>validScore(r.score)).length===valid;
  function integrity(items){
    el('data-integrity').replaceChildren(...items.map(text=>{
      const item=document.createElement('li');
      item.textContent=text;
      return item;
    }));
  }
  function clearScores(){
    data=null;
    for(const id of ['global-score','taiwan-score','formal-score'])el(id).textContent='—';
    for(const id of ['global-score-info','global-score-date','taiwan-score-info','taiwan-score-date',
      'formal-reason','gate-checks','risk-chart','risk-chart-note','risk-factors','risk-limitations','risk-date'])el(id).replaceChildren();
    for(const id of ['risk-series','risk-range','risk-date'])el(id).disabled=true;
    el('risk-gate').textContent='正式模型狀態無法確認';
    el('risk-count').textContent='評分資料不可用';
  }
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
    if(!data)return;
    const kind=el('risk-series').value;
    const selected=el('risk-date').value;
    let rows=kind==='global_archive'?(globalArchive?.records||[]):kind==='global'?data.global_history:kind==='forward'?data.prospective_history:data.taiwan_history;
    const limit=el('risk-range').value;
    if(limit!=='all')rows=rows.slice(-Number(limit));
    el('risk-chart').innerHTML=chart(rows,kind.startsWith('global')?null:data.taiwan.research_threshold);
    el('risk-chart-note').textContent=kind==='global_archive'?(globalArchive?'三年描述性重建：'+globalArchive.valid_scores+' / '+globalArchive.sessions+' 筆有效分數；按觀測日配對，可能包含後續修訂，非當時已知訊號。最高覆蓋率 90%（早期利率暖機期為 85%），不與實際留存紀錄混接。':'全球歷史資料無法取得，不能視為零風險。'):kind==='global'?'按實際執行時間留存；不將事後重建值混入。':kind==='forward'?'僅顯示已事前留存的研究預測；缺資料期間不補發。':'歷史重建使用凍結的全期間參考分布；不是無前視回測或前瞻績效。虛線為研究門檻 '+data.taiwan.research_threshold+'。';
    el('risk-date').innerHTML=rows.filter(r=>Number.isFinite(r.score)).slice().reverse().map(r=>'<option value="'+esc(r.date)+'">'+esc(r.date)+'</option>').join('');
    el('risk-date').disabled=!el('risk-date').options.length;
    if([...el('risk-date').options].some(option=>option.value===selected))el('risk-date').value=selected;
    el('risk-date').onchange=()=>showDetail(rows);
    showDetail(rows);
  }
  function showDetail(rows){const row=rows.find(r=>r.date===el('risk-date').value);el('risk-factors').innerHTML=row?'<p class="small muted">所選日期：'+esc(row.date)+(row.signal_date?'｜訊號資料日：'+esc(row.signal_date):'')+'｜分數 '+num(row.score)+'</p>'+factors(row.components||[]):'<p class="muted">尚無可檢視的因子紀錄。</p>';}
  async function load(){
    if(loading)return;
    loading=true;
    try{
      const [dashboard,archive,calibration,pit,quality]=await Promise.allSettled(
        ['risk_dashboard.json','global_history.json','calibration.json','pit_full_replay_audit.json','quality.json'].map(getRadarData)
      );
      const next=dashboard.value;
      if(next?.schema_version!==1||!Number.isFinite(Date.parse(next.generated_at))||
        !next.global||!next.taiwan||!Array.isArray(next.limitations)||
        !validSeries(next.taiwan_history)||!validSeries(next.global_history)||!validSeries(next.prospective_history)||
        !countsMatch(next.taiwan_history,next.historical_sessions,next.valid_historical_scores)){
        throw new Error('評分檔缺失或歷史日期、筆數、分數格式不一致');
      }
      const candidate=archive.value;
      globalArchive=candidate?.schema_version===1&&validSeries(candidate.records)&&
        countsMatch(candidate.records,candidate.sessions,candidate.valid_scores)&&
        candidate.input_sha256?.[hashKey]===next.source_panel_sha256?candidate:null;
      const matchedCalibration=calibration.value?.source_panel_sha256===next.source_panel_sha256&&
        calibration.value?.historical_sessions===next.historical_sessions&&
        calibration.value?.valid_historical_scores===next.valid_historical_scores;
      const matchedPit=pit.value?.input_sha256?.[hashKey]===next.source_panel_sha256&&
        pit.value?.sessions===next.historical_sessions&&pit.value?.mismatch_count===0;
      const summary=quality.value?.summary;
      integrity([
        '評分產出時間（UTC）：'+next.generated_at,
        '台灣重建：'+next.valid_historical_scores+' / '+next.historical_sessions+' 筆有效，'+
          (next.historical_sessions-next.valid_historical_scores)+' 筆無分數',
        globalArchive?'全球重建：'+globalArchive.valid_scores+' / '+globalArchive.sessions+' 筆有效':'全球重建檔無法讀取或與本次評分版本不一致',
        matchedCalibration?'台灣校準版本與有效筆數一致':'台灣校準報告缺失或與本次評分版本不一致',
        matchedPit?'PIT 內部重播：'+pit.value.checks+' 個位置，0 項不一致':'PIT 重播報告缺失、版本不一致或檢出差異',
        summary?'市場品質（'+quality.value.evaluated_at+' UTC）：'+summary.pass+' 通過、'+summary.caution+' 待查、'+summary.blocked+' 排除':'市場資料品質報告無法取得'
      ]);
      data=next;
      el('risk-series').disabled=false;
      el('risk-range').disabled=false;
    const g=data.global,t=data.taiwan.latest_research;
    el('global-score').textContent=num(validScore(g.score)?g.score:null);el('global-score-info').textContent='品質覆蓋 '+num(g.coverage*100)+'%｜最低 '+num(g.min_coverage*100)+'%';
    el('global-score-date').textContent='資料擷取：'+(g.as_of||'未知');
    el('taiwan-score').textContent=num(validScore(t?.score)?t.score:null);el('taiwan-score-info').textContent=t?'評分日 '+t.date+'｜訊號日 '+t.signal_date:'等待合格資料';
    el('taiwan-score-date').textContent=!t?'':t.status==='prospective_research'?'已留存前瞻研究預測':'歷史重建分數 · 非今日訊號';
    const gate=data.taiwan.quality_gate;
    const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Taipei'}).format(new Date());
    const current=gate?.evaluated_for_date===today;
    const formal=current&&data.formal_model_status==='PASS'&&gate.status==='PASS'&&gate.checks?.length===5&&
      gate.checks.every(check=>check.passed===true)&&data.taiwan.as_of===today&&validScore(data.taiwan.score);
    el('risk-gate').textContent='正式模型 '+(formal?'PASS':data.formal_model_status==='BLOCKED'?'BLOCKED':'資料待更新');
    el('formal-score').textContent=formal?num(data.taiwan.score):'尚未符合條件';
    el('formal-reason').textContent=current?(data.taiwan.reason||('評分日 '+(data.taiwan.as_of||'—'))):'最近關卡日期 '+(gate?.evaluated_for_date||'未知');
    el('gate-checks').innerHTML='<ul>'+ (data.taiwan.quality_gate?.checks||[]).map(c=>'<li class="'+(c.passed?'':'warn')+'">'+esc(c.label)+'：'+(c.passed?'通過':'待完成')+'</li>').join('')+'</ul><a href="model_readiness.json">查看品質關卡報告</a>';

    el('risk-count').textContent=data.historical_sessions+' 個交易日已整合 · '+data.valid_historical_scores+' 筆歷史研究分數';
    el('risk-limitations').innerHTML=data.limitations.map(s=>'<li>'+esc(s)+'</li>').join('');
    el('risk-error').textContent='';renderHistory();
    }catch(e){
      clearScores();
      integrity(['評分檔無法核對。']);
      el('risk-error').textContent=e.message+'，約一分鐘後重試。';
    }finally{
      loading=false;
    }
  }
  el('risk-series').onchange=renderHistory;el('risk-range').onchange=renderHistory;
  async function forwardHealth(){try{
    const h=await getRadarData('forward_health.json');
    if(!Number.isFinite(Date.parse(h?.checked_at_utc))||![h.snapshots,h.predictions,h.outcomes].every(n=>Number.isInteger(n)&&n>=0))throw Error();
    const labels={captured:'當日快照已保存',capture_incomplete:'當日擷取未完整',capture_due_no_current_attempt:'晚間應擷取但未見當日紀錄',outside_capture_window:'目前不在擷取時段'};
    const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Taipei'}).format(new Date());
    el('forward-health').textContent=h.taipei_date+'｜'+(h.taipei_date===today?(labels[h.status]||h.status):'上次檢查紀錄，今日狀態待更新')+'｜累積快照 '+h.snapshots+'、預測 '+h.predictions+'、結果 '+h.outcomes+'｜檢查時間 '+h.checked_at_utc;
  }catch(e){el('forward-health').textContent='無法取得前瞻健康報告，不能視為正常執行。';}}
  load();forwardHealth();setInterval(()=>{load();forwardHealth();},60000);
})();
