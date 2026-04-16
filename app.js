// Navigation functionality
document.addEventListener('DOMContentLoaded', function() {
    // Mobile menu toggle
    const navToggle = document.querySelector('.nav-toggle');
    const navMenu = document.querySelector('.nav-menu');
    
    navToggle.addEventListener('click', function() {
        navMenu.classList.toggle('active');
    });
    
    // Smooth scrolling for navigation links
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');
            showSection(targetId.substring(1));
        });
    });
    
    // File upload functionality
    const uploadZone = document.getElementById('uploadZone');
    const fileInput = document.getElementById('fileInput');
    
    if (uploadZone && fileInput) {
        uploadZone.addEventListener('click', () => fileInput.click());
        
        uploadZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadZone.style.borderColor = '#1f77b4';
        });
        
        uploadZone.addEventListener('dragleave', () => {
            uploadZone.style.borderColor = '#e0e0e0';
        });
        
        uploadZone.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadZone.style.borderColor = '#e0e0e0';
            handleFiles(e.dataTransfer.files);
        });
        
        fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files);
        });
    }
});

// Show specific section
function showSection(sectionId) {
    // Hide all sections
    document.querySelectorAll('.section').forEach(section => {
        section.classList.add('hidden');
    });
    
    // Show target section
    const targetSection = document.getElementById(sectionId);
    if (targetSection) {
        targetSection.classList.remove('hidden');
    }
    
    // Update active nav link
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === `#${sectionId}`) {
            link.classList.add('active');
        }
    });
    
    // Scroll to section
    if (sectionId !== 'home') {
        targetSection.scrollIntoView({ behavior: 'smooth' });
    }
}

// Handle file uploads
function handleFiles(files) {
    if (files.length > 0) {
        console.log('Files selected:', files);
        // Add file handling logic here
    }
}

// Run analysis
function runAnalysis() {
    const uploadZone = document.getElementById('uploadZone');
    uploadZone.innerHTML = `
        <div class="upload-icon">⏳</div>
        <h3>Analyzing...</h3>
        <p>Please wait while we process your data</p>
    `;
    
    setTimeout(() => {
        uploadZone.innerHTML = `
            <div class="upload-icon">✅</div>
            <h3>Analysis Complete!</h3>
            <p>Your results are ready</p>
            <button class="btn btn-primary" onclick="showSection('results')">View Results</button>
        `;
    }, 2000);
}

// Generate meal plan
async function generateMealPlan() {
    const gender = document.querySelector('select').value;
    const age = document.querySelectorAll('input[type="number"]')[0].value;
    const weight = document.querySelectorAll('input[type="number"]')[1].value;
    const height = document.querySelectorAll('input[type="number"]')[2].value;
    const activity = document.querySelectorAll('select')[1].value;
    const goal = document.querySelectorAll('select')[2].value;
    const region = document.querySelectorAll('select')[3].value;
    
    const restrictions = [];
    document.querySelectorAll('.tag input:checked').forEach(cb => {
        restrictions.push(cb.parentElement.textContent.trim());
    });
    
    try {
        const response = await fetch('/api/meal-plan', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                age: parseInt(age),
                gender: gender,
                weight: parseFloat(weight),
                height: parseFloat(height),
                activity_level: activity,
                goal: goal,
                dietary_restrictions: restrictions.join(','),
                region: region,
                days: 30
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const resultPanel = document.getElementById('mealPlanResult');
            resultPanel.classList.remove('hidden');
            
            // Update summary
            const summaryCards = resultPanel.querySelectorAll('.summary-value');
            summaryCards[0].textContent = data.meal_plan.calorie_target;
            summaryCards[1].textContent = data.meal_plan.days;
            
            resultPanel.style.opacity = '0';
            resultPanel.style.transform = 'translateY(20px)';
            
            setTimeout(() => {
                resultPanel.style.transition = 'all 0.5s ease';
                resultPanel.style.opacity = '1';
                resultPanel.style.transform = 'translateY(0)';
            }, 100);
        }
    } catch (error) {
        console.error('Error generating meal plan:', error);
        alert('Error generating meal plan. Please try again.');
    }
}

// Switch tabs
function switchTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active class from all buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show target tab
    document.getElementById(`${tabName}Tab`).classList.add('active');
    
    // Add active class to clicked button
    event.target.classList.add('active');
}

// Analyze health checkup
async function analyzeHealth() {
    const inputs = document.querySelectorAll('.lab-field input');
    const bloodParams = {};
    const bloodKeys = ['hemoglobin', 'rbc', 'wbc', 'glucose', 'hba1c', 'cholesterol', 'ldl', 'hdl', 'triglycerides'];
    
    inputs.forEach((input, index) => {
        if (index < bloodKeys.length) {
            bloodParams[bloodKeys[index]] = parseFloat(input.value);
        }
    });
    
    const gender = document.querySelector('#manualTab select')?.value || 'Male';
    
    try {
        const response = await fetch('/api/health-checkup', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                blood_params: JSON.stringify(bloodParams),
                urine_params: '{}',
                gender: gender
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const resultPanel = document.getElementById('healthResult');
            resultPanel.classList.remove('hidden');
            
            // Update health score
            const scoreValue = document.querySelector('.score-value');
            const scoreStatus = document.querySelector('.score-status');
            
            let currentScore = 0;
            const targetScore = data.result.health_score;
            
            const interval = setInterval(() => {
                if (currentScore >= targetScore) {
                    clearInterval(interval);
                } else {
                    currentScore++;
                    scoreValue.textContent = currentScore;
                }
            }, 20);
            
            scoreStatus.textContent = data.result.health_status;
        }
    } catch (error) {
        console.error('Error analyzing health:', error);
        alert('Error analyzing health checkup. Please try again.');
    }
}

// Start grounding exercise
function startGrounding() {
    const steps = [
        "Look around and name 5 things you can see",
        "Touch 4 different objects and describe how they feel",
        "Listen carefully and identify 3 sounds",
        "Notice 2 different smells around you",
        "Focus on 1 taste (or imagine a pleasant taste)"
    ];
    
    let currentStep = 0;
    
    const showStep = () => {
        if (currentStep < steps.length) {
            alert(`Step ${currentStep + 1}: ${steps[currentStep]}`);
            currentStep++;
            setTimeout(showStep, 3000);
        }
    };
    
    showStep();
}

// Start breathing exercise
function startBreathing() {
    alert("Starting breathing exercise...\n\nFollow the pattern: Inhale → Hold → Exhale → Hold\n\nThis will guide you through the breathing technique.");
}

// Initialize dashboard metrics
function updateMetrics() {
    // Simulate real-time metric updates
    const metrics = document.querySelectorAll('.metric-val');
    metrics.forEach(metric => {
        const value = metric.textContent;
        if (value.includes('%')) {
            const numValue = parseInt(value);
            const newValue = numValue + Math.floor(Math.random() * 5) - 2;
            metric.textContent = `${Math.max(0, Math.min(100, newValue))}%`;
        }
    });
}

// Update metrics every 5 seconds
setInterval(updateMetrics, 5000);

// Add smooth scroll behavior
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth'
            });
        }
    });
});

// Console log for debugging
console.log('Patient Care Monitor v3.0 - Modern Healthcare Platform');
console.log('No Streamlit or Gradio - Pure HTML/CSS/JavaScript');
