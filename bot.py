import os
import json
import time
import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

# ── Konfigurimi ──────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")   # nga BotFather
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")  # ID-ja jote
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "30"))  # sekonda

# ── Alertet ruhen këtu (mund të ngarkohen nga skedar) ──
ALERTS_FILE = "alerts.json"

# ── Kujtesa: cilat alarme janë dërguar ──
triggered = set()

# ────────────────────────────────────────────────────────
def load_alerts():
    """Lexo alertet nga skedari JSON"""
    if not os.path.exists(ALERTS_FILE):
        return []
    try:
        with open(ALERTS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Gabim lexim alerts.json: {e}")
        return []

def save_alerts(alerts):
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts, f, indent=2)

# ────────────────────────────────────────────────────────
def get_prices():
    """Merr çmimet e fundit nga API publike falas"""
    prices = {}
    try:
        # XAU dhe Forex nga Frankfurter + Gold API
        r = requests.get(
            "https://api.metals.live/v1/spot",
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            for item in data:
                if item.get("gold"):
                    prices["XAU"] = float(item["gold"])
                if item.get("silver"):
                    prices["XAG"] = float(item["silver"])
    except Exception as e:
        logging.warning(f"metals.live: {e}")

    try:
        # BTC dhe ETH nga CoinGecko (falas)
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=bitcoin,ethereum&vs_currencies=usd",
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            prices["BTC"] = data["bitcoin"]["usd"]
            prices["ETH"] = data["ethereum"]["usd"]
    except Exception as e:
        logging.warning(f"CoinGecko: {e}")

    try:
        # EUR/USD nga Frankfurter
        r = requests.get(
            "https://api.frankfurter.app/latest?from=EUR&to=USD",
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            prices["EUR"] = data["rates"]["USD"]
    except Exception as e:
        logging.warning(f"Frankfurter: {e}")

    return prices

# ────────────────────────────────────────────────────────
def send_telegram(message):
    """Dërgon mesazh Telegram"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("TELEGRAM_TOKEN ose TELEGRAM_CHAT_ID mungon!")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=10)
        if r.status_code == 200:
            logging.info(f"✅ Telegram dërguar: {message[:60]}")
            return True
        else:
            logging.error(f"Telegram error: {r.text}")
    except Exception as e:
        logging.error(f"Telegram exception: {e}")
    return False

# ────────────────────────────────────────────────────────
def check_alerts(prices, alerts):
    """Kontrollo nëse ndonjë alert është arritur"""
    updated = False
    for alert in alerts:
        aid = str(alert["id"])
        if aid in triggered:
            continue  # tashmë u dërgua gjatë kësaj seance

        if alert.get("t"):
            continue  # u shënua si hit

        asset = alert["a"]   # p.sh. "XAU"
        direction = alert["d"]  # "above" ose "below"
        target = float(alert["p"])
        note = alert.get("n", "")

        current = prices.get(asset)
        if current is None:
            continue

        hit = False
        if direction == "above" and current >= target:
            hit = True
        elif direction == "below" and current <= target:
            hit = True

        if hit:
            arrow = "🟢▲" if direction == "above" else "🔴▼"
            msg = (
                f"⚡ <b>MARKET ALERT</b>\n\n"
                f"{arrow} <b>{asset}/USD</b>\n"
                f"Çmimi: <b>${current:,.2f}</b>\n"
                f"Targeti: ${target:,.2f} ({direction})\n"
            )
            if note:
                msg += f"📝 {note}\n"
            msg += f"\n⏰ {time.strftime('%H:%M:%S %d/%m/%Y')}"

            if send_telegram(msg):
                triggered.add(aid)
                alert["t"] = True  # shëno si hit
                updated = True
                logging.info(f"🎯 Alert HIT: {asset} {direction} {target}")

    if updated:
        save_alerts(alerts)

# ────────────────────────────────────────────────────────
def run_keepalive():
    """Ping i thjeshtë HTTP për Render.com — mban serverin gjallë"""
    from threading import Thread
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class PingHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Market Alert Bot is running!")
        def log_message(self, *args):
            pass  # heq logjet e tepërta

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), PingHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    logging.info(f"🌐 Keepalive server në port {port}")

# ────────────────────────────────────────────────────────
def main():
    logging.info("🚀 Market Alert Bot startoi!")

    # Keepalive për Render.com
    run_keepalive()

    # Dërgo mesazh fillestare
    send_telegram(
        "✅ <b>Market Alert Bot u startua!</b>\n"
        f"Kontrollon çdo {CHECK_INTERVAL} sekonda.\n"
        f"Alertet aktive: {len(load_alerts())}"
    )

    while True:
        try:
            alerts = load_alerts()
            if alerts:
                prices = get_prices()
                if prices:
                    logging.info(f"📊 Çmimet: {prices}")
                    check_alerts(prices, alerts)
                else:
                    logging.warning("⚠️ Nuk u morën çmimet.")
            else:
                logging.info("📋 Nuk ka alertete aktive.")
        except Exception as e:
            logging.error(f"Gabim kryesor: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
