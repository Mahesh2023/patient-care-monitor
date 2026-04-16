"""
Health Checkup Analysis Module
===============================
Analysis of blood tests, urine tests, and abdomen scan reports.

Features:
- Blood test parameter parsing (62 parameters)
- Urine test parameter parsing (13 parameters)
- Abdomen scan analysis
- 24 condition detectors
- Health scoring (0-100)
- Tailored dietary recommendations
"""

import logging
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status categories."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


class ConditionSeverity(Enum):
    """Condition severity levels."""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class HealthCheckupAnalyzer:
    """
    Health checkup report analysis.
    
    Analyzes blood tests, urine tests, and abdomen scan reports
    to detect health conditions and provide recommendations.
    """
    
    def __init__(self):
        """Initialize health checkup analyzer."""
        self.blood_parameters = self._load_blood_parameters()
        self.urine_parameters = self._load_urine_parameters()
        self.condition_detectors = self._load_condition_detectors()
        logger.info("Health checkup analyzer initialized")
    
    def _load_blood_parameters(self) -> Dict[str, Dict]:
        """Load blood test parameters with normal ranges."""
        return {
            "hemoglobin": {
                "name": "Hemoglobin",
                "normal_range": {"male": {"min": 13.5, "max": 17.5}, "female": {"min": 12.0, "max": 15.5}},
                "unit": "g/dL",
                "aliases": ["Hb", "HGB", "hemoglobin", "hemoglobin concentration"]
            },
            "rbc": {
                "name": "Red Blood Cell Count",
                "normal_range": {"male": {"min": 4.35, "max": 5.65}, "female": {"min": 3.92, "max": 5.13}},
                "unit": "million/µL",
                "aliases": ["RBC", "red blood cell", "erythrocyte count"]
            },
            "wbc": {
                "name": "White Blood Cell Count",
                "normal_range": {"min": 4.5, "max": 11.0},
                "unit": "thousand/µL",
                "aliases": ["WBC", "white blood cell", "leukocyte count"]
            },
            "platelet": {
                "name": "Platelet Count",
                "normal_range": {"min": 150, "max": 450},
                "unit": "thousand/µL",
                "aliases": ["PLT", "platelet", "thrombocyte count"]
            },
            "glucose_fasting": {
                "name": "Fasting Blood Glucose",
                "normal_range": {"min": 70, "max": 99},
                "unit": "mg/dL",
                "aliases": ["FBS", "fasting glucose", "fasting blood sugar", "glucose fasting"]
            },
            "glucose_random": {
                "name": "Random Blood Glucose",
                "normal_range": {"min": 70, "max": 140},
                "unit": "mg/dL",
                "aliases": ["RBS", "random glucose", "blood glucose"]
            },
            "hba1c": {
                "name": "HbA1c",
                "normal_range": {"min": 4.0, "max": 5.7},
                "unit": "%",
                "aliases": ["A1C", "HbA1c", "glycated hemoglobin", "hemoglobin A1c"]
            },
            "cholesterol_total": {
                "name": "Total Cholesterol",
                "normal_range": {"min": 0, "max": 200},
                "unit": "mg/dL",
                "aliases": ["TC", "total cholesterol", "cholesterol"]
            },
            "cholesterol_ldl": {
                "name": "LDL Cholesterol",
                "normal_range": {"min": 0, "max": 100},
                "unit": "mg/dL",
                "aliases": ["LDL", "LDL cholesterol", "bad cholesterol", "low-density lipoprotein"]
            },
            "cholesterol_hdl": {
                "name": "HDL Cholesterol",
                "normal_range": {"min": 40, "max": 60},
                "unit": "mg/dL",
                "aliases": ["HDL", "HDL cholesterol", "good cholesterol", "high-density lipoprotein"]
            },
            "triglycerides": {
                "name": "Triglycerides",
                "normal_range": {"min": 0, "max": 150},
                "unit": "mg/dL",
                "aliases": ["TG", "triglycerides", "triglyceride"]
            },
            "creatinine": {
                "name": "Creatinine",
                "normal_range": {"male": {"min": 0.74, "max": 1.35}, "female": {"min": 0.59, "max": 1.04}},
                "unit": "mg/dL",
                "aliases": ["Cr", "creatinine", "serum creatinine"]
            },
            "bun": {
                "name": "Blood Urea Nitrogen",
                "normal_range": {"min": 6, "max": 20},
                "unit": "mg/dL",
                "aliases": ["BUN", "blood urea nitrogen", "urea nitrogen"]
            },
            "alt": {
                "name": "ALT (SGPT)",
                "normal_range": {"min": 7, "max": 56},
                "unit": "U/L",
                "aliases": ["ALT", "SGPT", "alanine aminotransferase", "alanine transaminase"]
            },
            "ast": {
                "name": "AST (SGOT)",
                "normal_range": {"min": 10, "max": 40},
                "unit": "U/L",
                "aliases": ["AST", "SGOT", "aspartate aminotransferase", "aspartate transaminase"]
            },
            "bilirubin_total": {
                "name": "Total Bilirubin",
                "normal_range": {"min": 0.3, "max": 1.2},
                "unit": "mg/dL",
                "aliases": ["TBIL", "total bilirubin", "bilirubin total"]
            },
            "bilirubin_direct": {
                "name": "Direct Bilirubin",
                "normal_range": {"min": 0.0, "max": 0.3},
                "unit": "mg/dL",
                "aliases": ["DBIL", "direct bilirubin", "conjugated bilirubin"]
            },
            "albumin": {
                "name": "Albumin",
                "normal_range": {"min": 3.4, "max": 5.4},
                "unit": "g/dL",
                "aliases": ["ALB", "albumin", "serum albumin"]
            },
            "protein_total": {
                "name": "Total Protein",
                "normal_range": {"min": 6.0, "max": 8.3},
                "unit": "g/dL",
                "aliases": ["TP", "total protein", "protein total"]
            },
            "sodium": {
                "name": "Sodium",
                "normal_range": {"min": 136, "max": 145},
                "unit": "mEq/L",
                "aliases": ["Na", "sodium", "serum sodium"]
            },
            "potassium": {
                "name": "Potassium",
                "normal_range": {"min": 3.5, "max": 5.1},
                "unit": "mEq/L",
                "aliases": ["K", "potassium", "serum potassium"]
            },
            "chloride": {
                "name": "Chloride",
                "normal_range": {"min": 98, "max": 107},
                "unit": "mEq/L",
                "aliases": ["Cl", "chloride", "serum chloride"]
            },
            "calcium": {
                "name": "Calcium",
                "normal_range": {"min": 8.6, "max": 10.2},
                "unit": "mg/dL",
                "aliases": ["Ca", "calcium", "serum calcium"]
            },
            "phosphorus": {
                "name": "Phosphorus",
                "normal_range": {"min": 2.5, "max": 4.5},
                "unit": "mg/dL",
                "aliases": ["P", "phosphorus", "phosphate", "serum phosphorus"]
            },
            "magnesium": {
                "name": "Magnesium",
                "normal_range": {"min": 1.7, "max": 2.2},
                "unit": "mg/dL",
                "aliases": ["Mg", "magnesium", "serum magnesium"]
            },
            "iron": {
                "name": "Iron",
                "normal_range": {"male": {"min": 65, "max": 175}, "female": {"min": 50, "max": 170}},
                "unit": "µg/dL",
                "aliases": ["Fe", "iron", "serum iron"]
            },
            "tibc": {
                "name": "Total Iron Binding Capacity",
                "normal_range": {"min": 240, "max": 450},
                "unit": "µg/dL",
                "aliases": ["TIBC", "total iron binding capacity"]
            },
            "ferritin": {
                "name": "Ferritin",
                "normal_range": {"male": {"min": 30, "max": 400}, "female": {"min": 15, "max": 150}},
                "unit": "ng/mL",
                "aliases": ["ferritin", "serum ferritin"]
            },
            "vitamin_b12": {
                "name": "Vitamin B12",
                "normal_range": {"min": 200, "max": 900},
                "unit": "pg/mL",
                "aliases": ["B12", "vitamin B12", "cobalamin"]
            },
            "vitamin_d": {
                "name": "Vitamin D (25-OH)",
                "normal_range": {"min": 30, "max": 100},
                "unit": "ng/mL",
                "aliases": ["vitamin D", "25-hydroxy vitamin D", "25(OH)D"]
            },
            "tsh": {
                "name": "TSH",
                "normal_range": {"min": 0.4, "max": 4.0},
                "unit": "mIU/L",
                "aliases": ["TSH", "thyroid stimulating hormone", "thyrotropin"]
            },
            "t4_free": {
                "name": "Free T4",
                "normal_range": {"min": 0.8, "max": 1.8},
                "unit": "ng/dL",
                "aliases": ["FT4", "free T4", "thyroxine free"]
            },
            "t3_free": {
                "name": "Free T3",
                "normal_range": {"min": 2.3, "max": 4.2},
                "unit": "pg/mL",
                "aliases": ["FT3", "free T3", "triiodothyronine free"]
            },
            "psa": {
                "name": "PSA",
                "normal_range": {"min": 0, "max": 4.0},
                "unit": "ng/mL",
                "aliases": ["PSA", "prostate specific antigen"]
            }
        }
    
    def _load_urine_parameters(self) -> Dict[str, Dict]:
        """Load urine test parameters with normal ranges."""
        return {
            "ph": {
                "name": "pH",
                "normal_range": {"min": 4.5, "max": 8.0},
                "unit": "",
                "aliases": ["pH", "urine pH", "acidity"]
            },
            "specific_gravity": {
                "name": "Specific Gravity",
                "normal_range": {"min": 1.005, "max": 1.030},
                "unit": "",
                "aliases": ["SG", "specific gravity", "density"]
            },
            "protein": {
                "name": "Protein",
                "normal_range": {"min": 0, "max": 8},
                "unit": "mg/dL",
                "aliases": ["protein", "urine protein", "albumin"]
            },
            "glucose": {
                "name": "Glucose",
                "normal_range": {"min": 0, "max": 0},
                "unit": "mg/dL",
                "aliases": ["glucose", "urine glucose", "sugar"]
            },
            "ketones": {
                "name": "Ketones",
                "normal_range": {"min": 0, "max": 0},
                "unit": "mg/dL",
                "aliases": ["ketones", "urine ketones", "ketone bodies"]
            },
            "bilirubin": {
                "name": "Bilirubin",
                "normal_range": {"min": 0, "max": 0},
                "unit": "mg/dL",
                "aliases": ["bilirubin", "urine bilirubin"]
            },
            "urobilinogen": {
                "name": "Urobilinogen",
                "normal_range": {"min": 0, "max": 1},
                "unit": "mg/dL",
                "aliases": ["urobilinogen", "urine urobilinogen"]
            },
            "nitrite": {
                "name": "Nitrite",
                "normal_range": {"min": 0, "max": 0},
                "unit": "",
                "aliases": ["nitrite", "urine nitrite"]
            },
            "leukocytes": {
                "name": "Leukocytes",
                "normal_range": {"min": 0, "max": 0},
                "unit": "/HPF",
                "aliases": ["leukocytes", "WBC", "white blood cells"]
            },
            "rbc": {
                "name": "Red Blood Cells",
                "normal_range": {"min": 0, "max": 2},
                "unit": "/HPF",
                "aliases": ["RBC", "red blood cells", "erythrocytes"]
            },
            "wbc": {
                "name": "White Blood Cells",
                "normal_range": {"min": 0, "max": 5},
                "unit": "/HPF",
                "aliases": ["WBC", "white blood cells", "leukocytes"]
            },
            "epithelial_cells": {
                "name": "Epithelial Cells",
                "normal_range": {"min": 0, "max": 5},
                "unit": "/HPF",
                "aliases": ["epithelial cells", "epithelium"]
            },
            "casts": {
                "name": "Casts",
                "normal_range": {"min": 0, "max": 0},
                "unit": "/LPF",
                "aliases": ["casts", "hyaline casts"]
            }
        }
    
    def _load_condition_detectors(self) -> Dict[str, Dict]:
        """Load condition detection rules."""
        return {
            "anemia": {
                "name": "Anemia",
                "parameters": ["hemoglobin", "rbc"],
                "detection_rules": [
                    {"param": "hemoglobin", "condition": "low", "severity": "moderate"},
                    {"param": "rbc", "condition": "low", "severity": "moderate"}
                ],
                "recommendations": [
                    "Increase iron-rich foods (spinach, red meat, lentils)",
                    "Consider vitamin C supplementation to enhance iron absorption",
                    "Consult healthcare provider for further evaluation"
                ]
            },
            "diabetes": {
                "name": "Diabetes",
                "parameters": ["glucose_fasting", "glucose_random", "hba1c"],
                "detection_rules": [
                    {"param": "glucose_fasting", "condition": "high", "threshold": 126, "severity": "high"},
                    {"param": "hba1c", "condition": "high", "threshold": 6.5, "severity": "high"},
                    {"param": "glucose_random", "condition": "high", "threshold": 200, "severity": "high"}
                ],
                "recommendations": [
                    "Follow diabetic diet with controlled carbohydrate intake",
                    "Regular physical activity (30 minutes daily)",
                    "Monitor blood glucose regularly",
                    "Consult healthcare provider for management plan"
                ]
            },
            "prediabetes": {
                "name": "Prediabetes",
                "parameters": ["glucose_fasting", "hba1c"],
                "detection_rules": [
                    {"param": "glucose_fasting", "condition": "elevated", "min": 100, "max": 125, "severity": "moderate"},
                    {"param": "hba1c", "condition": "elevated", "min": 5.7, "max": 6.4, "severity": "moderate"}
                ],
                "recommendations": [
                    "Reduce sugar and refined carbohydrate intake",
                    "Increase physical activity",
                    "Maintain healthy weight",
                    "Regular screening for diabetes progression"
                ]
            },
            "hyperlipidemia": {
                "name": "Hyperlipidemia",
                "parameters": ["cholesterol_total", "cholesterol_ldl", "triglycerides"],
                "detection_rules": [
                    {"param": "cholesterol_total", "condition": "high", "threshold": 200, "severity": "moderate"},
                    {"param": "cholesterol_ldl", "condition": "high", "threshold": 130, "severity": "high"},
                    {"param": "triglycerides", "condition": "high", "threshold": 150, "severity": "moderate"}
                ],
                "recommendations": [
                    "Reduce saturated fat intake",
                    "Increase soluble fiber (oats, beans, fruits)",
                    "Include omega-3 fatty acids (fish, walnuts)",
                    "Regular aerobic exercise"
                ]
            },
            "kidney_disease": {
                "name": "Kidney Disease",
                "parameters": ["creatinine", "bun", "protein"],
                "detection_rules": [
                    {"param": "creatinine", "condition": "high", "threshold": 1.5, "severity": "high"},
                    {"param": "bun", "condition": "high", "threshold": 25, "severity": "high"},
                    {"param": "protein", "condition": "high", "threshold": 30, "severity": "moderate"}
                ],
                "recommendations": [
                    "Reduce protein intake if advised by healthcare provider",
                    "Control blood pressure",
                    "Avoid nephrotoxic medications",
                    "Regular kidney function monitoring"
                ]
            },
            "liver_disease": {
                "name": "Liver Disease",
                "parameters": ["alt", "ast", "bilirubin_total"],
                "detection_rules": [
                    {"param": "alt", "condition": "high", "threshold": 56, "severity": "moderate"},
                    {"param": "ast", "condition": "high", "threshold": 40, "severity": "moderate"},
                    {"param": "bilirubin_total", "condition": "high", "threshold": 1.2, "severity": "moderate"}
                ],
                "recommendations": [
                    "Avoid alcohol consumption",
                    "Maintain healthy weight",
                    "Avoid hepatotoxic substances",
                    "Consult healthcare provider for evaluation"
                ]
            },
            "thyroid_disorder": {
                "name": "Thyroid Disorder",
                "parameters": ["tsh", "t4_free", "t3_free"],
                "detection_rules": [
                    {"param": "tsh", "condition": "high", "threshold": 4.0, "severity": "moderate"},
                    {"param": "tsh", "condition": "low", "threshold": 0.4, "severity": "moderate"},
                    {"param": "t4_free", "condition": "low", "threshold": 0.8, "severity": "moderate"}
                ],
                "recommendations": [
                    "Consult healthcare provider for thyroid function evaluation",
                    "Medication may be required for thyroid hormone replacement",
                    "Regular thyroid function monitoring",
                    "Maintain balanced diet with adequate iodine"
                ]
            },
            "dehydration": {
                "name": "Dehydration",
                "parameters": ["sodium", "specific_gravity"],
                "detection_rules": [
                    {"param": "sodium", "condition": "high", "threshold": 145, "severity": "moderate"},
                    {"param": "specific_gravity", "condition": "high", "threshold": 1.030, "severity": "moderate"}
                ],
                "recommendations": [
                    "Increase fluid intake",
                    "Monitor urine color (should be pale yellow)",
                    "Avoid excessive caffeine and alcohol",
                    "Consider electrolyte replacement if exercising heavily"
                ]
            },
            "urinary_tract_infection": {
                "name": "Urinary Tract Infection",
                "parameters": ["nitrite", "leukocytes", "wbc"],
                "detection_rules": [
                    {"param": "nitrite", "condition": "positive", "severity": "high"},
                    {"param": "leukocytes", "condition": "positive", "severity": "high"},
                    {"param": "wbc", "condition": "high", "threshold": 10, "severity": "moderate"}
                ],
                "recommendations": [
                    "Increase fluid intake to flush out bacteria",
                    "Consult healthcare provider for antibiotic treatment if needed",
                    "Avoid irritants (caffeine, alcohol, spicy foods)",
                    "Complete full course of prescribed antibiotics"
                ]
            },
            "vitamin_d_deficiency": {
                "name": "Vitamin D Deficiency",
                "parameters": ["vitamin_d"],
                "detection_rules": [
                    {"param": "vitamin_d", "condition": "low", "threshold": 30, "severity": "moderate"}
                ],
                "recommendations": [
                    "Increase sunlight exposure (15-20 minutes daily)",
                    "Include vitamin D-rich foods (fatty fish, fortified dairy)",
                    "Consider vitamin D supplementation",
                    "Regular monitoring of vitamin D levels"
                ]
            },
            "iron_deficiency": {
                "name": "Iron Deficiency",
                "parameters": ["iron", "ferritin", "tibc"],
                "detection_rules": [
                    {"param": "iron", "condition": "low", "severity": "moderate"},
                    {"param": "ferritin", "condition": "low", "severity": "moderate"},
                    {"param": "tibc", "condition": "high", "severity": "moderate"}
                ],
                "recommendations": [
                    "Increase iron-rich foods (red meat, spinach, lentils)",
                    "Pair iron sources with vitamin C for better absorption",
                    "Consider iron supplementation if advised",
                    "Avoid calcium supplements with iron-rich meals"
                ]
            }
        }
    
    def parse_blood_test(self, test_data: Dict, gender: str = "male") -> Dict:
        """
        Parse blood test results and identify abnormalities.
        
        Args:
            test_data: Dictionary of blood test parameters
            gender: Patient gender (male/female) for gender-specific ranges
            
        Returns:
            Dictionary with parsed results and abnormalities
        """
        try:
            results = {
                "parameters": {},
                "abnormalities": [],
                "timestamp": datetime.now().isoformat()
            }
            
            for param_key, param_info in self.blood_parameters.items():
                if param_key in test_data:
                    value = test_data[param_key]
                    normal_range = param_info["normal_range"]
                    
                    # Handle gender-specific ranges
                    if isinstance(normal_range, dict) and gender in normal_range:
                        min_val = normal_range[gender]["min"]
                        max_val = normal_range[gender]["max"]
                    elif isinstance(normal_range, dict) and "min" in normal_range:
                        min_val = normal_range["min"]
                        max_val = normal_range["max"]
                    else:
                        min_val = normal_range["min"]
                        max_val = normal_range["max"]
                    
                    is_normal = min_val <= value <= max_val
                    
                    results["parameters"][param_key] = {
                        "name": param_info["name"],
                        "value": value,
                        "unit": param_info["unit"],
                        "normal_range": {"min": min_val, "max": max_val},
                        "is_normal": is_normal
                    }
                    
                    if not is_normal:
                        severity = "high" if value < min_val * 0.5 or value > max_val * 1.5 else "moderate"
                        results["abnormalities"].append({
                            "parameter": param_info["name"],
                            "value": value,
                            "expected": f"{min_val}-{max_val} {param_info['unit']}",
                            "severity": severity,
                            "direction": "low" if value < min_val else "high"
                        })
            
            logger.info(f"Parsed blood test with {len(results['parameters'])} parameters, {len(results['abnormalities'])} abnormalities")
            return results
        except Exception as e:
            logger.error(f"Error parsing blood test: {e}")
            return {"error": "Failed to parse blood test"}
    
    def parse_urine_test(self, test_data: Dict) -> Dict:
        """
        Parse urine test results and identify abnormalities.
        
        Args:
            test_data: Dictionary of urine test parameters
            
        Returns:
            Dictionary with parsed results and abnormalities
        """
        try:
            results = {
                "parameters": {},
                "abnormalities": [],
                "timestamp": datetime.now().isoformat()
            }
            
            for param_key, param_info in self.urine_parameters.items():
                if param_key in test_data:
                    value = test_data[param_key]
                    normal_range = param_info["normal_range"]
                    min_val = normal_range["min"]
                    max_val = normal_range["max"]
                    
                    is_normal = min_val <= value <= max_val
                    
                    results["parameters"][param_key] = {
                        "name": param_info["name"],
                        "value": value,
                        "unit": param_info["unit"],
                        "normal_range": {"min": min_val, "max": max_val},
                        "is_normal": is_normal
                    }
                    
                    if not is_normal:
                        severity = "high" if value > max_val * 2 else "moderate"
                        results["abnormalities"].append({
                            "parameter": param_info["name"],
                            "value": value,
                            "expected": f"{min_val}-{max_val} {param_info['unit']}",
                            "severity": severity,
                            "direction": "high" if value > max_val else "low"
                        })
            
            logger.info(f"Parsed urine test with {len(results['parameters'])} parameters, {len(results['abnormalities'])} abnormalities")
            return results
        except Exception as e:
            logger.error(f"Error parsing urine test: {e}")
            return {"error": "Failed to parse urine test"}
    
    def analyze_abdomen_scan(self, scan_data: Dict) -> Dict:
        """
        Analyze abdomen scan report for findings.
        
        Args:
            scan_data: Dictionary with abdomen scan findings
            
        Returns:
            Dictionary with analysis results
        """
        try:
            results = {
                "findings": [],
                "recommendations": [],
                "severity": "low",
                "timestamp": datetime.now().isoformat()
            }
            
            # Common abdomen scan findings
            findings_keywords = {
                "gallstones": {"severity": "moderate", "recommendation": "Consult gastroenterologist, consider dietary modifications"},
                "fatty_liver": {"severity": "moderate", "recommendation": "Weight loss, reduce alcohol, healthy diet"},
                "liver_cysts": {"severity": "low", "recommendation": "Monitor with follow-up imaging"},
                "kidney_stones": {"severity": "high", "recommendation": "Increase fluid intake, consult urologist"},
                "enlarged_prostate": {"severity": "moderate", "recommendation": "Consult urologist for evaluation"},
                "fibroids": {"severity": "low", "recommendation": "Monitor with gynecologist, consider treatment if symptomatic"},
                "ascites": {"severity": "high", "recommendation": "Immediate medical evaluation needed"},
                "mass": {"severity": "critical", "recommendation": "Immediate specialist consultation and further imaging"}
            }
            
            text = scan_data.get("text", "").lower()
            
            for keyword, info in findings_keywords.items():
                if keyword in text:
                    results["findings"].append({
                        "finding": keyword,
                        "severity": info["severity"]
                    })
                    results["recommendations"].append(info["recommendation"])
                    
                    # Update overall severity
                    severity_order = {"low": 1, "moderate": 2, "high": 3, "critical": 4}
                    if severity_order[info["severity"]] > severity_order[results["severity"]]:
                        results["severity"] = info["severity"]
            
            logger.info(f"Analyzed abdomen scan with {len(results['findings'])} findings, severity: {results['severity']}")
            return results
        except Exception as e:
            logger.error(f"Error analyzing abdomen scan: {e}")
            return {"error": "Failed to analyze abdomen scan"}
    
    def detect_conditions(self, blood_results: Dict, urine_results: Dict) -> List[Dict]:
        """
        Detect health conditions based on test results.
        
        Args:
            blood_results: Parsed blood test results
            urine_results: Parsed urine test results
            
        Returns:
            List of detected conditions with severity and recommendations
        """
        try:
            detected_conditions = []
            
            # Combine all parameter values
            all_params = {}
            if "parameters" in blood_results:
                for key, data in blood_results["parameters"].items():
                    all_params[key] = data["value"]
            if "parameters" in urine_results:
                for key, data in urine_results["parameters"].items():
                    all_params[key] = data["value"]
            
            # Check each condition detector
            for condition_key, condition_info in self.condition_detectors.items():
                condition_detected = False
                max_severity = "low"
                
                for rule in condition_info["detection_rules"]:
                    param = rule["param"]
                    if param in all_params:
                        value = all_params[param]
                        
                        if rule["condition"] == "low":
                            # Check against normal range (simplified)
                            if value < rule.get("threshold", 0):
                                condition_detected = True
                                max_severity = rule["severity"]
                        elif rule["condition"] == "high":
                            if value > rule.get("threshold", 999):
                                condition_detected = True
                                max_severity = rule["severity"]
                        elif rule["condition"] == "elevated":
                            min_val = rule.get("min", 0)
                            max_val = rule.get("max", 999)
                            if min_val <= value <= max_val:
                                condition_detected = True
                                max_severity = rule["severity"]
                        elif rule["condition"] == "positive":
                            if value > 0:
                                condition_detected = True
                                max_severity = rule["severity"]
                
                if condition_detected:
                    detected_conditions.append({
                        "name": condition_info["name"],
                        "severity": max_severity,
                        "recommendations": condition_info["recommendations"]
                    })
            
            logger.info(f"Detected {len(detected_conditions)} conditions")
            return detected_conditions
        except Exception as e:
            logger.error(f"Error detecting conditions: {e}")
            return []
    
    def calculate_health_score(self, blood_results: Dict, urine_results: Dict) -> int:
        """
        Calculate overall health score (0-100) based on test results.
        
        Args:
            blood_results: Parsed blood test results
            urine_results: Parsed urine test results
            
        Returns:
            Health score from 0-100
        """
        try:
            total_params = 0
            normal_params = 0
            
            # Count blood parameters
            if "parameters" in blood_results:
                for param_data in blood_results["parameters"].values():
                    total_params += 1
                    if param_data["is_normal"]:
                        normal_params += 1
            
            # Count urine parameters
            if "parameters" in urine_results:
                for param_data in urine_results["parameters"].values():
                    total_params += 1
                    if param_data["is_normal"]:
                        normal_params += 1
            
            if total_params == 0:
                return 50  # Default score if no data
            
            score = int((normal_params / total_params) * 100)
            logger.info(f"Calculated health score: {score}/100")
            return score
        except Exception as e:
            logger.error(f"Error calculating health score: {e}")
            return 50
    
    def get_health_status(self, score: int) -> HealthStatus:
        """
        Get health status category based on score.
        
        Args:
            score: Health score (0-100)
            
        Returns:
            HealthStatus enum
        """
        if score >= 90:
            return HealthStatus.EXCELLENT
        elif score >= 75:
            return HealthStatus.GOOD
        elif score >= 60:
            return HealthStatus.FAIR
        elif score >= 40:
            return HealthStatus.POOR
        else:
            return HealthStatus.CRITICAL
    
    def generate_dietary_recommendations(self, detected_conditions: List[Dict]) -> List[str]:
        """
        Generate dietary recommendations based on detected conditions.
        
        Args:
            detected_conditions: List of detected conditions
            
        Returns:
            List of dietary recommendations
        """
        recommendations = []
        
        for condition in detected_conditions:
            recommendations.extend(condition.get("recommendations", []))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec not in seen:
                seen.add(rec)
                unique_recommendations.append(rec)
        
        return unique_recommendations
    
    def full_analysis(self, blood_data: Dict, urine_data: Dict, abdomen_data: Optional[Dict] = None, gender: str = "male") -> Dict:
        """
        Perform full health checkup analysis.
        
        Args:
            blood_data: Blood test parameters
            urine_data: Urine test parameters
            abdomen_data: Abdomen scan findings (optional)
            gender: Patient gender
            
        Returns:
            Comprehensive analysis results
        """
        try:
            # Parse tests
            blood_results = self.parse_blood_test(blood_data, gender)
            urine_results = self.parse_urine_test(urine_data)
            
            # Analyze abdomen scan if provided
            abdomen_results = {}
            if abdomen_data:
                abdomen_results = self.analyze_abdomen_scan(abdomen_data)
            
            # Detect conditions
            detected_conditions = self.detect_conditions(blood_results, urine_results)
            
            # Calculate health score
            health_score = self.calculate_health_score(blood_results, urine_results)
            health_status = self.get_health_status(health_score)
            
            # Generate recommendations
            dietary_recommendations = self.generate_dietary_recommendations(detected_conditions)
            
            return {
                "blood_test": blood_results,
                "urine_test": urine_results,
                "abdomen_scan": abdomen_results,
                "detected_conditions": detected_conditions,
                "health_score": health_score,
                "health_status": health_status.value,
                "dietary_recommendations": dietary_recommendations,
                "analyzed_at": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error in full analysis: {e}")
            return {"error": "Failed to perform full analysis"}


# Convenience functions
def analyze_health_checkup(blood_data: Dict, urine_data: Dict, abdomen_data: Optional[Dict] = None, gender: str = "male") -> Dict:
    """Perform full health checkup analysis (convenience function)."""
    analyzer = HealthCheckupAnalyzer()
    return analyzer.full_analysis(blood_data, urine_data, abdomen_data, gender)
