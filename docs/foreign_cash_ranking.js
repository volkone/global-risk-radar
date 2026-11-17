(() => {
  const section = document.getElementById('foreign-cash-ranking');
  const status = section.querySelector('[role=status]');
  const grid = section.querySelector('.foreign-plot');
  const filter = section.querySelector('select');
  const selected = section.querySelector('.foreign-selection');
  const top = section.querySelector('.foreign-top');
  const events = section.querySelector('.foreign-events');
  const format = new Intl.NumberFormat('zh-TW');
  let data;
  const time = date => Date.parse(date);
  const label = item => '第' + item.rank + '名 ' + item.date.replaceAll('-', '');

  function fill(table, rows) {
    table.replaceChildren(...rows.map(item => {
      const row = document.createElement('tr');
      for (const value of [label(item), format.format(item.net_twd)]) {
        row.insertCell().textContent = value;
      }
      return row;
    }));
  }

  function renderEntries() {
    const rank = Number(filter.value);
    const records = data.entries.filter(item => !rank || item.rank === rank);
    const start = time(data.start_date);
    const span = time(data.end_date) - start || 1;
    const active = records.at(-1);
    selected.textContent = active ? label(active) + ' · ' + format.format(active.net_twd) + ' 元' : '這個名次目前沒有入榜記錄';
    grid.replaceChildren(...records.map(item => {
      const point = document.createElement('button');
      point.type = 'button';
      point.className = 'foreign-point';
      point.dataset.rank = item.rank;
      point.style.left = (2 + 96 * (time(item.date) - start) / span) + '%';
      point.style.top = (5 + 90 * (item.rank - 1) / 24) + '%';
      point.style.setProperty('--point-hue', (item.rank * 43) % 360);
      point.title = label(item) + ' · ' + format.format(item.net_twd) + ' 元';
      point.setAttribute('aria-label', point.title);
      point.onclick = () => { selected.textContent = point.title; };
      point.onfocus = point.onclick;
      return point;
    }));
    fill(events, records.slice().reverse());
  }

  async function load() {
    try {
      data = await getRadarData('foreign_cash_ranking.json');
      if (data.unit !== 'TWD' || !Array.isArray(data.top) || !Array.isArray(data.entries) ||
          !Number.isFinite(time(data.start_date)) || !Number.isFinite(time(data.end_date))) throw Error();
      status.textContent = data.start_date + ' 至 ' + data.end_date + '，共 ' +
        format.format(data.sessions) + ' 個交易日';
      section.querySelector('.foreign-start').textContent = data.start_date;
      section.querySelector('.foreign-end').textContent = data.end_date;
      for (let rank = 1; rank <= 25; rank++) filter.add(new Option('第 ' + rank + ' 名', rank));
      filter.disabled = false;
      filter.onchange = renderEntries;
      fill(top, data.top);
      renderEntries();
    } catch {
      status.textContent = '外資賣超排行暫時無法載入，請重新整理。';
    }
  }
  load();
})();
