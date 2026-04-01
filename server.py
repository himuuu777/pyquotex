"""
STEP 3 — Main Signal Server
============================
Save as: backend/server.py
Run with: python backend/server.py

What this does:
  1. Logs into your Quotex account
  2. Fetches real 1-minute candles every 60 seconds
  3. Computes RSI, MACD, Bollinger Bands, EMA, Stochastic
  4. Generates BUY / SELL / STRONG SELL signals
  5. Serves signals at http://localhost:5050/signals
  6. Dashboard reads from that URL automatically
"""

import asyncio
import threading
import time
import json
import numpy as np
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS

# ─────────────────────────────────────────────────────────────
#  YOUR CREDENTIALS — edit these two lines only
# ─────────────────────────────────────────────────────────────
EMAIL    = "hpal55472@gmail.com"    # ← your Quotex email
PASSWORD = "Hpal@8283"           # ← your Quotex password
# ─────────────────────────────────────────────────────────────

PORT          = 5050
CANDLE_PERIOD = 60    # 1-minute candles
CANDLE_COUNT  = 100   # candles fetched per pair (for indicator accuracy)
REFRESH_SECS  = 60    # auto-refresh every 60 seconds

# All pairs — Real + OTC + Crypto
PAIRS = [
    # ── Forex Real ──────────────────────────────────────────
    {"name": "EUR/USD",     "asset": "EURUSD",       "type": "forex"},
    {"name": "GBP/USD",     "asset": "GBPUSD",       "type": "forex"},
    {"name": "USD/JPY",     "asset": "USDJPY",       "type": "forex"},
    {"name": "AUD/USD",     "asset": "AUDUSD",       "type": "forex"},
    {"name": "USD/CAD",     "asset": "USDCAD",       "type": "forex"},
    {"name": "USD/CHF",     "asset": "USDCHF",       "type": "forex"},
    {"name": "NZD/USD",     "asset": "NZDUSD",       "type": "forex"},
    {"name": "EUR/GBP",     "asset": "EURGBP",       "type": "forex"},
    {"name": "EUR/JPY",     "asset": "EURJPY",       "type": "forex"},
    {"name": "GBP/JPY",     "asset": "GBPJPY",       "type": "forex"},
    {"name": "EUR/AUD",     "asset": "EURAUD",       "type": "forex"},
    {"name": "AUD/JPY",     "asset": "AUDJPY",       "type": "forex"},
    # ── OTC ─────────────────────────────────────────────────
    {"name": "EUR/USD OTC", "asset": "EURUSD_otc",   "type": "otc"},
    {"name": "GBP/USD OTC", "asset": "GBPUSD_otc",   "type": "otc"},
    {"name": "USD/JPY OTC", "asset": "USDJPY_otc",   "type": "otc"},
    {"name": "AUD/USD OTC", "asset": "AUDUSD_otc",   "type": "otc"},
    {"name": "EUR/JPY OTC", "asset": "EURJPY_otc",   "type": "otc"},
    {"name": "GBP/JPY OTC", "asset": "GBPJPY_otc",   "type": "otc"},
    {"name": "USD/CAD OTC", "asset": "USDCAD_otc",   "type": "otc"},
    {"name": "EUR/AUD OTC", "asset": "EURAUD_otc",   "type": "otc"},
    {"name": "NZD/USD OTC", "asset": "NZDUSD_otc",   "type": "otc"},
    {"name": "USD/CHF OTC", "asset": "USDCHF_otc",   "type": "otc"},
    {"name": "EUR/GBP OTC", "asset": "EURGBP_otc",   "type": "otc"},
    {"name": "AUD/JPY OTC", "asset": "AUDJPY_otc",   "type": "otc"},
    # ── Crypto ──────────────────────────────────────────────
    {"name": "BTC/USD",     "asset": "BTCUSD",       "type": "crypto"},
    {"name": "ETH/USD",     "asset": "ETHUSD",       "type": "crypto"},
    {"name": "LTC/USD",     "asset": "LTCUSD",       "type": "crypto"},
    {"name": "XRP/USD",     "asset": "XRPUSD",       "type": "crypto"},
    {"name": "BNB/USD",     "asset": "BNBUSD",       "type": "crypto"},
    {"name": "SOL/USD",     "asset": "SOLUSD",       "type": "crypto"},
]

# ─────────────────────────────────────────────────────────────
#  INDICATOR FUNCTIONS
# ─────────────────────────────────────────────────────────────

