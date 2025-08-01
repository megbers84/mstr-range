from flask import Flask, render_template, request
import yfinance as yf
import requests
import re
import math
from datetime import datetime, date

app = Flask(__name__)

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
            days = (date.fromisoformat(exp) - date.today()).days
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
        "price_at_25": round(2.5 / mnav * price),
        "price_at_4": round(4 / mnav * price),
        "projected_25": round(price_25),
        "projected_4": round(price_40),
        "btc_price": round(btc_price),
        "moves": moves
    }

@app.route("/", methods=["GET", "POST"])
def index():
    default_data = {"btc_held": 628791, "shares_out": 156473000, "btc_future": 250000}
    result = None

    if request.method == "POST":
        btc_held = int(request.form.get("btc_held", default_data["btc_held"]))
        shares_out = int(request.form.get("shares_out", default_data["shares_out"]))
        btc_future = int(request.form.get("btc_future", default_data["btc_future"]))
        result = get_data(btc_held, shares_out, btc_future)

    return render_template("index.html", result=result, defaults=default_data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=81)
