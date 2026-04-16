"""
Visualization Utilities
=======================
Interactive data visualization components using Chart.js.

Features:
- Patient state trend charts
- Pain level history charts
- Heart rate trend charts
- Comfort/arousal scatter plots
- Action Unit radar charts
"""

import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class ChartJSGenerator:
    """Generate Chart.js configurations for various chart types."""
    
    def __init__(self):
        """Initialize ChartJS generator."""
        self.default_colors = {
            "primary": "#4dabf7",
            "success": "#51cf66",
            "warning": "#fcc419",
            "danger": "#ff6b6b",
            "info": "#339af0",
            "secondary": "#868e96"
        }
    
    def create_line_chart(
        self,
        labels: List[str],
        datasets: List[Dict[str, Any]],
        title: str = "",
        options: Optional[Dict] = None
    ) -> Dict:
        """
        Create a line chart configuration.
        
        Args:
            labels: X-axis labels
            datasets: List of dataset dictionaries with data, label, color
            title: Chart title
            options: Additional Chart.js options
            
        Returns:
            Chart.js configuration dictionary
        """
        try:
            config = {
                "type": "line",
                "data": {
                    "labels": labels,
                    "datasets": []
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": bool(title),
                            "text": title,
                            "font": {"size": 16}
                        },
                        "legend": {
                            "display": True,
                            "position": "top"
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": True,
                            "grid": {"color": "rgba(255,255,255,0.1)"}
                        },
                        "x": {
                            "grid": {"color": "rgba(255,255,255,0.1)"}
                        }
                    },
                    "animation": {"duration": 0}
                }
            }
            
            # Add datasets with default styling
            for i, dataset in enumerate(datasets):
                color = dataset.get("color", self.default_colors["primary"])
                config["data"]["datasets"].append({
                    "label": dataset.get("label", f"Dataset {i+1}"),
                    "data": dataset.get("data", []),
                    "borderColor": color,
                    "backgroundColor": color + "20",  # Add transparency
                    "fill": dataset.get("fill", False),
                    "tension": dataset.get("tension", 0.4)
                })
            
            # Merge custom options
            if options:
                self._deep_merge(config["options"], options)
            
            logger.info("Line chart configuration created successfully")
            return config
        except Exception as e:
            logger.error(f"Error creating line chart: {e}")
            return {"error": "Failed to create line chart"}
    
    def create_bar_chart(
        self,
        labels: List[str],
        datasets: List[Dict[str, Any]],
        title: str = "",
        horizontal: bool = False,
        options: Optional[Dict] = None
    ) -> Dict:
        """
        Create a bar chart configuration.
        
        Args:
            labels: X-axis labels
            datasets: List of dataset dictionaries
            title: Chart title
            horizontal: Whether to create horizontal bar chart
            options: Additional Chart.js options
            
        Returns:
            Chart.js configuration dictionary
        """
        try:
            config = {
                "type": "bar" if not horizontal else "bar",
                "data": {
                    "labels": labels,
                    "datasets": []
                },
                "options": {
                    "indexAxis": "y" if horizontal else "x",
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": bool(title),
                            "text": title,
                            "font": {"size": 16}
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": True,
                            "grid": {"color": "rgba(255,255,255,0.1)"}
                        },
                        "x": {
                            "grid": {"color": "rgba(255,255,255,0.1)"}
                        }
                    },
                    "animation": {"duration": 0}
                }
            }
            
            # Add datasets with default styling
            for i, dataset in enumerate(datasets):
                color = dataset.get("color", self.default_colors["primary"])
                config["data"]["datasets"].append({
                    "label": dataset.get("label", f"Dataset {i+1}"),
                    "data": dataset.get("data", []),
                    "backgroundColor": color,
                    "borderColor": color,
                    "borderWidth": 1
                })
            
            # Merge custom options
            if options:
                self._deep_merge(config["options"], options)
            
            logger.info("Bar chart configuration created successfully")
            return config
        except Exception as e:
            logger.error(f"Error creating bar chart: {e}")
            return {"error": "Failed to create bar chart"}
    
    def create_radar_chart(
        self,
        labels: List[str],
        datasets: List[Dict[str, Any]],
        title: str = "",
        options: Optional[Dict] = None
    ) -> Dict:
        """
        Create a radar chart configuration.
        
        Args:
            labels: Axis labels
            datasets: List of dataset dictionaries
            title: Chart title
            options: Additional Chart.js options
            
        Returns:
            Chart.js configuration dictionary
        """
        try:
            config = {
                "type": "radar",
                "data": {
                    "labels": labels,
                    "datasets": []
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": bool(title),
                            "text": title,
                            "font": {"size": 16}
                        }
                    },
                    "scales": {
                        "r": {
                            "beginAtZero": True,
                            "max": 1.0,
                            "grid": {"color": "rgba(255,255,255,0.1)"}
                        }
                    },
                    "animation": {"duration": 0}
                }
            }
            
            # Add datasets with default styling
            for i, dataset in enumerate(datasets):
                color = dataset.get("color", self.default_colors["primary"])
                config["data"]["datasets"].append({
                    "label": dataset.get("label", f"Dataset {i+1}"),
                    "data": dataset.get("data", []),
                    "borderColor": color,
                    "backgroundColor": color + "40",
                    "pointBackgroundColor": color,
                    "pointBorderColor": "#fff",
                    "pointHoverBackgroundColor": "#fff",
                    "pointHoverBorderColor": color
                })
            
            # Merge custom options
            if options:
                self._deep_merge(config["options"], options)
            
            logger.info("Radar chart configuration created successfully")
            return config
        except Exception as e:
            logger.error(f"Error creating radar chart: {e}")
            return {"error": "Failed to create radar chart"}
    
    def create_doughnut_chart(
        self,
        labels: List[str],
        data: List[float],
        title: str = "",
        colors: Optional[List[str]] = None,
        options: Optional[Dict] = None
    ) -> Dict:
        """
        Create a doughnut chart configuration.
        
        Args:
            labels: Segment labels
            data: Data values
            title: Chart title
            colors: Custom colors for segments
            options: Additional Chart.js options
            
        Returns:
            Chart.js configuration dictionary
        """
        try:
            if colors is None:
                colors = [
                    self.default_colors["primary"],
                    self.default_colors["success"],
                    self.default_colors["warning"],
                    self.default_colors["danger"],
                    self.default_colors["info"]
                ]
            
            config = {
                "type": "doughnut",
                "data": {
                    "labels": labels,
                    "datasets": [{
                        "data": data,
                        "backgroundColor": colors,
                        "borderColor": "#1e1e2e",
                        "borderWidth": 2
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": bool(title),
                            "text": title,
                            "font": {"size": 16}
                        },
                        "legend": {
                            "display": True,
                            "position": "right"
                        }
                    },
                    "animation": {"duration": 0}
                }
            }
            
            # Merge custom options
            if options:
                self._deep_merge(config["options"], options)
            
            logger.info("Doughnut chart configuration created successfully")
            return config
        except Exception as e:
            logger.error(f"Error creating doughnut chart: {e}")
            return {"error": "Failed to create doughnut chart"}
    
    def _deep_merge(self, base: Dict, update: Dict) -> None:
        """Deep merge two dictionaries."""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value


