import os, re, json, time, datetime, threading, requests

BOT_TOKEN  = os.environ.get("BOT_TOKEN",  "")
GEMINI_KEY = os.environ.get("GEMINI_KEY", "")

print("==================================================")
print("  APEX-FX Bot - Gemini FREE")
print("==================================================")
if not BOT_TOKEN:  print("WARNING: BOT_TOKEN missing!")
if not GEMINI_KEY: print("WARNING: GEMINI_KEY missing!")

BASE = "https://api.telegram.org/bot" + BOT_TOKEN
GEM  = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

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
    except:
        pass

def get_updates(offset=None):
    try:
        p = {"timeout": 30, "allowed_updates": ["message"]}
        if offset:
            p["offset"] = offset
        r = requests.get(BASE + "/getUpdates", params=p, timeout=35)
        if r.status_code == 200:
            return r.json().get("result", [])
    except Exception as e:
        print("updates error: " + str(e))
    return []

def session():
    h = datetime.datetime.now(datetime.timezone.utc).hour
    if 13 <= h < 17:
        return "London-NY Overlap", "PRIME", True
    if 8 <= h < 13:
        return "London Session", "ACTIVE", True
    if 17 <= h < 22:
        return "New York Session", "ACTIVE", True
    return "Asian Session", "LOW", False

