"""
NEXUS — SAWT Agent v3.1 (FIXED)
Endpoint: /trigger-call  (was /api/trigger-call — caused 404 in n8n)

Run: uvicorn agents.sawt_agent:app --port 8002 --reload
"""

import os, logging, time, requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path="D:/nexus/.env")
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("SAWT")

app = FastAPI(title="NEXUS SAWT Agent", version="3.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

VAPI_KEY             = os.getenv("VAPI_API_KEY")
VAPI_HDRS            = {"Authorization": f"Bearer {VAPI_KEY}", "Content-Type": "application/json"}
NGROK_URL            = os.getenv("NGROK_URL", "").rstrip("/")
MAKE_WEBHOOK         = os.getenv("MAKE_WEBHOOK_URL", "")
SUPABASE_URL         = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def build_prompt(triage: dict, source: str) -> str:
    return f"""You are NEXUS, an AI medical coordination assistant for rural UAE communities.
You are calling on behalf of a patient who needs urgent care.

SITUATION:
- Urgency: {triage.get('urgency','HIGH')}
- Summary: {triage.get('summary','Patient needs urgent attention')}
- Location: {triage.get('location',"Al Qua'a, UAE")}
- Source: {source}

GOALS:
1. Introduce yourself as NEXUS AI (never claim to be human)
2. State patient situation in 2 sentences
3. Ask if clinic can help or dispatch
4. Get confirmation/ETA
5. Thank them and end call

Keep call under 90 seconds. Switch to Arabic if they speak Arabic."""


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
        log.info(f"Supabase → {r.status_code}")
    except Exception as e:
        log.error(f"Supabase failed: {e}")


def notify_make(payload: dict):
    if not MAKE_WEBHOOK or "REPLACE" in MAKE_WEBHOOK:
        return
    try:
        r = requests.post(MAKE_WEBHOOK, json=payload, timeout=10)
        log.info(f"Make.com → {r.status_code}")
    except Exception as e:
        log.error(f"Make.com failed: {e}")


def place_vapi_call(phone: str, triage: dict, source: str) -> dict:
    phone_id = os.getenv("VAPI_PHONE_NUMBER_ID")
    if not phone_id:
        raise ValueError("VAPI_PHONE_NUMBER_ID not set")

    callback = f"{NGROK_URL}/vapi-callback" if NGROK_URL else None

    body = {
        "phoneNumberId": phone_id,
        "customer": {"number": phone, "name": "Al Ain Medical Clinic"},
        "assistant": {
            "model": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "systemPrompt": build_prompt(triage, source),
                "temperature": 0.3,
                "maxTokens": 400
            },
            "voice": {
                "provider": "11labs",
                "voiceId": "21m00Tcm4TlvDq8ikWAM",
                "stability": 0.5,
                "similarityBoost": 0.75
            },
            "firstMessage": (
                "مرحباً، أنا NEXUS، مساعد طبي ذكي. "
                "Hello, I am NEXUS, an AI medical assistant calling about a patient who needs urgent care."
            ),
            "endCallMessage": "Thank you. Goodbye. شكراً.",
            "endCallFunctionEnabled": True,
            "maxDurationSeconds": 120,
            "backchannelingEnabled": True,
            "backgroundDenoisingEnabled": True,
            "transcriber": {"provider":"deepgram","model":"nova-2","language":"multi","smartFormat":True},
            **({"serverUrl": callback} if callback else {})
        },
        "metadata": {
            "urgency":     triage.get("urgency"),
            "source":      source,
            "from_number": triage.get("from_number",""),
            "nexus_v":     "3.1"
        }
    }

    r = requests.post("https://api.vapi.ai/call/phone", headers=VAPI_HDRS, json=body, timeout=15)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"VAPI {r.status_code}: {r.text[:200]}")

    call = r.json()
    log.info(f"✅ Call initiated | id={call.get('id')} → {phone}")
    return call


# ── THIS IS THE FIXED ENDPOINT — was /api/trigger-call causing 404 ──
@app.post("/trigger-call")
async def trigger_call(request: Request):
    data     = await request.json()
    urgency  = data.get("urgency", "HIGH")
    summary  = data.get("summary", "Patient requires urgent attention")
    source   = data.get("source", "HERALD")
    from_num = data.get("from_number", data.get("from", "unknown"))
    phone    = data.get("clinic_phone") or os.getenv("DEMO_CLINIC_PHONE")

    if not phone:
        raise HTTPException(status_code=400, detail="No phone. Set DEMO_CLINIC_PHONE in .env")

    triage = {
        "urgency":      urgency,
        "summary":      summary,
        "location":     data.get("location", "Al Qua'a, UAE"),
        "from_number":  from_num
    }

    call    = place_vapi_call(phone, triage, source)
    call_id = call.get("id", f"vapi_{int(time.time())}")

    # Save initial record to Supabase
    save_to_supabase({
        "call_id":    call_id,
        "from_number": from_num,
        "intent":     "emergency_call",
        "urgency":    urgency,
        "transcript": "",
        "ai_summary": summary,
        "outcome":    "in_progress",
        "agent_used": f"SAWT+{source}"
    })

    return {"status":"call_initiated","call_id":call_id,"phone":phone,"urgency":urgency}


@app.post("/vapi-callback")
async def vapi_callback(request: Request):
    """VAPI fires this when call ends — save transcript + notify Make.com"""
    data       = await request.json()
    call_obj   = data.get("call", data)
    call_id    = call_obj.get("id", f"vapi_{int(time.time())}")
    transcript = call_obj.get("transcript", "")
    summary    = call_obj.get("summary", "")
    started    = call_obj.get("startedAt", "")
    ended      = call_obj.get("endedAt", "")
    metadata   = call_obj.get("metadata", {})
    urgency    = metadata.get("urgency", "HIGH")
    source     = metadata.get("source", "SAWT")
    from_num   = metadata.get("from_number", "unknown")

    duration = None
    try:
        if started and ended:
            from datetime import datetime
            s = datetime.fromisoformat(started.replace("Z",""))
            e = datetime.fromisoformat(ended.replace("Z",""))
            duration = int((e - s).total_seconds())
    except Exception:
        pass

    log.info(f"📞 Callback | id={call_id} | duration={duration}s | transcript={len(transcript)}chars")

    record = {
        "call_id":          call_id,
        "from_number":      from_num,
        "started_at":       started or None,
        "ended_at":         ended or None,
        "duration_seconds": duration,
        "intent":           "emergency_call",
        "urgency":          urgency,
        "transcript":       transcript,
        "ai_summary":       summary,
        "outcome":          "completed",
        "agent_used":       f"SAWT+{source}"
    }
    save_to_supabase(record)

    notify_make({
        "call_id":          call_id,
        "from_number":      from_num,
        "urgency":          urgency,
        "duration_seconds": duration,
        "transcript":       transcript,
        "ai_summary":       summary,
        "outcome":          "completed",
        "source":           source,
        "location":         "Al Qua'a, UAE"
    })

    return {"received": True, "call_id": call_id}


@app.get("/health")
def health():
    return {
        "agent":        "SAWT",
        "status":       "online",
        "vapi_key":     bool(VAPI_KEY),
        "callback_url": f"{NGROK_URL}/vapi-callback" if NGROK_URL else "NOT SET",
        "make":         bool(MAKE_WEBHOOK and "REPLACE" not in MAKE_WEBHOOK),
        "supabase":     bool(SUPABASE_URL)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agents.sawt_agent:app", host="0.0.0.0", port=8002, reload=True)