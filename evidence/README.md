# NEXUS — Autonomous Emergency Response Platform

![Challenge](https://img.shields.io/badge/Challenge-2%3A%20Reaching%20People%20Quickly-blue)
![Stack](https://img.shields.io/badge/Stack-n8n%20%7C%20Claude%20%7C%20YOLOv8%20%7C%20Supabase-success)
![Cost](https://img.shields.io/badge/Cost-AED%200%20Zero%20Investment-brightgreen)
![Status](https://img.shields.io/badge/Status-Live%20%26%20Tested-orange)
![Architecture](https://img.shields.io/badge/Architecture-Loop%20Engineering%202026-purple)

> **"The first autonomous multi-agent platform that sees a fall and alerts the clinic in under 10 seconds. No app. No smartphone. Just a camera and a phone."**

---

## 1. The Challenge and the Problem — Criterion 2: Relevance

**Challenge 2: Reaching people quickly across a dispersed community.**

Al Qua'a spans a large desert region of Al Ain, UAE. Three things kill people in rural medical emergencies:

- **Distance:** Nearest clinic is 15–40 minutes away by road
- **Time:** Informal emergency response averages 18–35 minutes — within the fatal window
- **Technology barriers:** Majority of elderly residents (60+) have never downloaded an app

When an elderly person falls alone at 2 AM, no automated system exists to detect it and alert anyone. NEXUS closes that gap — without requiring any action from the victim.

---

## 2. Who It Is For — Criterion 1: Impact

| Group | Description | Estimated Size |
|---|---|---|
| **Primary** | Elderly residents of Al Qua'a (60+), basic phone only | ~400–600 individuals |
| **Secondary** | Camel farm workers, dispersed households far from clinic | ~200–400 workers |
| **Tertiary** | Al Qua'a clinic staff with no automated early-warning system | ~15–30 staff |

**Total directly affected: 800–1,200 residents in the Al Qua'a–Nahel corridor.**

Cost of inaction: a resident falls, cannot reach a phone, nobody knows for hours. NEXUS changes that to under 10 seconds.

---

## 3. The Solution — Criteria 2 + 4: Relevance + Readiness

NEXUS is a **4-agent autonomous platform** with two trigger paths — neither requires a smartphone.

### Two Input Paths

```
PATH 1 — Web Form (any device, any browser)
  Resident or coordinator fills NEXUS.html form
  → Make.com webhook fires instantly
  → Gmail alert dispatched with full patient details
  → Twilio SMS sent to clinic coordinator
  → Row written to Google Sheets automatically
  → All in under 10 seconds, zero human intervention

PATH 2 — Camera (BASAR autonomous fall detection)
  YOLOv8n-pose watches webcam 24/7
  → Head-below-hip ratio detects fallen posture
  → 3 consecutive frame confirmation (no false positives)
  → Make.com fires EMERGENCY alert automatically
  → Gmail + SMS + Google Sheets in under 10 seconds
  → No action required from the victim
```

### The 4 Agents

| Agent | Real-World Problem Solved | Technology |
|---|---|---|
| **BASAR** (بصر) | Elderly person falls alone at 2 AM. No phone nearby. Nobody knows for hours. BASAR watches 24/7 and alerts the clinic within 10 seconds — zero human trigger. | YOLOv8n-pose, OpenCV |
| **ORACLE** | A coordinator cannot assess severity quickly. Is this a cold or a stroke? ORACLE classifies every input as LOW/MEDIUM/HIGH/EMERGENCY in under 2 seconds, in Arabic or English. | Claude claude-sonnet-4-6 |
| **BASIRA** | The clinic has no idea how many patients to expect next week. BASIRA runs every 6 hours, analyses alert history, and predicts weekly health demand so the clinic can pre-position staff and supplies. | Claude (scheduled loop) |
| **SENTINEL** | Patient data (names, phones, medical summaries) flows through multiple services with nobody monitoring for breaches. SENTINEL scans every 5 minutes and scores risk with a MOSCA Score (0–100). 100% offline, no API key needed. | Rule-based detection |

---

## 4. Impact and Testable Claims — Criterion 6: Falsifiability

### Claim 1: Alert delivered in under 10 seconds
From form submission or BASAR fall detection → Gmail + SMS received.

**Evidence:** `evidence/make_execution_log.png` — Make.com run showing webhook-to-email timestamp diff.

### Claim 2: BASAR detects falls with no GPU, no internet from the victim
YOLOv8n-pose runs on a standard laptop CPU. Fall confirmed across 3 consecutive frames to eliminate false positives.

**Evidence:** `evidence/basar_fall_screenshot.png` — camera window showing red FALL DETECTED overlay.
`evidence/gmail_basar_alert.png` — Gmail received with all fields populated.

### Claim 3: All alerts logged automatically with full metadata
15 fields logged per event: name, phone, urgency, summary, location, timestamp, falls, frames, people, uptime.

**Evidence:** `evidence/google_sheet.png` — populated spreadsheet screenshot.

### Claim 4: SENTINEL scores patient data security at 100/100
Rule-based threat detection runs offline with no API keys.

**Evidence:** `evidence/sentinel_report_1.json` — MOSCA Score 100, Risk LOW, System secure.

### Claim 5: BASIRA predicts 7-day health demand autonomously
Claude generates community-specific forecasts every 6 hours.

**Evidence:** `evidence/basira_prediction_*.json` — saved prediction with daily demand levels.

### Claim 6: Full deployment costs AED 0
Every component runs on a permanently free tier.

**Evidence:** `evidence/cost_breakdown.md` — screenshots of all free-tier dashboards.

### Honest Limitations
- YOLOv8 fall detection uses head-below-hip ratio — not clinically validated, a practical real-time approximation
- BASIRA predictions are pattern-based, not population-level medical data
- Make.com free tier allows 1,000 operations/month — sufficient for pilot, upgrade path exists

---

## 5. Feasibility and Deployment — Criterion 3: Feasibility

### What You Need to Deploy Today

| Item | Detail | Cost |
|---|---|---|
| Laptop / computer | Any CPU with 4GB RAM, built-in webcam | Already at clinic |
| SIM card | Any UAE network | AED 10–30 |
| Internet connection | 3G / mobile data (2 Mbps sufficient) | Already available |
| Setup time | Clone repo, fill .env, activate Make.com scenario | ~30 minutes |

**A community coordinator in Al Qua'a could deploy NEXUS from a pickup truck.**

### Full Cost Breakdown — AED 0

| Component | Tool | Free Tier |
|---|---|---|
| Fall detection | YOLOv8n (MIT license) | Open source |
| AI classification + prediction | Claude API (Anthropic) | Free trial credits |
| Automation pipeline | Make.com | 1,000 ops/month |
| Email alerts | Gmail API | Unlimited |
| SMS alerts | Twilio | Sandbox free |
| Spreadsheet log | Google Sheets | Unlimited |
| Database | Supabase | 500MB free |
| Workflow orchestration | n8n cloud | 2,500 exec/month |
| Security monitoring | SENTINEL (offline) | AED 0 forever |
| **TOTAL** | | **AED 0** |

---

## 6. Scalability — Criterion 5: Scalability

| Timeline | Action | Cost |
|---|---|---|
| **Month 1** | Deploy in Al Qua'a — 1 laptop, 1 SIM, Make.com active | AED 0 |
| **Month 3** | Add cameras at 3 community gathering points | AED 50 per webcam |
| **Month 6** | Clone to Nahel and Al Wagan — same repo, new .env | AED 0 |
| **Year 1** | SEHA clinic API integration — alerts route to appointment booking | Partnership |
| **Year 2** | MENA expansion — n8n self-hosted per region, federated BASAR network | ~AED 800/month |

The Make.com scenario and n8n workflow are **exportable JSON** — a new community is live in under 1 hour with no technical knowledge beyond filling a .env file.

---

## 7. Evidence and Validation — Criterion 6: Falsifiability

All evidence is in `/evidence/`:

| File | What It Proves |
|---|---|
| `make_execution_log.png` | Make.com run showing webhook → Gmail in under 10 seconds |
| `gmail_basar_alert.png` | Gmail received from BASAR fall detection, all fields correct |
| `gmail_form_alert.png` | Gmail received from NEXUS.html form submission |
| `sms_alert.png` | Twilio SMS received on demo phone |
| `google_sheet.png` | Spreadsheet row with all 15 columns auto-populated |
| `basar_fall_screenshot.png` | Camera window showing red FALL DETECTED overlay + skeleton |
| `basar_test_frame.jpg` | Auto-saved by --test mode |
| `fall_alert_*.json` | Raw payload sent on fall detection |
| `sentinel_report_1.json` | MOSCA Score 100/100, system secure ✅ |
| `cost_breakdown.md` | Free tier proof for every service |
| `demo_video.mp4` | End-to-end demo: form + camera fall → Gmail in real time |

---

## 8. How to Run and Verify — Criterion 7: Documentation

### Setup
```bash
git clone https://github.com/Uv-git-hub/nexus
cd nexus
pip install -r requirements.txt
# Fill in .env (all free — see .env.example)
```

### Test 1 — Form pipeline (→ Gmail + SMS + Sheets in 10 seconds)
1. Open `NEXUS.html` in any browser
2. Fill: name, +971 phone, Al Qua'a, Emergency type
3. Click Submit → check Gmail within 10 seconds

### Test 2 — BASAR fall detection
```powershell
# Real camera (lie flat to trigger):
python agents\basar_agent.py

# Test without camera (fires real Gmail):
python agents\basar_agent.py --test
```

### Test 3 — SENTINEL security scan
```powershell
python agents\sentinel_agent.py --once
# Output: MOSCA Score: 100/100 | Risk: LOW | System secure ✅
```

### Test 4 — BASIRA health prediction
```powershell
python agents\basira_agent.py --once
# Output: 7-day demand forecast saved to evidence/
```

### Run all agents simultaneously
```powershell
# Terminal 1
python agents\basar_agent.py

# Terminal 2
python agents\sentinel_agent.py

# Terminal 3
python agents\basira_agent.py

# Terminal 4
node backend\server.js
```

### Tools Used
Claude claude-sonnet-4-6 (Anthropic), YOLOv8n-pose, n8n cloud, Make.com, Twilio, Supabase, FastAPI, OpenCV, Google Sheets API, Gmail API, Express.js

---

## Architecture — Loop Engineering

```
LOOP 1 — Emergency Response (event-driven, <10 seconds)
──────────────────────────────────────────────────────
  [BASAR] Webcam detects fall (YOLOv8, 3-frame confirm)
       ↓
  [Make.com] Routes in parallel:
       ├── Gmail alert (HTML, 15 fields)
       ├── Twilio SMS (urgency, name, location)
       └── Google Sheets row (auto-logged)
       ↓
  [Supabase] Full record stored

LOOP 2 — Health Prediction (every 6 hours, autonomous)
──────────────────────────────────────────────────────
  Schedule trigger
       ↓
  [BASIRA/Claude] 7-day demand forecast for Al Qua'a
       ↓
  [SENTINEL] MOSCA security scan
       ↓
  Evidence folder updated

The agents never sleep. The community is always protected.
```

---

## Team

Built for **Tatweer Hackathon 2026 — Challenge 2: Reaching people quickly.**
Community: Al Qua'a, Al Ain, UAE · Loop Engineering 2026 · AED 0 deployment

GitHub: https://github.com/Uv-git-hub/nexus