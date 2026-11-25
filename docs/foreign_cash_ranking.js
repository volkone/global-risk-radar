(() => {
  const section = document.getElementById('foreign-cash-ranking');
  const status = section.querySelector('[role=status]');
  const directions = section.querySelectorAll('.foreign-direction button');
  const sellOnly = section.querySelectorAll('[data-sell-only]');
  const title = section.querySelector('.foreign-board-title');
  const filter = section.querySelector('select');
  const windowInput = section.querySelector('.foreign-window');
  const thresholdInput = section.querySelector('.foreign-threshold');
  const summary = section.querySelector('.foreign-rebound-summary');
  const top = section.querySelector('.foreign-top');
  const events = section.querySelector('.foreign-events');
  const previous = section.querySelector('.foreign-prev');
  const next = section.querySelector('.foreign-next');
  const counter = section.querySelector('.foreign-page');
  const format = new Intl.NumberFormat('zh-TW');
  const decimals = new Intl.NumberFormat('zh-TW', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const pageSize = 12;
  let page = 0;
  let buying = false;
  let data;
  const amount = ({net_twd}) => (net_twd > 0 ? '+' : '') + decimals.format(net_twd / 100_000_000);

  function addCell(row, value) {
    const cell = row.insertCell();
    cell.textContent = value;
    return cell;
  }

  function rebound(item, days, threshold) {
    if (item.rebound_window === null) return {complete: false, label: '收盤資料不足'};
    const observations = item.rebound_window.slice(0, days);
    const missing = observations.findIndex(row => row.change === null);
    const known = missing < 0 ? observations : observations.slice(0, missing);
    const index = known.findIndex(row => row.change * 10_000 >= row.previous * threshold);
    const complete = known.length === days;
    if (index >= 0) {
      const row = known[index];
      const gain = decimals.format(100 * row.change / row.previous);
      return {complete, day: index + 1, label: `已確認 · 第 ${index + 1} 日 ${row.date}（+${gain}%）`};
    }
    if (missing >= 0) {
      return {complete, label: '收盤資料不足'};
    }
    return {complete, label: complete ? '已逾期' : `等待確認 · ${known.length}/${days} 日`};
  }

  function reboundResults(records) {
    if (!windowInput.value || !thresholdInput.value ||
        !windowInput.checkValidity() || !thresholdInput.checkValidity()) {
      summary.textContent = '請輸入 1 至 20 個交易日，以及 0.01% 至 100% 的門檻。';
      return null;
    }
    const days = Number(windowInput.value);
    const threshold = Math.round(Number(thresholdInput.value) * 100);
    const results = records.map(item => rebound(item, days, threshold));
    const eligible = results.filter(result => result.complete);
    const confirmed = eligible.filter(result => result.day);
    const counts = Array.from({length: days}, (_, index) =>
      '第 ' + (index + 1) + ' 日 ' + confirmed.filter(result => result.day === index + 1).length + ' 筆');
    summary.textContent = `從入榜隔日起算，以證交所加權指數收盤較前收的漲幅判定。官方收盤資料 ${data.rebound.price_start} 至 ${data.rebound.price_end}。 ` +
      (eligible.length
        ? `完整觀察 ${eligible.length}/${records.length} 筆，${days} 日內確認 ${confirmed.length} 筆（${decimals.format(100 * confirmed.length / eligible.length)}%）。首次確認分布：${counts.join('、')}。`
        : '目前沒有完整觀察樣本。');
    return results;
  }

  function renderEntries() {
    const rank = Number(filter.value);
    const board = buying ? data.buy : data;
    const records = board.entries.filter(item => !rank || item.rank === rank);
    const results = buying ? null : reboundResults(records);
    const start = page * pageSize;
    const visible = records.slice(start, start + pageSize);
    events.replaceChildren(...visible.map((item, index) => {
      const row = document.createElement('tr');
      row.dataset.rank = item.rank;
      addCell(row, item.date);
      const rarityCell = row.insertCell();
      const percent = document.createElement('strong');
      percent.className = 'foreign-rarity';
      const proportion = 100 * item.rank / item.sessions_to_date;
      percent.textContent = proportion < 0.01 ? '前不到 0.01%' : '前 ' + decimals.format(proportion) + '%';
      const fraction = document.createElement('span');
      fraction.className = 'foreign-denominator';
      fraction.textContent = '第 ' + item.rank + ' 名／' + format.format(item.sessions_to_date) + ' 日';
      rarityCell.append(percent, fraction);
      addCell(row, amount(item));
      if (!buying) {
        addCell(row, results?.[start + index].label ?? '—').className = 'foreign-rebound-cell';
      }
      return row;
    }));
    counter.textContent = visible.length
      ? '第 ' + (start + 1) + '–' + (start + visible.length) + ' 筆，共 ' + format.format(records.length) + ' 筆'
      : '這個名次目前沒有入榜記錄';
    previous.disabled = page === 0;
    next.disabled = start + pageSize >= records.length;
  }

  function renderBoard(showBuying) {
    buying = showBuying;
    page = 0;
    for (const button of directions) {
      button.setAttribute('aria-pressed', String((button.dataset.direction === 'buy') === buying));
    }
    for (const element of sellOnly) element.hidden = buying;
    title.textContent = buying ? '買超歷史總榜' : '賣超歷史總榜';
    const board = buying ? data.buy : data;
    top.replaceChildren(...board.top.map(item => {
      const row = document.createElement('tr');
      addCell(row, '第' + item.rank + '名 ' + item.date.replaceAll('-', ''));
      addCell(row, amount(item));
      return row;
    }));
    top.closest('.foreign-scroll').scrollTop = 0;
    renderEntries();
  }

  function validRanking(board, sign) {
    const validRow = item => typeof item?.date === 'string' && Number.isInteger(item.rank) &&
      item.rank >= 1 && item.rank <= 25 && Number.isSafeInteger(item.net_twd) && item.net_twd * sign > 0;
    return Array.isArray(board?.top) && board.top.every(validRow) &&
      Array.isArray(board.entries) && board.entries.every(item =>
        validRow(item) && Number.isInteger(item.sessions_to_date) && item.sessions_to_date >= item.rank);
  }

  async function load() {
    try {
      data = await getForeignCashRanking();
      if (data.unit !== 'TWD' || !validRanking(data, -1) || !data.rebound ||
          !data.entries.every(item => item.rebound_window === null || Array.isArray(item.rebound_window))) throw Error();
      const buyReady = validRanking(data.buy, 1);
      status.textContent = data.start_date + ' 至 ' + data.end_date + '，共 ' +
        format.format(data.sessions) + ' 個交易日' + (buyReady ? '' : ' · 買超榜待更新');
      for (let rank = 1; rank <= 25; rank++) filter.add(new Option('第 ' + rank + ' 名', rank));
      data.entries.reverse();
      if (buyReady) data.buy.entries.reverse();
      for (const button of directions) {
        const showBuying = button.dataset.direction === 'buy';
        button.disabled = showBuying && !buyReady;
        button.onclick = () => renderBoard(showBuying);
      }
      filter.disabled = false;
      filter.onchange = windowInput.oninput = thresholdInput.oninput = () => { page = 0; renderEntries(); };
      previous.onclick = () => { page--; renderEntries(); };
      next.onclick = () => { page++; renderEntries(); };
      renderBoard(false);
    } catch {
      status.textContent = '外資買賣超排行暫時無法載入，請重新整理。';
    }
  }
  load();
})();
