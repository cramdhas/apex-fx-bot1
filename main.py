"""
APEX·FX — Telegram Signal Bot (Google Gemini FREE)
No credit card. No payment. 100% free.

GET FREE API KEY:
  1. Go to aistudio.google.com
  2. Sign in with any Gmail account
  3. Click "Get API Key" → "Create API key"
  4. Copy the key — paste it below or set in Railway Variables

SETUP:
  pip install google-generativeai requests

RAILWAY ENVIRONMENT VARIABLES:
  BOT_TOKEN   = your telegram bot token (from @BotFather)
  GEMINI_KEY  = your gemini api key (from aistudio.google.com)
"""

import os
import re
import json
import time
import datetime
import threading
import requests
import google.generativeai as genai

# ── CREDENTIALS (set in Railway → Variables tab) ───────────────────────
BOT_TOKEN  = os.environ.get("BOT_TOKEN",  "")   # From @BotFather
GEMINI_KEY = os.environ.get("GEMINI_KEY", "")   # From aistudio.google.com
# ──────────────────────────────────────────────────────────────────────

if not BOT_TOKEN or not GEMINI_KEY:
    print("⚠  Set BOT_TOKEN and GEMINI_KEY in Railway environment variables!")

# Configure Gemini
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")   # free, fast model

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ── AI PROMPT ─────────────────────────────────────────────────────────
SIGNAL_PROMPT = """You are APEX-FX, a professional EUR/USD forex signal AI.
Analyze the current market and return ONLY valid JSON — no extra text.

Signal rules:
- BUY or SELL only when 3+ confluences align AND confidence >= 72%
- Consider: EMA 20/50/200, RSI, MACD, support/resistance, price action
- London-NY overlap (13-17 UTC) = best signals
- Asian session (22-08 UTC) = prefer WAIT

Return ONLY this JSON, nothing else:
{{
  "signal": "BUY",
  "grade": "A+",
  "confidence": 84,
  "entry": "1.08420",
  "stopLoss": "1.08180",
  "slPips": 24,
  "tp1": "1.08680",
  "tp1Pips": 26,
  "tp2": "1.08940",
  "tp2Pips": 52,
  "tp3": "1.09200",
  "tp3Pips": 78,
  "rr": "1:3.2",
  "session": "London-NY Overlap",
  "newsRisk": "LOW",
  "confluences": ["H4 demand zone bounce", "RSI divergence H1", "MACD crossover H4"],
  "invalidation": "H1 close below 1.0820",
  "sentiment": "Bullish"
}}

Current market context:
UTC Time: {utc_time}
Session: {session}
Day: {day}

Respond with JSON only."""

# ── HELPERS ───────────────────────────────────────────────────────────

def send_message(chat_id, text, parse_mode="MarkdownV2"):
    try:
        r = requests.post(f"{BASE_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[ERR] send_message: {e}")
        return False

def send_typing(chat_id):
    try:
        requests.post(f"{BASE_URL}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except: pass

def get_updates(offset=None):
    params = {"timeout": 30, "allowed_updates": ["message"]}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(f"{BASE_URL}/getUpdates", params=params, timeout=35)
        if r.status_code == 200:
            return r.json().get("result", [])
    except Exception as e:
        print(f"[ERR] get_updates: {e}")
    return []

def get_session_info():
    h = datetime.datetime.utcnow().hour
    if 13 <= h < 17:
        return "London-NY Overlap", "PRIME",  True
    if  8 <= h < 13:
        return "London Session",    "ACTIVE", True
    if 13 <= h < 22:
        return "New York Session",  "ACTIVE", True
    return "Asian Session", "LOW", False

# ── GEMINI SIGNAL ─────────────────────────────────────────────────────

def get_ai_signal():
    now     = datetime.datetime.utcnow()
    sname, squality, _ = get_session_info()

    prompt = SIGNAL_PROMPT.format(
        utc_time = now.strftime("%H:%M UTC"),
        session  = f"{sname} ({squality})",
        day      = now.strftime("%A")
    )

    try:
        response = model.generate_content(prompt)
        raw      = response.text.strip()
        # Strip markdown code fences if Gemini adds them
        raw = re.sub(r"```json|```", "", raw).strip()
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"[ERR] Gemini API: {e}")
    return None

# ── FORMAT SIGNAL ─────────────────────────────────────────────────────