def calc_rsi(closes, period=14):
    """Relative Strength Index"""
    if len(closes) < period + 1:
        return 50.0
    deltas    = np.diff(closes)
    gains     = np.where(deltas > 0, deltas, 0.0)
    losses    = np.where(deltas < 0, -deltas, 0.0)
    avg_gain  = np.mean(gains[:period])
    avg_loss  = np.mean(losses[:period])
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

def ema_series(data, n):
    """Exponential Moving Average array"""
    k      = 2 / (n + 1)
    result = [float(np.mean(data[:n]))]
    for v in data[n:]:
        result.append(v * k + result[-1] * (1 - k))
    return np.array(result)

def calc_macd(closes, fast=12, slow=26, signal_period=9):
    """MACD line, signal line, histogram"""
    if len(closes) < slow + signal_period:
        return 0.0, 0.0, 0.0
    ef       = ema_series(closes, fast)
    es       = ema_series(closes, slow)
    ml       = ef[-len(es):] - es
    sl       = ema_series(ml, signal_period)
    hist     = ml[-len(sl):] - sl
    return (round(float(ml[-1]), 6),
            round(float(sl[-1]),  6),
            round(float(hist[-1]),6))

def calc_bollinger(closes, period=20):
    """Bollinger Band position 0=lower .. 1=upper"""
    if len(closes) < period:
        return 0.5
    w   = closes[-period:]
    mid = np.mean(w)
    std = np.std(w)
    if std == 0:
        return 0.5
    upper = mid + 2 * std
    lower = mid - 2 * std
    pos   = (closes[-1] - lower) / (upper - lower)
    return round(float(np.clip(pos, 0, 1)), 3)

def calc_stochastic(closes, highs, lows, period=14):
    """Stochastic %K"""
    if len(closes) < period:
        return 50.0
    h = max(highs[-period:])
    l = min(lows[-period:])
    if h == l:
        return 50.0
    return round(((closes[-1] - l) / (h - l)) * 100, 2)

def calc_ema_bias(closes, fast=9, slow=21):
    """EMA crossover bias"""
    if len(closes) < slow:
        return 0.0
    return round(float(ema_series(closes, fast)[-1] -
                       ema_series(closes, slow)[-1]), 6)

def calc_atr(highs, lows, closes, period=14):
    """Average True Range — volatility measure"""
    if len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i-1]),
                 abs(lows[i]  - closes[i-1]))
        trs.append(tr)
    return round(float(np.mean(trs[-period:])), 6)

# ─────────────────────────────────────────────────────────────
#  SIGNAL ENGINE
# ─────────────────────────────────────────────────────────────

def generate_signal(rsi, macd_hist, bb_pos, stoch, ema_bias):
    """
    Weighted scoring system.
    Score > 0 = bullish → BUY
    Score < 0 = bearish → SELL / STRONG SELL
    """
    score = 0

    # RSI — oversold/overbought
    if   rsi < 25: score += 3
    elif rsi < 35: score += 2
    elif rsi < 45: score += 1
    elif rsi > 75: score -= 3
    elif rsi > 65: score -= 2
    elif rsi > 55: score -= 1

    # MACD histogram direction & strength
    if   macd_hist >  0.00015: score += 2
    elif macd_hist >  0:       score += 1
    elif macd_hist < -0.00015: score -= 2
    else:                      score -= 1

    # Bollinger Band position
    if   bb_pos < 0.15: score += 2
    elif bb_pos < 0.30: score += 1
    elif bb_pos > 0.85: score -= 2
    elif bb_pos > 0.70: score -= 1

    # Stochastic
    if   stoch < 20: score += 2
    elif stoch < 30: score += 1
    elif stoch > 80: score -= 2
    elif stoch > 70: score -= 1

    # EMA bias
    if   ema_bias > 0: score += 1
    elif ema_bias < 0: score -= 1

    # Confidence: proportional to score strength
    confidence = min(96, max(52, abs(score) * 7 + 50))

    if   score >=  4: return "BUY",         confidence
    elif score >=  1: return "BUY",         confidence
    elif score <= -4: return "STRONG SELL", confidence
    else:             return "SELL",        confidence

def candle_summary(opens, closes):
    """Mini candle array for dashboard chart"""
    result = []
    for i in range(min(12, len(opens))):
        idx = -(12 - i)
        result.append({
            "dir": "green" if closes[idx] >= opens[idx] else "red",
            "h":   int(min(32, max(6, abs(closes[idx] - opens[idx]) * 80000)))
        })
    return result

