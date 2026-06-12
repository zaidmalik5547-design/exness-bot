import os
import requests
import telebot
import time
import threading
from flask import Flask

TELEGRAM_TOKEN = "8739441280:AAFfEGVFsbs1ILsdTLJy9bMo62YaT6HwYiE"
bot = telebot.TeleBot(TELEGRAM_TOKEN)

USER_CHAT_ID = None
COINS_TO_SCAN = ["BTC", "ETH", "PAXG", "EUR", "GBP"]
last_signals = {coin: "HOLD" for coin in COINS_TO_SCAN}
active_trades = {} 

HEADERS = {'User-Agent': 'Mozilla/5.0'}

# --- 🟢 KEEP-ALIVE SERVER (Render Port Fix) 🟢 ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Faisal's Pro Trading Bot is Running 24/7 on Cloud!"

def run_server():
    # Render apna port khud batayega ab
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- INDICATORS FORMULAS ---
def calculate_rsi(prices, period=14):
    gains, losses = [], []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0: gains.append(change); losses.append(0)
        else: gains.append(0); losses.append(abs(change))
    avg_gain = sum(gains[-period:]) / period if gains else 0
    avg_loss = sum(losses[-period:]) / period if losses else 0
    if avg_loss == 0: return 100
    return 100 - (100 / (1 + (avg_gain / avg_loss)))

def calculate_ema(prices, period=20):
    k = 2 / (period + 1)
    ema = prices[0]
    for p in prices[1:]: ema = p * k + ema * (1 - k)
    return ema

def calculate_macd(prices):
    def get_ema_array(data, period):
        k = 2 / (period + 1)
        emas = [data[0]]
        for p in data[1:]: emas.append(p * k + emas[-1] * (1 - k))
        return emas
    ema12 = get_ema_array(prices, 12)
    ema26 = get_ema_array(prices, 26)
    macd_line = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    signal_line = get_ema_array(macd_line, 9)
    return macd_line[-1], signal_line[-1]

def check_volume_spike(klines, period=20):
    volumes = [float(candle[5]) for candle in klines]
    current_volume = volumes[-1]
    avg_volume = sum(volumes[-period-1:-1]) / period if period else 1
    return current_volume > (avg_volume * 1.2)

def calculate_atr(klines, period=14):
    true_ranges = []
    for i in range(1, len(klines)):
        high, low, prev_close = float(klines[i][2]), float(klines[i][3]), float(klines[i-1][4])
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(true_ranges[-period:]) / period if true_ranges else 0

