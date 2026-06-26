"""
NEXUS — HERALD Agent v3.1
WhatsApp → Claude ORACLE triage → Arabic/English reply → SAWT escalation
"""

import os, json, logging, time, requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import anthropic

# ── Load env from absolute path — works regardless of cwd ─
from dotenv import load_dotenv
load_dotenv("D:/nexus/.env", override=True)

# ── Verify key loaded (shows in uvicorn log on startup) ───
_key = os.getenv("ANTHROPIC_API_KEY", "")
print(f"[HERALD] ANTHROPIC_API_KEY loaded: {'YES ' + _key[:15] if _key else 'NO — CHECK D:/nexus/.env'}")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("HERALD")

app = FastAPI(title="NEXUS HERALD Agent", version="3.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SUPABASE_URL         = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
MAKE_WEBHOOK         = os.getenv("MAKE_WEBHOOK_URL", "")

ORACLE_SYSTEM = """
You are NEXUS ORACLE — an AI medical triage screening assistant for rural UAE communities.
You are NOT a medical professional. You do NOT diagnose conditions.

URGENCY DEFINITIONS:
- EMERGENCY: chest pain, stroke symptoms, unconscious, severe bleeding, can't breathe
- HIGH: high fever >39C, broken bone, severe pain, diabetic crisis, head injury
- MEDIUM: moderate pain, infection symptoms, persistent vomiting, minor injury
- LOW: cold/flu, minor cut, general health question

You MUST respond ONLY with valid JSON — no markdown, no extra text:
{
  "urgency": "LOW|MEDIUM|HIGH|EMERGENCY",
  "triage_summary": "2-sentence plain English summary",
  "recommended_action": "what to do right now",
  "facility_type": "self-care|clinic|hospital|emergency",
  "first_aid_steps": ["step 1", "step 2"],
  "reply_en": "your full reply in English (warm, clear, 3-4 sentences)",
  "reply_ar": "your full reply in Arabic (same content)",
  "disclaimer_en": "This is AI triage screening, not a medical diagnosis. Always consult a qualified healthcare professional.",
  "disclaimer_ar": "هذه أداة فرز آلي وليست تشخيصاً طبياً. استشر دائماً متخصصاً في الرعاية الصحية المؤهلاً."
}
"""

URGENCY_EMOJI = {"LOW":"🟢","MEDIUM":"🟡","HIGH":"🔴","EMERGENCY":"🚨"}


def detect_language(text: str) -> str:
    arabic = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    return "ar" if arabic > len(text) * 0.2 else "en"


def send_whatsapp(to: str, body: str):
    sid   = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_ = f"whatsapp:{os.getenv('TWILIO_WHATSAPP_NUMBER')}"
    to_   = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
    r = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, token),
        data={"From": from_, "To": to_, "Body": body},
        timeout=10
    )
    log.info(f"WhatsApp → {to_} | {r.status_code}")
    return r.status_code


def trigger_emergency(urgency, summary, from_number, triage):
    """Try n8n first, fall back to SAWT directly."""
    webhook = os.getenv("N8N_EMERGENCY_WEBHOOK", "")

    payload = {
        "urgency":      urgency,
        "summary":      summary,
        "from_number":  from_number,
        "triage":       triage,
        "action":       "TRIGGER_VOICE_CALL",
        "source":       "HERALD",
        "location":     "Al Qua'a region, UAE",
        "clinic_phone": os.getenv("DEMO_CLINIC_PHONE", "+916355088167")
    }

    # Try n8n
    if webhook and "REPLACE" not in webhook and "yuvy" in webhook:
        try:
            r = requests.post(webhook, json=payload, timeout=5)
            log.info(f"n8n emergency fired → {r.status_code}")
            if r.status_code < 300:
                return
        except Exception as e:
            log.error(f"n8n failed: {e}")

    # Direct SAWT fallback
    try:
        r = requests.post("http://localhost:8002/trigger-call", json=payload, timeout=5)
        log.info(f"SAWT direct → {r.status_code}")
    except Exception as e:
        log.error(f"SAWT direct failed: {e}")


