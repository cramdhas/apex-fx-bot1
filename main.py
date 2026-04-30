import os, re, json, time, datetime, threading, requests

BOT_TOKEN  = os.environ.get("BOT_TOKEN",  "")
GEMINI_KEY = os.environ.get("GEMINI_KEY", "")

print("==================================================")
print("  APEX-FX Bot - Gemini FREE")
print("==================================================")
print("BOT_TOKEN set: " + ("YES" if BOT_TOKEN else "NO"))
print("GEMINI_KEY set: " + ("YES" if GEMINI_KEY else "NO"))

BASE = "https://api.telegram.org/bot" + BOT_TOKEN
GEM  = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

def send(chat_id, text):
    try:
        r = requests.post(BASE + "/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10)
        print("send status: " + str(r.status_code))
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
        p = {"timeout": 25, "allowed_updates": ["message"]}
        if offset:
            p["offset"] = offset
        r = requests.get(BASE + "/getUpdates", params=p, timeout=30)
        if r.status_code == 200:
            return r.json().get("result", [])
    except Exception as e:
        print("updates error: " + str(e))
    return []

def session():
    try:
        h = datetime.datetime.now(datetime.timezone.utc).hour
        if 13 <= h < 17:
            return "London-NY Overlap", "PRIME", True
        if 8 <= h < 13:
            return "London Session", "ACTIVE", True
        if 17 <= h < 22:
            return "New York Session", "ACTIVE", True
        return "Asian Session", "LOW", False
    except:
        return "Unknown", "ACTIVE", True

def get_signal():
    try:
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
            "Respond with JSON only."
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
            print("Gemini API error: " + str(resp["error"].get("message","")))
            return None
            
        cands = resp.get("candidates", [])
        if not cands:
            print("Gemini: no candidates. Full resp: " + str(resp)[:300])
            return None
            
        raw = cands[0].get("content",{}).get("parts",[{}])[0].get("text","")
        if not raw:
            print("Gemini: empty text")
            return None
            
        print("Gemini response: " + raw[:100])
        raw = raw.replace("```json","").replace("```","").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            return json.loads(m.group())
        print("Gemini: no JSON found")
    except Exception as e:
        print("get_signal error: " + str(e))
    return None

def fmt(data):
    try:
        sig   = data.get("signal", "WAIT")
        conf  = data.get("confidence", 0)
        grade = data.get("grade", "")
        if sig == "WAIT":
            return (
                "⏸ <b>EURUSD — WAIT</b>\n\n"
                "Confidence: " + str(conf) + "%\n"
                "<i>No quality setup right now.</i>\n\n"
                "🤖 APEX-FX | /signal to retry"
            )
        arrow = "🟢" if sig == "BUY" else "🔴"
        nr    = data.get("newsRisk", "LOW")
        ni    = "🟢" if nr=="LOW" else ("🟡" if nr=="MEDIUM" else "🔴")
        sent  = data.get("sentiment", "Neutral")
        si    = "📈" if sent=="Bullish" else ("📉" if sent=="Bearish" else "➡️")
        cf    = "\n".join(["✅ " + str(c) for c in data.get("confluences",[])])
        return (
            arrow + " <b>EURUSD " + sig + "</b> | Grade: <b>" + grade + "</b>\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "📍 Entry: <code>" + str(data.get("entry","—")) + "</code>\n"
            "🛑 SL: <code>" + str(data.get("stopLoss","—")) + "</code> (-" + str(data.get("slPips","?")) + "p)\n"
            "🎯 TP1: <code>" + str(data.get("tp1","—")) + "</code> (+" + str(data.get("tp1Pips","?")) + "p)\n"
            "🎯 TP2: <code>" + str(data.get("tp2","—")) + "</code> (+" + str(data.get("tp2Pips","?")) + "p)\n"
            "⚖️ R/R: " + str(data.get("rr","—")) + " | " + str(conf) + "%\n\n"
            "━━━━━━━━━━━━━━━━━\n"
            "📊 " + str(data.get("session","—")) + "\n"
            + si + " " + sent + "\n\n"
            "<b>Confluences:</b>\n" + cf + "\n\n"
            "⚠️ <i>" + str(data.get("invalidation","")) + "</i>\n"
            + ni + " News: " + nr + "\n\n"
            "━━━━━━━━━━━━━━━━━\n"
            "💰 Max 1-2% risk\n"
            "🤖 APEX-FX | Gemini\n"
            "<i>Not financial advice</i>"
        )
    except Exception as e:
        print("fmt error: " + str(e))
        return "❌ Format error. Try /signal again."

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

def broadcast():
    while True:
        try:
            time.sleep(900)
            _, _, active = session()
            if not active or not subs: continue
            data = get_signal()
            if not data: continue
            sig  = data.get("signal","WAIT")
            conf = data.get("confidence",0)
            if sig=="WAIT" or conf<75: continue
            msg = fmt(data)
            for cid in list(subs):
                send(cid, msg)
                time.sleep(0.1)
            print("Broadcast done: " + sig + " " + str(conf) + "%")
        except Exception as e:
            print("broadcast error: " + str(e))

def do_start(cid, name):
    send(cid,
        "👋 <b>Welcome, " + (name or "Trader") + "!</b>\n\n"
        "I am <b>APEX-FX</b>, your 24/7 AI EUR/USD signal bot.\n"
        "Powered by Google Gemini — 100% free.\n\n"
        "<b>Commands:</b>\n"
        "⚡ /signal — Live EUR/USD signal\n"
        "📊 /status — Session info\n"
        "❓ /help — All commands\n\n"
        "🤖 Running 24/7 on Railway"
    )

def do_help(cid):
    send(cid,
        "📋 <b>APEX-FX Commands</b>\n\n"
        "⚡ /signal — AI EUR/USD signal\n"
        "📊 /status — Session info\n"
        "❓ /help — This message\n\n"
        "<b>Best Times (UTC):</b>\n"
        "🟢 13:00-17:00 — London-NY\n"
        "🟡 08:00-13:00 — London\n"
        "🟡 17:00-22:00 — New York\n"
        "🔴 22:00-08:00 — Asian\n\n"
        "🤖 APEX-FX | Gemini Free"
    )

def do_status(cid):
    try:
        sname, sq, _ = session()
        icon = "🟢" if sq=="PRIME" else ("🟡" if sq=="ACTIVE" else "🔴")
        now  = datetime.datetime.now(datetime.timezone.utc)
        send(cid,
            "📊 <b>Market Status</b>\n\n"
            "🕐 " + now.strftime("%H:%M UTC") + "\n"
            "📍 " + sname + "\n"
            "📶 " + icon + " " + sq + "\n\n"
            "🟢 13:00-17:00 London-NY\n"
            "🟡 08:00-13:00 London\n"
            "🟡 17:00-22:00 New York\n"
            "🔴 22:00-08:00 Asian\n\n"
            "🤖 APEX-FX"
        )
    except Exception as e:
        print("do_status error: " + str(e))
        send(cid, "❌ Error. Try again.")

def do_signal(cid):
    try:
        typing(cid)
        send(cid, "⚡ <b>Analyzing EUR/USD...</b>\n<i>Please wait...</i>")
        data = get_signal()
        if not data:
            send(cid, "❌ Analysis failed. Try /signal again.\n🤖 APEX-FX")
            return
        send(cid, fmt(data))
    except Exception as e:
        print("do_signal error: " + str(e))
        send(cid, "❌ Error. Try /signal again.")

load()
threading.Thread(target=broadcast, daemon=True).start()
print("[INFO] Bot is running. Listening for messages...")

offset = None
while True:
    try:
        updates = get_updates(offset)
        for upd in updates:
            try:
                offset = upd["update_id"] + 1
                msg    = upd.get("message", {})
                if not msg: continue
                cid  = msg["chat"]["id"]
                text = msg.get("text","").strip()
                name = msg.get("from",{}).get("first_name","")
                subs.add(cid)
                save()
                print("MSG: " + str(cid) + " " + name + ": " + text)
                cmd = text.split()[0].lower().split("@")[0] if text else ""
                if   cmd == "/start":  do_start(cid, name)
                elif cmd == "/signal": do_signal(cid)
                elif cmd == "/status": do_status(cid)
                elif cmd == "/help":   do_help(cid)
                else: send(cid, "⚡ /signal for signal\n❓ /help for commands\n🤖 APEX-FX")
            except Exception as e:
                print("update error: " + str(e))
        if not updates:
            time.sleep(1)
    except Exception as e:
        print("main loop error: " + str(e))
        time.sleep(5)