def esc(s):
    """Escape MarkdownV2 special characters."""
    if not isinstance(s, str):
        s = str(s)
    for ch in r"\.()[]{}+-=#|>!*_~`":
        s = s.replace(ch, f"\\{ch}")
    return s

def format_signal(data):
    sig   = data.get("signal", "WAIT")
    grade = data.get("grade", "—")
    conf  = data.get("confidence", 0)

    if sig == "WAIT":
        return (
            "⏸ *EURUSD — WAIT*\n\n"
            f"Confidence: {conf}% \\(below threshold\\)\n"
            "_No quality setup right now\\._\n\n"
            "🤖 APEX\\-FX \\| Send /signal to retry"
        )

    arrow = "🟢" if sig == "BUY" else "🔴"
    nr    = data.get("newsRisk", "LOW")
    ni    = "🟢" if nr == "LOW" else "🟡" if nr == "MEDIUM" else "🔴"
    sent  = data.get("sentiment", "Neutral")
    si    = "📈" if sent == "Bullish" else "📉" if sent == "Bearish" else "➡️"

    confs     = data.get("confluences", [])
    cf_lines  = "\n".join([f"✅ {esc(c)}" for c in confs])

    return (
        f"{arrow} *EURUSD {esc(sig)} SIGNAL* \\| Grade: *{esc(grade)}*\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"📍 *Entry:* `{esc(data.get('entry','—'))}`\n"
        f"🛑 *Stop Loss:* `{esc(data.get('stopLoss','—'))}` \\(\\-{data.get('slPips','?')} pips\\)\n"
        f"🎯 *TP1:* `{esc(data.get('tp1','—'))}` \\(\\+{data.get('tp1Pips','?')} pips\\)\n"
        f"🎯 *TP2:* `{esc(data.get('tp2','—'))}` \\(\\+{data.get('tp2Pips','?')} pips\\)\n"
        f"🎯 *TP3:* `{esc(data.get('tp3','—'))}` \\(\\+{data.get('tp3Pips','?')} pips\\)\n"
        f"⚖️ *R/R:* `{esc(data.get('rr','—'))}` \\| Confidence: {conf}%\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📊 *Session:* {esc(data.get('session','—'))}\n"
        f"{si} *Sentiment:* {esc(sent)}\n\n"
        f"*Confluences:*\n{cf_lines}\n\n"
        f"⚠️ *Invalidation:* _{esc(data.get('invalidation','N/A'))}_\n"
        f"{ni} *News Risk:* {esc(nr)}\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"💰 Max 1\\-2% risk per trade\n"
        f"🤖 APEX\\-FX \\| Powered by Gemini\n"
        f"_⚠️ Not financial advice_"
    )

# ── SUBSCRIBERS ───────────────────────────────────────────────────────

subscribed = set()

def save_subs():
    try:
        with open("subs.json", "w") as f:
            json.dump(list(subscribed), f)
    except: pass

def load_subs():
    global subscribed
    try:
        with open("subs.json") as f:
            subscribed = set(json.load(f))
        print(f"[INFO] {len(subscribed)} subscribers loaded")
    except:
        pass

# ── COMMANDS ──────────────────────────────────────────────────────────

def cmd_start(chat_id, name):
    n = esc(name or "Trader")
    send_message(chat_id,
        f"👋 *Welcome, {n}\\!*\n\n"
        "I'm *APEX\\-FX*, your 24/7 AI EUR/USD signal bot\\.\n"
        "Powered by Google Gemini — 100% free\\.\n\n"
        "*Commands:*\n"
        "⚡ /signal — Live EUR/USD signal now\n"
        "📊 /status — Current session info\n"
        "❓ /help   — All commands\n\n"
        "_Best signals: London\\-NY overlap \\(13:00\\-17:00 UTC\\)_\n\n"
        "🤖 Running 24/7 on Railway cloud"
    )

def cmd_help(chat_id):
    send_message(chat_id,
        "📋 *APEX\\-FX Commands*\n\n"
        "⚡ /signal — AI EUR/USD signal\n"
        "📊 /status — Session \\& market info\n"
        "❓ /help   — This message\n"
        "🏠 /start  — Welcome\n\n"
        "*Signal Grades:*\n"
        "🥇 A\\+ — Very high confidence \\(≥85%\\)\n"
        "🥈 A   — High \\(75\\-84%\\)\n"
        "🥉 B   — Moderate \\(72\\-74%\\)\n"
        "⏸ WAIT — No setup found\n\n"
        "*Best Trading Times \\(UTC\\):*\n"
        "🟢 13:00\\-17:00 — London\\-NY \\(PRIME\\)\n"
        "🟡 08:00\\-13:00 — London\n"
        "🟡 13:00\\-22:00 — New York\n"
        "🔴 22:00\\-08:00 — Asian \\(avoid\\)\n\n"
        "_Always use 1\\-2% max risk per trade_\n"
        "🤖 APEX\\-FX \\| Powered by Gemini \\(Free\\)"
    )