def get_signal():
    now = datetime.datetime.now(datetime.timezone.utc)
    sname, sq, _ = session()
    prompt = (
        "You are a professional forex signal AI for EURUSD. "
        "Return ONLY valid JSON with no extra text and no markdown.\n"
        "Use this exact structure:\n"
        '{"signal":"BUY","grade":"A+","confidence":84,'
        '"entry":"1.08420","stopLoss":"1.08180","slPips":24,'
        '"tp1":"1.08680","tp1Pips":26,"tp2":"1.08940","tp2Pips":52,'
        '"rr":"1:2.2","session":"London-NY Overlap","newsRisk":"LOW",'
        '"confluences":["H4 demand zone","RSI divergence H1","MACD crossover"],'
        '"invalidation":"H1 close below 1.0820","sentiment":"Bullish"}\n'
        "Rules: signal BUY or SELL only if confidence>=72 and 3+ confluences. "
        "Otherwise signal must be WAIT.\n"
        "UTC: " + now.strftime("%H:%M") + " | Day: " + now.strftime("%A") +
        " | Session: " + sname + " (" + sq + ")\n"
        "Respond with JSON only. No explanation. No markdown."
    )
    try:
        r = requests.post(
            GEM + "?key=" + GEMINI_KEY,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        print("Gemini status: " + str(r.status_code))
        resp = r.json()
        print("Gemini raw: " + str(resp)[:200])

        # safely extract text
        raw = ""
        if "candidates" in resp:
            cands = resp["candidates"]
            if cands and len(cands) > 0:
                content = cands[0].get("content", {})
                parts = content.get("parts", [])
                if parts and len(parts) > 0:
                    raw = parts[0].get("text", "")
        elif "error" in resp:
            print("Gemini API error: " + str(resp["error"]))
            return None

        if not raw:
            print("Gemini: empty response")
            return None

        raw = raw.replace("```json", "").replace("```", "").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            return json.loads(m.group())
        else:
            print("Gemini: no JSON found in: " + raw[:100])
    except Exception as e:
        print("Gemini error: " + str(e))
    return None

def fmt(data):
    sig   = data.get("signal", "WAIT")
    conf  = data.get("confidence", 0)
    grade = data.get("grade", "")
    if sig == "WAIT":
        return (
            "⏸ <b>EURUSD — WAIT</b>\n\n"
            "Confidence: " + str(conf) + "% (below threshold)\n"
            "<i>No quality setup right now.</i>\n\n"
            "🤖 APEX-FX | Send /signal to retry"
        )
    arrow = "🟢" if sig == "BUY" else "🔴"
    nr    = data.get("newsRisk", "LOW")
    ni    = "🟢" if nr == "LOW" else ("🟡" if nr == "MEDIUM" else "🔴")
    sent  = data.get("sentiment", "Neutral")
    si    = "📈" if sent == "Bullish" else ("📉" if sent == "Bearish" else "➡️")
    confs = data.get("confluences", [])
    cf    = "\n".join(["✅ " + c for c in confs])
    return (
        arrow + " <b>EURUSD " + sig + " SIGNAL</b> | Grade: <b>" + grade + "</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📍 <b>Entry:</b> <code>" + str(data.get("entry","—")) + "</code>\n"
        "🛑 <b>Stop Loss:</b> <code>" + str(data.get("stopLoss","—")) + "</code>"
        " (-" + str(data.get("slPips","?")) + " pips)\n"
        "🎯 <b>TP1:</b> <code>" + str(data.get("tp1","—")) + "</code>"
        " (+" + str(data.get("tp1Pips","?")) + " pips)\n"
        "🎯 <b>TP2:</b> <code>" + str(data.get("tp2","—")) + "</code>"
        " (+" + str(data.get("tp2Pips","?")) + " pips)\n"
        "⚖️ <b>R/R:</b> " + str(data.get("rr","—")) +
        " | Confidence: " + str(conf) + "%\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "📊 " + str(data.get("session","—")) + "\n"
        + si + " Sentiment: " + sent + "\n\n"
        "<b>Confluences:</b>\n" + cf + "\n\n"
        "⚠️ <i>Invalidation: " + str(data.get("invalidation","N/A")) + "</i>\n"
        + ni + " News Risk: " + nr + "\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "💰 Max 1-2% risk per trade\n"
        "🤖 APEX-FX | Powered by Gemini\n"
        "<i>Not financial advice</i>"
    )

subs = set()

def save():
    try:
        with open("subs.json", "w") as f:
            json.dump(list(subs), f)
    except:
        pass

def load():
    global subs
    try:
        with open("subs.json") as f:
            subs = set(json.load(f))
        print("Loaded " + str(len(subs)) + " subscribers")
    except:
        pass

def broadcast():
    while True:
        time.sleep(900)
        _, _, active = session()
        if not active or not subs:
            continue
        print("Broadcasting to " + str(len(subs)) + " users...")
        data = get_signal()
        if not data:
            continue
        sig  = data.get("signal", "WAIT")
        conf = data.get("confidence", 0)
        if sig == "WAIT" or conf < 75:
            print("Skipped " + sig + " @ " + str(conf) + "%")
            continue
        msg = fmt(data)
        for cid in list(subs):
            send(cid, msg)
            time.sleep(0.1)
        print("Sent " + sig + " @ " + str(conf) + "% to " + str(len(subs)) + " users")

def do_start(cid, name):
    send(cid,
        "👋 <b>Welcome, " + (name or "Trader") + "!</b>\n\n"
        "I am <b>APEX-FX</b>, your 24/7 AI EUR/USD signal bot.\n"
        "Powered by Google Gemini — 100% free.\n\n"
        "<b>Commands:</b>\n"
        "⚡ /signal — Live EUR/USD signal\n"
        "📊 /status — Session info\n"
        "❓ /help — All commands\n\n"
        "<i>Best signals: London-NY overlap 13:00-17:00 UTC</i>\n\n"
        "🤖 Running 24/7 on Railway cloud"
    )

def do_help(cid):
    send(cid,
        "📋 <b>APEX-FX Commands</b>\n\n"
        "⚡ /signal — AI EUR/USD signal\n"
        "📊 /status — Session info\n"
        "❓ /help — This message\n"
        "🏠 /start — Welcome\n\n"
        "<b>Signal Grades:</b>\n"
        "🥇 A+ — Very high (85%+)\n"
        "🥈 A  — High (75-84%)\n"
        "🥉 B  — Moderate (72-74%)\n"
        "⏸ WAIT — No setup found\n\n"
        "<b>Best Times (UTC):</b>\n"
        "🟢 13:00-17:00 — London-NY (PRIME)\n"
        "🟡 08:00-13:00 — London\n"
        "🟡 17:00-22:00 — New York\n"
        "🔴 22:00-08:00 — Asian (avoid)\n\n"
        "<i>Always use 1-2% max risk per trade</i>\n"
        "🤖 APEX-FX | Gemini (Free)"
    )

def do_status(cid):
    sname, sq, _ = session()
    icon = "🟢" if sq == "PRIME" else ("🟡" if sq == "ACTIVE" else "🔴")
    now  = datetime.datetime.now(datetime.timezone.utc)
    send(cid,
        "📊 <b>Market Status</b>\n\n"
        "🕐 " + now.strftime("%H:%M UTC") + " (" + now.strftime("%A") + ")\n"
        "📍 <b>Session:</b> " + sname + "\n"
        "📶 <b>Quality:</b> " + icon + " " + sq + "\n\n"
        "<b>Schedule (UTC):</b>\n"
        "🟢 13:00-17:00 — London-NY Overlap\n"
        "🟡 08:00-13:00 — London\n"
        "🟡 17:00-22:00 — New York\n"
        "🔴 22:00-08:00 — Asian\n\n"
        "<i>Use /signal for live AI analysis</i>\n"
        "🤖 APEX-FX"
    )

def do_signal(cid):
    typing(cid)
    send(cid, "⚡ <b>Analyzing EUR/USD...</b>\n<i>Scanning timeframes + indicators...</i>")
    data = get_signal()
    if not data:
        send(cid, "❌ Analysis failed. Please try /signal again.\n🤖 APEX-FX")
        return
    send(cid, fmt(data))
    now = datetime.datetime.now(datetime.timezone.utc)
    print(now.strftime("%H:%M") + " Signal sent to " + str(cid) +
          " | " + str(data.get("signal")) + " @ " + str(data.get("confidence")) + "%")

load()
threading.Thread(target=broadcast, daemon=True).start()
print("[INFO] Listening for Telegram messages...")

offset = None
while True:
    updates = get_updates(offset)
    for upd in updates:
        offset = upd["update_id"] + 1
        msg    = upd.get("message", {})
        if not msg:
            continue
        cid  = msg["chat"]["id"]
        text = msg.get("text", "").strip()
        name = msg.get("from", {}).get("first_name", "")
        subs.add(cid)
        save()
        print("MSG from " + str(cid) + " (" + name + "): " + text)
        cmd = text.split()[0].lower().split("@")[0] if text else ""
        if   cmd == "/start":  do_start(cid, name)
        elif cmd == "/signal": do_signal(cid)
        elif cmd == "/status": do_status(cid)
        elif cmd == "/help":   do_help(cid)
        else:
            send(cid,
                "⚡ Send /signal for a live EUR/USD signal\n"
                "❓ Send /help to see all commands\n"
                "🤖 APEX-FX"
            )
    if not updates:
        time.sleep(1)
