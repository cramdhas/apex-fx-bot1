import os, re, json, time, datetime, threading, requests

BOT_TOKEN  = os.environ.get("BOT_TOKEN",  "")
GEMINI_KEY = os.environ.get("GEMINI_KEY", "")

# ── TRADE SETTINGS (your personal settings) ───────────────────────────
LOT_SIZE = 0.01
SL_PIPS  = 15
TP1_PIPS = 50
TP2_PIPS = 70
TP3_PIPS = 100
# ──────────────────────────────────────────────────────────────────────

print("==================================================")
print("  APEX-FX Bot - Real Price + Gemini FREE")
print("==================================================")
print("BOT_TOKEN: " + ("YES" if BOT_TOKEN else "NO"))
print("GEMINI_KEY: " + ("YES" if GEMINI_KEY else "NO"))

BASE = "https://api.telegram.org/bot" + BOT_TOKEN
GEM  = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# ── GET REAL-TIME EUR/USD PRICE ───────────────────────────────────────

def get_live_price():
    """Fetch real-time EUR/USD price from free API."""
    try:
        # Primary source: Frankfurter (free, no key needed)
        r = requests.get(
            "https://api.frankfurter.app/latest?from=EUR&to=USD",
            timeout=10
        )
        if r.status_code == 200:
            price = r.json()["rates"]["USD"]
            print("Live price (Frankfurter): " + str(price))
            return round(float(price), 5)
    except Exception as e:
        print("Frankfurter error: " + str(e))

    try:
        # Backup source: ExchangeRate-API (free, no key needed)
        r = requests.get(
            "https://open.er-api.com/v6/latest/EUR",
            timeout=10
        )
        if r.status_code == 200:
            price = r.json()["rates"]["USD"]
            print("Live price (ExchangeRate): " + str(price))
            return round(float(price), 5)
    except Exception as e:
        print("ExchangeRate error: " + str(e))

    print("Could not fetch live price")
    return None

def calc_levels(price, signal):
    """Calculate exact SL/TP levels from real price."""
    pip = 0.0001
    if signal == "BUY":
        sl  = round(price - (SL_PIPS  * pip), 5)
        tp1 = round(price + (TP1_PIPS * pip), 5)
        tp2 = round(price + (TP2_PIPS * pip), 5)
        tp3 = round(price + (TP3_PIPS * pip), 5)
    else:  # SELL
        sl  = round(price + (SL_PIPS  * pip), 5)
        tp1 = round(price - (TP1_PIPS * pip), 5)
        tp2 = round(price - (TP2_PIPS * pip), 5)
        tp3 = round(price - (TP3_PIPS * pip), 5)
    return sl, tp1, tp2, tp3

# ── TELEGRAM HELPERS ──────────────────────────────────────────────────