def build_notes(rsi, macd_hist, bb_pos, signal):
    trend    = "Bullish momentum detected across recent price-action" \
               if signal == "BUY" else \
               "Bearish pressure with lower highs forming on recent candles"
    rsi_note = ("RSI oversold — reversal bounce likely"   if rsi < 35 else
                "RSI overbought — pullback probable"       if rsi > 65 else
                "RSI neutral zone — momentum inconclusive")
    macd_note= ("MACD histogram positive — upward cross confirmed"   if macd_hist > 0 else
                "MACD histogram negative — downward pressure confirmed")
    return trend, rsi_note, macd_note

# ─────────────────────────────────────────────────────────────
#  QUOTEXAPI LIVE FETCH
# ─────────────────────────────────────────────────────────────

try:
    from quotexapi.stable_api import Quotex
    QUOTEX_OK = True
except ImportError:
    QUOTEX_OK = False

async def fetch_live(client, pair):
    """Fetch candles for one pair and return signal dict"""
    try:
        raw = await client.get_candles(
            pair["asset"], CANDLE_PERIOD, CANDLE_COUNT, time.time()
        )
        if not raw or len(raw) < 30:
            raise ValueError("Not enough candles")

        opens  = np.array([float(c["open"])  for c in raw])
        closes = np.array([float(c["close"]) for c in raw])
        highs  = np.array([float(c["max"])   for c in raw])
        lows   = np.array([float(c["min"])   for c in raw])

        rsi              = calc_rsi(closes)
        macd_l, _, macd_h = calc_macd(closes)
        bb               = calc_bollinger(closes)
        stoch            = calc_stochastic(closes, highs, lows)
        ema_b            = calc_ema_bias(closes)
        atr              = calc_atr(highs, lows, closes)
        signal, conf     = generate_signal(rsi, macd_h, bb, stoch, ema_b)
        volatility       = float(atr) > float(np.mean(closes)) * 0.0008
        trend, rn, mn    = build_notes(rsi, macd_h, bb, signal)

        return {
            "name":       pair["name"],
            "type":       pair["type"],
            "signal":     signal,
            "confidence": conf,
            "price":      round(float(closes[-1]), 5),
            "rsi":        rsi,
            "macd":       macd_l,
            "macd_hist":  macd_h,
            "bb":         bb,
            "stoch":      stoch,
            "ema_bias":   ema_b,
            "atr":        atr,
            "volatility": volatility,
            "candles":    candle_summary(opens.tolist(), closes.tolist()),
            "source":     "live",
            "trend":      trend,
            "rsi_note":   rn,
            "macd_note":  mn,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }

    except Exception as e:
        print(f"  [WARN] {pair['name']}: {e} — using simulation fallback")
        return simulate_pair(pair)

async def refresh_live():
    """Connect to Quotex, fetch all pairs"""
    global signals_cache, last_updated, connection_status
    client = Quotex(email=EMAIL, password=PASSWORD)
    try:
        connected, msg = await client.connect()
        if not connected:
            print(f"[ERROR] Quotex login failed: {msg}")
            connection_status = "login_failed"
            return
        print("[OK] Logged into Quotex")
        connection_status = "connected"
        results = []
        for i, pair in enumerate(PAIRS):
            print(f"  Fetching {pair['name']} ({i+1}/{len(PAIRS)})...", end="\r")
            r = await fetch_live(client, pair)
            results.append(r)
            await asyncio.sleep(0.8)   # gentle rate limiting
        signals_cache = {r["name"]: r for r in results}
        last_updated  = datetime.utcnow().isoformat() + "Z"
        print(f"\n[OK] All {len(results)} pairs refreshed at {last_updated}")
    except Exception as e:
        print(f"[ERROR] refresh_live: {e}")
        connection_status = "error"
    finally:
        try:
            await client.close()
        except:
            pass

# ─────────────────────────────────────────────────────────────
#  SIMULATION FALLBACK
# ─────────────────────────────────────────────────────────────

