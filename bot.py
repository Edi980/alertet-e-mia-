import os
import json
import time
import requests
import logging
import threading
import yfinance as yf
from flask import Flask, request, render_template_string, redirect

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "30"))
ALERTS_FILE = "alerts.json"

app = Flask(__name__)

# ── FUNKSIONET BAZË ─────────────────────────────────
def load_alerts():
    if not os.path.exists(ALERTS_FILE):
        return []
    try:
        with open(ALERTS_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_alerts(alerts):
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts, f, indent=2)

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
        return r.status_code == 200
    except:
        return False

def get_market_prices():
    """Merr çmimet për BTC (nga Binance) dhe XAU, US30, NAS100 (nga Yahoo Finance)"""
    prices = {}
    
    # 1. Kripto nga Binance (Ultra e saktë, pa vonesa)
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5)
        if r.status_code == 200:
            prices["BTC"] = float(r.json()["price"])
    except Exception as e:
        logging.error(f"Gabim Binance BTC: {e}")

    # 2. Asetet e tjera nga Yahoo Finance (Shumë afër IC Markets)
    try:
        # XAUUSD=X (Gold), ^DJI (Dow Jones/US30), ^IXIC (Nasdaq/NAS100)
        tickers = yf.Tickers("XAUUSD=X ^DJI ^IXIC")
        prices["XAU"] = tickers.tickers["XAUUSD=X"].fast_info['last_price']
        prices["US30"] = tickers.tickers["^DJI"].fast_info['last_price']
        prices["NAS100"] = tickers.tickers["^IXIC"].fast_info['last_price']
    except Exception as e:
        logging.error(f"Gabim Yahoo Finance: {e}")

    return prices

# ── LOGJIKA E BOTIT NË PRAPASKENË ───────────────────
def background_checker():
    logging.info("🚀 Gjurmuesi i çmimeve filloi në prapaskenë!")
    send_telegram("✅ <b>Boti u rindez dhe po gjurmon tregun (XAU, BTC, US30, NAS100)!</b>")
    
    while True:
        try:
            alerts = load_alerts()
            if alerts:
                prices = get_market_prices()
                if prices:
                    updated = False
                    for alert in alerts:
                        if alert.get("t"): # Nëse është goditur (hit), kaloje
                            continue
                            
                        asset = alert["a"]
                        target = float(alert["p"])
                        direction = alert["d"]
                        current_price = prices.get(asset)
                        
                        if not current_price:
                            continue

                        hit = False
                        if direction == "above" and current_price >= target:
                            hit = True
                        elif direction == "below" and current_price <= target:
                            hit = True

                        if hit:
                            msg = (f"⚡ <b>ALARM I GODITUR!</b>\n\n"
                                   f"Tregu: <b>{asset}</b>\n"
                                   f"Çmimi Aktual: <b>${current_price:,.2f}</b>\n"
                                   f"Targeti: ${target:,.2f}\n\n"
                                   f"📝 Shënimi: {alert['n']}")
                            if send_telegram(msg):
                                alert["t"] = True
                                updated = True
                    
                    if updated:
                        save_alerts(alerts)
        except Exception as e:
            logging.error(f"Gabim në gjurmues: {e}")
            
        time.sleep(CHECK_INTERVAL)

# ── FAQJA WEB PËR COPY-PASTE (FRONT-END) ─────────────
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Shto Analizën (JSON)</title>
    <style>
        body { font-family: Arial; padding: 20px; background-color: #f4f4f9; }
        textarea { width: 100%; height: 300px; padding: 10px; border-radius: 5px; border: 1px solid #ccc; font-family: monospace; }
        button { padding: 10px 20px; background-color: #28a745; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; margin-top: 10px; }
        button:hover { background-color: #218838; }
        .alert-box { background: white; padding: 15px; margin-top: 20px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .tag { padding: 3px 8px; border-radius: 3px; color: white; font-weight: bold; font-size: 12px; }
        .bg-xau { background-color: #f39c12; }
        .bg-btc { background-color: #f1c40f; color: black; }
        .bg-us30 { background-color: #2980b9; }
        .bg-nas100 { background-color: #8e44ad; }
    </style>
</head>
<body>
    <h2>Gjurmuesi i Alarmeve ICT/SMC</h2>
    <form method="POST" action="/process_json">
        <label><b>Bëj paste JSON-in e Mapuesit këtu:</b></label><br>
        <textarea name="json_data" placeholder='{"strategic_bias": "sell", ...}' required></textarea><br>
        <button type="submit">Krijo Alarmet</button>
    </form>
    
    <div class="alert-box">
        <h3>Alarmet Aktive në Databazë:</h3>
        <ul>
            {% for a in alerts %}
                {% if not a.t %}
                    <li>
                        <span class="tag bg-{{ a.a | lower }}">{{ a.a }}</span> 
                        <b>{{ a.p }}</b> - {{ a.n }} (Drejtimi: {{ a.d }})
                    </li>
                {% endif %}
            {% endfor %}
            {% if not alerts %}<li>Nuk ka alarme aktive. Bëj paste JSON-in më lart.</li>{% endif %}
        </ul>
    </div>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    alerts = load_alerts()
    return render_template_string(HTML_PAGE, alerts=alerts)

@app.route("/process_json", methods=["POST"])
def process_json():
    raw_data = request.form.get("json_data", "")
    try:
        data = json.loads(raw_data)
        text_data = raw_data.upper()
        
        # 1. Zbulimi Automatik i Asetit nga teksti i JSON
        asset = "XAU" # Default
        if "BTC" in text_data or "BITCOIN" in text_data: 
            asset = "BTC"
        elif "US30" in text_data or "DOW" in text_data: 
            asset = "US30"
        elif "NAS100" in text_data or "NASDAQ" in text_data or "USTEC" in text_data: 
            asset = "NAS100"
        elif "XAU" in text_data or "GOLD" in text_data: 
            asset = "XAU"

        new_alerts = []
        
        # 2. Ekstrakto alarmet nga "key_zones"
        if "key_zones" in data:
            for zone in data["key_zones"]:
                zone_id = zone.get("id", "ZONË E PANJOHUR")
                direction = zone.get("direction", "sell")
                activation_price = zone.get("anchor_price")
                dol_price = zone.get("tp1")
                
                # Alarmi i Aktivizimit (Activation)
                if activation_price:
                    trigger_dir = "above" if direction == "sell" else "below" 
                    new_alerts.append({
                        "id": int(time.time() * 1000),
                        "a": asset,
                        "d": trigger_dir,
                        "p": str(activation_price),
                        "n": f"🔔 ACTIVATION: {zone_id}",
                        "t": False
                    })
                    time.sleep(0.01)
                
                # Alarmi i Targetit (DOL)
                if dol_price:
                    trigger_dir = "below" if direction == "sell" else "above"
                    new_alerts.append({
                        "id": int(time.time() * 1000),
                        "a": asset,
                        "d": trigger_dir,
                        "p": str(dol_price),
                        "n": f"🎯 DOL / TARGET: {zone_id} TP1",
                        "t": False
                    })
                    time.sleep(0.01)

        save_alerts(new_alerts)
        send_telegram(f"🔄 <b>Alarmet u përditësuan!</b>\nAseti i zbuluar: {asset}")
        return redirect("/")
        
    except Exception as e:
        return f"<h3>Pati një gabim në leximin e JSON:</h3><p>{e}</p><a href='/'>Kthehu mbrapa</a>"

if __name__ == "__main__":
    threading.Thread(target=background_checker, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