def cmd_status(chat_id):
    utc   = datetime.datetime.utcnow().strftime("%H:%M UTC")
    day   = datetime.datetime.utcnow().strftime("%A")
    sname, sq, active = get_session_info()
    icon  = "🟢" if sq == "PRIME" else "🟡" if sq == "ACTIVE" else "🔴"
    send_message(chat_id,
        f"📊 *Market Status*\n\n"
        f"🕐 `{esc(utc)}` \\({esc(day)}\\)\n"
        f"📍 *Session:* {esc(sname)}\n"
        f"📶 *Quality:* {icon} {esc(sq)}\n\n"
        f"*Schedule \\(UTC\\):*\n"
        f"🟢 13:00\\-17:00 — London\\-NY Overlap\n"
        f"🟡 08:00\\-13:00 — London\n"
        f"🟡 13:00\\-22:00 — New York\n"
        f"🔴 22:00\\-08:00 — Asian\n\n"
        f"_Use /signal for live AI analysis_\n"
        f"🤖 APEX\\-FX"
    )

def cmd_signal(chat_id):
    send_typing(chat_id)
    send_message(chat_id,
        "⚡ *Analyzing EUR/USD\\.\\.\\.*\n"
        "_Scanning timeframes \\+ indicators\\.\\.\\._"
    )
    data = get_ai_signal()
    if not data:
        send_message(chat_id,
            "❌ *Analysis failed*\n\nGemini API error\\. Please try /signal again\\.\n🤖 APEX\\-FX")
        return
    send_message(chat_id, format_signal(data))
    print(f"[{datetime.datetime.utcnow().strftime('%H:%M UTC')}] Signal → {chat_id} | {data.get('signal')} @ {data.get('confidence')}%")

# ── AUTO BROADCAST ────────────────────────────────────────────────────

def auto_broadcast():
    """Every 15 min during active sessions, send A/A+ signals to all users."""
    while True:
        time.sleep(900)
        _, _, active = get_session_info()
        if not active or not subscribed:
            continue
        print(f"[AUTO] Scanning for broadcast to {len(subscribed)} users...")
        data = get_ai_signal()
        if not data:
            continue
        sig  = data.get("signal", "WAIT")
        conf = data.get("confidence", 0)
        if sig == "WAIT" or conf < 75:
            print(f"[AUTO] Skipped — {sig} @ {conf}%")
            continue
        msg = format_signal(data)
        for cid in list(subscribed):
            send_message(cid, msg)
            time.sleep(0.1)
        print(f"[AUTO] Broadcast done — {sig} @ {conf}% to {len(subscribed)} users")

# ── MAIN ──────────────────────────────────────────────────────────────

def main():
    print("=" * 52)
    print("  APEX·FX Bot — Powered by Gemini (FREE) 🚀")
    print("=" * 52)
    load_subs()
    threading.Thread(target=auto_broadcast, daemon=True).start()
    print("[INFO] Listening for Telegram messages...\n")

    offset = None
    while True:
        updates = get_updates(offset)
        for upd in updates:
            offset  = upd["update_id"] + 1
            msg     = upd.get("message", {})
            if not msg:
                continue
            chat_id = msg["chat"]["id"]
            text    = msg.get("text", "").strip()
            fname   = msg.get("from", {}).get("first_name", "")

            subscribed.add(chat_id)
            save_subs()
            print(f"[MSG] {chat_id} ({fname}): {text}")

            cmd = text.split()[0].lower().split("@")[0] if text else ""
            if   cmd == "/start":  cmd_start(chat_id, fname)
            elif cmd == "/signal": cmd_signal(chat_id)
            elif cmd == "/status": cmd_status(chat_id)
            elif cmd == "/help":   cmd_help(chat_id)
            else:
                send_message(chat_id,
                    "⚡ Send /signal for a live EUR/USD signal\\.\n"
                    "❓ Send /help to see all commands\\.\n"
                    "🤖 APEX\\-FX"
                )
        if not updates:
            time.sleep(1)

if __name__ == "__main__":
    main()
