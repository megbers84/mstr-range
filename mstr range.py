import yfinance as yf
import requests
import re
import math
from datetime import datetime, date

def prompt_override(label, current_val):
    try:
        val = input(f"{label} [{current_val}]: ").strip().replace(",", "")
        return int(val) if val else current_val
    except:
        return current_val

def closest_expiry(target_days, all_dates):
    target = date.today().toordinal() + target_days
    return min(all_dates, key=lambda d: abs(date.fromisoformat(d).toordinal() - target))

btc = yf.Ticker("BTC-USD")
btc_price = btc.history(period="1d")["Close"].iloc[-1]

btc_held = None
try:
    resp = requests.get("https://ir.microstrategy.com/bitcoin")
    match = re.search(r"MicroStrategy[^\.]{0,200}acquired[^\.]{0,200}([\d,]+)\s+bitcoins", resp.text, re.IGNORECASE)
    if match:
        btc_held = int(match.group(1).replace(",", ""))
except Exception as e:
    print(f"Error fetching BTC holdings: {e}")

if btc_held is None:
    btc_held = 628791

print("\nEnter BTC held by MSTR (or press Enter to use default)")
btc_held = prompt_override("", btc_held)
print("")

ticker = yf.Ticker("MSTR")
shares_out = ticker.info.get("sharesOutstanding", 256_473_000)
price = ticker.history(period="1d")["Close"].iloc[-1]

print("\nEnter MSTR shares outstanding (or press Enter to use default)")
shares_out = prompt_override("", shares_out)
print("")

print("\nEnter projected BTC price for future mNAV projection (or press Enter to use 250000)")
btc_future = prompt_override("", 250_000)
print("")

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

print("\n--- EXPECTED MOVE RANGES ---\n")

targets = {"1 Day": 1, "1 Week": 7, "1 Month": 30}
all_expiries = ticker.options
expiries = {label: closest_expiry(days, all_expiries) for label, days in targets.items()}

for label, exp in expiries.items():
    iv = get_avg_iv(exp)
    if iv:
        days = (date.fromisoformat(exp) - date.today()).days
        move = expected_move(iv, yesterday_close, days)
        high = yesterday_close + move
        low = yesterday_close - move
        print(f"{label} (via {exp}):\n")
        print(f"  High: ${high:.0f}")
        print(f"  Low : ${low:.0f}\n")
    else:
        print(f"{label} ({exp}): IV not available")

print("\n--- MNAV PROJECTIONS ---\n")
print(f"mNAV :                      {mnav:,.2f}")
print(f"mstr price at mnav = 2.5 :  {2.5 / mnav * price:.0f}")
print(f"mstr price at mnav = 4 :    {4 / mnav * price:.0f}")

future_btc_value = btc_future * btc_held
price_25 = (future_btc_value * 2.5) / shares_out
price_40 = (future_btc_value * 4) / shares_out

print(f"\n--- PROJECTED MSTR PRICE WITH BTC @ ${btc_future:,} ---\n")
print(f"mstr price at mnav = 2.5 :  ${price_25:.0f}")
print(f"mstr price at mnav = 4   :  ${price_40:.0f}\n")

input("Press Enter to exit...")
