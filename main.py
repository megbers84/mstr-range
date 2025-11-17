# main.py – FIXED MVRV (uses CoinMetrics free API)
from flask import Flask, render_template, request
import yfinance as yf
import requests, math, json, os
from datetime import date

app = Flask(__name__)

def fetch_shares_outstanding():
    try:
        r = requests.get("https://financialmodelingprep.com/api/v3/profile/MSTR?apikey=demo", timeout=10)
        return int(r.json()[0]["outShares"])
    except:
        return 299800000

def fetch_btc_held():
    try:
        r = requests.get("https://api.saylortracker.com/v1/companies/microstrategy", timeout=10)
        return int(r.json()["bitcoin_holdings"])
    except:
        return 641205

def fetch_fng():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10).json()
        d = r["data"][0]
        return {"value": d["value"], "classification": d["value_classification"]}
    except:
        return {"value": "N/A", "classification": "N/A"}

def fetch_mvrv():
    try:
        today = date.today().isoformat()
        params = {
            "metrics": "CapMrktCurUSD,CapRealizedUSD",
            "frequency": "1d",
            "start": today,
            "end": today
        }
        r = requests.get("https://community-api.coinmetrics.io/v2/assets/btc/metric-data", params=params, timeout=10)
        data = r.json()["data"]["metricData"]["series"][0]
        if len(data) < 3: raise ValueError("Insufficient data")
        mcap = float(data[1])
        rcap = float(data[2])
        return round(mcap / rcap, 3)
    except:
        return "N/A"

def get_data(btc_held, shares_out, btc_future):
    btc_price = yf.Ticker("BTC-USD").history(period="1d")["Close"].iloc[-1]
    mstr = yf.Ticker("MSTR")
    price = mstr.history(period="1d")["Close"].iloc[-1]
    yesterday = mstr.history(period="2d")["Close"].iloc[-2]

    moves = {}
    expiries = mstr.options
    if expiries:
        targets = {"1 Day": 1, "1 Week": 7, "1 Month": 30}
        for label, days in targets.items():
            exp = min(expiries, key=lambda x: abs((date.fromisoformat(x) - date.today()).days - days))
            chain = mstr.option_chain(exp)
            ivs = chain.calls.impliedVolatility.tolist() + chain.puts.impliedVolatility.tolist()
            ivs = [iv for iv in ivs if iv > 0.01]
            iv = sum(ivs)/len(ivs) if ivs else 0
            actual_days = max((date.fromisoformat(exp) - date.today()).days, 1)
            move = yesterday * iv * math.sqrt(actual_days / 365)
            moves[label] = {
                "low": int(yesterday - move),
                "high": int(yesterday + move),
                "exp": exp
            }
    else:
        moves = {"1 Day": None, "1 Week": None, "1 Month": None}

    btc_value = btc_price * btc_held
    market_cap = price * shares_out
    mnav = market_cap / btc_value
    future_value = btc_future * btc_held
    proj_25 = (future_value * 2.5) / shares_out
    proj_4 = (future_value * 4) / shares_out

    return {
        "btc_price": int(btc_price),
        "mnav": round(mnav, 2),
        "price_at_1": int(price / mnav),
        "price_at_25": int(price * 2.5 / mnav),
        "price_at_4": int(price * 4 / mnav),
        "projected_25": int(proj_25),
        "projected_4": int(proj_4),
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
