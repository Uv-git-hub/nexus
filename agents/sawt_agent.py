"""
NEXUS — SAWT Agent (صوت = "Voice")
Autonomously calls clinics/emergency contacts via VAPI.
After the call ends, VAPI fires /vapi-callback which:
  1. Saves full transcript + metadata to Supabase (calls table)
  2. Posts to Make.com webhook → Gmail summary + Google Sheet row

Run: uvicorn sawt_agent:app --port 8002 --reload
Test: curl -X POST http://localhost:8002/trigger-call \
      -H "Content-Type: application/json" \
      -d '{"urgency":"HIGH","summary":"Patient with chest pain","from_number":"+971501234567"}'
"""

import os
import logging
import time
import json
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("SAWT")

app = FastAPI(title="NEXUS SAWT Agent", version="3.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VAPI_KEY = os.getenv("VAPI_API_KEY")
VAPI_HDRS = {"Authorization": f"Bearer {VAPI_KEY}", "Content-Type": "application/json"}

# Your n8n public URL base — used so VAPI can call back to /vapi-callback
# Use ngrok to expose locally: ngrok http 8002 → set NGROK_URL in .env
CALLBACK_BASE = os.getenv("NGROK_URL", os.getenv("N8N_WEBHOOK_BASE", "")).rstrip("/")

MAKE_WEBHOOK = os.getenv("MAKE_WEBHOOK_URL", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


# ── Helpers ───────────────────────────────────────────────

def build_system_prompt(triage: dict, source: str = "HERALD") -> str:
    urgency = triage.get("urgency", "HIGH")
    summary = triage.get("summary", "Patient requires urgent medical attention")
    location = triage.get("location", "Al Qua'a region, UAE")
    from_number = triage.get("from_number", "unknown")

    return f"""You are NEXUS, an AI medical coordination assistant for rural UAE communities.
You are making an outbound call on behalf of a patient who needs urgent care.

PATIENT SITUATION:
- Urgency Level: {urgency}
- Clinical Summary: {summary}
- Patient Location: {location}
- Caller Phone: {from_number}
- Alert Source: {source}

YOUR GOALS (follow in order):
1. Introduce yourself clearly as NEXUS AI assistant (NOT human)
2. State the patient situation in 2 clear sentences
3. Ask if the clinic/contact can assist or dispatch help
4. If YES: confirm ETA or next steps, get any reference number
5. Thank them and end the call professionally

STRICT RULES:
- NEVER claim to be human — you are an AI assistant
- Keep the call under 90 seconds total
- If the person responds in Arabic, switch fully to Arabic
- Be calm, professional, and respectful at all times
- When you have confirmed the response or exhausted options, end the call

FIRST MESSAGE (say this exactly):
مرحباً، أنا NEXUS، مساعد طبي ذكي. أتصل بشأن مريض يحتاج إلى رعاية عاجلة.
Hello, I am NEXUS, an AI medical assistant. I am calling regarding a patient who needs urgent care in {location}. Urgency level: {urgency}."""


def save_to_supabase(record: dict):
    """Write call record to Supabase via REST API (no SDK dependency issues)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        log.warning("Supabase credentials not set — skipping DB write")
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
            log.error(f"Supabase error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"Supabase write failed: {e}")


def notify_make(payload: dict):
    """
    Fire Make.com webhook so Make can:
      1. Send Gmail summary
      2. Append row to Google Sheets
    """
    if not MAKE_WEBHOOK or "REPLACE" in MAKE_WEBHOOK:
        log.warning("MAKE_WEBHOOK_URL not set — skipping Make.com notification")
        return
    try:
        r = requests.post(MAKE_WEBHOOK, json=payload, timeout=10)
        log.info(f"Make.com notified → {r.status_code}")
    except Exception as e:
        log.error(f"Make.com webhook failed: {e}")


def trigger_vapi_call(clinic_phone: str, triage: dict, source: str = "HERALD") -> dict:
    """Place an outbound call via VAPI and return the call object."""
    phone_number_id = os.getenv("VAPI_PHONE_NUMBER_ID")
    if not phone_number_id or "REPLACE" in phone_number_id:
        raise ValueError("VAPI_PHONE_NUMBER_ID not set in .env")

    # The serverUrl must be publicly reachable — use ngrok in dev
    callback_url = f"{CALLBACK_BASE}/vapi-callback" if CALLBACK_BASE else None

    payload = {
        "phoneNumberId": phone_number_id,
        "customer": {
            "number": clinic_phone,
            "name": "Al Ain Medical Clinic",
        },
        "assistant": {
            "model": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "systemPrompt": build_system_prompt(triage, source),
                "temperature": 0.3,
                "maxTokens": 400,
            },
            "voice": {
                "provider": "11labs",
                "voiceId": "21m00Tcm4TlvDq8ikWAM",  # Rachel
                "stability": 0.5,
                "similarityBoost": 0.75,
            },
            "firstMessage": (
                "مرحباً، أنا NEXUS، مساعد طبي ذكي. "
                "Hello, I am NEXUS, an AI medical assistant calling about a patient who needs urgent care."
            ),
            "endCallMessage": "Thank you for your help. Goodbye. شكراً جزيلاً.",
            "endCallFunctionEnabled": True,
            "maxDurationSeconds": 120,
            "backchannelingEnabled": True,
            "backgroundDenoisingEnabled": True,
            "transcriber": {
                "provider": "deepgram",
                "model": "nova-2",
                "language": "multi",
                "smartFormat": True,
            },
            # VAPI posts end-of-call report to this URL
            **({"serverUrl": callback_url} if callback_url else {}),
        },
        "metadata": {
            "urgency": triage.get("urgency"),
            "source": source,
            "from_number": triage.get("from_number", ""),
            "nexus_v": "3.1",
        },
    }

    r = requests.post(
        "https://api.vapi.ai/call/phone",
        headers=VAPI_HDRS,
        json=payload,
        timeout=15,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(f"VAPI error {r.status_code}: {r.text[:300]}")

    call = r.json()
    log.info(f"✅ SAWT call initiated | call_id={call.get('id')} → {clinic_phone}")
    return call


# ── API Endpoints ─────────────────────────────────────────

@app.post("/trigger-call")
async def trigger_call(request: Request):
    """
    Called by n8n Emergency Pipeline when HERALD detects HIGH/EMERGENCY
    or by BASAR directly when a fall is detected.
    """
    data = await request.json()

    urgency = data.get("urgency", "HIGH")
    summary = data.get("summary", "Patient requires urgent attention")
    source = data.get("source", "HERALD")
    from_number = data.get("from_number", data.get("from", "unknown"))
    phone = data.get("clinic_phone") or os.getenv("DEMO_CLINIC_PHONE")

    if not phone:
        raise HTTPException(
            status_code=400,
            detail="No clinic_phone provided and DEMO_CLINIC_PHONE not set in .env",
        )

    triage = {
        "urgency": urgency,
        "summary": summary,
        "location": data.get("location", "Al Qua'a region, UAE"),
        "from_number": from_number,
    }

    call = trigger_vapi_call(phone, triage, source)
    call_id = call.get("id", f"unknown_{int(time.time())}")

    # Save initial record immediately (will be updated by /vapi-callback)
    save_to_supabase({
        "call_id": call_id,
        "from_number": from_number,
        "intent": "emergency_call",
        "urgency": urgency,
        "transcript": "",
        "ai_summary": summary,
        "outcome": "in_progress",
        "agent_used": f"SAWT+{source}",
    })

    return {
        "status": "call_initiated",
        "call_id": call_id,
        "phone": phone,
        "urgency": urgency,
    }


@app.post("/vapi-callback")
async def vapi_callback(request: Request):
    """
    VAPI fires this webhook when a call ends.
    Payload contains full transcript, duration, summary.
    We then:
      1. Update Supabase with full call details
      2. Notify Make.com → Gmail + Google Sheets
    """
    data = await request.json()

    # VAPI end-of-call report structure
    call_obj = data.get("call", data)  # VAPI may nest under "call"
    call_id = call_obj.get("id", f"vapi_{int(time.time())}")
    status = call_obj.get("status", "ended")
    transcript = call_obj.get("transcript", "")
    ended_at = call_obj.get("endedAt", "")
    started_at = call_obj.get("startedAt", "")
    duration = call_obj.get("endedAt", "")
    metadata = call_obj.get("metadata", {})
    summary = call_obj.get("summary", "")

    # Try to extract duration in seconds
    duration_seconds = None
    try:
        if started_at and ended_at:
            from datetime import datetime
            fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
            s = datetime.strptime(started_at[:26] + "Z", fmt)
            e = datetime.strptime(ended_at[:26] + "Z", fmt)
            duration_seconds = int((e - s).total_seconds())
    except Exception:
        pass

    urgency = metadata.get("urgency", "HIGH")
    source = metadata.get("source", "SAWT")
    from_number = metadata.get("from_number", "unknown")

    log.info(f"📞 VAPI callback | call_id={call_id} | status={status} | duration={duration_seconds}s")
    log.info(f"   Transcript length: {len(transcript)} chars")

    # Build unified record
    record = {
        "call_id": call_id,
        "from_number": from_number,
        "started_at": started_at or None,
        "ended_at": ended_at or None,
        "duration_seconds": duration_seconds,
        "intent": "emergency_call",
        "urgency": urgency,
        "transcript": transcript,
        "ai_summary": summary,
        "outcome": "completed" if status == "ended" else status,
        "agent_used": f"SAWT+{source}",
    }

    # 1. Save to Supabase
    save_to_supabase(record)

    # 2. Notify Make.com for Gmail + Google Sheets
    make_payload = {
        "call_id": call_id,
        "from_number": from_number,
        "urgency": urgency,
        "duration_seconds": duration_seconds,
        "transcript": transcript,
        "ai_summary": summary,
        "outcome": record["outcome"],
        "agent": f"SAWT+{source}",
        "started_at": started_at,
        "ended_at": ended_at,
        # Gmail-friendly HTML body
        "email_html": f"""
<h2>NEXUS Emergency Call Report</h2>
<p><b>Call ID:</b> {call_id}</p>
<p><b>Urgency:</b> {urgency}</p>
<p><b>From:</b> {from_number}</p>
<p><b>Duration:</b> {duration_seconds or 'N/A'} seconds</p>
<p><b>Summary:</b> {summary}</p>
<hr/>
<h3>Full Transcript</h3>
<pre style="font-family:monospace;white-space:pre-wrap">{transcript}</pre>
<hr/>
<p style="color:gray;font-size:12px">NEXUS Autonomous Emergency Response Platform v3.1 | Al Qua'a, UAE</p>
""",
    }
    notify_make(make_payload)

    return {"received": True, "call_id": call_id}


@app.get("/call-result/{call_id}")
async def call_result(call_id: str):
    """Fetch call transcript + outcome from VAPI directly."""
    r = requests.get(
        f"https://api.vapi.ai/call/{call_id}",
        headers=VAPI_HDRS,
        timeout=10,
    )
    result = r.json()
    return {
        "call_id": call_id,
        "status": result.get("status"),
        "transcript": result.get("transcript", ""),
        "ended_at": result.get("endedAt", ""),
        "summary": result.get("summary", ""),
    }


@app.get("/health")
def health():
    return {
        "agent": "SAWT",
        "status": "online",
        "vapi_key_set": bool(VAPI_KEY),
        "make_webhook_set": bool(MAKE_WEBHOOK and "REPLACE" not in MAKE_WEBHOOK),
        "supabase_set": bool(SUPABASE_URL),
        "callback_url": f"{CALLBACK_BASE}/vapi-callback" if CALLBACK_BASE else "NOT SET — set NGROK_URL",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("sawt_agent:app", host="0.0.0.0", port=8002, reload=True)