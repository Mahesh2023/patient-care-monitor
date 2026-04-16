"""
Patient Care Monitor Backend - FastAPI Server
============================================
Simplified backend to ensure basic functionality works
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from datetime import datetime
import json
import os

app = FastAPI(
    title="Patient Care Monitor API",
    description="Healthcare platform",
    version="3.0"
)

print("=" * 50)
print("Patient Care Monitor API Starting...")
print("=" * 50)

app = FastAPI(
    title="Patient Care Monitor API",
    description="Healthcare platform with telomere analysis, disease risk prediction, and nutrition planning",
    version="3.0"
)

print("=" * 50)
print("Patient Care Monitor API Starting...")
print("=" * 50)
print(f"Patient Monitoring Available: {PATIENT_MONITORING_AVAILABLE}")
print(f"Teloscopy Nutrition Available: {REAL_NUTRITION_AVAILABLE if 'REAL_NUTRITION_AVAILABLE' in locals() else False}")
print(f"Teloscopy Agents Available: {REAL_AGENTS_AVAILABLE if 'REAL_AGENTS_AVAILABLE' in locals() else False}")
print("=" * 50)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for CSS and JS
app.mount("/static", StaticFiles(directory="."), name="static")

# ==================== API ENDPOINTS ====================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main HTML page"""
    try:
        with open("index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Index.html not found</h1>"

@app.get("/index.html", response_class=HTMLResponse)
async def get_index():
    """Serve index.html"""
    try:
        with open("index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Index.html not found</h1>"

@app.get("/styles.css")
async def get_styles():
    """Serve styles.css"""
    try:
        return FileResponse("styles.css", media_type="text/css")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="styles.css not found")

@app.get("/app.js")
async def get_app_js():
    """Serve app.js"""
    try:
        return FileResponse("app.js", media_type="application/javascript")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="app.js not found")

