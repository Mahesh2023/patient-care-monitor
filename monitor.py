"""
Patient Care Monitor - Main Orchestrator
==========================================
Runs the real-time monitoring pipeline:
  Camera → Face Analysis → Pain Detection → rPPG → Fusion → Alerts

Usage:
    python monitor.py                  # Run with webcam
    python monitor.py --video file.mp4 # Run on video file
    python monitor.py --demo           # Run demo mode with synthetic data

This is the non-dashboard version. For the full dashboard, run:
    streamlit run dashboard.py
"""

import argparse
import sys
import time
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np

from config import SystemConfig, DISCLAIMERS
from modules.face_analyzer import FaceAnalyzer
from modules.pain_detector import PainDetector, PainLevel
from modules.rppg_estimator import RPPGEstimator
from modules.voice_analyzer import VoiceAnalyzer
from modules.text_sentiment import TextSentimentAnalyzer
from modules.fusion_engine import FusionEngine, PatientAlertLevel
from alerts.alert_system import AlertSystem
from utils.session_logger import SessionLogger


class PatientCareMonitor:
    """
    Main orchestrator for the patient care monitoring system.
    Coordinates all modules and runs the real-time pipeline.
    """

    def __init__(self, config: SystemConfig = None):
        self.config = config or SystemConfig()

        # Initialize modules
        self.face_analyzer = FaceAnalyzer()
        self.pain_detector = PainDetector(
            mild_threshold=self.config.pain.pspi_mild_threshold,
            moderate_threshold=self.config.pain.pspi_moderate_threshold,
            severe_threshold=self.config.pain.pspi_severe_threshold,
        )
        self.rppg = RPPGEstimator(
            fps=self.config.rppg.fps,
            buffer_size=self.config.rppg.buffer_size,
        )
        self.voice_analyzer = VoiceAnalyzer(
            sample_rate=self.config.voice.sample_rate,
        )
        self.text_analyzer = TextSentimentAnalyzer()
        self.fusion = FusionEngine()
        self.alert_system = AlertSystem(
            cooldown_sec=self.config.alerts.alert_cooldown_sec,
            consecutive_threshold=self.config.alerts.consecutive_frames_threshold,
        )
        self.logger = SessionLogger()

        self._frame_count = 0
        self._start_time = 0.0
        self._running = False

    def process_frame(self, frame: np.ndarray, timestamp: float = None) -> dict:
        """
        Process a single video frame through the full pipeline.

        Args:
            frame: BGR image from camera
            timestamp: Optional timestamp (defaults to time.time())

        Returns:
            dict with patient state and visualization info
        """
        if timestamp is None:
            timestamp = time.time()

        self._frame_count += 1

        # Skip frames for performance
        if self._frame_count % self.config.process_every_n_frames != 0:
            return {"skipped": True}

        # 1. Face Analysis
        face_result = self.face_analyzer.analyze(frame, timestamp)

        # 2. Pain Detection
        pain_assessment = self.pain_detector.assess(
            face_result.aus if face_result.face_detected else None,
            timestamp
        )

        # 3. rPPG Heart Rate
        if face_result.forehead_roi is not None:
            self.rppg.add_frame(face_result.forehead_roi, timestamp)
        hr_result = self.rppg.estimate_heart_rate(timestamp)

        # 4. Fusion
        state = self.fusion.fuse(
            face_result=face_result,
            pain_assessment=pain_assessment,
            heart_rate=hr_result,
            timestamp=timestamp,
        )

        # 5. Alert check
        alert = self.alert_system.process_state(state)

        # 6. Log
        self.logger.log_state(state)

        return {
            "skipped": False,
            "state": state,
            "alert": alert,
            "face_detected": face_result.face_detected,
            "calibrated": self.face_analyzer.is_calibrated,
            "frame_count": self._frame_count,
        }

    def draw_overlay(self, frame: np.ndarray, result: dict) -> np.ndarray:
        """Draw monitoring overlay on frame for display."""
        if result.get("skipped"):
            return frame

        overlay = frame.copy()
        h, w = overlay.shape[:2]
        state = result.get("state")

        if state is None:
            return overlay

        # Status bar background
        cv2.rectangle(overlay, (0, 0), (w, 140), (30, 30, 30), -1)

        # Calibration indicator
        if not result.get("calibrated"):
            cv2.putText(overlay, "CALIBRATING... Please look at camera neutrally",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
            return overlay

        # Face detection status
        face_color = (0, 255, 0) if result.get("face_detected") else (0, 0, 255)
        face_text = "Face: OK" if result.get("face_detected") else "Face: NOT DETECTED"
        cv2.putText(overlay, face_text, (10, 25),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, face_color, 1)

        # Comfort level bar
        comfort_pct = int(state.comfort_level * 100)
        bar_color = (0, 200, 0) if comfort_pct > 60 else ((0, 200, 255) if comfort_pct > 30 else (0, 0, 255))
        cv2.putText(overlay, f"Comfort: {comfort_pct}%", (10, 50),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.rectangle(overlay, (160, 38), (160 + comfort_pct * 2, 52), bar_color, -1)
        cv2.rectangle(overlay, (160, 38), (360, 52), (100, 100, 100), 1)

        # Pain indicator
        if state.pain_assessment:
            pain = state.pain_assessment
            pain_color = (0, 255, 0)
            if pain.pain_level == PainLevel.MILD:
                pain_color = (0, 200, 255)
            elif pain.pain_level == PainLevel.MODERATE:
                pain_color = (0, 100, 255)
            elif pain.pain_level == PainLevel.SEVERE:
                pain_color = (0, 0, 255)

            cv2.putText(overlay, f"Pain: {pain.pspi_score:.1f} ({pain.pain_level.value})",
                        (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, pain_color, 1)

        # Heart rate
        if state.heart_rate and state.heart_rate.confidence > 0.3:
            hr = state.heart_rate
            hr_color = (0, 0, 255) if hr.is_abnormal else (0, 200, 0)
            cv2.putText(overlay, f"HR: {hr.bpm:.0f} bpm ({hr.signal_quality})",
                        (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, hr_color, 1)

        # Alert indicator
        if state.alert_level != PatientAlertLevel.NORMAL:
            alert_colors = {
                PatientAlertLevel.ATTENTION: (0, 200, 255),
                PatientAlertLevel.CONCERN: (0, 100, 255),
                PatientAlertLevel.URGENT: (0, 0, 255),
            }
            color = alert_colors.get(state.alert_level, (200, 200, 200))
            cv2.putText(overlay, f"ALERT: {state.alert_level.value.upper()}",
                        (w - 280, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            for i, reason in enumerate(state.alert_reasons[:2]):
                cv2.putText(overlay, reason[:50],
                            (w - 350, 55 + i * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # Observations (bottom of frame)
        y_obs = h - 10
        for obs in reversed(state.observations[:3]):
            cv2.putText(overlay, obs[:80], (10, y_obs),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            y_obs -= 20

        # Frame counter
        cv2.putText(overlay, f"Frame: {self._frame_count}",
                     (w - 140, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (128, 128, 128), 1)

        return overlay

    def run_camera(self, source=0):
        """Run monitoring with camera/video input."""
        print(f"\n{'='*60}")
        print("  Patient Care Monitor - Real-time Mode")
        print(f"{'='*60}")
        print(f"\n{DISCLAIMERS['general']}\n")
        print(f"Session ID: {self.logger.session_id}")
        print("Press 'q' to quit, 'r' to reset calibration\n")

        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            print(f"ERROR: Cannot open video source: {source}")
            return

        self._running = True
        self._start_time = time.time()

        try:
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    if isinstance(source, str):  # Video file ended
                        break
                    continue

                result = self.process_frame(frame)
                display = self.draw_overlay(frame, result)

                cv2.imshow("Patient Care Monitor", display)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    self.face_analyzer.reset_calibration()
                    print("Calibration reset. Please look at camera neutrally.")

        finally:
            cap.release()
            cv2.destroyAllWindows()
            self._running = False
            elapsed = time.time() - self._start_time
            print(f"\nSession ended. Duration: {elapsed:.0f}s, Frames: {self._frame_count}")
            print(f"Log: {self.logger._log_file}")

    def run_demo(self):
        """Run demo mode with synthetic data to showcase the system."""
        print(f"\n{'='*60}")
        print("  Patient Care Monitor - DEMO MODE")
        print(f"{'='*60}")
        print(f"\n{DISCLAIMERS['general']}\n")

        print("Generating synthetic patient scenarios...\n")

        # Demo scenarios
        scenarios = [
            {
                "name": "Resting comfortably",
                "duration": 5,
                "pain_range": (0, 0.5),
                "comfort_range": (0.7, 0.9),
                "arousal_range": (0.2, 0.3),
            },
            {
                "name": "Mild discomfort",
                "duration": 5,
                "pain_range": (1.0, 2.5),
                "comfort_range": (0.4, 0.6),
                "arousal_range": (0.4, 0.5),
            },
            {
                "name": "Moderate pain episode",
                "duration": 5,
                "pain_range": (3.0, 6.0),
                "comfort_range": (0.2, 0.4),
                "arousal_range": (0.5, 0.7),
            },
            {
                "name": "Pain subsiding",
                "duration": 5,
                "pain_range": (1.0, 3.0),
                "comfort_range": (0.4, 0.6),
                "arousal_range": (0.3, 0.5),
            },
            {
                "name": "Comfortable again",
                "duration": 5,
                "pain_range": (0, 0.5),
                "comfort_range": (0.6, 0.8),
                "arousal_range": (0.2, 0.4),
            },
        ]

        from modules.fusion_engine import PatientState

        all_states = []
        t = 0

        for scenario in scenarios:
            print(f"--- Scenario: {scenario['name']} ---")
            for i in range(scenario["duration"]):
                pain = np.random.uniform(*scenario["pain_range"])
                comfort = np.random.uniform(*scenario["comfort_range"])
                arousal = np.random.uniform(*scenario["arousal_range"])

                state = PatientState(
                    comfort_level=comfort,
                    arousal_level=arousal,
                    pain_level=pain / 10.0,
                    engagement_level=np.random.uniform(0.5, 0.8),
                    timestamp=t,
                )
                state.observations = [f"Scenario: {scenario['name']}"]

                # Determine alert level
                if pain > 4.0:
                    state.alert_level = PatientAlertLevel.CONCERN
                    state.alert_reasons = [f"Pain PSPI={pain:.1f}"]
                elif pain > 7.0:
                    state.alert_level = PatientAlertLevel.URGENT
                    state.alert_reasons = [f"Severe pain PSPI={pain:.1f}"]

                alert = self.alert_system.process_state(state)
                self.logger.log_state(state)
                all_states.append(state)

                # Display
                pain_bar = "#" * int(pain * 2)
                comfort_bar = "=" * int(comfort * 20)
                print(f"  t={t:3d}s | Pain: {pain:4.1f} [{pain_bar:<12}] | "
                      f"Comfort: {comfort:.2f} [{comfort_bar:<20}] | "
                      f"Alert: {state.alert_level.value}")

                if alert:
                    print(f"  >>> ALERT: {alert.level} - {', '.join(alert.reasons)}")

                t += 1

        # Text analysis demo
        print(f"\n--- Text Sentiment Demo ---")
        test_texts = [
            "Patient appears comfortable and resting well",
            "Patient complaining of sharp pain in lower back",
            "Very anxious and confused, keeps asking for help",
            "Feeling much better after medication",
            "Patient is calm and sleeping peacefully",
        ]
        for text in test_texts:
            result = self.text_analyzer.analyze(text, time.time())
            print(f"  \"{text}\"")
            print(f"    Valence: {result.valence:.2f} | Arousal: {result.arousal:.2f} | "
                  f"Pain: {result.pain_mentioned} | Distress: {result.distress_mentioned}")

        print(f"\n{'='*60}")
        print(f"Demo complete. {len(all_states)} states logged.")
        print(f"Session log: {self.logger._log_file}")
        print(f"Alerts: {len(self.alert_system.get_alert_history())}")
        print(f"{'='*60}\n")

    def close(self):
        """Clean up resources."""
        self.face_analyzer.close()


def main():
    parser = argparse.ArgumentParser(
        description="Patient Care Monitor - Multimodal monitoring for caregivers"
    )
    parser.add_argument("--video", type=str, default=None,
                        help="Video file to process (default: webcam)")
    parser.add_argument("--demo", action="store_true",
                        help="Run demo mode with synthetic data")
    parser.add_argument("--camera", type=int, default=0,
                        help="Camera device index (default: 0)")
    args = parser.parse_args()

    monitor = PatientCareMonitor()

    try:
        if args.demo:
            monitor.run_demo()
        elif args.video:
            monitor.run_camera(args.video)
        else:
            monitor.run_camera(args.camera)
    finally:
        monitor.close()


if __name__ == "__main__":
    main()
