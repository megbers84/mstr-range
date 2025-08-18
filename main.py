from flask import Flask, render_template, request
import yfinance as yf
import requests, re, math, json, os
from datetime import date, timedelta

app = Flask(__name__)
RANGE_FILE = "ranges.json"

def _load_ranges():
    if os.path.exists(RANGE_FILE):
        try:
            with open(RANGE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"weekly": {}, "monthly": {}}

def _save_ranges(data):
    tmp = RANGE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, RANGE_FILE)

def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())  # Monday anchor

def _first_of_month(d: date) -> date:
    return d.replace(day=1)

def fetch_shares_outstanding():
    try:
        url = "https://finviz.com/quote.ashx?t=MSTR"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        m = re.search(r"Shs Outstand</td><td.*?>([\d\.]+)([MB])", resp.text)
        if m:
            num = float(m.group(1)); suf = m.group(2)
            return int(num * (1_000_000 if suf == "M" else 1_000_000_000))
    except:
        pass
    return None

def fetch_btc_held():
    headers = {"User-Agent": "Mozilla/5.0"}
    # Primary: Bitbo page
    try:
        r = requests.get("https://bitbo.io/treasuries/microstrategy", headers=headers, timeout=10)
        m = re.search(r"owns\s+([\d,]+)\s+bitcoins", r.text, flags=re.I)
        if m: return int(m.group(1).replace(",", ""))
    except:
        pass
    # Fallback: BitcoinTreasuries page
    try:
        r = requests.get("https://bitcointreasuries.net/public-companies/microstrategy", headers=headers, timeout=10)
        m = re.search(r'hold\s+([\d,]+)\s*BTC', r.text, flags=re.I)
        if m: return int(m.group(1).replace(",", ""))
    except:
        pass
    return None

def fetch_fng():
    try:
        res = requests.get("https://api.alternative.me/fng/?limit=1&format=json", timeout=10)
        data = res.json().get("data", [{}])[0]
        return {"value": data.get("value"), "classification": data.get("value_classification")}
    except:
        return {"value": "N/A", "classification": "N/A"}

def fetch_mvrv():
    try:
        price = yf.Ticker("BTC-USD").history(period="1d")["Close"].iloc[-1]
        supply = 19_700_000
        market_cap = price * supply
        url = "https://community-api.coinmetrics.io/v2/assets/btc/metric-data"
        params = {"metrics": "CapRealizedUSD",
                  "start": date.today().strftime("%Y-%m-%d"),
                  "end": date.today().strftime("%Y-%m-%d"),
                  "frequency": "1d"}
        r = requests.get(url, params=params, timeout=10)
        series = r.json().get("data", {}).get("metricData", {}).get("series", [])
        if not series or not series[0] or len(series[0]) < 2:
            return "N/A"
        realized_cap = float(series[0][1])
        return round(market_cap / realized_cap, 2)
    except:
        return "N/A"

def _expected_move(iv, base_price, days):
    return base_price * iv * math.sqrt(days / 365)

def _avg_iv_for_exp(ticker, exp_str):
    try:
        chain = ticker.option_chain(exp_str)
        ivs = list(chain.calls['impliedVolatility']) + list(chain.puts['impliedVolatility'])
        ivs = [v for v in ivs if v and 0 < v < 5]
        return sum(ivs)/len(ivs) if ivs else None
    except:
        return None

def _closest_expiry(target_days, all_dates):
    tgt = date.today().toordinal() + target_days
    return min(all_dates, key=lambda d: abs(date.fromisoformat(d).toordinal() - tgt))

def _compute_range_once(kind, anchor_dt, ticker_obj, ref_price):
    """kind: 'weekly'(7d) or 'monthly'(30d)."""
    all_exp = ticker_obj.options
    if not all_exp:
        return None
    target_days = 7 if kind == "weekly" else 30
    exp = _closest_expiry(target_days, all_exp)
    iv = _avg_iv_for_exp(ticker_obj, exp)
    if not iv:
        return None
    days = max((date.fromisoformat(exp) - anchor_dt).days, 1)
    move = _expected_move(iv, ref_price, days)
    return {
        "anchor": anchor_dt.isoformat(),
        "exp": exp,
        "days": days,
        "iv": round(iv, 4),
        "low": round(ref_price - move, 2),
        "high": round(ref_price + move, 2),
        "ref_price": round(ref_price, 2)
    }

