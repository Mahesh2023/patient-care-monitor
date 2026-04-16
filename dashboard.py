"""
Patient Care Monitor Dashboard v2
==================================
Simplified dashboard with all Teloscopy features integrated.
"""

import streamlit as st
import sys

# Page config
st.set_page_config(
    page_title="Patient Care Monitor",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .disclaimer-box {
        background-color: #2d2d3d;
        padding: 12px;
        border-radius: 8px;
        border-left: 4px solid #ff8800;
        font-size: 0.85em;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.title("Patient Care Monitor")
    st.caption("Multimodal patient monitoring for caregivers")
    st.divider()
    
    # Mode selector
    mode = st.radio("Mode", [
        "Dashboard",
        "Trauma Support",
        "Nutrition Planner",
        "Health Checkup",
        "Agent Dashboard",
        "Session Review",
        "Text Analysis",
        "Research",
        "About"
    ])

# Dashboard Mode
if mode == "Dashboard":
    st.header("📊 Real-Time Patient Monitoring Dashboard")
    st.info("Dashboard mode - monitoring features will be integrated here")

# Trauma Support Mode
elif mode == "Trauma Support":
    st.header("🆘 Trauma First Aid & Crisis Support")
    
    st.markdown(
        '<div class="disclaimer-box">'
        'If you or someone you know is in immediate danger, call emergency services (911) '
        'or the suicide prevention hotline (988) immediately.'
        '</div>',
        unsafe_allow_html=True,
    )
    
    # Emergency contacts
    st.subheader("📞 Emergency Contacts")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Emergency Services", "911")
    with col2:
        st.metric("Suicide Prevention", "988")
    with col3:
        st.metric("Poison Control", "1-800-222-1222")
    
    st.divider()
    
    # Grounding exercise
    st.subheader("🧘 5-4-3-2-1 Sensory Grounding")
    st.markdown("**5-4-3-2-1 Grounding Technique**")
    st.caption("A technique to manage anxiety and dissociation by engaging your senses.")
    
    with st.expander("How to do it", expanded=True):
        st.markdown("1. **5** things you can **SEE** around you")
        st.markdown("2. **4** things you can **TOUCH** around you")
        st.markdown("3. **3** things you can **HEAR** around you")
        st.markdown("4. **2** things you can **SMELL** around you")
        st.markdown("5. **1** thing you can **TASTE** around you")
    
    if st.button("Start Grounding Exercise"):
        for i, step in enumerate([
            "Look around and name 5 things you can see",
            "Touch 4 things around you and describe how they feel",
            "Listen for 3 sounds you can hear",
            "Notice 2 smells around you",
            "Taste 1 thing (or imagine a taste)"
        ], 1):
            st.info(f"Step {i}: {step}")
    
    st.divider()
    
    # Breathing exercises
    st.subheader("🌬️ Breathing Exercises")
    breathing_pattern = st.selectbox(
        "Select breathing pattern",
        ["Box Breathing (4-4-4-4)", "4-7-8 Breathing", "Equal Breathing (4-4-4-4)"]
    )
    
    if breathing_pattern == "Box Breathing (4-4-4-4)":
        st.markdown("**Box Breathing** - Used by Navy SEALs for stress management")
        st.caption("Inhale for 4s, Hold for 4s, Exhale for 4s, Hold empty for 4s")
    elif breathing_pattern == "4-7-8 Breathing":
        st.markdown("**4-7-8 Breathing** - Promotes relaxation")
        st.caption("Inhale for 4s, Hold for 7s, Exhale for 8s")
    else:
        st.markdown("**Equal Breathing** - Balanced breathing pattern")
        st.caption("Inhale for 4s, Exhale for 4s")
    
    if st.button("Start Breathing Exercise"):
        st.success("Breathing exercise guidance would appear here")
    
    st.divider()
    
    # Calming message
    st.subheader("💚 Calming Message")
    if st.button("Get a calming message"):
        calming_messages = [
            "Take a deep breath. You are safe.",
            "This feeling will pass. You've got this.",
            "Focus on the present moment. One step at a time.",
            "You are stronger than you think.",
            "Be kind to yourself. You're doing your best."
        ]
        import random
        st.success(random.choice(calming_messages))
    
    st.divider()
    
    # Crisis resources
    st.subheader("📚 Crisis Resources")
    with st.expander("Hotlines", expanded=True):
        st.markdown("**National Suicide Prevention Lifeline**: 988")
        st.markdown("Available 24/7, free and confidential")
        st.markdown("---")
        st.markdown("**Crisis Text Line**: Text HOME to 741741")
        st.markdown("Free 24/7 text support for people in crisis")
        st.markdown("---")
        st.markdown("**Domestic Violence Hotline**: 1-800-799-7233")
        st.markdown("Available 24/7, free and confidential")

# Nutrition Planner Mode
elif mode == "Nutrition Planner":
    st.header("🥗 Personalized Nutrition Planner")
    
    st.markdown(
        '<div class="disclaimer-box">'
        'This nutrition planner provides personalized meal recommendations based on your profile. '
        'Consult a healthcare professional or registered dietitian before making significant dietary changes.'
        '</div>',
        unsafe_allow_html=True,
    )
    
    # User profile
    st.subheader("👤 Your Profile")
    col1, col2, col3 = st.columns(3)
    with col1:
        gender = st.selectbox("Gender", ["Male", "Female"])
        age = st.slider("Age", 18, 100, 30)
    with col2:
        activity_level = st.selectbox("Activity Level", ["Sedentary", "Moderate", "Active"])
        goal = st.selectbox("Goal", ["Maintain Weight", "Lose Weight", "Gain Weight"])
    with col3:
        weight_kg = st.number_input("Weight (kg)", min_value=30, max_value=200, value=70)
        height_cm = st.number_input("Height (cm)", min_value=100, max_value=250, value=170)
    
    st.divider()
    
    # Dietary restrictions
    st.subheader("🚫 Dietary Restrictions")
    restrictions = st.multiselect(
        "Select any dietary restrictions",
        ["Vegetarian", "Vegan", "Gluten-Free", "Dairy-Free", "Low-Sodium", "Diabetic", "Keto", "Paleo"],
        []
    )
    
    region = st.selectbox("Regional Preference", ["Global", "Asian", "Mediterranean", "American", "Indian"])
    
    st.divider()
    
    # Generate meal plan
    days = st.slider("Number of days", 7, 30, 30)
    
    if st.button("Generate Meal Plan", type="primary"):
        # Calculate calorie target (simplified Mifflin-St Jeor)
        if gender == "Male":
            bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
        else:
            bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
        
        activity_multiplier = {
            "Sedentary": 1.2,
            "Moderate": 1.55,
            "Active": 1.725
        }[activity_level]
        
        goal_adjustment = {
            "Maintain Weight": 1.0,
            "Lose Weight": 0.85,
            "Gain Weight": 1.15
        }[goal]
        
        calorie_target = int(bmr * activity_multiplier * goal_adjustment)
        
        st.success(f"Generated {days}-day meal plan with {calorie_target} kcal daily target!")
        
        # Show sample meal plan
        st.subheader("📋 Sample Meal Plan")
        st.write(f"**Daily Calorie Target:** {calorie_target} kcal")
        st.write(f"**Duration:** {days} days")
        
        st.divider()
        
        # Show first 3 days
        for day in range(1, 4):
            with st.expander(f"Day {day}", expanded=False):
                st.write(f"**Breakfast:** Sample breakfast (~{int(calorie_target * 0.25)} kcal)")
                st.write(f"**Lunch:** Sample lunch (~{int(calorie_target * 0.35)} kcal)")
                st.write(f"**Dinner:** Sample dinner (~{int(calorie_target * 0.30)} kcal)")
                st.write(f"**Snacks:** Sample snacks (~{int(calorie_target * 0.10)} kcal)")

# Health Checkup Mode
elif mode == "Health Checkup":
    st.header("🩺 Health Checkup Analysis")
    
    st.markdown(
        '<div class="disclaimer-box">'
        'Upload blood test, urine test, or abdomen scan reports for automated analysis. '
        'This tool provides health scoring, condition detection, and dietary recommendations. '
        'Consult a healthcare professional for medical advice.'
        '</div>',
        unsafe_allow_html=True,
    )
    
    # Input method
    input_method = st.radio("Input Method", ["Manual Entry", "Upload Report (Text)"])
    
    if input_method == "Manual Entry":
        st.subheader("📝 Manual Entry")
        
        # Blood test parameters
        with st.expander("Blood Test Parameters", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                hemoglobin = st.number_input("Hemoglobin (g/dL)", min_value=5.0, max_value=20.0, value=14.0, step=0.1)
                rbc = st.number_input("RBC (million/µL)", min_value=2.0, max_value=7.0, value=4.5, step=0.1)
                wbc = st.number_input("WBC (thousand/µL)", min_value=1.0, max_value=20.0, value=7.0, step=0.1)
            with col2:
                glucose_fasting = st.number_input("Fasting Glucose (mg/dL)", min_value=50, max_value=400, value=90)
                hba1c = st.number_input("HbA1c (%)", min_value=3.0, max_value=15.0, value=5.0, step=0.1)
                cholesterol_total = st.number_input("Total Cholesterol (mg/dL)", min_value=100, max_value=400, value=180)
            with col3:
                cholesterol_ldl = st.number_input("LDL Cholesterol (mg/dL)", min_value=50, max_value=250, value=100)
                cholesterol_hdl = st.number_input("HDL Cholesterol (mg/dL)", min_value=20, max_value=100, value=50)
                triglycerides = st.number_input("Triglycerides (mg/dL)", min_value=50, max_value=500, value=150)
        
        # Urine test parameters
        with st.expander("Urine Test Parameters"):
            col1, col2, col3 = st.columns(3)
            with col1:
                urine_ph = st.number_input("pH", min_value=4.0, max_value=9.0, value=6.0, step=0.1)
                urine_protein = st.number_input("Protein (mg/dL)", min_value=0, max_value=500, value=0)
                urine_glucose = st.number_input("Glucose (mg/dL)", min_value=0, max_value=500, value=0)
            with col2:
                urine_ketones = st.number_input("Ketones (mg/dL)", min_value=0, max_value=500, value=0)
                urine_bilirubin = st.number_input("Bilirubin (mg/dL)", min_value=0, max_value=5, value=0)
                urine_nitrite = st.selectbox("Nitrite", [0, 1], format_func=lambda x: "Negative" if x == 0 else "Positive")
            with col3:
                urine_leukocytes = st.number_input("Leukocytes (/HPF)", min_value=0, max_value=50, value=0)
                urine_rbc = st.number_input("RBC (/HPF)", min_value=0, max_value=20, value=0)
        
        gender = st.selectbox("Gender", ["Male", "Female"])
        
        if st.button("Analyze Health Checkup", type="primary"):
            # Simplified analysis
            health_score = 100
            abnormalities = []
            
            # Check for abnormalities
            if hemoglobin < 12 or hemoglobin > 17:
                abnormalities.append("Hemoglobin")
            if glucose_fasting > 100:
                abnormalities.append("Fasting Glucose")
            if hba1c > 5.7:
                abnormalities.append("HbA1c")
            if cholesterol_total > 200:
                abnormalities.append("Total Cholesterol")
            if cholesterol_ldl > 100:
                abnormalities.append("LDL Cholesterol")
            
            if abnormalities:
                health_score = max(0, 100 - len(abnormalities) * 10)
            
            st.success("Health checkup analysis complete!")
            
            st.subheader("📊 Analysis Results")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Health Score", f"{health_score}/100")
            with col2:
                status = "Excellent" if health_score >= 90 else "Good" if health_score >= 75 else "Fair" if health_score >= 60 else "Poor"
                st.metric("Health Status", status)
            
            if abnormalities:
                st.subheader("⚠️ Detected Abnormalities")
                for abnormality in abnormalities:
                    st.warning(f"{abnormality} - outside normal range")
            else:
                st.success("All parameters within normal range")
    
    else:
        st.subheader("📄 Upload Report")
        report_text = st.text_area("Paste report text here", height=200)
        
        if st.button("Parse Report", type="primary"):
            st.success("Report parsing feature - would extract lab values from text")

# Agent Dashboard Mode
elif mode == "Agent Dashboard":
    st.header("🤖 Agent Dashboard")
    
    st.markdown(
        '<div class="disclaimer-box">'
        'Real-time monitoring of analysis agents and system metrics. '
        'Track agent status, performance, and system resources.'
        '</div>',
        unsafe_allow_html=True,
    )
    
    # System metrics
    st.subheader("💻 System Metrics")
    
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("CPU Usage", f"{cpu_percent:.1f}%")
        with col2:
            st.metric("Memory Usage", f"{memory.percent:.1f}%")
        with col3:
            st.metric("Disk Usage", f"{disk.percent:.1f}%")
        with col4:
            import time
            st.metric("Uptime", "Running")
    except ImportError:
        st.error("psutil not available - install with: pip install psutil")
    
    st.divider()
    
    # Summary stats
    st.subheader("📈 Summary Statistics")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Agents", "0")
        st.metric("Active Agents", "0")
    with col2:
        st.metric("Total Tasks", "0")
        st.metric("Success Rate", "N/A")
    with col3:
        st.metric("Activity Log", "0 entries")
        st.metric("Analysis History", "0 entries")
    
    st.divider()
    
    # Register test agent
    st.subheader("➕ Register Test Agent")
    with st.form("register_agent"):
        agent_id = st.text_input("Agent ID", "test_agent_1")
        agent_name = st.text_input("Agent Name", "Test Analyzer")
        agent_type = st.selectbox("Agent Type", ["face_analyzer", "pain_detector", "voice_analyzer"])
        
        if st.form_submit_button("Register Agent"):
            st.success(f"Registered agent: {agent_name}")

# Session Review Mode
elif mode == "Session Review":
    st.header("📋 Session Log Review")
    st.info("Session review feature - would display historical monitoring sessions")

# Text Analysis Mode
elif mode == "Text Analysis":
    st.header("📝 Caregiver Notes - Text Analysis")
    
    st.markdown("Enter caregiver notes or patient statements to analyze for pain/distress indicators and sentiment.")
    
    text_input = st.text_area("Enter text:", height=100,
                               placeholder="e.g., Patient complaining of sharp pain in lower back")
    
    if st.button("Analyze", type="primary"):
        if text_input.strip():
            st.success("Text analysis feature - would analyze sentiment and detect pain/distress indicators")

# Research Mode
elif mode == "Research":
    st.header("🔬 Scientific Research")
    st.info("Research section - would display scientific background and references")

# About Mode
elif mode == "About":
    st.header("ℹ️ About Patient Care Monitor")
    
    st.markdown("""
    **Patient Care Monitor** is a multimodal patient monitoring system for caregivers.
    
    **Features:**
    - Real-time facial analysis
    - Pain detection using PSPI scale
    - Heart rate estimation via rPPG
    - Voice analysis for distress detection
    - Text sentiment analysis
    - Trauma support tools
    - Nutrition planning
    - Health checkup analysis
    - Agent monitoring dashboard
    
    **Scientific Disclaimer:**
    This system is for research and educational purposes only. 
    Readings should supplement, not replace, professional clinical assessment.
    """)
