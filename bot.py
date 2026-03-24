import os
import json
import time
import requests
import logging
import threading
from flask import Flask, request, render_template_string, redirect

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "30"))
ALERTS_FILE = "alerts.json"

app = Flask(__name__)
live_prices = {"XAU": 0, "BTC": 0, "US30": 0, "NAS100": 0}

def load_alerts():
    if not os.path.exists(ALERTS_FILE): return []
    try:
        with open(ALERTS_FILE, "r") as f: return json.load(f)
    except: return []

def save_alerts(alerts):
    with open(ALERTS_FILE, "w") as f: json.dump(alerts, f, indent=2)

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
        return r.status_code == 200
    except: return False

def get_yahoo_price(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            return float(data['chart']['result'][0]['meta']['regularMarketPrice'])
    except Exception as e:
        logging.error(f"Gabim Yahoo ({symbol}): {e}")
    return None

def get_market_prices():
    prices = {}
    
    btc = get_yahoo_price("BTC-USD")
    if btc: prices["BTC"] = btc

    xau = get_yahoo_price("GC=F")
    if xau: prices["XAU"] = xau
    
    nas = get_yahoo_price("NQ=F")
    if nas: prices["NAS100"] = nas
    
    us30 = get_yahoo_price("YM=F")
    if us30: prices["US30"] = us30
    
    global live_prices
    live_prices.update(prices)
    return prices

def background_checker():
    logging.info("🚀 Gjurmuesi filloi!")
    while True:
        try:
            # TANI I MERR ÇMIMET GJITHMONË (që të mbushen kutitë lart)
            prices = get_market_prices()
            
            alerts = load_alerts()
            if alerts and prices:
                updated = False
                for alert in alerts:
                    if alert.get("t"): continue
                        
                    asset = alert["a"]
                    target = float(alert["p"])
                    direction = alert["d"]
                    current_price = prices.get(asset)
                    
                    if not current_price: continue

                    hit = False
                    if direction == "above" and current_price >= target: hit = True
                    elif direction == "below" and current_price <= target: hit = True

                    if hit:
                        msg = (f"⚡ <b>ALARM I GODITUR!</b>\n\n"
                               f"Tregu: <b>{asset}</b>\n"
                               f"Çmimi Aktual: <b>${current_price:,.2f}</b>\n"
                               f"Targeti: ${target:,.2f}\n\n"
                               f"📝 Shënimi: {alert['n']}")
                        if send_telegram(msg):
                            alert["t"] = True
                            updated = True
                if updated: save_alerts(alerts)
        except Exception as e: 
            logging.error(f"Gabim në gjurmues: {e}")
            
        time.sleep(CHECK_INTERVAL)

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Shto Analizën</title>
    <style>
        body { font-family: Arial; padding: 20px; background-color: #f4f4f9; }
        textarea { width: 100%; height: 200px; padding: 10px; border-radius: 5px; border: 1px solid #ccc; font-family: monospace; }
        button { padding: 10px 20px; background-color: #28a745; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; margin-top: 10px; }
        .box { background: white; padding: 15px; margin-top: 20px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .tag { padding: 3px 8px; border-radius: 3px; color: white; font-weight: bold; font-size: 12px; }
        .bg-xau { background-color: #f39c12; } .bg-btc { background-color: #f1c40f; color: black; }
        .bg-us30 { background-color: #2980b9; } .bg-nas100 { background-color: #8e44ad; }
        .prices { display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; }
        .price-card { background: #fff; padding: 10px 20px; border-radius: 5px; border-left: 4px solid #333; box-shadow: 0 2px 4px rgba(0,0,0,0.1); font-size: 14px;}
    </style>
</head>
<body>
    <h2>Gjurmuesi i Alarmeve ICT/SMC</h2>
    
    <div class="prices">
        <div class="price-card" style="border-color: #f39c12;"><b>XAU:</b> ${{ "{:,.2f}".format(prices.get('XAU', 0)) }}</div>
        <div class="price-card" style="border-color: #8e44ad;"><b>NAS100:</b> ${{ "{:,.2f}".format(prices.get('NAS100', 0)) }}</div>
        <div class="price-card" style="border-color: #2980b9;"><b>US30:</b> ${{ "{:,.2f}".format(prices.get('US30', 0)) }}</div>
        <div class="price-card" style="border-color: #f1c40f;"><b>BTC:</b> ${{ "{:,.2f}".format(prices.get('BTC', 0)) }}</div>
    </div>

    <form method="POST" action="/process_json">
        <textarea name="json_data" placeholder='Bëj paste JSON-in...' required></textarea><br>
        <button type="submit">Krijo Alarmet</button>
    </form>
    
    <div class="box">
        <h3>Alarmet Aktive:</h3>
        <ul>
            {% for a in alerts %}
                {% if not a.t %}
                    <li><span class="tag bg-{{ a.a | lower }}">{{ a.a }}</span> <b>{{ a.p }}</b> (Drejtimi: {{ a.d }}) - {{ a.n }}</li>
                {% endif %}
            {% endfor %}
            {% if not alerts %}<li>Nuk ka alarme aktive. Bëj paste JSON-in për të filluar.</li>{% endif %}
        </ul>
    </div>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML_PAGE, alerts=load_alerts(), prices=live_prices)

@app.route("/process_json", methods=["POST"])
def process_json():
    raw_data = request.form.get("json_data", "")
    try:
        data = json.loads(raw_data)
        text_data = raw_data.upper()
        
        asset = "XAU"
        if "BTC" in text_data or "BITCOIN" in text_data: asset = "BTC"
        elif "US30" in text_data or "DOW" in text_data: asset = "US30"
        elif "NAS100" in text_data or "NASDAQ" in text_data or "USTEC" in text_data: asset = "NAS100"

        new_alerts = []
        if "key_zones" in data:
            for zone in data["key_zones"]:
                zone_id = zone.get("id", "ZONË")
                direction = zone.get("direction", "sell")
                act_price = zone.get("anchor_price")
                dol_price = zone.get("tp1")
                
                if act_price:
                    new_alerts.append({"id": int(time.time()*1000), "a": asset, "d": "above" if direction == "sell" else "below", "p": str(act_price), "n": f"🔔 ACTIVATION: {zone_id}", "t": False})
                    time.sleep(0.01)
                if dol_price:
                    new_alerts.append({"id": int(time.time()*1000)+1, "a": asset, "d": "below" if direction == "sell" else "above", "p": str(dol_price), "n": f"🎯 DOL: {zone_id}", "t": False})

        save_alerts(new_alerts)
        send_telegram(f"🔄 <b>Alarmet u përditësuan!</b>\nAseti: {asset}")
        return redirect("/")
    except Exception as e:
        return f"Gabim: {e}"

if __name__ == "__main__":
    threading.Thread(target=background_checker, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
