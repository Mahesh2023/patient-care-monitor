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
import os

app = FastAPI(
    title="Patient Care Monitor API",
    description="Healthcare platform",
    version="3.0"
)

print("=" * 50)
print("Patient Care Monitor API Starting...")
print("=" * 50)

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

print(f"BASE_DIR: {BASE_DIR}")
print(f"Current working directory: {os.getcwd()}")
print(f"Files in BASE_DIR: {os.listdir(BASE_DIR) if os.path.exists(BASE_DIR) else 'DIR NOT FOUND'}")

# Check if static files exist
css_path = os.path.join(BASE_DIR, "styles.css")
js_path = os.path.join(BASE_DIR, "app.js")
html_path = os.path.join(BASE_DIR, "index.html")

print(f"CSS exists: {os.path.exists(css_path)} at {css_path}")
print(f"JS exists: {os.path.exists(js_path)} at {js_path}")
print(f"HTML exists: {os.path.exists(html_path)} at {html_path}")

# Mount static files for CSS and JS at root level
app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")

# ==================== API ENDPOINTS ====================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main HTML page"""
    try:
        html_path = os.path.join(BASE_DIR, "index.html")
        with open(html_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Index.html not found</h1>"

@app.get("/styles.css")
async def get_styles():
    """Serve styles.css"""
    try:
        css_path = os.path.join(BASE_DIR, "styles.css")
        print(f"Serving CSS from: {css_path}, exists: {os.path.exists(css_path)}")
        return FileResponse(css_path, media_type="text/css")
    except FileNotFoundError:
        print(f"CSS not found at {css_path}")
        raise HTTPException(status_code=404, detail=f"styles.css not found at {css_path}")

@app.get("/app.js")
async def get_app_js():
    """Serve app.js"""
    try:
        js_path = os.path.join(BASE_DIR, "app.js")
        print(f"Serving JS from: {js_path}, exists: {os.path.exists(js_path)}")
        return FileResponse(js_path, media_type="application/javascript")
    except FileNotFoundError:
        print(f"JS not found at {js_path}")
        raise HTTPException(status_code=404, detail=f"app.js not found at {js_path}")

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
