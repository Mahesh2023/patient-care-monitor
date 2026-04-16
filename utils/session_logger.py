"""
Session Logger
===============
Logs patient monitoring session data for review and trend analysis.
"""

import json
import os
import time
import logging
from datetime import datetime
from typing import Optional, Dict, List

from modules.fusion_engine import PatientState

logger = logging.getLogger(__name__)


class SessionLogger:
    """Logs session data to JSONL files for later review."""

    def __init__(self, log_dir: str = "data/session_logs"):
        self.log_dir = log_dir
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create log directory {log_dir}: {e}")
            raise
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_file = os.path.join(
            log_dir, f"session_{self._session_id}.jsonl"
        )
        self._entry_count = 0

    def log_state(self, state: PatientState):
        """Log a patient state to the session file."""
        try:
            entry = {
                "entry_id": self._entry_count,
                "session_id": self._session_id,
                **state.to_dict(),
            }
            with open(self._log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
            self._entry_count += 1
        except (IOError, OSError) as e:
            logger.error(f"Failed to write to log file {self._log_file}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error logging state: {e}")

    def load_session(self, session_file: str) -> List[dict]:
        """Load a session log from file."""
        entries = []
        filepath = os.path.join(self.log_dir, session_file)
        if os.path.exists(filepath):
            with open(filepath) as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))
        return entries

    def list_sessions(self) -> List[str]:
        """List available session log files."""
        if not os.path.exists(self.log_dir):
            return []
        return sorted([
            f for f in os.listdir(self.log_dir)
            if f.startswith("session_") and f.endswith(".jsonl")
        ])

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def entry_count(self) -> int:
        return self._entry_count
