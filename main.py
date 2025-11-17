# main.py
from flask import Flask, render_template, request
import yfinance as yf
import requests, math, json, os
from datetime import date, timedelta

app = Flask(__name__)
RANGE_FILE = "ranges.json"

def _load_ranges():
    if os.path.exists(RANGE_FILE):
        try:
            with open(RANGE_FILE, "r") as f:
                return json.load(f)
        except: pass
    return {"weekly": {}, "monthly": {}}

def _save_ranges(data):
    tmp = RANGE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, RANGE_FILE)

def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())

def _first_of_month(d: date) -> date:
    return d.replace(day=1)

def fetch_shares_outstanding():
    try:
        url = "https://financialmodelingprep.com/api/v3/profile/MSTR?apikey=YOUR_KEY"
        return int(requests.get(url, timeout=10).json()[0]["outShares"])
    except:
        return 299800000  # Nov 2025 actual

def fetch_btc_held():
    try:
        r = requests.get("https://api.saylortracker.com/v1/companies/microstrategy", timeout=10)
        return int(r.json()["bitcoin_holdings"])
    except:
        return 641205  # Nov 17 2025

def fetch_fng():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10).json()
        d = r["data"][0]
        return {"value": d["value"], "classification": d["value_classification"]}
    except:
        return {"value": "N/A", "classification": "N/A"}

def fetch_mvrv():
    try:
        mc = requests.get("https://api.blockchain.info/charts/market-cap?format=json&timespan=1days").json()["values"][-1]["y"] * 1e6
        rc = requests.get("https://api.blockchain.info/charts/realized-cap?format=json&timespan=1days").json()["values"][-1]["y"] * 1e6
        return round(mc / rc, 3)
    except:
        return "N/A"

def _expected_move(iv, price, days):
    return price * iv * math.sqrt(days / 365)

def _avg_iv(ticker, exp):
    try:
        chain = ticker.option_chain(exp)
        ivs = [v for v in chain.calls.impliedVolatility.append(chain.puts.impliedVolatility) if 0 < v < 5]
        return sum(ivs)/len(ivs) if ivs else None
    except: return None

def _closest_expiry(days, dates):
    target = date.today().toordinal() + days
    return min(dates, key=lambda x: abs(date.fromisoformat(x).toordinal() - target))

def get_data(btc_held, shares_out, btc_future):
    btc_price = yf.Ticker("BTC-USD").history(period="1d")["Close"].iloc[-1]
    mstr = yf.Ticker("MSTR")
    price = mstr.history(period="1d")["Close"].iloc[-1]
    yesterday = mstr.history(period="2d")["Close"].iloc[-2]

    # Short-term moves
    moves = {}
    expiries = mstr.options
    if expiries:
        targets = {"1 Day": 1, "1 Week": 7, "1 Month": 30}
        for label, d in targets.items():
            exp = _closest_expiry(d, expiries)
            iv = _avg_iv(mstr, exp)
            if iv:
                days = max((date.fromisoformat(exp) - date.today()).days, 1)
                move = _expected_move(iv, yesterday, days)
                moves[label] = {"low": round(yesterday - move), "high": round(yesterday + move), "exp": exp}
            else:
                moves[label] = None

    btc_value = btc_price * btc_held
    market_cap = price * shares_out
    mnav = market_cap / btc_value

    future_value = btc_future * btc_held
    proj_25 = (future_value * 2.5) / shares_out
    proj_4 = (future_value * 4) / shares_out

    return {
        "btc_price": round(btc_price),
        "mnav": round(mnav, 2),
        "price_at_1": round(price / mnav, 2),
        "price_at_25": round(price * 2.5 / mnav, 2),
        "price_at_4": round(price * 4 / mnav, 2),
        "projected_25": round(proj_25),
        "projected_4": round(proj_4),
        "moves": moves,
        "fear_greed": fetch_fng(),
        "mvrv_z": fetch_mvrv()
    }

@app.route("/", methods=["GET", "POST"])
def index():
    defaults = {
        "btc_held": fetch_btc_held(),
        "shares_out": fetch_shares_outstanding(),
        "btc_future": 250000
    }
    result = None
    if request.method == "POST":
        btc_held = int(request.form.get("btc_held", defaults["btc_held"]))
        shares_out = int(request.form.get("shares_out", defaults["shares_out"]))
        btc_future = int(request.form.get("btc_future", defaults["btc_future"]))
        result = get_data(btc_held, shares_out, btc_future)
    return render_template("index.html", result=result, defaults=defaults)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
