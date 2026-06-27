# NEXUS — Autonomous Emergency Response Platform

![Challenge](https://img.shields.io/badge/Challenge-2%3A%20Reaching%20People%20Quickly-blue)
![Cost](https://img.shields.io/badge/Deployment%20Cost-AED%200-brightgreen)
![Status](https://img.shields.io/badge/Status-Live%20%26%20Tested-orange)

## 1. The Challenge and The Problem (Criterion 2 — Relevance)

**Challenge 2: Reaching people quickly across a dispersed community.**

Al Qua'a spans a large desert region. When someone falls, has chest pain, or collapses, three things delay help: **distance** (nearest clinic 15–40 min away), **time** (informal emergency response averages 18–35 min), and **technology barriers** (majority of elderly residents have never used a smartphone app). People die in the gap between the event and the call.

## 2. Who It Is For (Criterion 1 — Impact)

**Primary:** Elderly residents of Al Qua'a (60+) who own a basic phone and have never downloaded an app.  
**Secondary:** Farm workers and dispersed households kilometres from any clinic.  
**Tertiary:** Al Qua'a clinic staff who currently have no automated early-warning system.

Estimated directly affected: 800–1,200 residents in the Al Qua'a–Nahel corridor.

## 3. The Solution (Criterion 2 — Relevance, Criterion 4 — Readiness)

NEXUS is a **6-agent autonomous platform** that converts any emergency signal — a WhatsApp message, a form submission, or a camera detecting a fall — into immediate coordinated action with zero human intervention.

| Agent | What It Does | Technology |
|---|---|---|
| BASAR (بصر) | Watches webcam, detects falls using YOLOv8 pose estimation | YOLOv8n-pose, OpenCV |
| ORACLE | Classifies urgency: LOW/MEDIUM/HIGH/EMERGENCY | Claude claude-sonnet-4-6 |
| HERALD | Receives WhatsApp, triages in Arabic or English, replies | FastAPI + Twilio |
| SAWT (صوت) | Places autonomous phone call to clinic in Arabic | VAPI + ElevenLabs |
| BASIRA | Predicts health demand every 6h | Claude (scheduled) |
| SENTINEL | Monitors data security, MOSCA score 0-100 | Rule-based + optional Ollama |

**Three trigger paths — none require a smartphone:**
1. WhatsApp message → HERALD → ORACLE triage → SAWT voice call to clinic + Make.com (Gmail + SMS + Sheets)
2. Web form submission → Make.com → Gmail + SMS + Sheets (logged instantly)
3. Camera fall detection → BASAR → Make.com → Gmail + SMS + Sheets + n8n → SAWT voice call

## 4. Impact and Testable Claims (Criterion 6 — Falsifiability)

**Claim 1:** Time from form/WhatsApp submission to Gmail+SMS alert: **under 10 seconds.**  
Evidence: Make.com execution logs in `/evidence/make_execution_log.png` — timestamp diff between webhook receipt and module completion.

**Claim 2:** BASAR fall detection works on a standard webcam with no GPU.  
Evidence: Run `python basar_agent.py --test` — fires Make.com webhook, Gmail arrives within 8 seconds. Screenshot in `/evidence/basar_test_email.png`.

**Claim 3:** Works with zero apps on the resident's side.  
Evidence: WhatsApp triage works from any SMS-capable phone via Twilio sandbox. No download required.

**Claim 4:** Full deployment cost = AED 0.  
Evidence: `/evidence/cost_breakdown.md` — screenshots of all free-tier dashboards.

**Honest limitations:**  
- VAPI trial credits are limited; the voice call demo may require a top-up after heavy testing.  
- YOLOv8 fall detection is a proxy (head below hip) — not clinically validated.  
- Twilio WhatsApp sandbox requires the resident to opt-in first ("join [word]").

## 5. Feasibility and Deployment (Criterion 3 — Feasibility)

| What you need | Details |
|---|---|
| Hardware | 1 laptop with webcam (AED 0 — already exists at most clinics) |
| Connectivity | Any mobile data connection (3G sufficient) |
| Phone | Any phone number (WhatsApp or basic SMS) |
| Setup time | ~30 minutes to clone, fill .env, activate Make.com scenario |

**Cost breakdown:**

| Component | Tool | Cost |
|---|---|---|
| Voice AI | VAPI + ElevenLabs | AED 0 (free credits) |
| AI triage | Claude API | AED 0 (free trial) |
| WhatsApp | Twilio sandbox | AED 0 |
| Automation | Make.com + n8n | AED 0 |
| Database | Supabase | AED 0 |
| Computer vision | YOLOv8n MIT license | AED 0 |
| **Total** | | **AED 0** |

**Maintenance:** The Make.com scenario runs 24/7 automatically. No IT staff required. The clinic coordinator checks Gmail + the Google Sheet.

## 6. Scalability (Criterion 5 — Scalability)

- **Month 1:** Al Qua'a — 1 laptop, 1 SIM, 1 Make.com scenario
- **Month 3:** Add camera nodes at 3 community points (webcams: AED 50 each)  
- **Month 6:** Clone to Nahel and Al Wagan — same Docker container, new phone number  
- **Year 1:** SEHA API integration — voice calls route to appointment booking directly  
- **Year 2:** MENA rollout — n8n self-hosted per region, federated BASAR network

The n8n workflow and Make.com scenario are exportable JSON — a new community is live in under 1 hour.

## 7. Evidence and Validation (Criterion 6 — Falsifiability)

All evidence is in `/evidence/`:
- `make_execution_log.png` — Make.com run showing <10s webhook→email
- `gmail_alert.png` — Received email with all fields populated
- `sms_alert.png` — Twilio SMS received
- `google_sheet.png` — Spreadsheet row written automatically
- `basar_test.png` — BASAR --test mode output
- `cost_breakdown.md` — Free tier proof
- `whatsapp_demo.png` — WhatsApp triage conversation

## 8. How to Run and Verify (Criterion 7 — Documentation)

### Setup
```bash
git clone https://github.com/Uv-git-hub/nexus
cd nexus
pip install -r requirements.txt
cp .env.example .env
# Fill in your keys (all free — see .env.example for signup links)
```

### Test Make.com pipeline (form → Gmail + SMS)
1. Open `NEXUS.html` in browser
2. Fill form with your name, +971 number, any urgency
3. Click Submit
4. Check Gmail at yuvypandey143@gmail.com and SMS within 10 seconds

### Test BASAR (camera fall detection)
```bash
# No webcam needed:
python basar_agent.py --test
# With webcam:
python basar_agent.py
# Lie down in front of camera — fall alert fires to Make.com
```

### Test WhatsApp triage
```bash
# Send WhatsApp to your Twilio sandbox number:
# "I have chest pain" → gets EMERGENCY triage + voice call
curl -X POST http://localhost:8001/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{"message":"I have chest pain","from":"+971501234567"}'
```

### Test SENTINEL security
```bash
python sentinel_agent.py --once
# Outputs MOSCA score and security report to /evidence/
```

### Full system
```bash
# Terminal 1: HERALD
uvicorn herald_agent:app --port 8001
# Terminal 2: SAWT  
uvicorn sawt_agent:app --port 8002
# Terminal 3: BASAR
python basar_agent.py
# Terminal 4: Backend
node backend/server.js
```

**Tools used:** Claude claude-sonnet-4-6, VAPI, ElevenLabs, YOLOv8n, n8n, Make.com, Twilio, Supabase, FastAPI, Express.js, OpenCV

**Demo video:** [link to your video] — shows full pipeline from form submission to Gmail/SMS in real time.