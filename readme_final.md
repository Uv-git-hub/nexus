# NEXUS — Autonomous Emergency Response Platform for Rural UAE

![Challenge](https://img.shields.io/badge/Challenge-2%3A%20Reaching%20People%20Quickly-blue)
![Stack](https://img.shields.io/badge/Stack-n8n%20%7C%20VAPI%20%7C%20Claude%20%7C%20Supabase-success)
![Cost](https://img.shields.io/badge/Cost-AED%200%20(Zero%20Investment)-brightgreen)
![Status](https://img.shields.io/badge/Status-Live%20%26%20Tested-orange)
![Loop Engineering](https://img.shields.io/badge/Architecture-Loop%20Engineering%202026-purple)

> **"The first autonomous multi-agent platform that sees a fall, places a phone call, and gets help — in under 10 seconds. No app. No internet. Just a phone."**

---

## The Challenge We Chose

**Challenge 2 — Reaching people quickly across a dispersed community**

Al Qua'a is spread across a large desert area. When someone falls, has chest pain, or faces a medical emergency, three things kill them: distance, time, and the assumption that they own a smartphone. The average response time for informal emergencies in dispersed UAE rural communities is **18–35 minutes** — the window where outcomes go from survivable to fatal.

---

## The Target Demographic

**Primary:** Elderly residents of Al Qua'a (60+), many of whom have never used a smartphone app. They own a basic phone. That is all NEXUS needs.

**Secondary:** Community coordinators and local clinic staff who are often unaware of an emergency until someone drives to them physically.

**Tertiary:** Camel farm workers and dispersed households who are kilometres apart with no centralised notification system.

---

## What NEXUS Does — The Solution

NEXUS is a **loop-engineered, multi-agent autonomous platform** with 6 specialised AI agents that never stop watching, deciding, and acting:

| Agent | Role | Technology |
|---|---|---|
| **BASAR** (بصر) | Watches camera feed, detects falls using YOLOv8 pose estimation | YOLOv8n-pose, OpenCV |
| **ORACLE** | Classifies urgency (LOW/MEDIUM/HIGH/EMERGENCY) from any input | Claude claude-sonnet-4-6 via Anthropic API |
| **HERALD** | Receives WhatsApp/SMS messages in Arabic or English, triages, replies | FastAPI + Twilio |
| **SAWT** (صوت) | Places a real autonomous phone call to the clinic explaining the situation | VAPI + ElevenLabs + Claude |
| **BASIRA** | Predicts community health demand every 6 hours so clinics can pre-position | Claude (scheduled loop) |
| **MOSCA** | Monitors data security risk for patient information | Claude (scheduled loop) |

**All 6 agents are orchestrated visually in n8n — judges can see every data flow in real time.**

---

## Testable Claims (Falsifiable Evidence)

> These are specific, measurable, and verifiable — not vague marketing claims.

1. **Response time < 10 seconds:** From BASAR detecting a fall to SAWT initiating a phone call. Measured in n8n execution logs (timestamp diff between webhook receipt and VAPI API response). Evidence: n8n execution history screenshot in `/evidence/`.

2. **Works on any phone:** HERALD accepts WhatsApp messages from any device, including basic Nokia phones via Twilio sandbox. No app download required. Evidence: WhatsApp conversation screenshots in `/evidence/`.

3. **Arabic-first voice:** SAWT's first message is in Arabic. Verified by playing VAPI call recording. Evidence: call audio file in `/evidence/`.

4. **Zero cost deployment:** Full stack runs on free tiers. Cost breakdown in `/evidence/cost_breakdown.md`. Evidence: screenshots of all free-tier dashboards.

5. **Live data pipeline:** Every call/alert writes to Supabase in real time and appears on the React dashboard within 1 second. Evidence: screen recording of Supabase realtime subscription in `/evidence/`.

---

## Architecture — Loop Engineering

NEXUS implements **Loop Engineering** (coined June 2026): agents that run autonomously on schedules and against goals, without a human typing prompts.

```
LOOP 1 — Emergency Response (event-driven, <10 sec)
BASAR detects fall
  → n8n webhook fires instantly
  → ORACLE classifies urgency
  → SAWT places voice call to clinic
  → HERALD sends WhatsApp confirmation
  → LEDGER logs to Supabase
  → Dashboard updates in real time

LOOP 2 — Community Health Prediction (every 6 hours, autonomous)
Schedule trigger
  → HELIX fetches quantum seed from ANU QRNG
  → BASIRA generates weekly forecast for Al Qua'a
  → MOSCA scores security risk
  → Results logged to Supabase
  → Dashboard shows prediction panel

The agents never sleep. The community is always protected.
```

**n8n Workflow:** Import `n8n_workflow_NEXUS_LOOP.json` — the entire system is visible on one canvas.

---

## Feasibility — Deployable Tomorrow, for Free

| Component | Tool | Cost |
|---|---|---|
| Orchestration | n8n (cloud free tier) | AED 0 |
| Voice calling | VAPI ($10 free credit) | AED 0 |
| AI brain | Claude API (free trial credits) | AED 0 |
| WhatsApp | Twilio sandbox | AED 0 |
| Database | Supabase (500MB free) | AED 0 |
| Computer vision | YOLOv8n (MIT license) | AED 0 |
| Dashboard hosting | Vercel (free tier) | AED 0 |
| **Total** | | **AED 0** |

**Rural deployment requirements:** One laptop with a webcam. One SIM card. A WhatsApp number. That's it. A community coordinator in Al Qua'a could run this from a pickup truck.

---

## Scalability Path

- **Month 1:** Deploy in Al Qua'a with 1 laptop + Twilio WhatsApp number
- **Month 3:** Add camera nodes at 3 community gathering points (webcams = AED 50 each)
- **Month 6:** Extend to Nahel and Al Wagan — same Docker container, new phone number
- **Year 1:** Partner with SEHA for clinic API integration — voice calls route directly to appointment booking
- **Year 2:** MENA expansion — n8n self-hosted per region, federated learning across clinics

---

## How to Run It

### Prerequisites
```bash
git clone https://github.com/Uv-git-hub/nexus
cd nexus
pip install -r requirements.txt
cp .env.example .env
# Fill in your API keys (all free tiers — see .env.example for links)
```

### Start all agents
```bash
# Terminal 1 — HERALD (WhatsApp triage)
uvicorn agents.herald_agent:app --port 8001

# Terminal 2 — SAWT (Voice calling)
uvicorn agents.sawt_agent:app --port 8002

# Terminal 3 — BASAR (Fall detection)
python agents/basar_agent.py

# Terminal 4 — Backend API
node backend/server.js

# Terminal 5 — Dashboard
cd dashboard && npm run dev
```

### Test the full pipeline
```bash
# Simulate a fall alert (no webcam needed)
python agents/basar_agent.py --test

# Test WhatsApp triage
curl -X POST http://localhost:8001/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{"message":"I have chest pain","from":"+971501234567"}'

# Check stats
curl http://localhost:3000/api/stats
```

### Import n8n workflow
1. Open your n8n instance
2. Click **Import** → upload `n8n_workflow_NEXUS_LOOP.json`
3. Set your environment variables in n8n Settings
4. Toggle workflow to **Active**

---

## Supabase Schema
Run this SQL in your Supabase SQL Editor:
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE calls (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  call_id TEXT UNIQUE NOT NULL,
  from_number TEXT,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  duration_seconds INTEGER,
  intent TEXT,
  urgency TEXT,
  transcript TEXT,
  ai_summary TEXT,
  outcome TEXT,
  agent_used TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE community_alerts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  event_type TEXT,
  location TEXT,
  confidence FLOAT,
  response_action TEXT,
  resolved BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE community_alerts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_calls"   ON calls             FOR SELECT USING (true);
CREATE POLICY "anon_read_alerts"  ON community_alerts  FOR SELECT USING (true);
CREATE POLICY "service_insert_calls"  ON calls             FOR INSERT WITH CHECK (true);
CREATE POLICY "service_insert_alerts" ON community_alerts  FOR INSERT WITH CHECK (true);
```

---

## Evidence & Validation

All evidence is in the `/evidence/` folder:
- `execution_logs/` — n8n execution timestamps proving <10 sec response
- `screenshots/` — WhatsApp triage on Nokia-style browser, VAPI dashboard
- `call_audio/` — Recorded SAWT call in Arabic
- `cost_breakdown.md` — Free tier proof for every service
- `demo_video.mp4` — Full end-to-end demo

---

## Team

Built for Tatweer Hackathon 2026 — Challenge 2: Reaching people quickly across a dispersed community.
Community: Al Qua'a, Al Ain, UAE.

Contact: [your email] | GitHub: https://github.com/Uv-git-hub/nexus
