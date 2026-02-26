from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from typing import Any
from urllib.parse import urlparse

from .journal import trade_to_dict


class DashboardState:
    def __init__(self) -> None:
        self._lock = Lock()
        self._data: dict[str, Any] = {
            "status": "idle",
            "context": {"symbol": "", "provider": "", "timeframe": ""},
            "latest_event": None,
            "metrics": {
                "equity": 0.0,
                "cash": 0.0,
                "position_open": False,
                "closed_trades": 0,
                "wins": 0,
                "losses": 0,
                "total_net_pnl": 0.0,
            },
            "recent_events": [],
            "recent_trades": [],
            "open_position": None,
            "coins": {},
        }

    def set_status(self, status: str) -> None:
        with self._lock:
            self._data["status"] = status

    def update_from_runner(self, runner, event) -> None:
        with self._lock:
            self._data["context"] = {
                "symbol": getattr(runner.config, "symbol", ""),
                "provider": getattr(runner.config, "exchange_provider", ""),
                "timeframe": getattr(runner.config, "timeframe", ""),
            }
            self._data["latest_event"] = event.__dict__.copy()
            self._data["metrics"]["equity"] = round(event.equity, 2)
            self._data["metrics"]["cash"] = round(runner.wallet.cash, 2)
            self._data["metrics"]["position_open"] = runner.wallet.position.is_open

            recent_events = self._data["recent_events"]
            recent_events.append(event.__dict__.copy())
            del recent_events[:-25]

            trades = runner.wallet.closed_trades
            wins = sum(1 for t in trades if t.net_pnl > 0)
            losses = sum(1 for t in trades if t.net_pnl <= 0)
            total_net = sum(t.net_pnl for t in trades)
            self._data["metrics"].update(
                {
                    "closed_trades": len(trades),
                    "wins": wins,
                    "losses": losses,
                    "total_net_pnl": round(total_net, 2),
                }
            )
            self._data["recent_trades"] = [trade_to_dict(t) for t in trades[-10:]]
            if runner.wallet.position.is_open:
                pos = runner.wallet.position
                mark = float(event.price)
                notional = pos.qty * pos.entry_price
                mark_value = pos.qty * mark
                self._data["open_position"] = {
                    "entry_ts": pos.entry_ts.isoformat() if pos.entry_ts else "",
                    "entry_price": pos.entry_price,
                    "mark_price": mark,
                    "qty": pos.qty,
                    "entry_notional": notional,
                    "mark_value": mark_value,
                    "unrealized_pnl": mark_value - notional,
                    "stop_loss_price": pos.stop_loss_price,
                    "take_profit_price": pos.take_profit_price,
                }
            else:
                self._data["open_position"] = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Crypto Bot Dashboard</title>
  <style>
    :root { --bg:#0b1117; --panel:#121a23; --line:#223042; --text:#e8edf3; --muted:#8ea1b5; --ok:#3ecf8e; --bad:#ff6b6b; --btc:#f7931a; --eth:#627eea; --sol:#14f195; --xrp:#346aa9; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background: radial-gradient(circle at top, #16202c, #0b1117 60%); color:var(--text); }
    .wrap { max-width:1200px; margin:0 auto; padding:20px; }
    h1 { margin:0 0 12px; font-size:20px; }
    .status { margin-bottom:15px; color:var(--muted); font-size:12px; }
    
    /* Coin Cards */
    .coins-grid { display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin-bottom:20px; }
    .coin-card { background:rgba(18,26,35,.95); border:1px solid var(--line); border-radius:12px; padding:15px; position:relative; overflow:hidden; }
    .coin-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
    .coin-card.btc::before { background:var(--btc); }
    .coin-card.eth::before { background:var(--eth); }
    .coin-card.sol::before { background:var(--sol); }
    .coin-card.xrp::before { background:var(--xrp); }
    .coin-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
    .coin-symbol { font-size:18px; font-weight:700; }
    .coin-symbol.btc { color:var(--btc); }
    .coin-symbol.eth { color:var(--eth); }
    .coin-symbol.sol { color:var(--sol); }
    .coin-symbol.xrp { color:var(--xrp); }
    .coin-signal { font-size:11px; padding:3px 8px; border-radius:4px; background:var(--line); }
    .coin-signal.buy { background:var(--ok); color:#000; }
    .coin-signal.sell { background:var(--bad); color:#fff; }
    .coin-price { font-size:28px; font-weight:700; margin:10px 0; }
    .coin-change { font-size:13px; }
    .coin-change.up { color:var(--ok); }
    .coin-change.down { color:var(--bad); }
    .coin-stats { display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin-top:12px; font-size:11px; color:var(--muted); }
    .coin-stats div { background:rgba(255,255,255,.03); padding:6px 8px; border-radius:6px; }
    .coin-stats span { color:var(--text); font-weight:600; }
    
    /* Main Grid */
    .grid { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:12px; }
    .card { background:rgba(18,26,35,.95); border:1px solid var(--line); border-radius:12px; padding:12px; }
    .label { color:var(--muted); font-size:12px; }
    .value { font-size:20px; margin-top:4px; }
    .value.ok { color: var(--ok); }
    .value.bad { color: var(--bad); }
    .row { display:grid; grid-template-columns: 1.15fr .85fr; gap:12px; margin-top:12px; }
    table { width:100%; border-collapse: collapse; font-size:12px; }
    th, td { border-bottom:1px solid var(--line); padding:8px 6px; text-align:left; }
    th { color:var(--muted); font-weight:600; }
    .trade-list { display:flex; flex-direction:column; gap:10px; margin-top:10px; max-height:560px; overflow:auto; }
    .trade-card { border:1px solid var(--line); border-radius:10px; overflow:hidden; background:#0f1620; }
    .trade-head { display:flex; justify-content:space-between; gap:8px; background:rgba(255,255,255,.03); padding:8px 10px; }
    .trade-title { font-size:12px; font-weight:700; }
    .trade-time { font-size:11px; color:var(--muted); }
    .trade-body { padding:10px; font-size:12px; line-height:1.45; }
    .trade-pnl { margin-top:8px; font-size:16px; font-weight:700; }
    .trade-pnl.ok { color: var(--ok); }
    .trade-pnl.bad { color: var(--bad); }
    .detail-lines { margin-top:8px; font-size:12px; line-height:1.5; }
    .detail-lines div { margin:2px 0; }
    @media (max-width: 900px) { .coins-grid { grid-template-columns: repeat(2, 1fr); } .grid { grid-template-columns: repeat(2, 1fr); } .row { grid-template-columns: 1fr; } }
    @media (max-width: 600px) { .coins-grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<div class="wrap">
  <h1>Crypto Bot Dashboard - Multi Coin</h1>
  <div class="status" id="status">loading...</div>
  
  <!-- 4 Coin Cards -->
  <div class="coins-grid" id="coins">
    <div class="coin-card btc">
      <div class="coin-header">
        <span class="coin-symbol btc">BTC</span>
        <span class="coin-signal" id="btc-signal">-</span>
      </div>
      <div class="coin-price" id="btc-price">-</div>
      <div class="coin-change" id="btc-change">-</div>
      <div class="coin-stats">
        <div>Equity: <span id="btc-equity">-</span></div>
        <div>Trades: <span id="btc-trades">-</span></div>
      </div>
    </div>
    <div class="coin-card eth">
      <div class="coin-header">
        <span class="coin-symbol eth">ETH</span>
        <span class="coin-signal" id="eth-signal">-</span>
      </div>
      <div class="coin-price" id="eth-price">-</div>
      <div class="coin-change" id="eth-change">-</div>
      <div class="coin-stats">
        <div>Equity: <span id="eth-equity">-</span></div>
        <div>Trades: <span id="eth-trades">-</span></div>
      </div>
    </div>
    <div class="coin-card sol">
      <div class="coin-header">
        <span class="coin-symbol sol">SOL</span>
        <span class="coin-signal" id="sol-signal">-</span>
      </div>
      <div class="coin-price" id="sol-price">-</div>
      <div class="coin-change" id="sol-change">-</div>
      <div class="coin-stats">
        <div>Equity: <span id="sol-equity">-</span></div>
        <div>Trades: <span id="sol-trades">-</span></div>
      </div>
    </div>
    <div class="coin-card xrp">
      <div class="coin-header">
        <span class="coin-symbol xrp">XRP</span>
        <span class="coin-signal" id="xrp-signal">-</span>
      </div>
      <div class="coin-price" id="xrp-price">-</div>
      <div class="coin-change" id="xrp-change">-</div>
      <div class="coin-stats">
        <div>Equity: <span id="xrp-equity">-</span></div>
        <div>Trades: <span id="xrp-trades">-</span></div>
      </div>
    </div>
  </div>
  
  <div class="grid" id="cards"></div>
  <div class="card" id="openpos" style="margin-top:12px;"></div>
  <div class="row">
    <div class="card">
      <div class="label">Recent Actions (BUY/SELL)</div>
      <table><thead><tr><th>Time</th><th>Price</th><th>Signal</th><th>Equity</th><th>Note</th></tr></thead><tbody id="events"></tbody></table>
    </div>
    <div class="card">
      <div class="label">Recent Trades (Detailed)</div>
      <div id="trades" class="trade-list"></div>
    </div>
  </div>
</div>
<script>
const coinSymbols = ['btc', 'eth', 'sol', 'xrp'];
const coinNames = {btc:'BTC', eth:'ETH', sol:'SOL', xrp:'XRP'};

function parseBotTs(ts) {
  if (!ts) return null;
  const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(ts) ? ts : `${ts}Z`;
  const d = new Date(normalized);
  return isNaN(d.getTime()) ? null : d;
}
function fmtN(v, digits=2) {
  const n = Number(v || 0);
  return Number.isFinite(n) ? n.toFixed(digits) : '-';
}
function fmtTime(ts) {
  if (!ts) return '-';
  const d = parseBotTs(ts);
  return d ? d.toLocaleString() : ts;
}
function fmtTimeWithUtc(ts) {
  if (!ts) return '-';
  const d = parseBotTs(ts);
  if (!d) return ts;
  return `${d.toLocaleString()} (UTC ${ts.replace('T', ' ').slice(0,16)})`;
}
function holdingTime(entryTs, exitTs) {
  const a = parseBotTs(entryTs), b = parseBotTs(exitTs);
  if (!a || !b) return '-';
  let mins = Math.max(0, Math.round((b - a) / 60000));
  const d = Math.floor(mins / 1440); mins -= d * 1440;
  const h = Math.floor(mins / 60); mins -= h * 60;
  const parts = [];
  if (d) parts.push(`${d}d`);
  if (h) parts.push(`${h}h`);
  parts.push(`${mins}m`);
  return parts.join(' ');
}

async function poll() {
  const res = await fetch('/api/state');
  const data = await res.json();
  
  document.getElementById('status').textContent = `status=${data.status} | latest=${data.latest_event ? fmtTimeWithUtc(data.latest_event.ts) : '-'}${data.context && data.context.symbol ? ' | ' + data.context.symbol : ''}`;
  
  // Update coins
  const coins = data.coins || {};
  coinSymbols.forEach(sym => {
    const coin = coins[sym.toUpperCase()] || {};
    const priceEl = document.getElementById(`${sym}-price`);
    const signalEl = document.getElementById(`${sym}-signal`);
    const changeEl = document.getElementById(`${sym}-change`);
    const equityEl = document.getElementById(`${sym}-equity`);
    const tradesEl = document.getElementById(`${sym}-trades`);
    
    if (priceEl) priceEl.textContent = coin.price ? `$${Number(coin.price).toLocaleString()}` : '-';
    if (signalEl) {
      signalEl.textContent = coin.signal || '-';
      signalEl.className = 'coin-signal ' + (coin.signal || '').toLowerCase();
    }
    if (changeEl) {
      const change = coin.change || 0;
      changeEl.textContent = change >= 0 ? `+${fmtN(change)}%` : `${fmtN(change)}%`;
      changeEl.className = 'coin-change ' + (change >= 0 ? 'up' : 'down');
    }
    if (equityEl) equityEl.textContent = coin.equity ? fmtN(coin.equity) : '-';
    if (tradesEl) tradesEl.textContent = coin.trades || '0';
  });
  
  // Main metrics
  const m = data.metrics;
  const cards = [
    ['Equity', m.equity],
    ['Cash', m.cash],
    ['Closed Trades', m.closed_trades],
    ['Wins / Losses', `${m.wins} / ${m.losses}`],
    ['Position Open', String(m.position_open)],
    ['Total Net PnL', m.total_net_pnl],
  ];
  document.getElementById('cards').innerHTML = cards.map(([k,v]) => `<div class="card"><div class="label">${k}</div><div class="value ${(k==='Total Net PnL' && Number(v)>=0)?'ok':''} ${(k==='Total Net PnL' && Number(v)<0)?'bad':''}">${v}</div></div>`).join('');
  
  // Open position
  const op = data.open_position;
  if (op) {
    const upnl = Number(op.unrealized_pnl || 0);
    const upnlClass = upnl >= 0 ? 'ok' : 'bad';
    document.getElementById('openpos').innerHTML = `
      <div class="label">Open Position (Detailed)</div>
      <div class="detail-lines">
        <div>Entry time: ${fmtTime(op.entry_ts)}</div>
        <div>Entry price: ${fmtN(op.entry_price)} | Mark price: ${fmtN(op.mark_price)}</div>
        <div>Quantity: ${fmtN(op.qty, 6)}</div>
        <div>Notional: ${fmtN(op.entry_notional)} → ${fmtN(op.mark_value)}</div>
        <div>Stop / Take: ${fmtN(op.stop_loss_price)} / ${fmtN(op.take_profit_price)}</div>
        <div class="trade-pnl ${upnlClass}">UNREALIZED P&L: ${upnl >= 0 ? '+' : ''}${fmtN(upnl)}</div>
      </div>`;
  } else {
    document.getElementById('openpos').innerHTML = `<div class="label">Open Position (Detailed)</div><div class="detail-lines"><div>No open position.</div></div>`;
  }
  
  // Events
  const actionEvents = (data.recent_events || []).filter(e => e.signal !== 'HOLD');
  document.getElementById('events').innerHTML = actionEvents.length
    ? actionEvents.slice().reverse().map(e => `<tr><td>${fmtTime(e.ts)}</td><td>${Number(e.price).toFixed(2)}</td><td>${e.signal}</td><td>${Number(e.equity).toFixed(2)}</td><td>${e.note || ''}</td></tr>`).join('')
    : `<tr><td colspan="5" style="color:#8ea1b5;">Henüz BUY/SELL yok (sinyal bekleniyor).</td></tr>`;
  
  // Trades
  const symbol = (data.context && data.context.symbol) ? data.context.symbol : 'ASSET';
  document.getElementById('trades').innerHTML = (data.recent_trades || []).slice().reverse().map(t => {
    const qty = Number(t.qty || 0);
    const entry = Number(t.entry_price || 0);
    const exit = Number(t.exit_price || 0);
    const entryNotional = entry * qty;
    const exitNotional = exit * qty;
    const pnl = Number(t.net_pnl || 0);
    const grossPnl = Number(t.gross_pnl || 0);
    const entryFee = Number(t.entry_fee ?? 0);
    const exitFee = Number(t.exit_fee ?? 0);
    const totalFees = Number(t.fees ?? 0);
    const retPct = entryNotional > 0 ? (pnl / entryNotional) * 100 : 0;
    const pnlClass = pnl >= 0 ? 'ok' : 'bad';
    return `<div class="trade-card">
      <div class="trade-head">
        <div class="trade-title">Paper trade on ${symbol}</div>
        <div class="trade-time">${fmtTime(t.exit_ts)}</div>
      </div>
      <div class="trade-body">
        <div>Price: ${fmtN(entry)} → ${fmtN(exit)}</div>
        <div>Quantity: ${fmtN(qty, 6)}</div>
        <div>Notional: ${fmtN(entryNotional)} → ${fmtN(exitNotional)}</div>
        <div>Holding time: ${holdingTime(t.entry_ts, t.exit_ts)}</div>
        <div>Gross P&L: ${fmtN(grossPnl)}</div>
        <div>Fees: buy ${fmtN(entryFee)} + sell ${fmtN(exitFee)} = total ${fmtN(totalFees)}</div>
        <div>Exit reason: ${t.exit_reason || '-'}</div>
        <div>Return: ${retPct >= 0 ? '+' : ''}${fmtN(retPct)}%</div>
        <div class="trade-pnl ${pnlClass}">NET P&L: ${pnl >= 0 ? '+' : ''}${fmtN(pnl)}</div>
      </div>
    </div>`;
  }).join('');
}
poll(); setInterval(poll, 1000);
</script>
</body>
</html>"""


def make_handler(state: DashboardState):
    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/state":
                self._send_json(state.snapshot())
                return
            if path == "/":
                body = DASHBOARD_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self._send_json({"error": "not found"}, status=404)

        def log_message(self, fmt: str, *args) -> None:  # silence
            return

    return Handler


class DashboardServer:
    def __init__(self, host: str, port: int, state: DashboardState) -> None:
        self.host = host
        self.port = port
        self.state = state
        self.httpd = ThreadingHTTPServer((host, port), make_handler(state))
        self.thread: Thread | None = None

    def start(self) -> None:
        self.thread = Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        try:
            self.httpd.shutdown()
        except KeyboardInterrupt:
            pass
        finally:
            self.httpd.server_close()
            if self.thread:
                try:
                    self.thread.join(timeout=2)
                except KeyboardInterrupt:
                    pass