def send(chat_id, text):
    try:
        requests.post(BASE + "/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10)
    except Exception as e:
        print("send error: " + str(e))

def typing(chat_id):
    try:
        requests.post(BASE + "/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except: pass

def get_updates(offset=None):
    try:
        p = {"timeout": 25, "allowed_updates": ["message"]}
        if offset: p["offset"] = offset
        r = requests.get(BASE + "/getUpdates", params=p, timeout=30)
        if r.status_code == 200:
            return r.json().get("result", [])
    except Exception as e:
        print("updates error: " + str(e))
    return []

# ── SESSION ───────────────────────────────────────────────────────────

def session():
    try:
        h = datetime.datetime.now(datetime.timezone.utc).hour
        if 13 <= h < 17: return "London-NY Overlap", "PRIME",  True
        if  8 <= h < 13: return "London Session",    "ACTIVE", True
        if 17 <= h < 22: return "New York Session",  "ACTIVE", True
        return "Asian Session", "LOW", False
    except: return "Market", "ACTIVE", True

# ── GEMINI AI SIGNAL ──────────────────────────────────────────────────

def get_signal():
    try:
        now   = datetime.datetime.now(datetime.timezone.utc)
        sname, sq, _ = session()
        price = get_live_price()

        if not price:
            return None

        prompt = (
            "You are a professional forex signal AI for EURUSD. "
            "Return ONLY valid JSON with no extra text and no markdown. "
            "Use this exact structure: "
            '{"signal":"BUY","grade":"A+","confidence":84,'
            '"analysis":"Brief market analysis in 1 sentence",'
            '"trend":"Bullish - price above EMA200",'
            '"keyLevel":"Support at 1.0820",'
            '"newsRisk":"LOW",'
            '"confluences":["H4 demand zone bounce","RSI divergence H1","MACD crossover H4"],'
            '"invalidation":"H1 close below 1.0820","sentiment":"Bullish"} '
            "Rules: BUY or SELL only if confidence>=72 and 3+ strong confluences align. "
            "Otherwise signal MUST be WAIT. Be strict — only signal on very clear setups. "
            "Current data: "
            "Live EUR/USD price: " + str(price) + " | "
            "UTC: " + now.strftime("%H:%M") + " | "
            "Day: " + now.strftime("%A") + " | "
            "Session: " + sname + " (" + sq + ") | "
            "JSON only, no explanation."
        )

        r = requests.post(
            GEM + "?key=" + GEMINI_KEY,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        print("Gemini HTTP: " + str(r.status_code))
        resp = r.json()

        if "error" in resp:
            print("Gemini error: " + str(resp["error"].get("message",""))[:100])
            return None

        cands = resp.get("candidates", [])
        if not cands:
            print("No candidates")
            return None

        raw = cands[0].get("content",{}).get("parts",[{}])[0].get("text","")
        raw = raw.replace("```json","").replace("```","").strip()
        m   = re.search(r"\{[\s\S]*\}", raw)
        if m:
            data = json.loads(m.group())
            data["livePrice"] = price
            return data
        print("No JSON found")
    except Exception as e:
        print("get_signal error: " + str(e))
    return None

# ── FORMAT SIGNAL ─────────────────────────────────────────────────────

def fmt(data):
    try:
        sig   = data.get("signal", "WAIT")
        conf  = data.get("confidence", 0)
        grade = data.get("grade", "")
        price = data.get("livePrice", 0)

        if sig == "WAIT":
            sname, sq, _ = session()
            now = datetime.datetime.now(datetime.timezone.utc)
            ist = now + datetime.timedelta(hours=5, minutes=30)
            return (
                "⏸ <b>EURUSD — WAIT</b>\n\n"
                "📍 Live Price: <code>" + str(price) + "</code>\n"
                "🔍 Confidence: " + str(conf) + "% (min 72% needed)\n\n"
                "<i>" + str(data.get("analysis","No quality setup right now.")) + "</i>\n\n"
                "🕐 IST: " + ist.strftime("%I:%M %p") + " | " + sname + "\n\n"
                "🤖 APEX-FX | /signal to retry"
            )

        # Calculate levels from real price
        sl, tp1, tp2, tp3 = calc_levels(price, sig)
        arrow = "🟢" if sig == "BUY" else "🔴"
        nr    = data.get("newsRisk", "LOW")
        ni    = "🟢" if nr=="LOW" else ("🟡" if nr=="MEDIUM" else "🔴")
        sent  = data.get("sentiment","Neutral")
        si    = "📈" if sent=="Bullish" else ("📉" if sent=="Bearish" else "➡️")
        cf    = "\n".join(["✅ " + str(c) for c in data.get("confluences",[])])

        # IST time
        now = datetime.datetime.now(datetime.timezone.utc)
        ist = now + datetime.timedelta(hours=5, minutes=30)
        sname, sq, _ = session()

        return (
            arrow + " <b>EURUSD " + sig + " SIGNAL</b> | Grade: <b>" + grade + "</b>\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "📍 <b>Live Price:</b> <code>" + str(price) + "</code>\n"
            "📍 <b>Entry Now:</b> <code>" + str(price) + "</code>\n"
            "🛑 <b>Stop Loss:</b> <code>" + str(sl) + "</code> (-" + str(SL_PIPS) + " pips)\n"
            "🎯 <b>TP1:</b> <code>" + str(tp1) + "</code> (+" + str(TP1_PIPS) + " pips)\n"
            "🎯 <b>TP2:</b> <code>" + str(tp2) + "</code> (+" + str(TP2_PIPS) + " pips)\n"
            "🎯 <b>TP3:</b> <code>" + str(tp3) + "</code> (+" + str(TP3_PIPS) + " pips)\n"
            "📦 <b>Lot Size:</b> " + str(LOT_SIZE) + "\n"
            "⚖️ <b>R/R:</b> 1:1.25 → 1:2.5 | Confidence: " + str(conf) + "%\n\n"
            "━━━━━━━━━━━━━━━━━\n"
            "📊 <b>Session:</b> " + sname + "\n"
            + si + " <b>Trend:</b> " + str(data.get("trend","—")) + "\n"
            "🔑 <b>Key Level:</b> " + str(data.get("keyLevel","—")) + "\n\n"
            "<b>Confluences:</b>\n" + cf + "\n\n"
            "⚠️ <i>Invalidation: " + str(data.get("invalidation","")) + "</i>\n"
            + ni + " <b>News Risk:</b> " + nr + "\n\n"
            "━━━━━━━━━━━━━━━━━\n"
            "🕐 <b>IST Time:</b> " + ist.strftime("%I:%M %p") + "\n"
            "📱 <b>Open MT5 → New Order → Market</b>\n"
            "💰 Lot: " + str(LOT_SIZE) + " | SL: " + str(sl) + " | TP: " + str(tp1) + "\n\n"
            "🤖 APEX-FX | Real Price Signal\n"
            "<i>⚠️ Not financial advice. Trade at your own risk.</i>"
        )
    except Exception as e:
        print("fmt error: " + str(e))
        return "❌ Format error. Try /signal again."

# ── SUBSCRIBERS ───────────────────────────────────────────────────────

subs = set()
def save():
    try:
        with open("subs.json","w") as f: json.dump(list(subs),f)
    except: pass
def load():
    global subs
    try:
        with open("subs.json") as f: subs = set(json.load(f))
        print("Subscribers: " + str(len(subs)))
    except: pass

# ── AUTO BROADCAST ────────────────────────────────────────────────────

def broadcast():
    while True:
        try:
            time.sleep(900)
            _, _, active = session()
            if not active or not subs: continue
            print("Auto-scanning for broadcast...")
            data = get_signal()
            if not data: continue
            sig  = data.get("signal","WAIT")
            conf = data.get("confidence",0)
            if sig == "WAIT" or conf < 75:
                print("Skipped: " + sig + " " + str(conf) + "%")
                continue
            msg = fmt(data)
            for cid in list(subs):
                send(cid, msg); time.sleep(0.1)
            print("Broadcast sent: " + sig + " " + str(conf) + "%")
        except Exception as e:
            print("broadcast error: " + str(e))

# ── COMMANDS ──────────────────────────────────────────────────────────

def do_start(cid, name):
    now = datetime.datetime.now(datetime.timezone.utc)
    ist = now + datetime.timedelta(hours=5, minutes=30)
    send(cid,
        "👋 <b>Welcome, " + (name or "Trader") + "!</b>\n\n"
        "I am <b>APEX-FX</b> — your 24/7 AI EUR/USD signal bot.\n\n"
        "<b>Your Trade Settings:</b>\n"
        "📦 Lot Size: " + str(LOT_SIZE) + "\n"
        "🛑 Stop Loss: " + str(SL_PIPS) + " pips\n"
        "🎯 TP1: " + str(TP1_PIPS) + " pips\n"
        "🎯 TP2: " + str(TP2_PIPS) + " pips\n"
        "🎯 TP3: " + str(TP3_PIPS) + " pips\n\n"
        "<b>Commands:</b>\n"
        "⚡ /signal — Live signal with real price\n"
        "💰 /price — Current EUR/USD price\n"
        "📊 /status — Session info\n"
        "❓ /help — All commands\n\n"
        "<b>Best Signal Times (IST):</b>\n"
        "🟢 6:30 PM - 10:30 PM — London-NY (PRIME)\n"
        "🟡 1:30 PM - 6:30 PM — London\n\n"
        "🕐 Your time now: " + ist.strftime("%I:%M %p IST") + "\n\n"
        "🤖 Running 24/7 on Railway"
    )

def do_help(cid):
    send(cid,
        "📋 <b>APEX-FX Commands</b>\n\n"
        "⚡ /signal — AI signal with real EUR/USD price\n"
        "💰 /price — Live EUR/USD price now\n"
        "📊 /status — Session info\n"
        "❓ /help — This message\n\n"
        "<b>Signal Times (IST):</b>\n"
        "🟢 6:30 PM - 10:30 PM — PRIME\n"
        "🟡 1:30 PM - 6:30 PM — Good\n"
        "🔴 Before 1:30 PM — Avoid\n\n"
        "<b>Your Settings:</b>\n"
        "Lot: " + str(LOT_SIZE) + " | SL: " + str(SL_PIPS) + "p | "
        "TP1: " + str(TP1_PIPS) + "p | TP2: " + str(TP2_PIPS) + "p | TP3: " + str(TP3_PIPS) + "p\n\n"
        "🤖 APEX-FX | Real Price Signals"
    )

def do_price(cid):
    try:
        typing(cid)
        price = get_live_price()
        now   = datetime.datetime.now(datetime.timezone.utc)
        ist   = now + datetime.timedelta(hours=5, minutes=30)
        sname, sq, _ = session()
        icon  = "🟢" if sq=="PRIME" else ("🟡" if sq=="ACTIVE" else "🔴")
        if price:
            send(cid,
                "💰 <b>EUR/USD Live Price</b>\n\n"
                "📍 Price: <code>" + str(price) + "</code>\n\n"
                "🕐 " + ist.strftime("%I:%M %p IST") + "\n"
                + icon + " " + sname + "\n\n"
                "<b>If you trade now:</b>\n"
                "BUY SL: <code>" + str(round(price - SL_PIPS*0.0001, 5)) + "</code>\n"
                "BUY TP1: <code>" + str(round(price + TP1_PIPS*0.0001, 5)) + "</code>\n"
                "SELL SL: <code>" + str(round(price + SL_PIPS*0.0001, 5)) + "</code>\n"
                "SELL TP1: <code>" + str(round(price - TP1_PIPS*0.0001, 5)) + "</code>\n\n"
                "🤖 APEX-FX"
            )
        else:
            send(cid, "❌ Could not fetch price. Try again.\n🤖 APEX-FX")
    except Exception as e:
        print("price error: " + str(e))

def do_status(cid):
    try:
        sname, sq, _ = session()
        icon = "🟢" if sq=="PRIME" else ("🟡" if sq=="ACTIVE" else "🔴")
        now  = datetime.datetime.now(datetime.timezone.utc)
        ist  = now + datetime.timedelta(hours=5, minutes=30)
        send(cid,
            "📊 <b>Market Status</b>\n\n"
            "🕐 IST: " + ist.strftime("%I:%M %p") + "\n"
            "🕐 UTC: " + now.strftime("%H:%M") + "\n"
            "📍 " + sname + "\n"
            "📶 " + icon + " " + sq + "\n\n"
            "<b>Schedule (IST):</b>\n"
            "🟢 6:30 PM - 10:30 PM — London-NY (PRIME)\n"
            "🟡 1:30 PM - 6:30 PM — London\n"
            "🟡 10:30 PM - 3:30 AM — New York\n"
            "🔴 3:30 AM - 1:30 PM — Asian (avoid)\n\n"
            "🤖 APEX-FX"
        )
    except Exception as e:
        print("status error: " + str(e))

def do_signal(cid):
    try:
        typing(cid)
        send(cid, "⚡ <b>Fetching live price + analyzing...</b>\n<i>Please wait...</i>")
        data = get_signal()
        if not data:
            send(cid, "❌ Analysis failed. Try /signal again.\n🤖 APEX-FX")
            return
        send(cid, fmt(data))
        print("Signal sent to " + str(cid) + " | " +
              str(data.get("signal")) + " @ " + str(data.get("confidence")) + "%" +
              " | Price: " + str(data.get("livePrice")))
    except Exception as e:
        print("signal error: " + str(e))
        send(cid, "❌ Error. Try /signal again.")

# ── MAIN ──────────────────────────────────────────────────────────────

load()
threading.Thread(target=broadcast, daemon=True).start()
print("[INFO] Bot running with real-time price feed!")

offset = None
while True:
    try:
        updates = get_updates(offset)
        for upd in updates:
            try:
                offset = upd["update_id"] + 1
                msg  = upd.get("message", {})
                if not msg: continue
                cid  = msg["chat"]["id"]
                text = msg.get("text","").strip()
                name = msg.get("from",{}).get("first_name","")
                subs.add(cid); save()
                print("MSG: " + str(cid) + " " + name + ": " + text)
                cmd = text.split()[0].lower().split("@")[0] if text else ""
                if   cmd=="/start":  do_start(cid,name)
                elif cmd=="/signal": do_signal(cid)
                elif cmd=="/price":  do_price(cid)
                elif cmd=="/status": do_status(cid)
                elif cmd=="/help":   do_help(cid)
                else: send(cid,
                    "⚡ /signal — Live EUR/USD signal\n"
                    "💰 /price — Current price\n"
                    "📊 /status — Session info\n"
                    "🤖 APEX-FX")
            except Exception as e:
                print("update error: " + str(e))
        if not updates: time.sleep(1)
    except Exception as e:
        print("main loop error: " + str(e))
        time.sleep(5)
