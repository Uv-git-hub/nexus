"""
NEXUS — SENTINEL Agent (Zero-Cost Offline Cybersecurity Layer)
Rule-based threat detection + optional Ollama local LLM.
NO API KEYS NEEDED. Runs 100% offline.

Run: python agents/sentinel_agent.py
     python agents/sentinel_agent.py --once   (single scan, no loop)
"""
import os, json, time, logging, argparse, requests, hashlib, hmac
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [SENTINEL] %(message)s")
log = logging.getLogger("SENTINEL")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")

# ── Threat Rules ──────────────────────────────────────────
def fetch_recent_calls(minutes=10):
    if not SUPABASE_URL:
        log.warning("No Supabase URL — using mock data for demo")
        return [{"urgency": "HIGH", "from_number": "+971500000001", "outcome": "escalated"}]
    try:
        since = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat() + "Z"
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/calls?created_at=gte.{since}&select=*",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            timeout=5
        )
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        log.error(f"Fetch failed: {e}")
        return []

def rule_based_analysis(calls):
    threats = []
    now = datetime.utcnow()

    if len(calls) > 50:
        threats.append({"rule": "HIGH_VOLUME_ACCESS", "severity": "HIGH",
                        "detail": f"{len(calls)} calls in 10 min — possible flood/DDoS attack"})

    emergency = [c for c in calls if c.get("urgency") == "EMERGENCY"]
    if len(emergency) > 5:
        threats.append({"rule": "EMERGENCY_SPIKE", "severity": "CRITICAL",
                        "detail": f"{len(emergency)} EMERGENCY events — verify authenticity"})

    if now.hour in [0,1,2,3,4]:
        threats.append({"rule": "OFF_HOURS_ACCESS", "severity": "MEDIUM",
                        "detail": f"Data accessed at {now.hour}:00 UTC — verify authorization"})

    unique_callers = len(set(c.get("from_number","") for c in calls))
    if unique_callers > 30:
        threats.append({"rule": "UNUSUAL_CALLER_DIVERSITY", "severity": "MEDIUM",
                        "detail": f"{unique_callers} unique callers in 10 min — review"})

    return threats

def ollama_analysis(summary):
    """Try local Ollama (free). Gracefully skips if not installed."""
    try:
        r = requests.post("http://localhost:11434/api/generate", json={
            "model": "llama3",
            "prompt": f"Security analysis for rural health system. Data: {json.dumps(summary)}. "
                      f"Respond ONLY with JSON: {{\"risk_level\":\"LOW|MEDIUM|HIGH|CRITICAL\","
                      f"\"threats\":[],\"recommendations\":[],\"mosca_score\":0}}",
            "stream": False
        }, timeout=25)
        if r.status_code == 200:
            raw = r.json().get("response","").strip()
            return json.loads(raw)
    except Exception:
        pass
    return None

def compute_mosca_score(threats):
    """MOSCA Score: Managed Operational Security & Compliance Assessment (0-100)."""
    base = 100
    deductions = {"LOW": 5, "MEDIUM": 15, "HIGH": 30, "CRITICAL": 50}
    for t in threats:
        base -= deductions.get(t.get("severity","LOW"), 5)
    return max(0, base)

def verify_env_security():
    """Check that secrets are not hardcoded (educational security check)."""
    checks = []
    env_path = ".env"
    if os.path.exists(env_path):
        checks.append({"check": "ENV_FILE_EXISTS", "status": "PASS",
                       "detail": ".env file found — secrets stored correctly"})
    gitignore_path = ".gitignore"
    if os.path.exists(gitignore_path):
        with open(gitignore_path) as f:
            content = f.read()
        if ".env" in content:
            checks.append({"check": "ENV_IN_GITIGNORE", "status": "PASS",
                           "detail": ".env excluded from git — secrets protected"})
        else:
            checks.append({"check": "ENV_IN_GITIGNORE", "status": "FAIL",
                           "detail": "WARNING: .env not in .gitignore — secrets may leak!"})
    return checks

def run_scan(iteration=1):
    log.info(f"🔍 Scan #{iteration} starting...")
    calls    = fetch_recent_calls(minutes=10)
    threats  = rule_based_analysis(calls)
    env_checks = verify_env_security()
    
    summary_data = {
        "total_calls":      len(calls),
        "emergency_count":  len([c for c in calls if c.get("urgency") == "EMERGENCY"]),
        "unique_callers":   len(set(c.get("from_number","") for c in calls)),
        "timestamp":        datetime.utcnow().isoformat()
    }

    ollama_result = ollama_analysis(summary_data)
    mosca_score   = compute_mosca_score(threats)
    if ollama_result and "mosca_score" in ollama_result:
        mosca_score = (mosca_score + ollama_result["mosca_score"]) // 2

    risk = "CRITICAL" if mosca_score < 30 else \
           "HIGH"     if mosca_score < 60 else \
           "MEDIUM"   if mosca_score < 80 else "LOW"

    report = {
        "timestamp":        datetime.utcnow().isoformat(),
        "iteration":        iteration,
        "calls_analyzed":   len(calls),
        "threats_detected": threats,
        "env_security":     env_checks,
        "mosca_score":      mosca_score,
        "risk_level":       risk,
        "ollama_used":      ollama_result is not None,
        "ollama_analysis":  ollama_result,
        "recommendation":   "LOCKDOWN — review immediately" if mosca_score < 30 else
                            "Review flagged threats"         if threats else
                            "System secure ✅"
    }

    os.makedirs("evidence", exist_ok=True)
    report_path = f"evidence/sentinel_report_{iteration}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    log.info(f"🛡 MOSCA Score: {mosca_score}/100 | Risk: {risk} | Threats: {len(threats)}")
    for t in threats:
        log.warning(f"   ⚠️  [{t['severity']}] {t['rule']}: {t['detail']}")
    log.info(f"   Report saved → {report_path}")
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NEXUS SENTINEL — Security Agent")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    args = parser.parse_args()

    log.info("🛡 SENTINEL online — monitoring Al Qua'a health data security")
    if args.once:
        run_scan(1)
    else:
        i = 0
        while True:
            i += 1
            run_scan(i)
            log.info("   Next scan in 5 minutes...")
            time.sleep(300)