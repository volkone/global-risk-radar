(() => {
  const section = document.getElementById('foreign-cash-ranking');
  const status = section.querySelector('[role=status]');
  const filter = section.querySelector('select');
  const top = section.querySelector('.foreign-top');
  const events = section.querySelector('.foreign-events');
  const previous = section.querySelector('.foreign-prev');
  const next = section.querySelector('.foreign-next');
  const counter = section.querySelector('.foreign-page');
  const format = new Intl.NumberFormat('zh-TW');
  const decimals = new Intl.NumberFormat('zh-TW', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const pageSize = 12;
  let page = 0;
  let data;
  const amount = item => decimals.format(item.net_twd / 100_000_000);

  function addCell(row, value) {
    const cell = row.insertCell();
    cell.textContent = value;
    return cell;
  }

  function renderEntries() {
    const rank = Number(filter.value);
    const records = data.entries.filter(item => !rank || item.rank === rank);
    const start = page * pageSize;
    const visible = records.slice(start, start + pageSize);
    events.replaceChildren(...visible.map(item => {
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
      return row;
    }));
    counter.textContent = visible.length
      ? '第 ' + (start + 1) + '–' + (start + visible.length) + ' 筆，共 ' + format.format(records.length) + ' 筆'
      : '這個名次目前沒有入榜記錄';
    previous.disabled = page === 0;
    next.disabled = start + pageSize >= records.length;
  }

  async function load() {
    try {
      data = await getRadarData('foreign_cash_ranking.json');
      if (data.unit !== 'TWD' || !Array.isArray(data.top) || !Array.isArray(data.entries) ||
          !data.entries.every(item => Number.isInteger(item.sessions_to_date) && item.sessions_to_date >= item.rank)) throw Error();
      status.textContent = data.start_date + ' 至 ' + data.end_date + '，共 ' +
        format.format(data.sessions) + ' 個交易日';
      for (let rank = 1; rank <= 25; rank++) filter.add(new Option('第 ' + rank + ' 名', rank));
      data.entries.reverse();
      filter.disabled = false;
      filter.onchange = () => { page = 0; renderEntries(); };
      previous.onclick = () => { page--; renderEntries(); };
      next.onclick = () => { page++; renderEntries(); };
      top.replaceChildren(...data.top.map(item => {
        const row = document.createElement('tr');
        addCell(row, '第' + item.rank + '名 ' + item.date.replaceAll('-', ''));
        addCell(row, amount(item));
        return row;
      }));
      renderEntries();
    } catch {
      status.textContent = '外資賣超排行暫時無法載入，請重新整理。';
    }
  }
  load();
})();