def patient_state_trend_chart(patient_states: List[Any]) -> Dict:
    """
    Create patient state trend chart.
    
    Args:
        patient_states: List of PatientState objects
        
    Returns:
        Chart.js configuration for patient state trends
    """
    generator = ChartJSGenerator()
    
    labels = [state.timestamp.strftime("%H:%M:%S") for state in patient_states]
    
    datasets = [
        {
            "label": "Comfort",
            "data": [state.comfort for state in patient_states],
            "color": generator.default_colors["success"],
            "fill": True
        },
        {
            "label": "Arousal",
            "data": [state.arousal for state in patient_states],
            "color": generator.default_colors["warning"],
            "fill": True
        },
        {
            "label": "Pain Level",
            "data": [state.pain_level for state in patient_states],
            "color": generator.default_colors["danger"],
            "fill": False
        }
    ]
    
    return generator.create_line_chart(
        labels=labels,
        datasets=datasets,
        title="Patient State Trends"
    )


def pain_level_history_chart(pain_assessments: List[Any]) -> Dict:
    """
    Create pain level history chart.
    
    Args:
        pain_assessments: List of PainAssessment objects
        
    Returns:
        Chart.js configuration for pain level history
    """
    generator = ChartJSGenerator()
    
    labels = [assessment.timestamp.strftime("%H:%M:%S") for assessment in pain_assessments]
    
    datasets = [
        {
            "label": "PSPI Score",
            "data": [assessment.pspi_score for assessment in pain_assessments],
            "color": generator.default_colors["danger"]
        },
        {
            "label": "Confidence",
            "data": [assessment.confidence for assessment in pain_assessments],
            "color": generator.default_colors["info"]
        }
    ]
    
    return generator.create_line_chart(
        labels=labels,
        datasets=datasets,
        title="Pain Level History"
    )