def save_to_supabase(record: dict):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/calls",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            json=record, timeout=10
        )
        if r.status_code in (200, 201):
            log.info("✅ Saved to Supabase")
        else:
            log.error(f"Supabase {r.status_code}: {r.text[:150]}")
    except Exception as e:
        log.error(f"Supabase failed: {e}")


def notify_make(triage, from_number, message):
    if not MAKE_WEBHOOK or "REPLACE" in MAKE_WEBHOOK:
        return
    try:
        requests.post(MAKE_WEBHOOK, json={
            "call_id":          f"wa_{from_number}_{int(time.time())}",
            "source":           "HERALD_WHATSAPP",
            "from_number":      from_number,
            "urgency":          triage.get("urgency"),
            "summary":          triage.get("triage_summary"),
            "location":         "Al Qua'a, UAE",
            "original_message": message,
            "timestamp":        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }, timeout=5)
        log.info("Make.com notified")
    except Exception as e:
        log.error(f"Make.com failed: {e}")


@app.post("/webhook/whatsapp")
async def handle_whatsapp(request: Request):
    data        = await request.json()
    message     = data.get("Body") or data.get("message", "")
    from_number = data.get("From") or data.get("from", "unknown")

    if not message:
        raise HTTPException(status_code=400, detail="No message body")

    log.info(f"📩 {from_number}: {message[:80]}")
    lang = detect_language(message)

    # Claude ORACLE triage
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=700,
        system=ORACLE_SYSTEM,
        messages=[{"role":"user","content":f"Patient message: {message}"}]
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"): raw = raw[4:]
    triage  = json.loads(raw.strip())
    urgency = triage["urgency"]
    summary = triage["triage_summary"]
    emoji   = URGENCY_EMOJI.get(urgency, "⚪")

    # Build reply
    reply_body  = triage["reply_ar"] if lang == "ar" else triage["reply_en"]
    disclaimer  = triage["disclaimer_ar"] if lang == "ar" else triage["disclaimer_en"]
    full_reply  = (
        f"{emoji} *NEXUS Medical Triage*\n\n"
        f"{reply_body}\n\n"
        f"🏥 *Action:* {triage['recommended_action']}\n\n"
        f"⚠️ _{disclaimer}_"
    )

    # Send WhatsApp (skip for test numbers)
    if not from_number.startswith("test"):
        send_whatsapp(from_number, full_reply)

    # Escalate HIGH/EMERGENCY
    if urgency in ("HIGH", "EMERGENCY"):
        log.warning(f"🚨 {urgency} — triggering SAWT")
        trigger_emergency(urgency, summary, from_number, triage)

    # Save to Supabase
    save_to_supabase({
        "call_id":    f"wa_{from_number}_{int(time.time())}",
        "from_number": from_number,
        "intent":     "whatsapp_triage",
        "urgency":    urgency,
        "transcript": message,
        "ai_summary": summary,
        "outcome":    "escalated" if urgency in ("HIGH","EMERGENCY") else "resolved",
        "agent_used": "HERALD+ORACLE"
    })

    # Log to Make.com → Google Sheets
    notify_make(triage, from_number, message)

    return {"status":"processed","urgency":urgency,"triage":triage,"reply":full_reply}


@app.get("/health")
def health():
    return {
        "agent":   "HERALD",
        "status":  "online",
        "version": "3.1",
        "claude":  bool(os.getenv("ANTHROPIC_API_KEY")),
        "supabase": bool(SUPABASE_URL),
        "make":    bool(MAKE_WEBHOOK and "REPLACE" not in MAKE_WEBHOOK)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agents.herald_agent:app", host="0.0.0.0", port=8001, reload=True)