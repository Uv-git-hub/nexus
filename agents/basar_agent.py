"""
NEXUS — BASAR Agent v5 (بصر = Sight)
Real webcam fall detection using YOLOv8 pose estimation.
Sends alerts + 15-min reports to Make.com → Google Sheets + Gmail + SMS

Run FROM the nexus root folder:
  python agents\basar_agent.py --test      ← test without camera
  python agents\basar_agent.py             ← use webcam
  python agents\basar_agent.py --source 1  ← external camera
"""

import os, sys, time, json, logging, argparse, threading, requests
import cv2
import numpy as np
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))
if not os.getenv("MAKE_WEBHOOK_URL"):
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [BASAR] %(message)s")
log = logging.getLogger("BASAR")

MAKE_WEBHOOK      = os.getenv("MAKE_WEBHOOK_URL", "")
N8N_BASAR_WEBHOOK = os.getenv("N8N_BASAR_WEBHOOK", "")
REPORT_INTERVAL   = 15 * 60


class BASARAgent:
    def __init__(self):
        log.info("Loading YOLOv8n-pose model (~6MB download on first run)...")
        try:
            from ultralytics import YOLO
            self.model = YOLO("yolov8n-pose.pt")
        except ImportError:
            log.error("ultralytics not installed. Run: pip install ultralytics")
            sys.exit(1)

        self.fall_thresh   = 0.82
        self.conf_thresh   = 0.50
        self.cooldown      = 30
        self.last_alert    = 0
        self.alert_count   = 0
        self.session_start = datetime.now(timezone.utc)
        self.stats = {
            "falls_detected":  0,
            "people_tracked":  0,
            "frames_analyzed": 0,
        }
        # ── Keep last annotated frame so labels never disappear ──
        self._last_annotated = None
        self._last_fall      = False
        self._last_people    = 0

        os.makedirs("incidents", exist_ok=True)
        os.makedirs("evidence",  exist_ok=True)
        self._start_report_timer()
        log.info(f"Make.com webhook: {'SET ✅' if MAKE_WEBHOOK else 'NOT SET ❌'}")

    def is_fallen(self, keypoints: np.ndarray) -> bool:
        if keypoints is None or len(keypoints) < 13:
            return False
        head_y  = float(keypoints[0][1])
        l_hip_y = float(keypoints[11][1])
        r_hip_y = float(keypoints[12][1])
        hip_y   = max(l_hip_y, r_hip_y)
        if hip_y < 30 or head_y < 10:
            return False
        if keypoints.shape[-1] == 3:
            if float(keypoints[0][2]) < 0.3 or max(float(keypoints[11][2]), float(keypoints[12][2])) < 0.3:
                return False
        return (head_y / hip_y) >= self.fall_thresh

    def _uptime(self):
        return int((datetime.now(timezone.utc) - self.session_start).total_seconds() / 60)

    def _send_to_make(self, payload: dict):
        if not MAKE_WEBHOOK:
            log.warning("MAKE_WEBHOOK_URL not set in .env — skipping")
            return
        try:
            r = requests.post(MAKE_WEBHOOK, json=payload, timeout=10)
            log.info(f"Make.com response: {r.status_code} {r.text[:80]}")
        except Exception as e:
            log.error(f"Make.com failed: {e}")

    def _send_to_n8n(self, payload: dict):
        if not N8N_BASAR_WEBHOOK:
            return
        try:
            r = requests.post(N8N_BASAR_WEBHOOK, json=payload, timeout=5)
            log.info(f"n8n response: {r.status_code}")
        except Exception as e:
            log.error(f"n8n failed: {e}")

    def _send_fall_alert(self, frame: np.ndarray):
        now = time.time()
        if now - self.last_alert < self.cooldown:
            return
        self.last_alert = now
        self.alert_count += 1
        self.stats["falls_detected"] += 1

        ts       = int(now)
        img_path = f"incidents/FALL_{ts}.jpg"
        cv2.imwrite(img_path, frame)
        log.warning(f"🚨 FALL #{self.alert_count} — saved {img_path}")

        payload = {
            "call_id":         f"BASAR_FALL_{ts}",
            "urgency":         "EMERGENCY",
            "event_type":      "FALL_DETECTED",
            "summary":         f"Fall detected by NEXUS BASAR camera at Al Qua'a. Alert #{self.alert_count}. Person may be injured and unable to call for help.",
            "source":          "BASAR_CV",
            "location":        "Al Qua'a, Al Ain, UAE",
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "patient_name":    "BASAR Camera System",
            "phone_number":    "AUTOMATED_DETECTION",
            "falls_detected":  str(self.stats["falls_detected"]),
            "people_tracked":  str(self.stats["people_tracked"]),
            "frames_analyzed": str(self.stats["frames_analyzed"]),
            "uptime_minutes":  str(self._uptime()),
            "confidence":      "0.89",
            "alert_count":     str(self.alert_count),
        }
        threading.Thread(target=self._send_to_make, args=(payload,), daemon=True).start()
        threading.Thread(target=self._send_to_n8n,  args=(payload,), daemon=True).start()

    def _send_summary_report(self):
        while True:
            time.sleep(REPORT_INTERVAL)
            payload = {
                "call_id":         f"BASAR_REPORT_{int(time.time())}",
                "urgency":         "LOW",
                "event_type":      "BASAR_15MIN_REPORT",
                "summary":         f"NEXUS BASAR 15-min Report | Falls: {self.stats['falls_detected']} | People: {self.stats['people_tracked']} | Frames: {self.stats['frames_analyzed']} | Uptime: {self._uptime()}min",
                "source":          "BASAR_CV",
                "location":        "Al Qua'a, Al Ain, UAE",
                "timestamp":       datetime.now(timezone.utc).isoformat(),
                "patient_name":    "BASAR_REPORT",
                "phone_number":    "AUTOMATED",
                "falls_detected":  str(self.stats["falls_detected"]),
                "people_tracked":  str(self.stats["people_tracked"]),
                "frames_analyzed": str(self.stats["frames_analyzed"]),
                "uptime_minutes":  str(self._uptime()),
                "confidence":      "1.0",
                "alert_count":     str(self.alert_count),
            }
            log.info(f"Sending 15-min report | Falls:{self.stats['falls_detected']} Frames:{self.stats['frames_analyzed']}")
            self._send_to_make(payload)
            with open(f"evidence/basar_report_{int(time.time())}.json", "w") as f:
                json.dump(payload, f, indent=2)

    def _start_report_timer(self):
        threading.Thread(target=self._send_summary_report, daemon=True).start()
        log.info("15-minute report timer started")

    def _draw_overlay(self, frame, fall_detected, people_count, frame_count):
        """Draw stable overlay on any frame — called every frame."""
        status_color = (0, 0, 255) if fall_detected else (0, 255, 0)
        status_text  = "FALL DETECTED!" if fall_detected else "MONITORING"
        cv2.rectangle(frame, (0, 0), (640, 55), (0, 0, 0), -1)
        cv2.putText(frame, f"NEXUS BASAR v5 | {status_text}",
                    (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2)
        cv2.putText(frame,
                    f"Falls:{self.alert_count} | People:{people_count} | Frames:{frame_count} | Uptime:{self._uptime()}min",
                    (8, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1)
        return frame

    def run(self, source=0):
        log.info(f"Opening camera source: {source}")
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            log.error(f"Cannot open camera {source}. Try: python agents\\basar_agent.py --test")
            sys.exit(1)

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        log.info("BASAR ACTIVE — watching for falls. Press Q to quit.")

        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            frame_count += 1
            self.stats["frames_analyzed"] += 1

            if frame_count % 3 != 0:
                # ── FIX: use last annotated frame so labels stay visible ──
                display = self._last_annotated if self._last_annotated is not None else frame.copy()
                display = self._draw_overlay(display, self._last_fall, self._last_people, frame_count)
                cv2.imshow("NEXUS BASAR — Safety Monitor", display)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                continue

            # ── Run YOLO every 3rd frame ──
            results = self.model(frame, verbose=False, conf=self.conf_thresh)
            fall_detected     = False
            people_this_frame = 0

            for r in results:
                if r.keypoints is not None:
                    for kp in r.keypoints.data:
                        people_this_frame += 1
                        if self.is_fallen(kp.cpu().numpy()):
                            fall_detected = True
                            self._send_fall_alert(frame)

            self.stats["people_tracked"] = max(self.stats["people_tracked"], people_this_frame)

            # Save state for non-YOLO frames
            annotated = results[0].plot() if results else frame.copy()
            self._last_annotated = annotated.copy()
            self._last_fall      = fall_detected
            self._last_people    = people_this_frame

            annotated = self._draw_overlay(annotated, fall_detected, people_this_frame, frame_count)
            cv2.imshow("NEXUS BASAR — Safety Monitor", annotated)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()
        log.info(f"BASAR stopped | Falls:{self.alert_count} | Frames:{frame_count}")

    def test_alert(self):
        log.info("TEST MODE — simulating fall alert...")
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(frame, "NEXUS BASAR TEST FALL", (80, 220),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        self.last_alert = 0
        self._send_fall_alert(frame)
        log.info("Test complete — check Gmail, SMS, and Google Sheets now!")
        log.info(f"Webhook: {MAKE_WEBHOOK[:50] if MAKE_WEBHOOK else 'NOT SET'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=0, help="Camera: 0=laptop cam, 1=external, or video path")
    parser.add_argument("--test",   action="store_true", help="Send test alert without camera")
    args = parser.parse_args()

    agent = BASARAgent()
    if args.test:
        agent.test_alert()
    else:
        src = int(args.source) if str(args.source).isdigit() else args.source
        agent.run(src)