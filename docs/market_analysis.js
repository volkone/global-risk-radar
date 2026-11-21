/* Explain the published snapshot using the radar's existing research thresholds. */
window.renderMarketAnalysis = function (snapshot, quality) {
  const root = document.getElementById('market-analysis');
  const datetime = new Intl.DateTimeFormat('zh-TW', {
    timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false
  });
  const stamp = Date.parse(snapshot?.updated_utc);
  if (!Number.isFinite(stamp) || quality?.snapshot_updated_at !== snapshot.updated_utc || !quality?.metrics) {
    root.textContent = '市場快照與品質報告尚未取得或版本不同，等待下一輪更新後再解讀。';
    return;
  }
  if (Date.now() - stamp > 24 * 60 * 60 * 1000) {
    root.textContent = '快照上次更新於 ' + datetime.format(stamp) + '（台灣時間），已超過 24 小時。等待更新後再解讀。';
    return;
  }
  const metrics = snapshot.metrics;
  const approved = (record, key) => record?.status === 'ok' && record.date &&
    record.cache_status !== 'stale' && !record.last_error && quality.metrics[key]?.quality === 'pass' &&
    quality.metrics[key].date === record.date;
  const valueAvailable = (record, key, field = 'value') => approved(record, key) && Number.isFinite(record[field]);
  const num = (n, digits = 2) => n.toLocaleString('zh-TW', {maximumFractionDigits: digits});
  const dated = (record, detail) => detail + '（' + record.date + '）';
  const {hy, ig, vix, indices, taiex, margin, maint, inst, fx} = metrics;
  const taiwanCredit = snapshot.taiwan_crash_watch?.credit;
  const creditReady = valueAvailable(maint, 'maint') && taiwanCredit?.status === 'ok' &&
    maint.date === taiwanCredit.date && Number.isInteger(taiwanCredit.accounts_below_130);
  const hyOk = valueAvailable(hy, 'hy');
  const hyChangeOk = hyOk && Number.isFinite(hy.change20bp);
  const vixOk = valueAvailable(vix, 'vix');
  const ndxOk = valueAvailable(indices, 'indices', 'drawdown_pct');
  const creditFlag = (hyOk && hy.value >= 4) || (hyChangeOk && hy.change20bp >= 75);
  const volFlag = vixOk && vix.value >= 25;
  let summary = '信用、波動與價格資料需合併判讀。';
  if (creditFlag && volFlag) summary = '信用利差與股市預期波動均觸及雷達門檻。先看壓力是否延續，再看台股盤後籌碼是否同步轉弱。';
  else if (creditFlag) summary = '信用利差已觸及雷達門檻。接著觀察 VIX 及股市回撤是否同步擴大。';
  else if (volFlag) summary = 'VIX 已觸及雷達門檻。接著觀察高收益債利差是否跟著擴大。';
  else if (ndxOk && indices.drawdown_pct >= 10) summary = hyChangeOk && vixOk
    ? 'Nasdaq 100 已達回撤門檻。已取得的信用利差與 VIX 尚未觸線，個別資料日見下方。'
    : 'Nasdaq 100 已達回撤門檻。信用與波動證據仍有缺口，等待資料更新。';
  else if (hyChangeOk && vixOk && ndxOk) summary = '已取得的信用利差、VIX 與 Nasdaq 100 回撤尚未達雷達門檻。接著觀察壓力是否在多個市場同時上升。';

  const cash = inst?.official_sources?.cash_inst;
  const futures = inst?.official_sources?.futures;
  const total = cash?.categories?.find(row => row.name === '合計')?.net_twd;
  const cashOk = approved(cash, 'inst.cash_inst') && Number.isFinite(total);
  const futuresOk = valueAvailable(futures, 'inst.futures', 'foreign_tx_net_oi');
  const pos = futures?.foreign_tx_net_oi;
  const cashEvidence = cashOk ? dated(cash, '三大法人現貨' + (total >= 0 ? '買超 ' : '賣超 ') +
    num(Math.abs(total) / 1e8) + ' 億元') : '法人現貨待核對';
  const futuresEvidence = futuresOk ? dated(futures, '外資台指期' + (pos === 0 ? '淨部位 0 口' :
    (pos > 0 ? '淨多 ' : '淨空 ') + num(Math.abs(pos), 0) + ' 口')) : '外資期貨待核對';
  let flow = '現貨看單日買賣超，期貨看未平倉部位；單日部位無法判定是否加碼。';
  if (cashOk && futuresOk && cash.date === futures.date && total > 0 && pos < 0) {
    flow = '同日現貨買超與期貨淨空並存。後續可看現貨買超能否延續，以及期貨淨空是否收斂。';
  } else if (cashOk && futuresOk && cash.date === futures.date && total < 0 && pos < 0) {
    flow = '同日現貨賣超、期貨維持淨空。後續可看現貨賣超是否延續，以及淨空部位是否增加。';
  } else if (cashOk && futuresOk && cash.date !== futures.date) {
    flow = '現貨與期貨日期不同，等同日資料齊備再比較。';
  }

  const twOfficial = taiex?.official_sources?.tw_price;
  const twSameDay = taiex?.date && taiex.date === twOfficial?.date;
  const taiexOk = twSameDay && valueAvailable(taiex, 'taiex', 'drawdown_pct') &&
    twOfficial?.status === 'ok' && twOfficial.cache_status !== 'stale' && !twOfficial.last_error;
  const availableOfficial = Number.isFinite(taiex?.official_close) && taiex.official_close_date;
  const credit = [
    hyOk ? dated(hy, '高收益債利差 ' + num(hy.value) + '%' +
      (hyChangeOk ? '，20 交易日變化 ' + num(hy.change20bp) + ' bp' : '，20 交易日變化待核對')) : '高收益債利差待核對',
    valueAvailable(ig, 'ig') ? dated(ig, '投資級債利差 ' + num(ig.value) + '%') : '投資級債利差待核對'
  ];
  const cards = [
    ['信用與利差', credit.join('；'),
      '利差擴大代表市場要求更高的信用風險補償。雷達觀察高收益債利差達 4%，或 20 交易日擴大 75 bp。'],
    ['股市回撤與波動', [
      ndxOk ? dated(indices, 'Nasdaq 100 近一年高點回撤 ' + num(indices.drawdown_pct) + '%') : 'Nasdaq 100 回撤待核對',
      vixOk ? dated(vix, 'VIX ' + num(vix.value)) : 'VIX 待核對',
      availableOfficial ? '台股官方收盤 ' + num(taiex.official_close) + ' 點（' + taiex.official_close_date + '）' : '台股官方收盤待取得',
      taiexOk ? dated(taiex, '台股近一年高點回撤 ' + num(taiex.drawdown_pct) + '%') :
        (taiex?.date && !twSameDay ? '行情來源 ' + taiex.date + ' 與官方收盤日不同，台股回撤待核對' : '台股回撤待品質核對')
    ].join('；'), 'VIX 反映美股近端預期波動。接著觀察回撤擴大時，VIX 是否升至 25，信用利差是否同步走闊。'],
    ['台股現貨與期貨籌碼', cashEvidence + '；' + futuresEvidence, flow],
    ['融資與新台幣', [
      valueAvailable(margin, 'margin') && margin.unit === 'TWD'
        ? dated(margin, '上市融資餘額 ' + num(margin.value / 1e8) + ' 億元') : '融資餘額待核對',
      creditReady ? dated(maint, '全市場整戶維持率 ' + num(maint.value) + '%，低於 130% ' +
        num(taiwanCredit.accounts_below_130, 0) + ' 戶') : '全市場信用交易資料待公布或核對',
      valueAvailable(fx, 'fx') ? dated(fx, '美元兌新台幣 ' + num(fx.value, 3)) : '美元兌新台幣待核對'
    ].join('；'), '融資餘額看資金撤出規模。觀察低於 130% 的戶數與應處分金額，可進一步看信用交易壓力。匯率搭配法人現貨趨勢交叉觀察。']
  ];

  function element(tag, text, className) {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  const grid = element('div', '', 'grid');
  for (const [title, evidence, interpretation] of cards) {
    const card = element('article', '', 'card');
    card.append(element('h3', title), element('p', evidence), element('p', interpretation, 'small muted'));
    grid.append(card);
  }
  root.replaceChildren(element('p', summary), grid,
    element('p', '快照更新 ' + datetime.format(stamp) + '（台灣時間）。各指標依個別資料日解讀，各來源尚未取得的欄位以待核對標示。', 'small muted'));
};
