/* Explain matched observations and mark the specific numbers that triggered a rule. */
window.renderMarketAnalysis = function (snapshot, quality, ranking) {
  const root = document.getElementById('market-analysis');
  const alerts = document.getElementById('alerts');
  const signals = new Map();
  const datetime = new Intl.DateTimeFormat('zh-TW', {
    timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false
  });
  const stamp = Date.parse(snapshot?.updated_utc);
  if (!Number.isFinite(stamp) || quality?.snapshot_updated_at !== snapshot.updated_utc || !quality?.metrics) {
    root.textContent = '市場快照與品質報告尚未取得或版本不同，等待下一輪更新後再解讀。';
    renderRiskNumbers('市場異常判斷待資料核對。');
    return;
  }
  if (Date.now() - stamp > 24 * 60 * 60 * 1000) {
    root.textContent = '快照上次更新於 ' + datetime.format(stamp) + '（台灣時間），已超過 24 小時。等待更新後再解讀。';
    renderRiskNumbers('市場異常判斷待快照更新。');
    return;
  }
  const metrics = snapshot.metrics;
  const approved = (record, key) => record?.status === 'ok' && record.date &&
    record.cache_status !== 'stale' && !record.last_error && quality.metrics[key]?.quality === 'pass' &&
    quality.metrics[key].date === record.date;
  const valueAvailable = (record, key, field = 'value') => approved(record, key) && Number.isFinite(record[field]);
  const num = (n, digits = 2) => n.toLocaleString('zh-TW', {maximumFractionDigits: digits});
  const signed = value => (value > 0 ? '+' : '') + num(value);
  const dated = (record, detail) => detail + '（' + record.date + '）';
  const flag = (id, date, reading, condition, note) => {
    signals.set(id, {date, reading, condition, note});
  };
  const {hy, ig, vix, indices, taiex, margin, maint, inst, fx} = metrics;
  const taiwanCredit = snapshot.taiwan_crash_watch?.credit;
  const creditReady = valueAvailable(maint, 'maint') && taiwanCredit?.status === 'ok' &&
    maint.date === taiwanCredit.date;
  const newCreditRegime = taiwanCredit?.date >= '2026-11-24';
  const lowAccounts = taiwanCredit?.low_maintenance_accounts ?? taiwanCredit?.accounts_below_130;
  const creditCount = Number.isInteger(lowAccounts)
    ? '，' + (newCreditRegime ? '低維持率帳戶 ' : '低於 130% ') + num(lowAccounts, 0) + ' 戶' : '';
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
  if (hyOk && hy.value >= 4) flag('hy-value', hy.date, '高收益債利差 ' + num(hy.value) + '%', '達 4%',
    '信用風險溢酬偏高。觀察利差是否連續走闊，以及 VIX 是否同步升高。');
  if (hyChangeOk && hy.change20bp >= 75) flag('hy-change', hy.date,
    '高收益債利差 20 日變化 ' + signed(hy.change20bp) + ' bp', '擴大至少 75 bp',
    '信用市場重新定價速度加快。觀察投資級債利差是否同步擴大。');
  if (volFlag) flag('vix-value', vix.date, 'VIX ' + num(vix.value), '達 ' + (vix.value >= 35 ? 35 : 25),
    '美股短期預期波動偏高。觀察 VIX 能否回到 25 以下，以及高收益債利差是否繼續擴大。');
  if (ndxOk && indices.drawdown_pct >= 10) flag('indices-drawdown', indices.date,
    'Nasdaq 100 近一年高點回撤 ' + num(indices.drawdown_pct) + '%',
    '達 ' + (indices.drawdown_pct >= 20 ? 20 : 10) + '%',
    '科技股距前高仍遠。觀察那斯達克反彈時費半是否同步回升，以及波動是否下降。');
  if (taiexOk && taiex.drawdown_pct >= 5) {
    const level = [25, 20, 15, 10, 5].find(threshold => taiex.drawdown_pct >= threshold);
    flag('taiex-drawdown', taiex.date, '台股近一年高點回撤 ' + num(taiex.drawdown_pct) + '%',
      '達 ' + level + '%', '加權指數仍低於一年高點。確認上市櫃站上 20 日線的家數是否持續增加。');
  }

  const watch = snapshot.taiwan_crash_watch;
  const market = watch?.market;
  const post = watch?.leverage;
  const daily = market?.taiex_pct;
  const largeMove = twSameDay && approved(taiex, 'taiex') && market?.mode === 'close' &&
    market.date === taiex.date && Number.isFinite(daily) && Math.abs(daily) >= 4;
  if (largeMove) {
    flag('taiex-change', market.date, '加權指數單日 ' + signed(daily) + '%', '單日漲跌幅絕對值達 4%',
      daily > 0
        ? '單日大幅反彈。下一交易日用成交額與上市櫃上漲家數確認反彈能否延續。'
        : '單日急跌。下一交易日看開盤缺口、下跌家數與跌停比例是否收斂。');
  }
  const foreign = post?.cash?.foreign_twd;
  if (cashOk && post?.date === cash.date && Number.isFinite(foreign) && foreign < 0) {
    const rank = ranking?.unit === 'TWD' && ranking.end_date === cash.date && Array.isArray(ranking.top)
      ? ranking.top.find(row => row?.date === cash.date && row.net_twd === foreign &&
          Number.isInteger(row.rank) && row.rank >= 1 && row.rank <= 25)
      : null;
    const divergence = largeMove && daily >= 4 && market.date === cash.date;
    if (rank || divergence) {
      const context = futuresOk && futures.date === cash.date && pos < 0
        ? '同日外資台指期淨空 ' + num(-pos, 0) + ' 口。' : '';
      flag('foreign-cash', cash.date, '外資現貨賣超 ' + num(-foreign / 1e8) + ' 億元',
        rank ? '歷史單日賣超前 25 名 · 第 ' + rank.rank + ' 名' : '加權漲達 4% 且外資反向賣超',
        context + (divergence ? '價格與外資現貨方向背離。' : '') +
        '觀察外資賣超與期貨淨空是否同步收斂，並確認下跌家數是否減少。');
    }
  }
  const marginFiveDays = post?.five_day_pct;
  if (valueAvailable(margin, 'margin') && margin.unit === 'TWD' && post?.date === margin.date &&
      post.margin_twd === margin.value && Number.isFinite(marginFiveDays) && Math.abs(marginFiveDays) >= 10) {
    flag('margin-five-day', post.date, '上市融資餘額 5 日 ' + signed(marginFiveDays) + '%',
      '5 個交易日變動幅度達 10%',
      marginFiveDays < 0
        ? '近期槓桿部位快速縮減。觀察維持率與處分金額是否同步改善。'
        : '融資部位快速回升。觀察加權漲幅、市場廣度與整戶維持率能否同步改善。');
  }
  for (const [key, label] of [['tse', '上市'], ['otc', '上櫃']]) {
    const breadth = watch?.trend_breadth?.markets?.[key];
    const pct = breadth?.ma20?.pct;
    if (breadth?.status === 'ok' && breadth.date && breadth.date === watch.trend_breadth.expected_date &&
        Number.isFinite(pct) && pct >= 0 && pct <= 20 && breadth.ma20.eligible > 0) {
      flag(key + '-ma20', breadth.date, label + '站上 20 日線 ' + num(pct) + '%', '低於或等於 20%',
        '多數個股仍在短期均線下。觀察站回均線的家數是否連續增加。');
    }
  }
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
      creditReady ? dated(maint, '全市場整戶維持率 ' + num(maint.value) + '%' + creditCount)
        : '全市場信用交易資料待公布或核對',
      valueAvailable(fx, 'fx') ? dated(fx, '美元兌新台幣 ' + num(fx.value, 3)) : '美元兌新台幣待核對'
    ].join('；'), '融資餘額反映槓桿部位的增減。搭配整戶維持率與應處分金額判讀信用交易壓力，並用匯率交叉觀察法人現貨方向。']
  ];

  function element(tag, text, className) {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function renderRiskNumbers(fallback) {
    for (const node of document.querySelectorAll('[data-risk-number]')) {
      const signal = signals.get(node.dataset.riskNumber);
      const active = signal && signal.date === node.dataset.riskDate;
      node.classList.toggle('risk-number', Boolean(active));
      if (active) node.setAttribute('aria-describedby', 'market-risk-' + node.dataset.riskNumber);
      else node.removeAttribute('aria-describedby');
    }
    if (!signals.size) {
      alerts.textContent = fallback;
      return;
    }
    const list = element('ul', '', 'market-risk-links');
    for (const [key, signal] of signals) {
      const link = element('a', signal.reading, 'risk-number');
      link.href = '#market-risk-' + key;
      const row = element('li', '');
      row.append(link);
      list.append(row);
    }
    alerts.replaceChildren(list);
  }
  const grid = element('div', '', 'grid');
  for (const [title, evidence, interpretation] of cards) {
    const card = element('article', '', 'card');
    card.append(element('h3', title), element('p', evidence), element('p', interpretation, 'small muted'));
    grid.append(card);
  }
  const risk = element('section', '', 'market-risk');
  risk.append(element('h3', '異常數據與觀察建議'));
  if (signals.size) {
    const list = element('ul', '', 'market-risk-notes');
    for (const [key, signal] of signals) {
      const item = element('li', '');
      item.id = 'market-risk-' + key;
      item.append(element('strong', signal.reading, 'risk-number'),
        element('p', signal.date + ' · ' + signal.condition, 'small muted'),
        element('p', signal.note));
      list.append(item);
    }
    risk.append(list);
  } else {
    risk.append(element('p', '本次已核對的指標均在標示門檻內。', 'muted'));
  }
  root.replaceChildren(element('p', summary), risk, grid,
    element('p', '快照更新 ' + datetime.format(stamp) + '（台灣時間）。各指標依個別資料日解讀，各來源尚未取得的欄位以待核對標示。', 'small muted'));
  renderRiskNumbers('本次已核對的指標均在標示門檻內。');
};
