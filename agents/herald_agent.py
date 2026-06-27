"""
NEXUS — HERALD Agent
WhatsApp message → Claude ORACLE triage → Arabic/English reply
Triggers SAWT (voice call) for HIGH/EMERGENCY cases via n8n

Run: uvicorn herald_agent:app --port 8001 --reload
Test: curl -X POST http://localhost:8001/webhook/whatsapp \
      -H "Content-Type: application/json" \
      -d '{"message":"I have chest pain","from":"+971501234567"}'
"""

import os
import json
import logging
import time
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import anthropic
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("HERALD")

app = FastAPI(title="NEXUS HERALD Agent", version="3.1")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
MAKE_WEBHOOK = os.getenv("MAKE_WEBHOOK_URL", "")

ORACLE_SYSTEM = """
You are NEXUS ORACLE — an AI medical triage screening assistant for rural UAE communities.
You are NOT a medical professional. You do NOT diagnose conditions.

Your ONLY role:
1. Assess urgency: LOW / MEDIUM / HIGH / EMERGENCY
2. Recommend next action and facility type
3. Provide simple first-aid for non-emergency cases
4. Respond in the same language as the patient (Arabic or English)

URGENCY DEFINITIONS:
- EMERGENCY: chest pain, stroke symptoms, unconscious, severe bleeding, can't breathe
- HIGH: high fever >39°C, broken bone, severe pain, diabetic crisis, head injury
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

URGENCY_EMOJI = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴", "EMERGENCY": "🚨"}


def detect_language(text: str) -> str:
    arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
    return "ar" if arabic_chars > len(text) * 0.2 else "en"


def send_whatsapp(to: str, body: str):
    """Send WhatsApp reply via Twilio sandbox."""
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_num = f"whatsapp:{os.getenv('TWILIO_WHATSAPP_NUMBER')}"
    to_num = to if to.startswith("whatsapp:") else f"whatsapp:{to}"

    r = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, token),
        data={"From": from_num, "To": to_num, "Body": body},
        timeout=10,
    )
    log.info(f"WhatsApp sent → {to_num} | status={r.status_code}")
    if r.status_code not in (200, 201):
        log.error(f"Twilio error: {r.text[:200]}")
    return r.status_code


def trigger_n8n_emergency(urgency: str, summary: str, from_number: str, triage: dict):
    """Fire n8n emergency webhook → triggers SAWT voice call via n8n pipeline."""
    webhook = os.getenv("N8N_EMERGENCY_WEBHOOK")
    if not webhook or "REPLACE" in webhook:
        # Fallback: call SAWT directly
        log.warning("N8N_EMERGENCY_WEBHOOK not configured — calling SAWT directly")
        try:
            r = requests.post(
                "http://localhost:8002/trigger-call",
                json={
                    "urgency": urgency,
                    "summary": summary,
                    "from_number": from_number,
                    "source": "HERALD",
                    "location": "Al Qua'a region, UAE",
                },
                timeout=5,
            )
            log.info(f"SAWT direct call → {r.status_code}")
        except Exception as e:
            log.error(f"SAWT direct call failed: {e}")
        return

    payload = {
        "urgency": urgency,
        "summary": summary,
        "from_number": from_number,
        "triage": triage,
        "action": "TRIGGER_VOICE_CALL",
        "source": "HERALD",
        "location": "Al Qua'a region, UAE",
    }
    try:
        r = requests.post(webhook, json=payload, timeout=5)
        log.info(f"n8n emergency fired → {r.status_code}")
    except Exception as e:
        log.error(f"n8n webhook failed: {e}")


def save_to_supabase(record: dict):
    """Write triage record to Supabase via REST (no SDK)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        log.warning("Supabase credentials not configured — skipping")
        return
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/calls",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=record,
            timeout=10,
        )
        if r.status_code in (200, 201):
            log.info("✅ Saved to Supabase")
        else:
            log.error(f"Supabase {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"Supabase write failed: {e}")


def notify_make_whatsapp(triage: dict, from_number: str, message: str):
    """Optionally log WhatsApp triage to Make.com → Google Sheets."""
    if not MAKE_WEBHOOK or "REPLACE" in MAKE_WEBHOOK:
        return
    try:
        requests.post(
            MAKE_WEBHOOK,
            json={
                "source": "HERALD_WHATSAPP",
                "from_number": from_number,
                "original_message": message,
                "urgency": triage.get("urgency"),
                "summary": triage.get("triage_summary"),
                "action": triage.get("recommended_action"),
                "agent": "HERALD+ORACLE",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            timeout=5,
        )
        log.info("Make.com notified for WhatsApp triage")
    except Exception as e:
        log.error(f"Make.com notification failed: {e}")


@app.post("/webhook/whatsapp")
async def handle_whatsapp(request: Request):
    """Main entry — receives WhatsApp messages from Twilio."""
    data = await request.json()

    # Support both Twilio POST format and direct JSON test format
    message = data.get("Body") or data.get("message", "")
    from_number = data.get("From") or data.get("from", "unknown")

    if not message:
        raise HTTPException(status_code=400, detail="No message body")

    log.info(f"📩 Message from {from_number}: {message[:80]}")
    lang = detect_language(message)

    # ── Claude ORACLE triage ──────────────────────────────
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=700,
        system=ORACLE_SYSTEM,
        messages=[{"role": "user", "content": f"Patient message: {message}"}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if model adds them despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    triage = json.loads(raw.strip())

    urgency = triage["urgency"]
    summary = triage["triage_summary"]
    emoji = URGENCY_EMOJI.get(urgency, "⚪")

    # ── Build WhatsApp reply ──────────────────────────────
    reply_body = triage["reply_ar"] if lang == "ar" else triage["reply_en"]
    disclaimer = triage["disclaimer_ar"] if lang == "ar" else triage["disclaimer_en"]

    full_reply = (
        f"{emoji} *NEXUS Medical Triage*\n\n"
        f"{reply_body}\n\n"
        f"🏥 *Action:* {triage['recommended_action']}\n\n"
        f"⚠️ _{disclaimer}_"
    )

    # ── Send WhatsApp reply ───────────────────────────────
    if not from_number.startswith("test"):
        send_whatsapp(from_number, full_reply)

    # ── Escalate HIGH/EMERGENCY → SAWT via n8n ────────────
    if urgency in ("HIGH", "EMERGENCY"):
        log.warning(f"🚨 {urgency} case — triggering SAWT voice call")
        trigger_n8n_emergency(urgency, summary, from_number, triage)

    # ── Log to Supabase ───────────────────────────────────
    call_id = f"wa_{from_number}_{int(time.time())}"
    save_to_supabase({
        "call_id": call_id,
        "from_number": from_number,
        "intent": "whatsapp_triage",
        "urgency": urgency,
        "transcript": message,
        "ai_summary": summary,
        "outcome": "escalated" if urgency in ("HIGH", "EMERGENCY") else "resolved",
        "agent_used": "HERALD+ORACLE",
    })

    # ── Log WhatsApp triage to Make.com → Google Sheets ──
    notify_make_whatsapp(triage, from_number, message)

    return {
        "status": "processed",
        "urgency": urgency,
        "triage": triage,
        "reply": full_reply,
    }


@app.get("/health")
def health():
    return {
        "agent": "HERALD",
        "status": "online",
        "version": "3.1",
        "supabase_set": bool(SUPABASE_URL),
        "make_webhook_set": bool(MAKE_WEBHOOK and "REPLACE" not in MAKE_WEBHOOK),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("herald_agent:app", host="0.0.0.0", port=8001, reload=True)