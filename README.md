# Crypto Bot MVP (Python)

Sifir butce ile baslamak icin hazirlanan bir `paper trading` bot iskeleti.

## Neler var?
- Basit SMA crossover stratejisi
- Risk yonetimi (islem basina risk, gunluk zarar limiti)
- Stop-loss / take-profit cikis kurallari
- Paper wallet (spot mantigi, fee destekli)
- Paper/Live order executor switch (live modu guvenli stub)
- CSV uzerinden backtest/simulasyon
- Ornek veri uretici
- Trade journal JSONL export
- Opsiyonel Groq log analizi (trade kararindan bagimsiz)
- `.env` + `config/default.json` + `run_bot.py` CLI
- Binance/Bybit testnet live executor (dry-run default)
- Realtime paper replay runner (WebSocket-ready mimari)
- Public WebSocket market data client (Binance/Bybit, `websocket-client` ile)
- Localhost dashboard (`http.server`)

## Hedef
Ilk hedef kar degil; botun **dogru ve guvenli** calismasini test etmek.

## Kurulum
Python 3.10+ yeterli. Dis bagimlilik yok.

## Calistirma
1. Ornek veri uret:
```bash
python3 scripts/generate_sample_data.py
```

2. Backtest calistir:
```bash
python3 scripts/run_backtest.py
```

3. Live mimari demo (gercek emir gondermez):
```bash
python3 scripts/run_live_stub.py
```

4. Trade log analizi (Groq API key varsa Groq, yoksa local fallback):
```bash
export GROQ_API_KEY=your_key_here
python3 scripts/analyze_trade_logs.py
```

## Yeni Tek Komut CLI (onerilen)
Ortak argumanlari subcommand'den once ver:

```bash
# backtest
python3 scripts/run_bot.py backtest

# realtime paper replay (CSV stream simulasyonu)
python3 scripts/run_bot.py realtime --max-steps 140 --only-actions

# Binance/Bybit testnet live executor demo (gercek emir yok, dry-run)
python3 scripts/run_bot.py --exchange-provider bybit --mode live --dry-run-live live-demo

# trade log analizi (Groq key varsa API, yoksa local fallback)
python3 scripts/run_bot.py analyze
```

## Localhost Dashboard (Yeni)
Replay ile dashboard'i doldurur:

```bash
python3 scripts/run_dashboard.py --port 8765 --speed 0.02 --max-steps 220 --hold-seconds 30
```

Ac:
- `http://127.0.0.1:8765`
- `http://127.0.0.1:8765/api/state`

## Gercek Public WebSocket + Paper Bot (Yeni)
Bu script public market data websocket'ine baglanir ve kapaniş candle'larda paper botu calistirir.

```bash
pip install websocket-client
python3 scripts/run_ws_paper.py --provider binance --symbol BTCUSDT --interval 5m --only-actions
```

Bybit icin:
```bash
python3 scripts/run_ws_paper.py --provider bybit --symbol BTCUSDT --interval 5m --testnet --only-actions
```

## Gercek Public WS + Local Dashboard (Yeni)
Gercek market data, paper trading, localhost dashboard.

```bash
pip install websocket-client
python3 scripts/run_ws_dashboard.py --provider binance --symbol BTCUSDT --interval 5m --mainnet --port 8765 --only-actions
```

Not: Script acilista REST ile `--warmup-candles` (varsayilan 50) gecmis mumu yukler, sonra WS'ye gecer. Bu sayede 4h/1h gibi timeframe'lerde uzun isınma beklemezsin.

Bybit testnet public stream:
```bash
python3 scripts/run_ws_dashboard.py --provider bybit --symbol BTCUSDT --interval 5m --testnet --port 8765 --only-actions
```

Varsayilan trade log birikimi:
- `logs/ws_paper_trades.jsonl`

100+ islem performans raporu:
```bash
python3 scripts/report_trades.py --log-file logs/ws_paper_trades.jsonl --min-trades 100
```

## Konfigurasyon
- `config/default.json`: strateji/risk/mode ayarlari
- `config/fast-demo.json`: daha hizli sinyal ureten demo preset
- `config/profitability-test.json`: churn azaltan, maliyet-farkini daha iyi test eden preset
- `.env`: API key/secret (kod disinda)
- `.env.example`: ornek dosya

## Testnet / Live Guardrail
Preflight kontrol:
```bash
python3 scripts/run_bot.py --config config/default.json preflight
```

Testnet dry-run demo (guvenli):
```bash
python3 scripts/run_bot.py --mode live --exchange-provider binance --exchange-testnet --dry-run-live live-demo
```

Testnet gercek emir gonderme (API key/secret gerekir):
```bash
python3 scripts/run_bot.py --mode live --exchange-provider binance --exchange-testnet --no-dry-run-live live-demo --allow-send-orders --demo-qty 0.001 --max-demo-notional 200
```

Mainnet gercek emir icin ekstra guardrail:
- `--allow-mainnet-live` zorunlu

## GitHub + Render Deploy (Paper + Dashboard)
Bu proje `GitHub Pages` ile degil, `Render Web Service` ile yayinlanir (Python process + WebSocket gerekiyor).

Eklenen deploy dosyalari:
- `requirements.txt`
- `render.yaml`
- `.gitignore`

Onerilen akış:
1. `crypto-bot-mvp` klasorunu ayri bir GitHub repo olarak push et
2. Render'da `New +` -> `Blueprint` (veya Web Service) sec
3. Repo'yu bagla, `render.yaml` algilansin
4. Deploy et

Varsayilan Render start command (profitability test paper mode):
```bash
python3 scripts/run_ws_dashboard.py --config config/profitability-test.json --provider binance --symbol BTCUSDT --interval 1m --mainnet --host 0.0.0.0 --port $PORT --only-actions --log-file logs/profitability-test.jsonl
```

Notlar:
- `free` plan uyuyabilir; 7/24 izleme icin ucretli plan daha iyi
- `logs/*.jsonl` cloud'da kalici degildir (restart/deploy sonrasi sifirlanabilir)
- Kalici raporlama icin sonraki adim DB/kalici disk olmalidir

## Sonraki Adimlar
- Gercek borsa adapteri (sadece market data/order wrapper)
- Gercek borsa adapteri (Binance/Bybit REST+WS)
- WebSocket market data
- Binance/Bybit gerçek WebSocket client baglantisi (simdi replay + WS-ready runner var)
- Realtime dashboard'a websocket stream entegrasyonu (simdi replay dashboard var)
- JSON loglama ve dashboard
- Gercek paper/live switch + env config
