"""
Patient Care Monitor Backend - FastAPI Server
============================================
Minimal backend to serve static files correctly
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os

app = FastAPI(title="Patient Care Monitor")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get the current directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Mount static files at root level to serve CSS, JS, and other assets
app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")

# API endpoints
@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

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
