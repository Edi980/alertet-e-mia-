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
triggered = set()

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

def get_xau_price():
    """Merr çmimin vetëm për XAU për thjeshtësi, pasi JSON-i duket i orientuar nga Gold"""
    try:
        r = requests.get("https://api.metals.live/v1/spot", timeout=10)
        if r.status_code == 200:
            for item in r.json():
                if item.get("gold"):
                    return float(item["gold"])
    except:
        pass
    return None

# ── LOGJIKA E BOTIT NË PRAPASKENË ───────────────────
def background_checker():
    logging.info("🚀 Gjurmuesi i çmimeve filloi në prapaskenë!")
    send_telegram("✅ <b>Boti u rindez dhe po gjurmon çmimet!</b>")
    
    while True:
        try:
            alerts = load_alerts()
            if alerts:
                current_price = get_xau_price()
                if current_price:
                    updated = False
                    for alert in alerts:
                        if alert.get("t"): # Nëse është goditur (hit), kaloje
                            continue
                            
                        target = float(alert["p"])
                        direction = alert["d"]
                        
                        hit = False
                        if direction == "above" and current_price >= target:
                            hit = True
                        elif direction == "below" and current_price <= target:
                            hit = True

                        if hit:
                            msg = (f"⚡ <b>ALARM I GODITUR!</b>\n\n"
                                   f"Tregu: <b>XAU/USD</b>\n"
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
        textarea { width: 100%; height: 300px; padding: 10px; border-radius: 5px; border: 1px solid #ccc; }
        button { padding: 10px 20px; background-color: #28a745; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; margin-top: 10px; }
        button:hover { background-color: #218838; }
        .alert-box { background: white; padding: 15px; margin-top: 20px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    </style>
</head>
<body>
    <h2>Gjurmuesi i Alarmeve</h2>
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
                    <li><b>{{ a.p }}</b> - {{ a.n }} (Drejtimi: {{ a.d }})</li>
                {% endif %}
            {% endfor %}
            {% if not alerts %}<li>Nuk ka alarme aktive.</li>{% endif %}
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
        new_alerts = []
        
        # Ekstrakto alarmet nga "key_zones"
        if "key_zones" in data:
            for zone in data["key_zones"]:
                zone_id = zone.get("id", "ZONË E PANJOHUR")
                direction = zone.get("direction", "sell")
                activation_price = zone.get("anchor_price")
                dol_price = zone.get("tp1")
                
                # 1. Alarmi i Aktivizimit (Activation)
                if activation_price:
                    # Nëse presim të shesim, çmimi duhet të ngjitet ("above") drejt rezistencës
                    trigger_dir = "above" if direction == "sell" else "below" 
                    new_alerts.append({
                        "id": int(time.time() * 1000),
                        "a": "XAU",
                        "d": trigger_dir,
                        "p": str(activation_price),
                        "n": f"🔔 ACTIVATION: {zone_id} ({zone.get('zone_label')})",
                        "t": False
                    })
                    time.sleep(0.1)
                
                # 2. Alarmi i Targetit (DOL)
                if dol_price:
                    # Nëse po shesim, targeti goditet kur çmimi bie ("below")
                    trigger_dir = "below" if direction == "sell" else "above"
                    new_alerts.append({
                        "id": int(time.time() * 1000),
                        "a": "XAU",
                        "d": trigger_dir,
                        "p": str(dol_price),
                        "n": f"🎯 DOL / TARGET: {zone_id} TP1",
                        "t": False
                    })
                    time.sleep(0.1)

        save_alerts(new_alerts)
        send_telegram("🔄 <b>Alarmet u përditësuan!</b>\nU lexua JSON-i i ri me sukses.")
        return redirect("/")
        
    except Exception as e:
        return f"<h3>Pati një gabim në leximin e JSON:</h3><p>{e}</p><a href='/'>Kthehu mbrapa</a>"

if __name__ == "__main__":
    # Fillon gjurmuesin në një thread të ndarë që të mos bllokojë faqen web
    threading.Thread(target=background_checker, daemon=True).start()
    
    # Fillon faqen web (Flask) për Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