def _ensure_ranges(ticker_obj, yesterday_close):
    """Persist weekly/monthly 1σ; recompute only on Monday/1st."""
    today = date.today()
    weekly_anchor = _monday(today)
    monthly_anchor = _first_of_month(today)

    store = _load_ranges()

    if store.get("weekly", {}).get("anchor") != weekly_anchor.isoformat():
        wk = _compute_range_once("weekly", weekly_anchor, ticker_obj, yesterday_close)
        if wk: store["weekly"] = wk

    if store.get("monthly", {}).get("anchor") != monthly_anchor.isoformat():
        mo = _compute_range_once("monthly", monthly_anchor, ticker_obj, yesterday_close)
        if mo: store["monthly"] = mo

    _save_ranges(store)
    return store

def _signal(price, low, high):
    if price < low: return "BUY"
    if price > high: return "SELL"
    return ""

def get_data(btc_held, shares_out, btc_future):
    btc = yf.Ticker("BTC-USD")
    btc_price = btc.history(period="1d")["Close"].iloc[-1]

    ticker = yf.Ticker("MSTR")
    price = ticker.history(period="1d")["Close"].iloc[-1]
    hist = ticker.history(period="2d")
    yesterday_close = hist["Close"].iloc[-2]

    # Persisted 1σ ranges (weekly/monthly)
    ranges = _ensure_ranges(ticker, yesterday_close)
    wk, mo = ranges.get("weekly"), ranges.get("monthly")
    weekly_signal = _signal(price, wk["low"], wk["high"]) if wk else ""
    monthly_signal = _signal(price, mo["low"], mo["high"]) if mo else ""

    btc_value = btc_price * btc_held
    market_cap = price * shares_out
    mnav = market_cap / btc_value

    # Keep your existing short-term expected moves
    def closest_expiry(target_days, all_dates):
        return _closest_expiry(target_days, all_dates)

    def get_avg_iv(date_str):
        return _avg_iv_for_exp(ticker, date_str)

    targets = {"1 Day": 1, "1 Week": 7, "1 Month": 30}
    all_expiries = ticker.options
    expiries = {lbl: closest_expiry(days, all_expiries) for lbl, days in targets.items()} if all_expiries else {}

    moves = {}
    for label, exp in expiries.items():
        iv = get_avg_iv(exp)
        if iv:
            days = max((date.fromisoformat(exp) - date.today()).days, 1)
            move = _expected_move(iv, yesterday_close, days)
            moves[label] = {"high": round(yesterday_close + move),
                            "low": round(yesterday_close - move),
                            "exp": exp}
        else:
            moves[label] = None

    future_btc_value = btc_future * btc_held
    price_25 = (future_btc_value * 2.5) / shares_out
    price_40 = (future_btc_value * 4) / shares_out

    return {
        "mnav": round(mnav, 2),
        "price_at_1": round(1 / mnav * price),
        "price_at_25": round(2.5 / mnav * price),
        "price_at_4": round(4 / mnav * price),
        "projected_25": round(price_25),
        "projected_4": round(price_40),
        "btc_price": round(btc_price),
        "moves": moves,
        "fear_greed": fetch_fng(),
        "mvrv_z": fetch_mvrv(),
        "weekly_range": wk,
        "monthly_range": mo,
        "weekly_signal": weekly_signal,
        "monthly_signal": monthly_signal
    }

@app.route("/", methods=["GET", "POST"])
def index():
    live_shares = fetch_shares_outstanding() or 156_473_000
    live_btc = fetch_btc_held() or 628_791
    default_data = {"btc_held": live_btc, "shares_out": live_shares, "btc_future": 250000}

    result = None
    if request.method == "POST":
        btc_held = int(request.form.get("btc_held") or default_data["btc_held"])
        shares_out = int(request.form.get("shares_out") or default_data["shares_out"])
        btc_future = int(request.form.get("btc_future") or default_data["btc_future"])
        result = get_data(btc_held, shares_out, btc_future)

    return render_template("index.html", result=result, defaults=default_data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
