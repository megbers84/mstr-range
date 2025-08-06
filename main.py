from flask import Flask, render_template, request
import yfinance as yf
import requests
import re
import math
from datetime import date
import os

app = Flask(__name__)

def fetch_shares_outstanding():
    try:
        url = "https://finviz.com/quote.ashx?t=MSTR"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers)
        match = re.search(r"Shs Outstand</td><td.*?>([\d\.]+)([MB])", resp.text)
        if match:
            num = float(match.group(1))
            suffix = match.group(2)
            return int(num * (1_000_000 if suffix == "M" else 1_000_000_000))
    except:
        return None

def fetch_fng():
    try:
        res = requests.get("https://api.alternative.me/fng/?limit=1&format=json")
        data = res.json().get("data", [{}])[0]
        return {
            "value": data.get("value"),
            "classification": data.get("value_classification")
        }
    except:
        return {"value": "N/A", "classification": "N/A"}

def fetch_mvrv():
    try:
        price = yf.Ticker("BTC-USD").history(period="1d")["Close"].iloc[-1]
        supply = 19_700_000
        market_cap = price * supply

        url = "https://community-api.coinmetrics.io/v2/assets/btc/metric-data"
        params = {
            "metrics": "CapRealizedUSD",
            "start": date.today().strftime("%Y-%m-%d"),
            "end": date.today().strftime("%Y-%m-%d"),
            "frequency": "1d"
        }
        r = requests.get(url, params=params)
        values = r.json().get("data", {}).get("metricData", {}).get("series", [])
        if not values or not values[0] or len(values[0]) < 2:
            return "N/A"

        realized_cap = float(values[0][1])
        return round(market_cap / realized_cap, 2)
    except:
        return "N/A"

def get_data(btc_held, shares_out, btc_future):
    btc = yf.Ticker("BTC-USD")
    btc_price = btc.history(period="1d")["Close"].iloc[-1]
    ticker = yf.Ticker("MSTR")
    price = ticker.history(period="1d")["Close"].iloc[-1]
    hist = ticker.history(period="2d")
    yesterday_close = hist["Close"].iloc[-2]
    btc_value = btc_price * btc_held
    market_cap = price * shares_out
    mnav = market_cap / btc_value

    def expected_move(iv, base_price, days):
        return base_price * iv * math.sqrt(days / 365)

    def get_avg_iv(date_str):
        try:
            chain = ticker.option_chain(date_str)
            ivs = list(chain.calls['impliedVolatility']) + list(chain.puts['impliedVolatility'])
            ivs = [v for v in ivs if v and 0 < v < 5]
            return sum(ivs) / len(ivs) if ivs else None
        except:
            return None

    def closest_expiry(target_days, all_dates):
        target = date.today().toordinal() + target_days
        return min(all_dates, key=lambda d: abs(date.fromisoformat(d).toordinal() - target))

    targets = {"1 Day": 1, "1 Week": 7, "1 Month": 30}
    all_expiries = ticker.options
    expiries = {label: closest_expiry(days, all_expiries) for label, days in targets.items()}

    moves = {}
    for label, exp in expiries.items():
        iv = get_avg_iv(exp)
        if iv:
            days = max((date.fromisoformat(exp) - date.today()).days, 1)
            move = expected_move(iv, yesterday_close, days)
            high = yesterday_close + move
            low = yesterday_close - move
            moves[label] = {"high": round(high), "low": round(low), "exp": exp}
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
        "mvrv_z": fetch_mvrv()
    }

@app.route("/", methods=["GET", "POST"])
def index():
    live_shares = fetch_shares_outstanding() or 156_473_000
    default_data = {
        "btc_held": 628791,
        "shares_out": live_shares,
        "btc_future": 250000
    }
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
