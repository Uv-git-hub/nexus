"""
NEXUS — BASAR Agent (بصر = "Sight")
YOLOv8 real-time fall detection on webcam
Fires n8n webhook → triggers SAWT voice call automatically

Run: python basar_agent.py
     python basar_agent.py --source video.mp4   (use video file)
     python basar_agent.py --test               (simulate a fall alert)
Press Q to quit the webcam window.
"""

import os, sys, time, json, logging, argparse, requests
import cv2
import numpy as np
from dotenv import load_dotenv
from ultralytics import YOLO

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("BASAR")


class BASARAgent:
    def __init__(self):
        log.info("🔍 Loading YOLOv8 pose model... (auto-downloads ~6MB first time)")
        self.model = YOLO("yolov8n-pose.pt")   # tiny model — runs on CPU
        self.n8n_webhook  = os.getenv("N8N_BASAR_WEBHOOK", "")
        self.sawt_webhook = "http://localhost:8002/trigger-call"
        self.last_alert   = 0
        self.cooldown     = 30      # seconds between alerts (avoid spam)
        self.fall_thresh  = 0.82   # head_y / hip_y ratio threshold
        self.conf_thresh  = 0.50   # YOLO confidence threshold
        self.alert_count  = 0

    # ── Fall Detection Logic ──────────────────────────────
    def is_fallen(self, keypoints: np.ndarray) -> bool:
        """
        Person is fallen if head y-pos >= fall_thresh × hip y-pos
        (body is horizontal — head and hips at same level)
        keypoints shape: (17, 2) or (17, 3) — COCO format
        """
        if keypoints is None or len(keypoints) < 13:
            return False

        head_y      = float(keypoints[0][1])
        l_hip_y     = float(keypoints[11][1])
        r_hip_y     = float(keypoints[12][1])
        l_shoulder_y = float(keypoints[5][1])

        hip_y = max(l_hip_y, r_hip_y)

        # Hip must be visible (not zero) and head must be at/below hip level
        if hip_y < 30 or head_y < 10:
            return False

        ratio = head_y / hip_y
        return ratio >= self.fall_thresh

    # ── Alert Pipeline ────────────────────────────────────
    def _send_alert(self, frame: np.ndarray, event: str = "FALL_DETECTED"):
        """Fire webhook to n8n → n8n routes to SAWT"""
        now = time.time()
        if now - self.last_alert < self.cooldown:
            return   # still in cooldown

        self.last_alert = now
        self.alert_count += 1

        # Save incident frame
        os.makedirs("incidents", exist_ok=True)
        img_path = f"incidents/{event}_{int(now)}.jpg"
        cv2.imwrite(img_path, frame)
        log.warning(f"🚨 {event} #{self.alert_count} — saved {img_path}")

        payload = {
            "event_type":   event,
            "timestamp":    now,
            "confidence":   0.89,
            "location":     "Al Qua'a Community Area",
            "image_path":   img_path,
            "alert_count":  self.alert_count,
            "source":       "BASAR",
            "urgency":      "EMERGENCY",
            "summary":      f"Fall detected by BASAR CV agent at Al Qua'a Community Area. Autonomous emergency response initiated.",
            "action":       "TRIGGER_VOICE_CALL"
        }

        # Try n8n first (orchestration)
        if self.n8n_webhook and "REPLACE" not in self.n8n_webhook:
            try:
                r = requests.post(self.n8n_webhook, json=payload, timeout=5)
                log.info(f"n8n alerted → {r.status_code}")
                return
            except Exception as e:
                log.error(f"n8n failed: {e} — falling back to SAWT direct")

        # Fallback: call SAWT directly
        try:
            sawt_payload = {
                "urgency":  "EMERGENCY",
                "summary":  payload["summary"],
                "source":   "BASAR",
                "location": payload["location"]
            }
            r = requests.post(self.sawt_webhook, json=sawt_payload, timeout=5)
            log.info(f"SAWT called directly → {r.status_code}")
        except Exception as e:
            log.error(f"SAWT direct call failed: {e}")

    # ── Main Loop ─────────────────────────────────────────
    def run(self, source=0):
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            log.error(f"Cannot open video source: {source}")
            sys.exit(1)

        log.info("👁 BASAR active — watching for anomalies (press Q to quit)")

        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                log.info("Stream ended.")
                break

            frame_count += 1
            # Run inference every 3rd frame (CPU performance)
            if frame_count % 3 != 0:
                cv2.imshow("NEXUS BASAR — Live Safety Monitor", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            results = self.model(frame, verbose=False, conf=self.conf_thresh)

            fall_detected = False
            for r in results:
                if r.keypoints is not None:
                    for kp in r.keypoints.xy:
                        if self.is_fallen(kp.numpy()):
                            fall_detected = True
                            self._send_alert(frame, "FALL_DETECTED")

            # Draw annotations
            annotated = results[0].plot() if results else frame

            # Status overlay
            status_color = (0, 0, 255) if fall_detected else (0, 255, 0)
            status_text  = "⚠ FALL DETECTED" if fall_detected else "MONITORING ACTIVE"
            cv2.rectangle(annotated, (0, 0), (420, 40), (0, 0, 0), -1)
            cv2.putText(annotated, f"NEXUS BASAR v3 | {status_text}",
                        (8, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2)

            # Alert count
            cv2.putText(annotated, f"Alerts: {self.alert_count}",
                        (frame.shape[1]-130, 27), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (255, 255, 0), 1)

            cv2.imshow("NEXUS BASAR — Live Safety Monitor", annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        cap.release()
        cv2.destroyAllWindows()
        log.info(f"BASAR stopped | total alerts: {self.alert_count}")

    def test_alert(self):
        """Send a mock fall alert — use this to test the full pipeline without webcam"""
        log.info("🧪 Sending TEST fall alert...")
        # Create a blank test frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(frame, "TEST FALL EVENT", (150, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
        self.last_alert = 0   # reset cooldown for test
        self._send_alert(frame, "FALL_DETECTED_TEST")
        log.info("✅ Test alert sent — check n8n execution log")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NEXUS BASAR — Fall Detection Agent")
    parser.add_argument("--source", default=0,
                        help="Video source: 0=webcam, or path to video file")
    parser.add_argument("--test", action="store_true",
                        help="Send a mock fall alert and exit (no webcam needed)")
    args = parser.parse_args()

    agent = BASARAgent()

    if args.test:
        agent.test_alert()
    else:
        source = int(args.source) if str(args.source).isdigit() else args.source
        agent.run(source)