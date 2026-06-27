"""
NEXUS — SENTINEL Agent (Zero-Cost Offline Cybersecurity)
Rule-based threat detection. No API keys. 100% offline.
Produces MOSCA Score (0-100) for patient data security.

Run FROM D:\nexus:
  python agents\sentinel_agent.py --once   ← single scan
  python agents\sentinel_agent.py          ← continuous (every 5 min)
"""

import os, json, time, logging, argparse, requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SENTINEL] %(message)s")
log = logging.getLogger("SENTINEL")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")


def fetch_recent_calls(minutes: int = 10) -> list:
    if not SUPABASE_URL:
        log.warning("No Supabase URL — using mock data for demo")
        return [{"urgency": "HIGH", "from_number": "+971500000001", "outcome": "escalated"}]
    try:
        since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/calls?created_at=gte.{since}&select=*",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"
            },
            timeout=5
        )
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        log.error(f"Supabase fetch failed: {e}")
        return []


def rule_based_analysis(calls: list) -> list:
    threats = []
    now = datetime.now(timezone.utc)

    if len(calls) > 50:
        threats.append({
            "rule": "HIGH_VOLUME_ACCESS",
            "severity": "HIGH",
            "detail": f"{len(calls)} calls in 10 min — possible flood or DDoS attack"
        })

    emergency = [c for c in calls if c.get("urgency") == "EMERGENCY"]
    if len(emergency) > 5:
        threats.append({
            "rule": "EMERGENCY_SPIKE",
            "severity": "CRITICAL",
            "detail": f"{len(emergency)} EMERGENCY events — verify authenticity"
        })

    if now.hour in (0, 1, 2, 3, 4):
        threats.append({
            "rule": "OFF_HOURS_ACCESS",
            "severity": "MEDIUM",
            "detail": f"Data accessed at {now.hour:02d}:00 UTC — verify authorization"
        })

    unique_callers = len(set(c.get("from_number", "") for c in calls))
    if unique_callers > 30:
        threats.append({
            "rule": "UNUSUAL_CALLER_DIVERSITY",
            "severity": "MEDIUM",
            "detail": f"{unique_callers} unique callers in 10 min — review"
        })

    return threats


def verify_env_security() -> list:
    checks = []
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

    env_path = os.path.join(root, '.env')
    if os.path.exists(env_path):
        checks.append({
            "check": "ENV_FILE_EXISTS",
            "status": "PASS",
            "detail": ".env file found — secrets stored correctly"
        })

    gitignore_path = os.path.join(root, '.gitignore')
    if os.path.exists(gitignore_path):
        with open(gitignore_path, encoding="utf-8") as f:
            content = f.read()
        if ".env" in content:
            checks.append({
                "check": "ENV_IN_GITIGNORE",
                "status": "PASS",
                "detail": ".env excluded from git — secrets protected"
            })
        else:
            checks.append({
                "check": "ENV_IN_GITIGNORE",
                "status": "FAIL",
                "detail": "WARNING: .env not in .gitignore — secrets may leak!"
            })

    return checks


def compute_mosca_score(threats: list) -> int:
    base = 100
    deductions = {"LOW": 5, "MEDIUM": 15, "HIGH": 30, "CRITICAL": 50}
    for t in threats:
        base -= deductions.get(t.get("severity", "LOW"), 5)
    return max(0, base)


def run_scan(iteration: int = 1) -> dict:
    log.info(f"Scan #{iteration} starting...")

    calls      = fetch_recent_calls(minutes=10)
    threats    = rule_based_analysis(calls)
    env_checks = verify_env_security()

    mosca_score = compute_mosca_score(threats)

    risk = (
        "CRITICAL" if mosca_score < 30 else
        "HIGH"     if mosca_score < 60 else
        "MEDIUM"   if mosca_score < 80 else
        "LOW"
    )

    report = {
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "iteration":        iteration,
        "calls_analyzed":   len(calls),
        "threats_detected": threats,
        "env_security":     env_checks,
        "mosca_score":      mosca_score,
        "risk_level":       risk,
        "recommendation": (
            "LOCKDOWN — review immediately" if mosca_score < 30 else
            "Review flagged threats"         if threats else
            "System secure ✅"
        )
    }

    ev_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'evidence')
    os.makedirs(ev_dir, exist_ok=True)
    report_path = os.path.join(ev_dir, f"sentinel_report_{iteration}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    log.info(f"🛡  MOSCA Score: {mosca_score}/100 | Risk: {risk} | Threats: {len(threats)}")
    for t in threats:
        log.warning(f"   ⚠️  [{t['severity']}] {t['rule']}: {t['detail']}")
    log.info(f"   Report saved → {report_path}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NEXUS SENTINEL — Security Agent")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    args = parser.parse_args()

    log.info("🛡  SENTINEL online — monitoring Al Qua'a health data security")

    if args.once:
        run_scan(1)
    else:
        i = 0
        while True:
            i += 1
            run_scan(i)
            log.info("Next scan in 5 minutes...")
            time.sleep(300)