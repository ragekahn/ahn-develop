const $ = id => document.getElementById(id);

let chart = null;
let autoTimer = null;
const REFRESH_MS = 60_000;

function fmt(v, kr = false) {
  if (v == null) return '—';
  const opts = kr
    ? { style: 'currency', currency: 'KRW', maximumFractionDigits: 0 }
    : { style: 'currency', currency: 'USD', minimumFractionDigits: 2 };
  return new Intl.NumberFormat('en-US', opts).format(v);
}

function pctChange(bars) {
  if (bars.length < 2) return null;
  const last = bars[bars.length - 1].close;
  const prev = bars[bars.length - 2].close;
  return ((last - prev) / prev) * 100;
}

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) {
    const body = await r.json().catch(() => ({ error: r.statusText }));
    throw new Error(body.error || r.statusText);
  }
  return r.json();
}

function showError(msg) {
  const el = $('footer-status');
  el.textContent = msg;
  el.style.color = 'var(--red)';
}
function clearError() {
  const el = $('footer-status');
  el.textContent = '';
  el.style.color = '';
}
function updateHealth(ok) { $('health-dot').classList.toggle('ok', ok); }

async function loadConfig() {
  const cfg = await fetchJSON('/api/config');
  $('broker-label').textContent = `broker: ${cfg.broker}`;
  if (cfg.symbols?.length && !$('symbol-input').value) {
    $('symbol-input').value = cfg.symbols[0];
  }
  return cfg;
}

function buildChart(labels, close, smaShort, smaLong, wShort, wLong) {
  const ctx = $('price-chart').getContext('2d');
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Close', data: close, borderColor: '#58a6ff',
          backgroundColor: 'rgba(88,166,255,0.08)', fill: true,
          pointRadius: 0, borderWidth: 2, tension: 0.1 },
        { label: `SMA ${wShort}`, data: smaShort, borderColor: '#f2cc60',
          borderDash: [6, 3], pointRadius: 0, borderWidth: 1.5,
          spanGaps: false, tension: 0 },
        { label: `SMA ${wLong}`, data: smaLong, borderColor: '#bc8cff',
          borderDash: [3, 3], pointRadius: 0, borderWidth: 1.5,
          spanGaps: false, tension: 0 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#8b949e', font: { size: 11 } } },
        tooltip: {
          backgroundColor: '#161b22', titleColor: '#c9d1d9',
          bodyColor: '#c9d1d9', borderColor: '#30363d', borderWidth: 1,
        },
      },
      scales: {
        x: { ticks: { color: '#8b949e', maxTicksLimit: 15 }, grid: { color: '#21262d' } },
        y: { ticks: { color: '#8b949e' }, grid: { color: '#21262d' } },
      },
    },
  });
}

function updateStats(data) {
  const bars = data.bars;
  if (!bars.length) return;
  const last = bars[bars.length - 1].close;
  const kr = data.is_korean;
  $('stat-close').textContent = fmt(last, kr);
  const chg = pctChange(bars);
  const chgEl = $('stat-change');
  if (chg == null) { chgEl.textContent = '—'; chgEl.className = ''; }
  else {
    chgEl.textContent = `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`;
    chgEl.className = chg >= 0 ? 'up' : 'down';
  }
  const ss = data.sma_short[data.sma_short.length - 1];
  const sl = data.sma_long[data.sma_long.length - 1];
  $('stat-sma-short').textContent = ss != null ? fmt(ss, kr) : '—';
  $('stat-sma-long').textContent = sl != null ? fmt(sl, kr) : '—';
  const tag = $('market-label');
  tag.textContent = kr ? 'KRX' : 'US';
  tag.className = 'market-tag ' + (kr ? 'kr' : 'us');
}

async function loadBars() {
  const symbol = $('symbol-input').value.trim().toUpperCase();
  if (!symbol) return;
  const interval = $('interval-select').value;
  const wS = $('sma-short').value || 20;
  const wL = $('sma-long').value || 50;
  try {
    const data = await fetchJSON(
      `/api/bars?symbol=${encodeURIComponent(symbol)}&interval=${interval}` +
      `&sma_short=${wS}&sma_long=${wL}`
    );
    buildChart(
      data.bars.map(b => b.timestamp.slice(0, 10)),
      data.bars.map(b => b.close),
      data.sma_short, data.sma_long,
      data.sma_windows.short, data.sma_windows.long
    );
    updateStats(data);
    $('last-update').textContent = new Date().toLocaleTimeString();
    clearError();
  } catch (e) { showError(`bars: ${e.message}`); }
}

async function loadAccount() {
  try {
    const acct = await fetchJSON('/api/account');
    $('acct-cash').textContent = acct.cash?.toLocaleString() ?? '—';
    $('acct-equity').textContent = acct.equity?.toLocaleString() ?? '—';
    $('acct-pos-count').textContent = acct.positions?.length ?? 0;
    const tbody = document.querySelector('#positions-table tbody');
    if (!acct.positions?.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty-row">No open positions</td></tr>';
    } else {
      tbody.innerHTML = acct.positions
        .map(p => `<tr><td>${p.symbol}</td><td>${p.quantity}</td>` +
                  `<td>${p.avg_price.toLocaleString()}</td></tr>`)
        .join('');
    }
  } catch { /* broker may not expose account; safe to ignore */ }
}

function startAutoRefresh() {
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = setInterval(() => { loadBars(); loadAccount(); }, REFRESH_MS);
}
function startHealthPoll() {
  const poll = async () => {
    try { await fetchJSON('/api/health'); updateHealth(true); }
    catch { updateHealth(false); }
  };
  poll();
  setInterval(poll, 30_000);
}

async function init() {
  try { await loadConfig(); } catch { /* not critical */ }
  await loadBars();
  await loadAccount();
  startAutoRefresh();
  startHealthPoll();
  $('refresh-btn').addEventListener('click', () => { loadBars(); loadAccount(); });
  $('symbol-input').addEventListener('keydown', e => { if (e.key === 'Enter') loadBars(); });
  $('interval-select').addEventListener('change', loadBars);
  $('sma-short').addEventListener('change', loadBars);
  $('sma-long').addEventListener('change', loadBars);
}
init();