# --- BACKGROUND SCANNER ---
def scan_market():
    global USER_CHAT_ID
    while True:
        if USER_CHAT_ID is not None:
            print("\n⚡ Exness Pro-Scan Shuru Ho Raha Hai ⚡")
            for coin in COINS_TO_SCAN:
                try:
                    symbol = coin + "USDT"
                    
                    price_resp = requests.get(f"https://data-api.binance.vision/api/v3/ticker/price?symbol={symbol}", headers=HEADERS, timeout=10).json()
                    if 'price' not in price_resp: continue
                    live_price = float(price_resp['price'])
                    
                    if coin == "PAXG": display_name = "GOLD (XAUUSD)"
                    elif coin == "EUR": display_name = "FOREX (EURUSD)"
                    elif coin == "GBP": display_name = "FOREX (GBPUSD)"
                    else: display_name = coin

                    if coin in active_trades:
                        trade = active_trades[coin]
                        if trade['type'] == 'BUY':
                            if live_price >= trade['tp']:
                                bot.send_message(USER_CHAT_ID, f"🎉 **TARGET HIT!** 🎉\n\n{display_name} ne Take Profit (TP) hit kar diya hai!\nExit Price: `${live_price}`\n\nProfits enjoy karein! 💸")
                                del active_trades[coin]
                                last_signals[coin] = "HOLD"
                            elif live_price <= trade['sl']:
                                bot.send_message(USER_CHAT_ID, f"⚠️ **STOP LOSS HIT** ⚠️\n\n{display_name} ne Stop Loss hit kar diya hai.\nExit Price: `${live_price}`")
                                del active_trades[coin]
                                last_signals[coin] = "HOLD"
                        elif trade['type'] == 'SELL':
                            if live_price <= trade['tp']:
                                bot.send_message(USER_CHAT_ID, f"🎉 **TARGET HIT!** 🎉\n\n{display_name} ne Take Profit (TP) hit kar diya hai!\nExit Price: `${live_price}`\n\nProfits enjoy karein! 💸")
                                del active_trades[coin]
                                last_signals[coin] = "HOLD"
                            elif live_price >= trade['sl']:
                                bot.send_message(USER_CHAT_ID, f"⚠️ **STOP LOSS HIT** ⚠️\n\n{display_name} ne Stop Loss hit kar diya hai.\nExit Price: `${live_price}`")
                                del active_trades[coin]
                                last_signals[coin] = "HOLD"
                    
                    klines = requests.get(f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval=4h&limit=50", headers=HEADERS, timeout=10).json()
                    if isinstance(klines, dict) and 'code' in klines: continue
                        
                    closing_prices = [float(candle[4]) for candle in klines]
                    rsi = calculate_rsi(closing_prices)
                    ema = calculate_ema(closing_prices)
                    macd, macd_signal = calculate_macd(closing_prices)
                    vol_spike = check_volume_spike(klines)
                    atr = calculate_atr(klines)
                    
                    multiplier = 1.5 if coin in ["EUR", "GBP"] else 2
                    sl_distance, tp_distance = atr * multiplier, atr * (multiplier * 2)
                    
                    current_signal, msg = "HOLD", ""
                    
                    if rsi < 40 and live_price > ema and macd > macd_signal and vol_spike and coin not in active_trades:
                        current_signal = "BUY"
                        tp, sl = live_price + tp_distance, live_price - sl_distance
                        active_trades[coin] = {'type': 'BUY', 'entry': live_price, 'tp': tp, 'sl': sl}
                        msg = f"🟢 **PRO BUY: {display_name}** 🟢\n\nWhale Volume Detected! 🐋\nPrice: `${live_price}`\nRSI: `{rsi:.1f}`\n\n🎯 **TP:** `${tp:.4f}`\n🛡️ **SL:** `${sl:.4f}`\n\n*(Bot is trade ko track kar raha hai...)*"
                    
                    elif rsi > 60 and live_price < ema and macd < macd_signal and vol_spike and coin not in active_trades:
                        current_signal = "SELL"
                        tp, sl = live_price - tp_distance, live_price + sl_distance
                        active_trades[coin] = {'type': 'SELL', 'entry': live_price, 'tp': tp, 'sl': sl}
                        msg = f"🔴 **PRO SELL: {display_name}** 🔴\n\nWhale Volume Detected! 🐋\nPrice: `${live_price}`\nRSI: `{rsi:.1f}`\n\n🎯 **TP:** `${tp:.4f}`\n🛡️ **SL:** `${sl:.4f}`\n\n*(Bot is trade ko track kar raha hai...)*"

                    if current_signal != "HOLD" and current_signal != last_signals[coin]:
                        bot.send_message(USER_CHAT_ID, msg, parse_mode="Markdown")
                        last_signals[coin] = current_signal
                        print(f"🔥 ALERT Bheja & Tracking Shuru: {display_name} ({current_signal})")
                    else:
                        status = "TRACKING" if coin in active_trades else "HOLD"
                        print(f"• {display_name}: RSI={rsi:.0f} (Status: {status})")
                        
                except Exception as e:
                    print(f"Error checking {coin}: {e}")
            
            time.sleep(60) 
        else:
            time.sleep(10)

@bot.message_handler(commands=['start'])
def handle_start(message):
    global USER_CHAT_ID
    USER_CHAT_ID = message.chat.id
    bot.reply_to(message, "🚀 **Faisal's Exness 24/7 Cloud Tracker Connect Ho Gaya!**\n\nAb chahe aap phone band rakho, bot nahi rukega! 🔥", parse_mode="Markdown")
    print(f"\n✅ Telegram Connect Ho Gaya! Chat ID: {USER_CHAT_ID}")

if __name__ == "__main__":
    print("✅ Zinda Server aur Bot start ho rahe hain...")
    
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()

    t = threading.Thread(target=scan_market)
    t.daemon = True
    t.start()

    bot.infinity_polling()
  