@app.post("/api/analyze")
async def analyze_data(
    age: int,
    gender: str,
    weight: float,
    height: float,
    activity_level: str,
    goal: str,
    dietary_restrictions: str,
    region: str
):
    """Analyze user data and generate recommendations (simplified)"""
    try:
        return {
            "success": True,
            "message": "Analysis endpoint working",
            "age": age,
            "gender": gender,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/meal-plan")
async def generate_meal_plan(
    age: int,
    gender: str,
    weight: float,
    height: float,
    activity_level: str,
    goal: str,
    dietary_restrictions: str,
    region: str,
    days: int = 30
):
    """Generate personalized meal plan (simplified)"""
    try:
        return {
            "success": True,
            "calorie_target": 2000,
            "days": days,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/health-checkup")
async def analyze_health_checkup(
    blood_params: str,
    urine_params: str,
    gender: str
):
    """Analyze health checkup data (simplified)"""
    try:
        return {
            "success": True,
            "health_score": 85,
            "health_status": "Good",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/parse-report")
async def parse_report(text: str):
    """Parse lab report text (simplified)"""
    try:
        return {
            "success": True,
            "parsed_parameters": {},
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/agents/status")
async def get_agent_status():
    """Get status of all agents (simplified)"""
    return {
        "success": True,
        "agents": {
            "image_agent": {"status": "idle"},
            "genomics_agent": {"status": "idle"},
            "nutrition_agent": {"status": "idle"}
        },
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
        profile = UserProfile(
            age=age,
            gender=gender,
            weight=weight,
            height=height,
            activity_level=activity_level,
            goal=goal,
            dietary_restrictions=dietary_restrictions.split(",") if dietary_restrictions else [],
            region=region
        )
        
        # Generate disease risk predictions
        risks = DiseaseRiskPredictor.predict_from_telomere(
            mean_length_bp=7500,
            age=age,
            gender=gender
        )
        
        # Generate meal plan
        meal_plan = NutritionAdvisor.generate_meal_plan(profile, days=30)
        
        return {
            "success": True,
            "disease_risks": risks,
            "meal_plan": meal_plan,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/health-checkup")
async def analyze_health_checkup(
    blood_params: str,
    urine_params: str,
    gender: str
):
    """Analyze health checkup data"""
    try:
        blood_data = json.loads(blood_params)
        urine_data = json.loads(urine_params) if urine_params else {}
        
        result = HealthCheckupAnalyzer.analyze(blood_data, urine_data, gender)
        
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/meal-plan")
async def generate_meal_plan(
    age: int,
    gender: str,
    weight: float,
    height: float,
    activity_level: str,
    goal: str,
    dietary_restrictions: str,
    region: str,
    days: int = 30
):
    """Generate personalized meal plan"""
    try:
        profile = UserProfile(
            age=age,
            gender=gender,
            weight=weight,
            height=height,
            activity_level=activity_level,
            goal=goal,
            dietary_restrictions=dietary_restrictions.split(",") if dietary_restrictions else [],
            region=region
        )
        
        meal_plan = NutritionAdvisor.generate_meal_plan(profile, days)
        
        return {
            "success": True,
            "meal_plan": meal_plan
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/parse-report")
async def parse_report(text: str):
    """Parse lab report text"""
    try:
        result = ReportParser.parse_text(text)
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/agents/status")
async def get_agent_status():
    """Get status of all agents"""
    return {
        "success": True,
        "agents": AgentOrchestrator.get_agent_status()
    }

@app.post("/api/agents/process")
async def process_with_agent(analysis_type: str, data: str):
    """Process analysis through multi-agent system"""
    try:
        data_dict = json.loads(data)
        result = AgentOrchestrator.process_analysis(analysis_type, data_dict)
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.0",
        "patient_monitoring_available": PATIENT_MONITORING_AVAILABLE,
        "teloscopy_features": {
            "blood_ranges": bool(BLOOD_RANGES),
            "condition_rules": bool(CONDITION_RULES),
            "condition_advice": bool(CONDITION_ADVICE),
            "variant_db": bool(VARIANT_DB),
            "ayurvedic_remedies": bool(AYURVEDIC_REMEDIES),
            "country_profiles": bool(COUNTRY_PROFILES)
        }
    }

# ==================== PATIENT CARE MONITORING ENDPOINTS ====================

@app.post("/api/patient/analyze-frame")
async def analyze_patient_frame(file: UploadFile = File(...)):
    """Analyze a video frame for patient monitoring (face, pain, heart rate)"""
    if not PATIENT_MONITORING_AVAILABLE:
        raise HTTPException(status_code=503, detail="Patient monitoring modules not available")
    
    try:
        # Read image file
        import cv2
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid image file")
        
        # Initialize modules
        face_analyzer = FaceAnalyzer()
        pain_detector = PainDetector()
        rppg_estimator = RPPGEstimator()
        
        # Analyze face
        face_result = face_analyzer.analyze(frame, time.time())
        
        # Detect pain
        pain_assessment = pain_detector.assess(
            face_result.aus if face_result.face_detected else None,
            time.time()
        )
        
        # Estimate heart rate
        heart_rate_result = rppg_estimator.process_frame(frame, face_result.forehead_roi, time.time())
        
        return {
            "success": True,
            "face_detected": face_result.face_detected,
            "pain_assessment": {
                "pspi_score": pain_assessment.pspi_score,
                "pain_level": pain_assessment.pain_level.value,
                "confidence": pain_assessment.confidence
            },
            "heart_rate": {
                "bpm": heart_rate_result.bpm if heart_rate_result else None,
                "confidence": heart_rate_result.confidence if heart_rate_result else None
            },
            "action_units": face_result.aus.to_dict() if face_result.aus else {},
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/patient/analyze-voice")
async def analyze_patient_voice(file: UploadFile = File(...)):
    """Analyze voice for patient distress detection"""
    if not PATIENT_MONITORING_AVAILABLE:
        raise HTTPException(status_code=503, detail="Patient monitoring modules not available")
    
    try:
        # Read audio file
        contents = await file.read()
        
        # Initialize voice analyzer
        voice_analyzer = VoiceAnalyzer(sample_rate=16000)
        
        # Analyze voice (simplified - would need proper audio processing)
        voice_result = voice_analyzer.analyze_audio(
            np.frombuffer(contents, dtype=np.float32),
            time.time()
        )
        
        return {
            "success": True,
            "vocal_state": voice_result.vocal_state.value,
            "arousal": voice_result.arousal,
            "valence": voice_result.valence,
            "confidence": voice_result.confidence,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/patient/analyze-text")
async def analyze_patient_text(text: str):
    """Analyze text for patient sentiment and distress indicators"""
    if not PATIENT_MONITORING_AVAILABLE:
        raise HTTPException(status_code=503, detail="Patient monitoring modules not available")
    
    try:
        # Initialize text analyzer
        text_analyzer = TextSentimentAnalyzer()
        
        # Analyze text
        sentiment_result = text_analyzer.analyze(text, time.time())
        
        return {
            "success": True,
            "sentiment": sentiment_result.sentiment,
            "pain_indicators": sentiment_result.pain_indicators,
            "distress_indicators": sentiment_result.distress_indicators,
            "comfort_indicators": sentiment_result.comfort_indicators,
            "confidence": sentiment_result.confidence,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/patient/fusion-analysis")
async def fusion_analysis(
    face_data: Optional[Dict] = None,
    pain_data: Optional[Dict] = None,
    voice_data: Optional[Dict] = None,
    heart_rate_data: Optional[Dict] = None,
    text_data: Optional[Dict] = None
):
    """Perform multimodal fusion analysis for comprehensive patient state"""
    if not PATIENT_MONITORING_AVAILABLE:
        raise HTTPException(status_code=503, detail="Patient monitoring modules not available")
    
    try:
        # Initialize fusion engine
        fusion_engine = FusionEngine()
        
        # Create patient state from provided data
        patient_state = fusion_engine.fuse(
            face_result=face_data,
            pain_assessment=pain_data,
            voice_result=voice_data,
            heart_rate=heart_rate_data,
            text_sentiment=text_data,
            timestamp=time.time()
        )
        
        return {
            "success": True,
            "patient_state": patient_state.to_dict(),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
