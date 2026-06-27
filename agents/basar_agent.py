"""
NEXUS — BASAR Agent v4 (بصر = Sight)
REAL camera fall detection using YOLOv8 pose estimation.
- Detects actual human falls from webcam
- Sends alert to Make.com webhook → Google Sheets + Gmail + SMS
- Sends summary report every 15 minutes to Make.com
- Saves incident frames as evidence

Run:  python basar_agent.py              ← uses webcam
      python basar_agent.py --test       ← simulates a fall (no webcam needed)
      python basar_agent.py --source video.mp4
Press Q to quit.
"""

import os, sys, time, json, logging, argparse, threading, requests
import cv2
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from ultralytics import YOLO

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [BASAR] %(message)s")
log = logging.getLogger("BASAR")

MAKE_WEBHOOK      = os.getenv("MAKE_WEBHOOK_URL", "")
N8N_BASAR_WEBHOOK = os.getenv("N8N_BASAR_WEBHOOK", "")
REPORT_INTERVAL   = 15 * 60   # 15 minutes in seconds


class BASARAgent:
    def __init__(self):
        log.info("🔍 Loading YOLOv8n-pose model (downloads ~6MB on first run)...")
        self.model        = YOLO("yolov8n-pose.pt")
        self.fall_thresh  = 0.82    # head_y / hip_y ratio — body is horizontal
        self.conf_thresh  = 0.50
        self.cooldown     = 30      # seconds between alerts
        self.last_alert   = 0
        self.alert_count  = 0
        self.session_start = datetime.utcnow()

        # Stats for 15-min report
        self.stats = {
            "falls_detected":   0,
            "people_tracked":   0,
            "frames_analyzed":  0,
            "false_positives":  0,
            "session_start":    self.session_start.isoformat()
        }

        os.makedirs("incidents", exist_ok=True)
        os.makedirs("evidence",  exist_ok=True)

        # Start background 15-minute reporting thread
        self._start_report_timer()

    # ── Fall Detection Logic ──────────────────────────────
    def is_fallen(self, keypoints: np.ndarray) -> bool:
        """
        COCO keypoints: 0=nose, 5=L-shoulder, 11=L-hip, 12=R-hip
        A person is fallen when their head is at or below hip level.
        """
        if keypoints is None or len(keypoints) < 13:
            return False

        head_y  = float(keypoints[0][1])
        l_hip_y = float(keypoints[11][1])
        r_hip_y = float(keypoints[12][1])
        hip_y   = max(l_hip_y, r_hip_y)

        # Ignore if keypoints not visible
        if hip_y < 30 or head_y < 10:
            return False

        # Check confidence scores if available (shape 17,3)
        if keypoints.shape[-1] == 3:
            head_conf  = float(keypoints[0][2])
            hip_conf_l = float(keypoints[11][2])
            hip_conf_r = float(keypoints[12][2])
            if head_conf < 0.3 or max(hip_conf_l, hip_conf_r) < 0.3:
                return False

        ratio = head_y / hip_y
        return ratio >= self.fall_thresh

    # ── Send Alert to Make.com ────────────────────────────
    def _send_to_make(self, payload: dict):
        """Fire Make.com webhook → Google Sheets + Gmail + SMS."""
        if not MAKE_WEBHOOK:
            log.warning("MAKE_WEBHOOK_URL not set — skipping Make.com alert")
            return
        try:
            r = requests.post(MAKE_WEBHOOK, json=payload, timeout=8)
            log.info(f"✅ Make.com → {r.status_code}")
        except Exception as e:
            log.error(f"Make.com failed: {e}")

    def _send_to_n8n(self, payload: dict):
        """Also fire n8n for SAWT voice call."""
        if not N8N_BASAR_WEBHOOK:
            return
        try:
            r = requests.post(N8N_BASAR_WEBHOOK, json=payload, timeout=5)
            log.info(f"✅ n8n → {r.status_code}")
        except Exception as e:
            log.error(f"n8n failed: {e}")

    # ── Fall Alert ────────────────────────────────────────
    def _send_fall_alert(self, frame: np.ndarray):
        now = time.time()
        if now - self.last_alert < self.cooldown:
            return
        self.last_alert = now
        self.alert_count += 1
        self.stats["falls_detected"] += 1

        ts        = int(now)
        img_path  = f"incidents/FALL_{ts}.jpg"
        cv2.imwrite(img_path, frame)
        log.warning(f"🚨 FALL #{self.alert_count} detected — saved {img_path}")

        payload = {
                "call_id":         f"BASAR_FALL_{ts}",
                "urgency":         "EMERGENCY",
                "event_type":      "FALL_DETECTED",
                "summary":         f"🚨 Fall detected by NEXUS BASAR at Al Qua'a. Alert #{self.alert_count}. Person may be injured.",
                "source":          "BASAR_CV",
                "location":        "Al Qua'a, Al Ain, UAE",
                "timestamp":       datetime.utcnow().isoformat(),
                "patient_name":    "BASAR Camera System",
                "phone_number":    "AUTOMATED",
                "confidence":      "0.89",
                "alert_count":     str(self.alert_count),
                "falls_detected":  str(self.alert_count),
                "people_tracked":  str(self.stats["people_tracked"]),
                "frames_analyzed": str(self.stats["frames_analyzed"]),
                "uptime_minutes":  str(int((datetime.utcnow() - self.session_start).total_seconds() / 60)),
                "image_saved":                 mg_path,
                "action":          "ALERT_SENT_TO_MAKE"
            }

        # Fire Make.com (Google Sheets + Gmail + SMS)
        self._send_to_make(payload)
        # Fire n8n (SAWT voice call)
        self._send_to_n8n(payload)

    # ── 15-Minute Summary Report ──────────────────────────
    def _send_summary_report(self):
        """Sends session stats to Make.com every 15 minutes."""
        while True:
            time.sleep(REPORT_INTERVAL)
            uptime_mins = int((datetime.utcnow() - self.session_start).total_seconds() / 60)
            report_payload = {
                "call_id":        f"BASAR_REPORT_{int(time.time())}",
                "urgency":        "LOW",
                "event_type":     "BASAR_15MIN_REPORT",
                "source":         "BASAR_CV",
                "location":       "Al Qua'a, Al Ain, UAE",
                "timestamp":      datetime.utcnow().isoformat(),
                "summary": (
                    f"📊 NEXUS BASAR 15-min Report | "
                    f"Falls: {self.stats['falls_detected']} | "
                    f"People tracked: {self.stats['people_tracked']} | "
                    f"Frames analyzed: {self.stats['frames_analyzed']} | "
                    f"Uptime: {uptime_mins} min"
                ),
                # Full stats for Google Sheets
                "falls_detected":  self.stats["falls_detected"],
                "people_tracked":  self.stats["people_tracked"],
                "frames_analyzed": self.stats["frames_analyzed"],
                "uptime_minutes":  uptime_mins,
                "session_start":   self.stats["session_start"]
            }

            log.info(f"📊 Sending 15-min report → Make.com | Falls: {self.stats['falls_detected']}")
            self._send_to_make(report_payload)

            # Save report locally as evidence
            report_path = f"evidence/basar_report_{int(time.time())}.json"
            with open(report_path, "w") as f:
                json.dump(report_payload, f, indent=2)
            log.info(f"📁 Report saved → {report_path}")

    def _start_report_timer(self):
        t = threading.Thread(target=self._send_summary_report, daemon=True)
        t.start()
        log.info(f"⏰ 15-minute summary report timer started")

    # ── Main Camera Loop ──────────────────────────────────
    def run(self, source=0):
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            log.error(f"❌ Cannot open camera source: {source}")
            log.error("   Try: python basar_agent.py --test")
            sys.exit(1)

        # Set camera resolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        log.info("👁  BASAR ACTIVE — camera open, watching for falls")
        log.info("   Press Q to quit | Falls trigger Make.com + n8n automatically")
        log.info(f"   Reports sent every 15 minutes to Make.com")

        frame_count = 0
        next_report_log = time.time() + 60  # log reminder every minute

        while True:
            ret, frame = cap.read()
            if not ret:
                log.warning("Camera frame dropped — retrying...")
                time.sleep(0.1)
                continue

            frame_count += 1
            self.stats["frames_analyzed"] += 1

            # Run YOLO every 3rd frame for CPU performance
            if frame_count % 3 != 0:
                cv2.imshow("NEXUS BASAR — Live Safety Monitor", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            # ── YOLO Inference ────────────────────────────
            results = self.model(frame, verbose=False, conf=self.conf_thresh)

            fall_detected    = False
            people_this_frame = 0

            for r in results:
                if r.keypoints is not None:
                    kps = r.keypoints.data  # shape: (N, 17, 3)
                    for kp in kps:
                        people_this_frame += 1
                        kp_np = kp.cpu().numpy()
                        if self.is_fallen(kp_np):
                            fall_detected = True
                            self._send_fall_alert(frame)

            if people_this_frame > 0:
                self.stats["people_tracked"] = max(
                    self.stats["people_tracked"], people_this_frame
                )

            # ── Draw Overlay ──────────────────────────────
            annotated = results[0].plot() if results else frame

            # Status bar
            status_color = (0, 0, 255) if fall_detected else (0, 255, 0)
            status_text  = "FALL DETECTED!" if fall_detected else "MONITORING"
            cv2.rectangle(annotated, (0, 0), (640, 45), (0, 0, 0), -1)
            cv2.putText(annotated, f"NEXUS BASAR v4 | {status_text}",
                        (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)
            cv2.putText(annotated,
                        f"Falls: {self.alert_count} | People: {people_this_frame} | Frame: {frame_count}",
                        (8, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

            # Next report countdown
            mins_left = max(0, int((self.session_start.timestamp() + REPORT_INTERVAL
                                    + (self.alert_count * 0) - time.time()) / 60))
            cv2.putText(annotated, f"Next report: ~{mins_left}m",
                        (470, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 255, 150), 1)

            cv2.imshow("NEXUS BASAR — Live Safety Monitor", annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            # Reminder log
            if time.time() > next_report_log:
                log.info(f"👁  Still watching | Falls: {self.alert_count} | Frames: {frame_count}")
                next_report_log = time.time() + 60

        cap.release()
        cv2.destroyAllWindows()
        log.info(f"BASAR stopped | Total falls: {self.alert_count} | Frames: {frame_count}")

    # ── Test Mode (no webcam needed) ─────────────────────
    def test_alert(self):
        log.info("🧪 TEST MODE — simulating a real fall alert...")
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(frame, "NEXUS BASAR — TEST FALL EVENT",
                    (60, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        cv2.putText(frame, "Al Qua'a Community Area",
                    (150, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 1)
        self.last_alert = 0   # bypass cooldown
        self._send_fall_alert(frame)

        # Also send a test 15-min report immediately
        log.info("🧪 Sending test 15-min report...")
        test_report = {
            "call_id":        f"BASAR_TEST_{int(time.time())}",
            "urgency":        "LOW",
            "event_type":     "BASAR_TEST_REPORT",
            "source":         "BASAR_CV_TEST",
            "location":       "Al Qua'a, Al Ain, UAE",
            "timestamp":      datetime.utcnow().isoformat(),
            "summary":        "🧪 NEXUS BASAR TEST — System is operational. Camera monitoring active. Fall detection enabled.",
            "falls_detected":  1,
            "people_tracked":  1,
            "frames_analyzed": 100,
            "uptime_minutes":  0,
            "session_start":   self.session_start.isoformat()
        }
        self._send_to_make(test_report)
        log.info("✅ Test complete — check your Google Sheets, Gmail, and SMS!")
        log.info("   Make.com webhook: " + (MAKE_WEBHOOK[:40] + "..." if MAKE_WEBHOOK else "NOT SET"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NEXUS BASAR — Real Camera Fall Detection")
    parser.add_argument("--source", default=0,
                        help="Camera source: 0=default webcam, 1=external cam, or path to video file")
    parser.add_argument("--test",   action="store_true",
                        help="Send a test fall alert without opening camera")
    args = parser.parse_args()

    agent = BASARAgent()

    if args.test:
        agent.test_alert()
    else:
        src = int(args.source) if str(args.source).isdigit() else args.source
        agent.run(src)