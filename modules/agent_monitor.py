"""
Agent Monitor Module
====================
Real-time system metrics and agent status monitoring.

Features:
- Agent status tracking
- System metrics collection
- Performance monitoring
- Activity logging
- Analysis history
"""

import logging
import psutil
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent status types."""
    IDLE = "idle"
    ACTIVE = "active"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


class AgentMonitor:
    """
    Monitor analysis agents and system metrics.
    
    Tracks agent status, system performance, and activity logs
    for real-time dashboard display.
    """
    
    def __init__(self, max_history: int = 1000):
        """
        Initialize agent monitor.
        
        Args:
            max_history: Maximum number of activity log entries
        """
        self.agents: Dict[str, Dict] = {}
        self.activity_log = deque(maxlen=max_history)
        self.analysis_history = deque(maxlen=100)
        self.start_time = datetime.now()
        logger.info("Agent monitor initialized")
    
    def register_agent(self, agent_id: str, agent_name: str, agent_type: str) -> None:
        """
        Register an analysis agent.
        
        Args:
            agent_id: Unique agent identifier
            agent_name: Human-readable agent name
            agent_type: Type of agent (e.g., "face_analyzer", "pain_detector")
        """
        self.agents[agent_id] = {
            "name": agent_name,
            "type": agent_type,
            "status": AgentStatus.IDLE.value,
            "last_activity": None,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_processing_time": 0.0,
            "average_processing_time": 0.0,
            "registered_at": datetime.now().isoformat()
        }
        logger.info(f"Registered agent: {agent_name} ({agent_id})")
    
    def update_agent_status(self, agent_id: str, status: AgentStatus) -> None:
        """
        Update agent status.
        
        Args:
            agent_id: Agent identifier
            status: New agent status
        """
        if agent_id in self.agents:
            self.agents[agent_id]["status"] = status.value
            self.agents[agent_id]["last_activity"] = datetime.now().isoformat()
            
            # Log status change
            self.log_activity(
                agent_id,
                f"Status changed to {status.value}",
                "status_change"
            )
    
    def record_task_completion(self, agent_id: str, processing_time: float, success: bool = True) -> None:
        """
        Record task completion for agent.
        
        Args:
            agent_id: Agent identifier
            processing_time: Time taken to complete task in seconds
            success: Whether task completed successfully
        """
        if agent_id in self.agents:
            if success:
                self.agents[agent_id]["tasks_completed"] += 1
            else:
                self.agents[agent_id]["tasks_failed"] += 1
            
            self.agents[agent_id]["total_processing_time"] += processing_time
            total_tasks = (
                self.agents[agent_id]["tasks_completed"] + 
                self.agents[agent_id]["tasks_failed"]
            )
            self.agents[agent_id]["average_processing_time"] = (
                self.agents[agent_id]["total_processing_time"] / total_tasks
                if total_tasks > 0 else 0
            )
            
            self.log_activity(
                agent_id,
                f"Task completed in {processing_time:.3f}s - {'Success' if success else 'Failed'}",
                "task_completion"
            )
    
    def log_activity(self, agent_id: str, message: str, activity_type: str) -> None:
        """
        Log activity for an agent.
        
        Args:
            agent_id: Agent identifier
            message: Activity message
            activity_type: Type of activity
        """
        entry = {
            "agent_id": agent_id,
            "message": message,
            "type": activity_type,
            "timestamp": datetime.now().isoformat()
        }
        self.activity_log.append(entry)
    
    def get_agent_status(self, agent_id: str) -> Optional[Dict]:
        """
        Get status of a specific agent.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Agent status dictionary or None
        """
        return self.agents.get(agent_id)
    
    def get_all_agent_statuses(self) -> Dict[str, Dict]:
        """
        Get status of all registered agents.
        
        Returns:
            Dictionary of all agent statuses
        """
        return self.agents
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """
        Get current system metrics.
        
        Returns:
            Dictionary with system metrics
        """
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Network I/O
            net_io = psutil.net_io_counters()
            
            # Process count
            process_count = len(psutil.pids())
            
            # Uptime
            uptime = (datetime.now() - self.start_time).total_seconds()
            
            return {
                "cpu": {
                    "percent": cpu_percent,
                    "core_count": psutil.cpu_count(),
                    "frequency": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else {}
                },
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "percent": memory.percent,
                    "used": memory.used,
                    "free": memory.free
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent
                },
                "network": {
                    "bytes_sent": net_io.bytes_sent,
                    "bytes_recv": net_io.bytes_recv,
                    "packets_sent": net_io.packets_sent,
                    "packets_recv": net_io.packets_recv
                },
                "processes": {
                    "count": process_count
                },
                "uptime": {
                    "seconds": uptime,
                    "formatted": self._format_uptime(uptime)
                },
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            return {"error": str(e)}
    
    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    
    def get_activity_log(self, limit: int = 50) -> List[Dict]:
        """
        Get recent activity log entries.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of activity log entries
        """
        return list(self.activity_log)[-limit:]
    
    def get_analysis_history(self, limit: int = 20) -> List[Dict]:
        """
        Get recent analysis history.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of analysis history entries
        """
        return list(self.analysis_history)[-limit:]
    
    def record_analysis(self, analysis_type: str, result: Dict, duration: float) -> None:
        """
        Record an analysis in history.
        
        Args:
            analysis_type: Type of analysis performed
            result: Analysis result
            duration: Time taken for analysis
        """
        entry = {
            "type": analysis_type,
            "result": result,
            "duration": duration,
            "timestamp": datetime.now().isoformat()
        }
        self.analysis_history.append(entry)
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Get summary statistics for the monitoring system.
        
        Returns:
            Dictionary with summary statistics
        """
        total_tasks = sum(
            agent["tasks_completed"] + agent["tasks_failed"]
            for agent in self.agents.values()
        )
        total_completed = sum(
            agent["tasks_completed"]
            for agent in self.agents.values()
        )
        total_failed = sum(
            agent["tasks_failed"]
            for agent in self.agents.values()
        )
        
        active_agents = sum(
            1 for agent in self.agents.values()
            if agent["status"] == AgentStatus.ACTIVE.value
        )
        
        error_agents = sum(
            1 for agent in self.agents.values()
            if agent["status"] == AgentStatus.ERROR.value
        )
        
        success_rate = (total_completed / total_tasks * 100) if total_tasks > 0 else 0
        
        return {
            "agents": {
                "total": len(self.agents),
                "active": active_agents,
                "error": error_agents,
                "idle": len(self.agents) - active_agents - error_agents
            },
            "tasks": {
                "total": total_tasks,
                "completed": total_completed,
                "failed": total_failed,
                "success_rate": success_rate
            },
            "uptime": (datetime.now() - self.start_time).total_seconds(),
            "activity_log_entries": len(self.activity_log),
            "analysis_history_entries": len(self.analysis_history),
            "timestamp": datetime.now().isoformat()
        }
    
    def reset_agent_stats(self, agent_id: str) -> None:
        """
        Reset statistics for a specific agent.
        
        Args:
            agent_id: Agent identifier
        """
        if agent_id in self.agents:
            self.agents[agent_id]["tasks_completed"] = 0
            self.agents[agent_id]["tasks_failed"] = 0
            self.agents[agent_id]["total_processing_time"] = 0.0
            self.agents[agent_id]["average_processing_time"] = 0.0
            
            self.log_activity(
                agent_id,
                "Statistics reset",
                "reset"
            )
            logger.info(f"Reset statistics for agent {agent_id}")


# Global instance
agent_monitor = AgentMonitor()


# Convenience functions
def get_system_metrics() -> Dict[str, Any]:
    """Get current system metrics (convenience function)."""
    return agent_monitor.get_system_metrics()


def get_agent_statuses() -> Dict[str, Dict]:
    """Get all agent statuses (convenience function)."""
    return agent_monitor.get_all_agent_statuses()


def get_summary_stats() -> Dict[str, Any]:
    """Get summary statistics (convenience function)."""
    return agent_monitor.get_summary_stats()
