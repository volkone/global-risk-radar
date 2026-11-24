/* Display each measurement on the clock and scope of its source. */
(() => {
  const root = document.getElementById('taiwan-crash-watch');
  const formatter = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Taipei', dateStyle: 'short', timeStyle: 'short', hourCycle: 'h23'
  });
  const fmt = (value, places = 2) => Number.isFinite(value)
    ? value.toLocaleString('zh-TW', {minimumFractionDigits: places, maximumFractionDigits: places}) : '—';
  const signed = (value, suffix = '%') => Number.isFinite(value)
    ? `${value > 0 ? '+' : ''}${fmt(value)}${suffix}` : '—';
  const stamp = value => Number.isFinite(Date.parse(value)) ? formatter.format(new Date(value)) : '—';

  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function link(title, path) {
    const node = el('a', title);
    const url = new URL(path, location.href);
    if (url.protocol === 'https:' || url.origin === location.origin) node.href = url.href;
    return node;
  }

  function card(title, status, level = '') {
    const node = el('article', null, 'crash-card');
    node.append(el('h3', title), el('p', status, 'crash-state ' + level));
    return node;
  }

  function facts(rows) {
    const list = el('dl', null, 'crash-facts');
    for (const [label, value] of rows) list.append(el('dt', label), valueCell('dd', value));
    return list;
  }

  function valueCell(tag, value) {
    const cell = el(tag);
    if (value instanceof Node) cell.append(value);
    else cell.textContent = value;
    return cell;
  }

  function riskReading(value, key, date) {
    const number = el('span', value);
    number.dataset.riskNumber = key;
    number.dataset.riskDate = date;
    return number;
  }

  function table(headers, rows) {
    const wrap = el('div', null, 'crash-table');
    const table = el('table');
    const head = el('thead');
    const tr = el('tr');
    for (const name of headers) {
      const th = el('th', name);
      th.scope = 'col';
      tr.append(th);
    }
    head.append(tr);
    const body = el('tbody');
    for (const row of rows) {
      const next = el('tr');
      for (const value of row) next.append(valueCell('td', value));
      body.append(next);
    }
    table.append(head, body);
    wrap.append(table);
    return wrap;
  }

  function premarket(snapshot, today, clock) {
    const signal = snapshot?.premarket;
    const current = signal?.date === today;
    const dateLabel = current ? '今日' : '上次';
    const status = {
      alert: dateLabel + '盤前符合警戒條件',
      clear: dateLabel + '盤前未達警戒條件',
      unavailable: dateLabel + '盤前資料不足'
    }[signal?.status];
    let label = status ?? '尚無盤前紀錄';
    if (!current && snapshot?.date === today) {
      if (snapshot.trading_day === false) label = '今日休市' + (status ? ' · ' + status : '');
      else if (snapshot.trading_day === null) label = '今日交易日待確認';
      else if (clock >= '09:00') label = '今日未留存盤前紀錄';
      else label = '等候今日盤前資料';
    }
    const node = card('盤前急跌警戒', label, current && signal?.status === 'alert' ? 'warn' : '');
    if (signal) {
      node.append(facts([
        ['台股前一日漲跌', signed(signal.taiwan?.prior_day_pct)],
        ['台股近 20 個交易日回撤', signed(signal.taiwan?.drawdown_20_pct)],
        ['隔夜費半', signed(signal.sox?.value)],
        ['隔夜台積電 ADR', signed(signal.tsm?.value)]
      ]), el('p', `台股資料日 ${signal.taiwan?.date || '—'} · 美股資料日（美東） ${signal.us_date || '—'} · 擷取 ${stamp(signal.captured_at)}`, 'small muted'));
      if (signal.missing?.length) node.append(el('p', '待取得 · ' + signal.missing.join('、'), 'small warn'));
    }
    node.append(el('p', '台股前一日跌達 3% 或近 20 日回撤達 8%，且隔夜費半與台積電 ADR 均跌達 2%，即符合研究警戒。', 'small muted'));
    return node;
  }

  function marketBreadth(snapshot, today, clock, now) {
    const market = snapshot?.market;
    const dated = market?.date ? ' · ' + market.date : '';
    const isLive = market?.mode === 'intraday' && market.date === today && clock >= '09:00'
      && clock <= '13:30' && now - Date.parse(market.quote_at) >= 0
      && now - Date.parse(market.quote_at) <= 30 * 60 * 1000;
    const labels = {
      close: '官方盤後' + dated,
      intraday: (isLive ? '盤中快照' : '上次盤中快照') + dated,
      unavailable: '盤中資料待取得' + dated
    };
    const node = card('盤中賣壓擴散', labels[market?.mode] ?? '尚無市場快照');
    if (!market || !['intraday', 'close'].includes(market.mode)) {
      node.append(trendBreadth(snapshot?.trend_breadth));
      return node;
    }
    if (market.mode === 'close' && snapshot?.date !== today && clock >= '09:00' && clock <= '13:30') {
      node.append(el('p', '等待今日盤中快照。下方為收盤統計。', 'small muted'));
    }
    if (market.mode === 'intraday') {
      node.append(el('p', `指數時間 ${stamp(market.quote_at)} · 家數擷取 ${stamp(market.captured_at)}`, 'small muted'));
    }
    node.append(facts([
      ['加權指數開盤缺口', signed(market.gap_pct)],
      ['加權指數漲跌', market.mode === 'close'
        ? riskReading(signed(market.taiex_pct), 'taiex-change', market.date) : signed(market.taiex_pct)],
      ['櫃買指數漲跌', signed(market.tpex_pct)],
      ['櫃買相對加權', signed(market.relative_pp, ' 個百分點')]
    ]));
    node.append(table(['市場', '下跌比例', '跌停比例'], [['上市', market.tse], ['上櫃', market.otc]].map(([label, value]) => [
      label, value?.down_pct == null ? '—' : `${fmt(value.down_pct)}%（${value.down}/${value.compared}）`,
      value?.limit_down_pct == null ? '—' : `${fmt(value.limit_down_pct)}%（${value.limit_down}/${value.compared}）`
    ])));
    if (market.mode === 'intraday') {
      const coverage = [['上市', market.tse], ['上櫃', market.otc]].map(([label, value]) =>
        `${label} ${value ? fmt(value.coverage_pct, 1) + '%（' + (value.compared ?? 0) + '/' + value.members + '）' : '待取得'}`);
      node.append(el('p', '可比股票覆蓋 · ' + coverage.join(' · ') + '。母體為交易所公司名冊的四碼股票。覆蓋低於 85% 時暫缺比例。', 'small muted'));
      if (market.breadth_source_url) node.append(link('證交所盤中報價來源', market.breadth_source_url));
    } else {
      node.append(el('p', '分母為當日上漲、下跌、持平的可比股票。跌停家數已計入下跌家數。', 'small muted'));
      for (const [label, data] of [['證交所', market.tse], ['櫃買中心', market.otc]]) {
        if (data?.source_url) node.append(link(label, data.source_url), document.createTextNode(' '));
      }
    }
    node.append(trendBreadth(snapshot?.trend_breadth));
    return node;
  }

  function trendBreadth(breadth) {
    const node = el('section', null, 'crash-subsection trend-breadth');
    node.append(el('h4', '收盤市場廣度'));
    const markets = [['上市', breadth?.markets?.tse, 'tse'], ['上櫃', breadth?.markets?.otc, 'otc']];
    if (!markets.some(([, row]) => row)) {
      node.append(el('p', '等待完整的日收盤資料。', 'small muted'));
      return node;
    }
    const reading = stat => stat ? `${fmt(stat.pct)}%` : '—';
    const coverage = stat => stat ? `${fmt(stat.above, 0)} / ${fmt(stat.eligible, 0)} 檔` : '待取得';
    node.append(table(['市場', '站上 20 日線', '站上 60 日線'], markets.map(([name, row, key]) =>
      [name, row?.date ? riskReading(reading(row.ma20), key + '-ma20', row.date) : '—', reading(row?.ma60)])));
    for (const [label, row] of markets) {
      if (!row) continue;
      const status = row.status === 'stale' ? ' · 新資料待取得' : '';
      node.append(el('p', `${label} ${row.date}${status} · 20 日 ${coverage(row.ma20)} · 60 日 ${coverage(row.ma60)}`, 'small muted'));
      if (Number.isFinite(row.ma20_change_5d_pp))
        node.append(el('p', `${label}近 5 交易日廣度變化 · 20 日線 ${signed(row.ma20_change_5d_pp, ' 個百分點')} · 60 日線 ${signed(row.ma60_change_5d_pp, ' 個百分點')}`, 'small muted'));
    }
    node.append(el('p', '普通股、未還原權息。分母為具備該期間完整收盤資料的股票。', 'small muted'),
      link('市場廣度歷史與來源', 'taiwan_market_breadth.json'));
    return node;
  }

  function creditPressure(credit) {
    const node = el('section', null, 'crash-subsection credit-pressure');
    node.append(el('h4', '全市場信用交易'));
    const amount = value => Number.isFinite(value) ? fmt(value / 1e8) + ' 億元' : '—';
    const accounts = value => Number.isInteger(value) ? fmt(value, 0) + ' 戶' : '—';
    if (!credit?.date) {
      node.append(el('p', '證交所信用交易資料待取得。', 'small muted'));
      return node;
    }
    const pending = credit.status === 'pending' ? ` · ${credit.expected_date} 待公布` :
      credit.status === 'source_error' ? ' · 上次公告值' : '';
    const transition = credit.date === '2026-11-23';
    const newRegime = credit.date >= '2026-11-24';
    node.append(el('p', `資料日 ${credit.date}${pending}`, 'small muted'),
      facts([
        ['整戶擔保維持率', fmt(credit.maintenance_pct) + '%'],
        ['整戶維持率 1 日變化', signed(credit.change_1d_pp, ' 個百分點')],
        ['整戶維持率 5 日變化', signed(credit.change_5d_pp, ' 個百分點')],
        [newRegime ? '低維持率戶數' : '低於 130% 的帳戶',
          accounts(credit.low_maintenance_accounts ?? credit.accounts_below_130)],
        [transition ? '盤後統計補繳金額' : '當日通知補繳金額', amount(credit.margin_call_twd)],
        [transition ? '原統計次日處分戶數' : '次一營業日應處分戶數', accounts(credit.disposal_accounts)],
        [transition ? '原統計次日處分金額' : '次一營業日應處分金額', amount(credit.disposal_twd)]
      ]));
    if (transition) {
      node.append(el('p', '11/24 起追繳門檻調為 120%。此前依 130% 門檻已發出的追繳紀錄取消，相關擔保品免處分。', 'small muted'),
        link('證交所追繳門檻公告', 'https://www.twse.com.tw/staticFiles/news/news/tsecnews/8a8216d6a19afd9c01a2073bb7af0594.pdf'),
        document.createTextNode(' · '));
    } else if (credit.disposal_date) {
      node.append(el('p', '應處分日（依交易日曆） ' + credit.disposal_date, 'small muted'));
    }
    if (newRegime) {
      node.append(el('p', '11/24 起追繳門檻為 120%。來源未標明低維持率戶數採用的統計門檻。', 'small muted'),
        link('證交所追繳門檻公告', 'https://www.twse.com.tw/staticFiles/news/news/tsecnews/8a8216d6a19afd9c01a2073bb7af0594.pdf'),
        document.createTextNode(' · '));
    }
    node.append(el('p', transition ? '證交所彙整上市櫃整戶信用交易。'
      : '證交所彙整上市櫃整戶信用交易。應處分為券商須處理的部位。', 'small muted'),
      link('證交所臺股儀表板', credit.source_url), document.createTextNode(' · '),
      link('全市場信用交易歷史', 'taiwan_credit_history.json'));
    return node;
  }

  function afterClose(snapshot) {
    const post = snapshot?.leverage;
    const ready = post?.cash || Number.isFinite(post?.margin_twd);
    const node = card('盤後去槓桿', ready ? '上市市場 · ' + post.date
      : (post?.date ? post.date + ' · 盤後資料待取得' : '尚無盤後資料'));
    if (!post) {
      node.append(creditPressure(snapshot?.credit));
      return node;
    }
    const amount = value => Number.isFinite(value) ? signed(value / 1e8, ' 億元') : '—';
    const balance = Number.isFinite(post.margin_twd) ? fmt(post.margin_twd / 1e8) + ' 億元' : '—';
    node.append(facts([
      ['融資餘額', balance],
      ['融資 1 日變動', signed(post.one_day_pct)],
      ['融資 5 日變動', riskReading(signed(post.five_day_pct), 'margin-five-day', post.date)],
      ['外資及陸資', riskReading(amount(post.cash?.foreign_twd), 'foreign-cash', post.date)],
      ['投信', amount(post.cash?.trust_twd)],
      ['自營商', amount(post.cash?.dealer_twd)],
      ['三大法人合計', amount(post.cash?.total_twd)]
    ]));
    if (post.prior_date) node.append(el('p', `1 日比較日 ${post.prior_date} · 5 日比較日 ${post.five_day_prior_date}`, 'small muted'));
    node.append(el('p', '融資變動使用各交易日餘額。法人為現貨買賣超，自營商含自行買賣與避險。', 'small muted'));
    if (post.margin_source_url) node.append(link('融資來源', post.margin_source_url), document.createTextNode(' '));
    if (post.cash?.source_url) node.append(link('法人來源', post.cash.source_url));
    node.append(creditPressure(snapshot?.credit));
    return node;
  }

  let validation;
  async function renderResearch() {
    const panel = root.querySelector('.crash-research');
    try {
      validation ??= window.getRadarData('taiwan_crash_watch_validation.json').catch(error => {
        validation = undefined;
        throw error;
      });
      const report = await validation;
      if (report.schema_version !== 1 || !report.blocks?.[0]?.targets || !report.case) throw Error('crash report schema');
      const results = report.blocks[0].targets;
      const rows = [];
      const lead = r => r.lead_sessions_median === 0 ? '同日 08:30 模擬'
        : Number.isFinite(r.lead_sessions_median) ? '中位數 ' + r.lead_sessions_median + ' 個交易日' : '—';
      for (const [label, target] of [['單日跌 ≥4%', results['1']], ['5 日累跌 ≥8%', results['5']]]) {
        for (const [name, group] of [['多訊號', target.multisource], ['前一日跌 ≥3%', target.baseline]]) {
          rows.push([label, name, `${group.hits}/${target.events}`, group.misses, fmt(group.false_per_month),
            lead(group)]);
        }
      }
      const example = report.case;
      panel.replaceChildren(
        el('p', `${report.period.join(' 至 ')} · 決策時間 08:30 台北。單日目標以今日收盤對前收盤計算，5 日目標從前收盤算到第 5 個交易日收盤。`, 'small muted'),
        table(['驗證目標', '規則', '命中', '漏報', '月均誤報', '命中領先'], rows),
        el('p', '領先時間計至收盤首次達到跌幅門檻。滾動 5 日樣本可能重疊，完整報告列有去重事件。', 'small muted'),
        el('p', `11/20 盤前回放 · 前一日台股 ${signed(example.taiwan.prior_day_pct)}、20 日回撤 ${signed(example.taiwan.drawdown_20_pct)}、隔夜費半 ${signed(example.sox_pct)}、台積電 ADR ${signed(example.tsm_pct)}。多訊號與基準均符合條件，當日收跌 ${fmt(Math.abs(example.change_points))} 點（${signed(example.change_pct)}）。`),
        link('完整回測與資料來源', 'taiwan_crash_watch_validation.json')
      );
      panel.dataset.status = 'loaded';
    } catch {
      panel.textContent = '歷史驗證報告暫時無法載入。';
      panel.dataset.status = 'error';
    }
  }

  async function renderBreadthResearch() {
    const panel = root.querySelector('.crash-breadth-research');
    try {
      const report = await window.getRadarData('taiwan_breadth_validation.json');
      const block = report.blocks[0];
      const rows = Object.entries(block.targets).map(([days, target]) => [
        `${days === '1' ? '單日跌' : days + ' 日累跌'} ≥${Math.abs(target.threshold_pct)}%`, target.events,
        target.rule.hits, target.combined.hits,
        `${target.rule.false_alarms} → ${target.combined.false_alarms}`
      ]);
      const rule = report.rule;
      panel.replaceChildren(
        el('p', `${block.start} 至 ${block.end} · 模擬台北 08:30 使用前一交易日可重建的收盤資料。`, 'small muted'),
        el('p', `大盤距近 ${rule.high_window} 日收盤高點在 ${rule.within_high_pct}% 以內，且 20 日廣度在 ${rule.breadth_window} 個交易日下降至少 ${Math.abs(rule.breadth_change_pp)} 個百分點，其中至少 ${rule.min_declining_days} 日轉弱。`),
        table(['目標', '事件', '現行命中', '加入廣度命中', '誤報'], rows),
        el('p', '此回測使用公開研究的上市櫃合併廣度。線上廣度使用兩交易所的個股收盤重算。', 'small muted'),
        link('完整回測與資料來源', 'taiwan_breadth_validation.json')
      );
      panel.dataset.status = 'loaded';
    } catch {
      panel.textContent = '市場廣度回測暫時無法載入。';
      panel.dataset.status = 'error';
    }
  }

  window.renderTaiwanCrashWatch = snapshot => {
    const now = new Date();
    const [today, clock] = formatter.format(now).split(' ');
    const view = root.querySelector('.crash-cards');
    const checked = root.querySelector('.crash-updated');
    if (snapshot?.schema_version !== 1) {
      checked.textContent = '';
      view.replaceChildren(el('p', '警戒快照暫時不可用，請稍後重新整理。', 'small warn'));
      return;
    }
    view.replaceChildren(premarket(snapshot, today, clock), marketBreadth(snapshot, today, clock, now),
      afterClose(snapshot));
    const stats = snapshot.request_stats;
    checked.textContent = '擷取時間（台北） ' + stamp(snapshot.checked_at)
      + (stats ? ` · 本區請求 ${stats.requests}/${stats.limit} 次` : '');
  };
  renderResearch();
  renderBreadthResearch();
  setInterval(() => {
    if (root.querySelector('.crash-research').dataset.status === 'error') renderResearch();
    if (root.querySelector('.crash-breadth-research').dataset.status === 'error') renderBreadthResearch();
  }, 60000);
})();
