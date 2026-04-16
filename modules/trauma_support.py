"""
Trauma Support Module
====================
Provides trauma first aid tools and crisis support for patients.

Features:
- 5-4-3-2-1 Sensory Grounding technique
- Box Breathing exercises
- Emergency services integration
- Calming visualizations
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
import json

logger = logging.getLogger(__name__)


class TraumaSupport:
    """
    Trauma first aid and crisis support tools.
    
    Provides evidence-based techniques for managing acute distress,
    anxiety, and panic attacks.
    """
    
    def __init__(self):
        """Initialize trauma support module."""
        self.emergency_contacts = {
            "general": "911",
            "suicide_prevention": "988",
            "poison_control": "1-800-222-1222",
            "domestic_violence": "1-800-799-7233"
        }
        self.grounding_steps = self._initialize_grounding_steps()
        self.breathing_patterns = self._initialize_breathing_patterns()
        self.calming_messages = self._load_calming_messages()
    
    def _initialize_grounding_steps(self) -> Dict[str, str]:
        """Initialize 5-4-3-2-1 sensory grounding steps."""
        return {
            "5": "5 things you can SEE",
            "4": "4 things you can TOUCH",
            "3": "3 things you can HEAR",
            "2": "2 things you can SMELL",
            "1": "1 thing you can TASTE"
        }
    
    def _initialize_breathing_patterns(self) -> Dict[str, Dict[str, int]]:
        """Initialize breathing exercise patterns."""
        return {
            "box_breathing": {
                "inhale": 4,
                "hold": 4,
                "exhale": 4,
                "hold_empty": 4,
                "description": "Box Breathing: 4-4-4-4 pattern"
            },
            "4-7-8": {
                "inhale": 4,
                "hold": 7,
                "exhale": 8,
                "hold_empty": 0,
                "description": "4-7-8 Breathing: 4-7-8 pattern"
            },
            "equal_breathing": {
                "inhale": 4,
                "hold": 0,
                "exhale": 4,
                "hold_empty": 0,
                "description": "Equal Breathing: 4-4 pattern"
            }
        }
    
    def _load_calming_messages(self) -> List[str]:
        """Load calming and supportive messages."""
        return [
            "You are safe right now. This feeling will pass.",
            "Take your time. There's no rush.",
            "You are stronger than you know.",
            "This is temporary. You will get through this.",
            "Focus on your breath. In and out, slowly.",
            "You are not alone. Help is available.",
            "One moment at a time. Just one moment.",
            "You have survived 100% of your bad days so far.",
            "It's okay to not be okay sometimes.",
            "You are worthy of care and support."
        ]
    
    def get_grounding_exercise(self) -> Dict:
        """
        Get the 5-4-3-2-1 sensory grounding exercise.
        
        Returns:
            Dictionary with grounding steps and instructions.
        """
        try:
            exercise = {
                "name": "5-4-3-2-1 Sensory Grounding",
                "description": "Use your five senses to ground yourself in the present moment",
                "steps": self.grounding_steps,
                "instructions": [
                    "Take a deep breath and look around you.",
                    "Name 5 things you can see.",
                    "Name 4 things you can physically touch.",
                    "Name 3 things you can hear.",
                    "Name 2 things you can smell.",
                    "Name 1 thing you can taste."
                ],
                "duration_minutes": 5,
                "evidence": "Evidence-based technique for managing anxiety and dissociation"
            }
            logger.info("Grounding exercise retrieved successfully")
            return exercise
        except Exception as e:
            logger.error(f"Error retrieving grounding exercise: {e}")
            return {"error": "Failed to retrieve grounding exercise"}
    
    def get_breathing_exercise(self, pattern: str = "box_breathing") -> Dict:
        """
        Get a breathing exercise pattern.
        
        Args:
            pattern: Breathing pattern name (box_breathing, 4-7-8, equal_breathing)
            
        Returns:
            Dictionary with breathing pattern details.
        """
        try:
            if pattern not in self.breathing_patterns:
                logger.warning(f"Unknown breathing pattern: {pattern}, using box_breathing")
                pattern = "box_breathing"
            
            exercise = {
                "name": self.breathing_patterns[pattern]["description"],
                "pattern": self.breathing_patterns[pattern],
                "instructions": self._get_breathing_instructions(pattern),
                "cycles": 5,
                "total_duration_minutes": self._calculate_breathing_duration(pattern),
                "evidence": "Breathing exercises reduce stress and activate parasympathetic nervous system"
            }
            logger.info(f"Breathing exercise '{pattern}' retrieved successfully")
            return exercise
        except Exception as e:
            logger.error(f"Error retrieving breathing exercise: {e}")
            return {"error": "Failed to retrieve breathing exercise"}
    
    def _get_breathing_instructions(self, pattern: str) -> List[str]:
        """Get instructions for a breathing pattern."""
        instructions = {
            "box_breathing": [
                "Inhale slowly for 4 seconds through your nose",
                "Hold your breath for 4 seconds",
                "Exhale slowly for 4 seconds through your mouth",
                "Hold empty for 4 seconds",
                "Repeat for 5 cycles"
            ],
            "4-7-8": [
                "Inhale slowly for 4 seconds through your nose",
                "Hold your breath for 7 seconds",
                "Exhale slowly for 8 seconds through your mouth",
                "Repeat for 4 cycles"
            ],
            "equal_breathing": [
                "Inhale slowly for 4 seconds through your nose",
                "Exhale slowly for 4 seconds through your mouth",
                "Repeat for 10 cycles"
            ]
        }
        return instructions.get(pattern, instructions["box_breathing"])
    
    def _calculate_breathing_duration(self, pattern: str) -> float:
        """Calculate total duration of breathing exercise in minutes."""
        pattern_data = self.breathing_patterns[pattern]
        cycle_duration = sum(pattern_data.values())
        cycles = 5 if pattern == "box_breathing" else 4 if pattern == "4-7-8" else 10
        return (cycle_duration * cycles) / 60
    
    def get_random_calming_message(self) -> str:
        """
        Get a random calming message.
        
        Returns:
            Calming and supportive message.
        """
        import random
        try:
            message = random.choice(self.calming_messages)
            logger.info("Calming message retrieved successfully")
            return message
        except Exception as e:
            logger.error(f"Error retrieving calming message: {e}")
            return "Take a deep breath. You are safe."
    
    def get_emergency_contacts(self) -> Dict[str, str]:
        """
        Get emergency contact information.
        
        Returns:
            Dictionary of emergency contacts.
        """
        return {
            "emergency_services": self.emergency_contacts["general"],
            "suicide_prevention_hotline": self.emergency_contacts["suicide_prevention"],
            "poison_control": self.emergency_contacts["poison_control"],
            "domestic_violence_hotline": self.emergency_contacts["domestic_violence"],
            "note": "If you or someone you know is in immediate danger, call emergency services (911 in US)"
        }
    
    def assess_immediate_danger(self, user_input: str) -> Dict:
        """
        Assess if user is expressing immediate danger.
        
        Args:
            user_input: User's text input
            
        Returns:
            Dictionary with danger assessment and recommendations.
        """
        try:
            danger_keywords = [
                "suicide", "kill myself", "end it all", "want to die",
                "hurt myself", "self harm", "overdose",
                "emergency", "danger", "help me now"
            ]
            
            user_input_lower = user_input.lower()
            danger_detected = any(keyword in user_input_lower for keyword in danger_keywords)
            
            assessment = {
                "danger_detected": danger_detected,
                "timestamp": datetime.now().isoformat(),
                "recommendation": self._get_danger_recommendation(danger_detected)
            }
            
            if danger_detected:
                logger.warning("Immediate danger detected in user input")
            
            return assessment
        except Exception as e:
            logger.error(f"Error assessing immediate danger: {e}")
            return {"error": "Failed to assess danger"}
    
    def _get_danger_recommendation(self, danger_detected: bool) -> str:
        """Get recommendation based on danger assessment."""
        if danger_detected:
            return (
                "IMMEDIATE ACTION REQUIRED: Please call emergency services (911) "
                "or the suicide prevention hotline (988) right now. "
                "You are not alone and help is available 24/7."
            )
        else:
            return "Continue using grounding exercises and breathing techniques. If feelings persist, please reach out to a professional."
    
    def get_crisis_resources(self) -> Dict:
        """
        Get crisis resources and support information.
        
        Returns:
            Dictionary of crisis resources.
        """
        return {
            "hotlines": {
                "suicide_prevention": {
                    "name": "National Suicide Prevention Lifeline",
                    "number": "988",
                    "available": "24/7",
                    "description": "Free, confidential support for people in distress"
                },
                "crisis_text_line": {
                    "name": "Crisis Text Line",
                    "number": "Text HOME to 741741",
                    "available": "24/7",
                    "description": "Free text-based support for people in crisis"
                },
                "veterans_crisis": {
                    "name": "Veterans Crisis Line",
                    "number": "1-800-273-8255",
                    "available": "24/7",
                    "description": "Confidential support for veterans in crisis"
                }
            },
            "online_resources": [
                {
                    "name": "SAMHSA National Helpline",
                    "url": "https://www.samhsa.gov/find-help",
                    "description": "Treatment referral and information service"
                },
                {
                    "name": "National Alliance on Mental Illness (NAMI)",
                    "url": "https://www.nami.org",
                    "description": "Mental health support and education"
                }
            ],
            "disclaimer": (
                "This tool is not a substitute for professional mental health care. "
                "If you are experiencing a mental health crisis, please contact "
                "emergency services or a mental health professional immediately."
            )
        }
    
    def log_support_session(self, user_id: str, support_type: str, duration_minutes: int) -> bool:
        """
        Log a support session for tracking and analytics.
        
        Args:
            user_id: User identifier
            support_type: Type of support used (grounding, breathing, etc.)
            duration_minutes: Duration of support session
            
        Returns:
            True if logged successfully, False otherwise.
        """
        try:
            session_data = {
                "user_id": user_id,
                "support_type": support_type,
                "duration_minutes": duration_minutes,
                "timestamp": datetime.now().isoformat()
            }
            # In production, this would be logged to database
            logger.info(f"Support session logged: {session_data}")
            return True
        except Exception as e:
            logger.error(f"Error logging support session: {e}")
            return False


# Convenience functions for quick access
def get_grounding_exercise() -> Dict:
    """Get grounding exercise (convenience function)."""
    support = TraumaSupport()
    return support.get_grounding_exercise()


def get_breathing_exercise(pattern: str = "box_breathing") -> Dict:
    """Get breathing exercise (convenience function)."""
    support = TraumaSupport()
    return support.get_breathing_exercise(pattern)


def get_calming_message() -> str:
    """Get calming message (convenience function)."""
    support = TraumaSupport()
    return support.get_random_calming_message()


def get_emergency_contacts() -> Dict[str, str]:
    """Get emergency contacts (convenience function)."""
    support = TraumaSupport()
    return support.get_emergency_contacts()
