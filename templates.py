<!DOCTYPE html>
<html>
<head>
  <title>MSTR Tool</title>
</head>
<body style="font-family:sans-serif; max-width:600px; margin:auto; padding:2em;">
  <h1>MSTR Projection Tool</h1>
  <form method="post">
    <label>BTC Held by MSTR:<br><input name="btc_held" value="{{ defaults.btc_held }}"></label><br><br>
    <label>MSTR Shares Outstanding:<br><input name="shares_out" value="{{ defaults.shares_out }}"></label><br><br>
    <label>Projected BTC Price:<br><input name="btc_future" value="{{ defaults.btc_future }}"></label><br><br>
    <button type="submit">Calculate</button>
  </form>

  {% if result %}
    <hr>
    <h2>Expected Move Ranges</h2>
    {% for label, move in result.moves.items() %}
      {% if move %}
        <b>{{ label }}</b> (via {{ move.exp }}):<br>
        High: ${{ move.high }}<br>
        Low : ${{ move.low }}<br><br>
      {% else %}
        <b>{{ label }}</b>: IV not available<br>
      {% endif %}
    {% endfor %}

    <h2>mNAV Projections</h2>
    mNAV: {{ result.mnav }}<br>
    MSTR price if mNAV = 2.5: ${{ result.price_at_25 }}<br>
    MSTR price if mNAV = 4.0: ${{ result.price_at_4 }}<br>

    <h2>Future BTC @ ${{ defaults.btc_future }}</h2>
    MSTR price @ mNAV = 2.5: ${{ result.projected_25 }}<br>
    MSTR price @ mNAV = 4.0: ${{ result.projected_4 }}<br>
  {% endif %}
</body>
</html>
