import os
import time
import requests
from datetime import datetime, timezone

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8790202401:AAFexFEwnvUyckTP2fThpZeWqX9Xt4L4ARA")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1659962664")
SYMBOL = "ETHUSD"
CHECK_INTERVAL_SECONDS = 60 

# Track the last known price to detect crosses
last_price = None

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing. Not sending:", text)
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def get_delta_candles(resolution, start_time=None):
    """Fetches historical OHLCV data from Delta Exchange."""
    url = "https://api.delta.exchange/v2/history/candles"
    params = {"symbol": SYMBOL, "resolution": resolution}
    
    if start_time:
        params["start"] = int(start_time.timestamp())
        
    try:
        response = requests.get(url, params=params, timeout=10).json()
        if response.get("success"):
            return response.get("result", [])
    except Exception as e:
        print(f"Error fetching candles: {e}")
    return []

def get_ticker_price():
    """Fetches the current real-time traded price."""
    url = f"https://api.delta.exchange/v2/tickers/{SYMBOL}"
    try:
        response = requests.get(url, timeout=10).json()
        if response.get("success") and response.get("result"):
            return float(response["result"]["close"])
    except Exception as e:
        print(f"Error fetching ticker: {e}")
    return None

def calculate_levels():
    """Calculates Daily levels and Session VWAP."""
    # 1. Get Daily Candles for Previous Day High, Low, Close
    daily_candles = get_delta_candles("1d")
    if not daily_candles or len(daily_candles) < 2:
        return None
    
    # Sort just in case; the second to last candle is the fully closed previous day
    daily_candles.sort(key=lambda x: x.get('time', 0))
    prev_day = daily_candles[-2]
    
    pdh = float(prev_day["high"])
    pdl = float(prev_day["low"])
    pdc = float(prev_day["close"])
    
    # Pivot Calculations
    pp = (pdh + pdl + pdc) / 3
    r1 = (2 * pp) - pdl
    s1 = (2 * pp) - pdh

    # 2. Calculate Session VWAP (Session starts at 00:00 UTC)
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    intraday_candles = get_delta_candles("5m", start_time=start_of_day)
    
    cumulative_tp_vol = 0.0
    cumulative_vol = 0.0
    vwap = None
    
    if intraday_candles:
        for c in intraday_candles:
            high = float(c["high"])
            low = float(c["low"])
            close = float(c["close"])
            vol = float(c.get("volume", 0))
            
            typical_price = (high + low + close) / 3
            cumulative_tp_vol += typical_price * vol
            cumulative_vol += vol
            
        if cumulative_vol > 0:
            vwap = cumulative_tp_vol / cumulative_vol

    return {
        "Daily High": pdh,
        "Daily Low": pdl,
        "Central Pivot": pp,
        "R1": r1,
        "S1": s1,
        "VWAP": vwap
    }

def check_alerts(current_price, levels):
    global last_price
    
    # Initialize last_price on the first run without firing alerts
    if last_price is None:
        last_price = current_price
        print(f"Bot initialized. Current {SYMBOL} Price: {current_price:.2f}")
        return

    for level_name, level_value in levels.items():
        if level_value is None:
            continue
            
        # Detect upward cross
        if last_price < level_value and current_price >= level_value:
            msg = f"🚀 {SYMBOL} crossed ABOVE {level_name}!\n\nPrice: {current_price:.2f}\nLevel: {level_value:.2f}"
            print(msg)
            send_telegram_message(msg)
            
        # Detect downward cross
        elif last_price > level_value and current_price <= level_value:
            msg = f"📉 {SYMBOL} crossed BELOW {level_name}!\n\nPrice: {current_price:.2f}\nLevel: {level_value:.2f}"
            print(msg)
            send_telegram_message(msg)

    # Update state
    last_price = current_price

def main():
    print("Starting Delta Exchange Alert Bot...")
    # Send a startup message to confirm it's running
    send_telegram_message("✅ Bot started. Monitoring ETHUSD levels...")
    
    while True:
        levels = calculate_levels()
        current_price = get_ticker_price()
        
        if levels and current_price:
            check_alerts(current_price, levels)
            
        # Pause before next check
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
