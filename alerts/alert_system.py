"""
Alert System
=============
Manages caregiver alerts with cooldown, escalation, and logging.
"""

import json
import os
import time
import logging
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional

from modules.fusion_engine import PatientState, PatientAlertLevel

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """A caregiver alert."""
    alert_id: str
    level: str
    reasons: List[str]
    patient_state_summary: dict
    timestamp: float
    acknowledged: bool = False
    acknowledged_at: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


class AlertSystem:
    """
    Manages alerts with:
    - Cooldown period to prevent alert fatigue
    - Consecutive frame threshold to avoid false positives
    - Logging to disk
    - Alert history
    """

    def __init__(self, cooldown_sec: float = 30.0, consecutive_threshold: int = 5,
                 log_dir: str = "data/session_logs"):
        self.cooldown_sec = cooldown_sec
        self.consecutive_threshold = consecutive_threshold
        self.log_dir = log_dir

        self._last_alert_time: float = 0.0
        self._consecutive_alert_frames: int = 0
        self._current_alert_level = PatientAlertLevel.NORMAL
        self._alert_history: deque = deque(maxlen=100)
        self._alert_counter: int = 0

        # Ensure log directory exists
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create alert log directory {log_dir}: {e}")

        # Active alert callback (set by dashboard)
        self.on_alert = None

    def process_state(self, state: PatientState) -> Optional[Alert]:
        """
        Process a patient state and potentially generate an alert.
        Returns Alert if one should be triggered, None otherwise.
        """
        current_time = state.timestamp or time.time()

        if state.alert_level in (PatientAlertLevel.CONCERN, PatientAlertLevel.URGENT):
            self._consecutive_alert_frames += 1
        else:
            self._consecutive_alert_frames = max(0, self._consecutive_alert_frames - 1)

        # Check if we should fire an alert
        should_alert = (
            self._consecutive_alert_frames >= self.consecutive_threshold
            and (current_time - self._last_alert_time) >= self.cooldown_sec
            and state.alert_level in (PatientAlertLevel.CONCERN, PatientAlertLevel.URGENT)
        )

        # Urgent alerts bypass cooldown after half the period
        if (state.alert_level == PatientAlertLevel.URGENT
                and self._consecutive_alert_frames >= 3
                and (current_time - self._last_alert_time) >= self.cooldown_sec / 2):
            should_alert = True

        if not should_alert:
            return None

        self._alert_counter += 1
        alert = Alert(
            alert_id=f"ALERT-{self._alert_counter:04d}",
            level=state.alert_level.value,
            reasons=state.alert_reasons,
            patient_state_summary=state.to_dict(),
            timestamp=current_time,
        )

        self._last_alert_time = current_time
        self._consecutive_alert_frames = 0
        self._alert_history.append(alert)

        # Log to disk
        self._log_alert(alert)

        # Fire callback
        if self.on_alert:
            try:
                self.on_alert(alert)
            except Exception:
                pass

        return alert

    def _log_alert(self, alert: Alert):
        """Log alert to disk."""
        try:
            date_str = datetime.fromtimestamp(alert.timestamp).strftime("%Y-%m-%d")
            log_file = os.path.join(self.log_dir, f"alerts_{date_str}.jsonl")
            with open(log_file, "a") as f:
                f.write(json.dumps(alert.to_dict()) + "\n")
        except (IOError, OSError) as e:
            logger.error(f"Failed to write alert to log file {log_file}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error logging alert: {e}")

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged by caregiver."""
        for alert in self._alert_history:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                alert.acknowledged_at = time.time()
                return True
        return False

    def get_active_alerts(self) -> List[Alert]:
        """Get unacknowledged alerts."""
        return [a for a in self._alert_history if not a.acknowledged]

    def get_alert_history(self, n: int = 20) -> List[dict]:
        """Get recent alert history."""
        return [a.to_dict() for a in list(self._alert_history)[-n:]]

    def reset(self):
        self._consecutive_alert_frames = 0
        self._last_alert_time = 0.0