def heart_rate_trend_chart(hr_results: List[Any]) -> Dict:
    """
    Create heart rate trend chart.
    
    Args:
        hr_results: List of HeartRateResult objects
        
    Returns:
        Chart.js configuration for heart rate trends
    """
    generator = ChartJSGenerator()
    
    labels = [result.timestamp.strftime("%H:%M:%S") for result in hr_results]
    
    datasets = [
        {
            "label": "Heart Rate (BPM)",
            "data": [result.bpm for result in hr_results],
            "color": generator.default_colors["primary"]
        },
        {
            "label": "Confidence",
            "data": [result.confidence for result in hr_results],
            "color": generator.default_colors["success"]
        }
    ]
    
    return generator.create_line_chart(
        labels=labels,
        datasets=datasets,
        title="Heart Rate Trend"
    )


def action_unit_radar_chart(au_estimates: Any) -> Dict:
    """
    Create Action Unit radar chart.
    
    Args:
        au_estimates: AUEstimates object
        
    Returns:
        Chart.js configuration for Action Units
    """
    generator = ChartJSGenerator()
    
    # Get top 10 most active AUs
    au_dict = au_estimates.__dict__ if hasattr(au_estimates, '__dict__') else {}
    sorted_aus = sorted(au_dict.items(), key=lambda x: abs(x[1]), reverse=True)[:10]
    
    labels = [au[0] for au in sorted_aus]
    data = [abs(au[1]) for au in sorted_aus]
    
    datasets = [
        {
            "label": "AU Intensity",
            "data": data,
            "color": generator.default_colors["primary"]
        }
    ]
    
    return generator.create_radar_chart(
        labels=labels,
        datasets=datasets,
        title="Top 10 Action Units"
    )


def macronutrient_breakdown_chart(nutrition_data: Dict[str, float]) -> Dict:
    """
    Create macronutrient breakdown doughnut chart.
    
    Args:
        nutrition_data: Dictionary with protein, carbs, fat values
        
    Returns:
        Chart.js configuration for macronutrient breakdown
    """
    generator = ChartJSGenerator()
    
    labels = ["Protein", "Carbohydrates", "Fat"]
    data = [
        nutrition_data.get("protein", 0),
        nutrition_data.get("carbs", 0),
        nutrition_data.get("fat", 0)
    ]
    
    return generator.create_doughnut_chart(
        labels=labels,
        data=data,
        title="Macronutrient Breakdown"
    )


def disease_risk_chart(risk_data: Dict[str, float]) -> Dict:
    """
    Create disease risk horizontal bar chart.
    
    Args:
        risk_data: Dictionary with disease names and risk levels
        
    Returns:
        Chart.js configuration for disease risks
    """
    generator = ChartJSGenerator()
    
    # Sort by risk level
    sorted_risks = sorted(risk_data.items(), key=lambda x: x[1], reverse=True)
    
    labels = [risk[0] for risk in sorted_risks]
    data = [risk[1] for risk in sorted_risks]
    
    # Color coding based on risk level
    colors = []
    for value in data:
        if value > 0.7:
            colors.append(generator.default_colors["danger"])
        elif value > 0.4:
            colors.append(generator.default_colors["warning"])
        else:
            colors.append(generator.default_colors["success"])
    
    datasets = [
        {
            "label": "Risk Level",
            "data": data,
            "color": colors
        }
    ]
    
    return generator.create_bar_chart(
        labels=labels,
        datasets=datasets,
        title="Disease Risk Overview",
        horizontal=True
    )
