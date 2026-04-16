"""
Patient Care Monitor - Alert System
====================================
Manages caregiver alerts with cooldown, escalation, and logging.
"""

from alerts.alert_system import AlertSystem, Alert

__all__ = [
    "AlertSystem",
    "Alert",
]