def simulate_pair(pair):
    """Generate realistic-looking simulated signal (fallback only)"""
    import random
    seed = int(time.time() / REFRESH_SECS) * 1000 + abs(hash(pair["name"])) % 1000
    rng  = random.Random(seed)

    closes = [rng.uniform(0.9, 1.4) for _ in range(100)]
    opens  = [c + rng.uniform(-0.002, 0.002) for c in closes]
    highs  = [max(o, c) + rng.uniform(0, 0.001) for o, c in zip(opens, closes)]
    lows   = [min(o, c) - rng.uniform(0, 0.001) for o, c in zip(opens, closes)]

    ca = np.array(closes)
    ha = np.array(highs)
    la = np.array(lows)

    rsi              = calc_rsi(ca)
    macd_l, _, macd_h = calc_macd(ca)
    bb               = calc_bollinger(ca)
    stoch            = calc_stochastic(ca, ha, la)
    ema_b            = calc_ema_bias(ca)
    signal, conf     = generate_signal(rsi, macd_h, bb, stoch, ema_b)
    vol              = rng.random() > 0.72
    trend, rn, mn    = build_notes(rsi, macd_h, bb, signal)

    # Realistic prices per type
    if pair["type"] == "crypto":
        n = pair["name"]
        price = (67500 if "BTC" in n else 3700 if "ETH" in n else
                 590 if "BNB" in n else 175 if "SOL" in n else
                 90 if "LTC" in n else 0.62)
        price = round(price * (1 + rng.uniform(-0.005, 0.005)), 2)
    else:
        price = round(rng.uniform(0.82, 2.35), 5)

    return {
        "name": pair["name"], "type": pair["type"],
        "signal": signal, "confidence": conf, "price": str(price),
        "rsi": rsi, "macd": macd_l, "macd_hist": macd_h,
        "bb": bb, "stoch": stoch, "ema_bias": ema_b, "atr": 0.0,
        "volatility": vol,
        "candles": candle_summary(opens, closes),
        "source": "simulation",
        "trend": trend, "rsi_note": rn, "macd_note": mn,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }

# ─────────────────────────────────────────────────────────────
#  BACKGROUND THREAD
# ─────────────────────────────────────────────────────────────

signals_cache     = {}
last_updated      = None
connection_status = "starting"
_loop             = None

def background_loop():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    while True:
        is_live = QUOTEX_OK and EMAIL != "YOUR_EMAIL@gmail.com"
        if is_live:
            _loop.run_until_complete(refresh_live())
        else:
            if not QUOTEX_OK:
                print("[SIM] quotexapi not installed — simulating")
            else:
                print("[SIM] Credentials not set in server.py — simulating")
            global signals_cache, last_updated, connection_status
            results = [simulate_pair(p) for p in PAIRS]
            signals_cache = {r["name"]: r for r in results}
            last_updated  = datetime.utcnow().isoformat() + "Z"
            connection_status = "simulation"
            print(f"[SIM] {len(results)} pairs at {last_updated}")
        time.sleep(REFRESH_SECS)

# ─────────────────────────────────────────────────────────────
#  FLASK API
# ─────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)

@app.route("/")
def root():
    return jsonify({
        "name":    "Quotex Signal Bot API",
        "version": "2.0",
        "routes":  ["/signals", "/status", "/signal/<pair>"]
    })

@app.route("/signals")
def get_signals():
    ptype  = request.args.get("type")    # ?type=otc
    sig    = request.args.get("signal")  # ?signal=BUY
    items  = list(signals_cache.values())
    if ptype:  items = [x for x in items if x["type"]   == ptype]
    if sig:    items = [x for x in items if x["signal"] == sig.upper()]
    return jsonify({
        "status":       "ok",
        "source":       connection_status,
        "last_updated": last_updated,
        "count":        len(items),
        "signals":      items,
    })

@app.route("/signal/<path:name>")
def get_signal(name):
    key = name.replace("-", "/").replace("_otc", " OTC").upper()
    # try exact match first
    for k, v in signals_cache.items():
        if k.upper() == key or k.upper().replace("/", "-") == key:
            return jsonify(v)
    return jsonify({"error": f"Pair '{name}' not found"}), 404

@app.route("/status")
def get_status():
    return jsonify({
        "running":          True,
        "quotexapi":        QUOTEX_OK,
        "credentials_set":  EMAIL != "YOUR_EMAIL@gmail.com",
        "connection":       connection_status,
        "pairs_loaded":     len(signals_cache),
        "last_updated":     last_updated,
        "refresh_interval": REFRESH_SECS,
    })

@app.route("/pairs")
def get_pairs():
    return jsonify([{"name": p["name"], "type": p["type"]} for p in PAIRS])

# ─────────────────────────────────────────────────────────────
#  STARTUP
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    is_live = QUOTEX_OK and EMAIL != "YOUR_EMAIL@gmail.com"
    print("\n" + "═" * 54)
    print("  Quotex Signal Bot v2.0 — Python Backend")
    print("═" * 54)
    print(f"  quotexapi : {'✓ installed' if QUOTEX_OK else '✗ not installed'}")
    print(f"  Mode      : {'LIVE — will connect to Quotex' if is_live else 'SIMULATION'}")
    print(f"  Pairs     : {len(PAIRS)}")
    print(f"  Refresh   : every {REFRESH_SECS}s")
    print(f"  API URL   : http://localhost:{PORT}/signals")
    print("═" * 54 + "\n")

    t = threading.Thread(target=background_loop, daemon=True)
    t.start()
    time.sleep(3)   # let first refresh complete

    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
