# Multi-User Authentication & Security Implementation Plan
## Patient Care Monitor System

**Document Version:** 1.0  
**Date:** April 15, 2026  
**Status:** Comprehensive Research & Planning Phase Complete

---

## Executive Summary

This document provides a comprehensive implementation plan for adding multi-user authentication and security to the Patient Care Monitor system. The plan is based on extensive research into OWASP security standards, HIPAA compliance requirements, Python authentication best practices, and healthcare data security regulations.

### Key Recommendations
- **Authentication Method**: JWT tokens with database-backed session management
- **Password Hashing**: bcrypt with cost factor 12-14 (OWASP compliant)
- **Database**: PostgreSQL for production (SQLite for development)
- **Authorization**: Role-Based Access Control (RBAC) with 3-tier permissions
- **Session Management**: Hybrid approach (JWT for API, database sessions for dashboard)
- **HIPAA Compliance**: Full compliance with technical safeguards
- **Encryption**: TLS 1.3 for transit, AES-256 for data at rest

---

## 1. Research Findings

### 1.1 Authentication Best Practices (Python)

**Source:** WorkOS Python Authentication Guide 2026, FastAPI Security Documentation

**Key Findings:**
- Modern password hashing algorithms (bcrypt, Argon2, PBKDF2) are deliberately slow (100-300ms per hash) to prevent brute-force attacks
- Automatic salting is handled by modern libraries - no manual implementation needed
- Never use MD5, SHA1, or plain SHA256 for passwords (MD5 can test 180 billion combinations/second on GPUs)
- Rate limiting is essential: 5 login attempts per hour per email/IP
- Constant-time password comparison prevents timing attacks

**Recommended Libraries:**
```python
# Password hashing
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

# JWT handling
from jose import JWTError, jwt
from datetime import datetime, timedelta
```

### 1.2 OWASP Password Storage Standards

**Source:** OWASP Password Storage Cheat Sheet Series

**Key Findings:**
- **Argon2id** is the winner of the password hashing competition - first choice for new applications
- **bcrypt** is widely supported and battle-tested - excellent alternative
- **PBKDF2** when FIPS certification or enterprise support is required
- **scrypt** where resisting hardware-accelerated attacks is necessary
- Password hashing should be configurable with work factors
- Salts are mandatory and handled automatically by modern libraries
- Work factors should be tuned to limit attackers to <10 kH/s/GPU

**Recommended Configuration:**
```python
# bcrypt with cost factor 12 (default, ~0.3 seconds per hash)
# Increase to 13-14 for higher security environments
bcrypt__rounds=12
```

### 1.3 Session Management Strategies

**Source:** WorkOS Python Authentication Guide 2026

**Three Main Strategies:**

| Strategy | Pros | Cons | Best For |
|----------|------|------|----------|
| **JWT (Stateless)** | Fast, no database query, scalable | Cannot be immediately revoked, larger tokens | Startup MVPs, APIs |
| **Database Sessions** | Complete control, immediate revocation, auditability | Database query per request | Enterprise applications |
| **Redis Sessions** | Fast like JWT, revocation like databases | Additional infrastructure | Growing applications |

**Recommendation for Patient Care Monitor:**
- **Hybrid Approach**: JWT tokens for API authentication + database sessions for Streamlit dashboard
- This provides the best balance of performance, security, and control
- JWT tokens stored in database for revocation capability
- Session tokens for dashboard with automatic logout

### 1.4 Database Options for User Storage

**Source:** FreeCodeCamp Python SQL Guide, SQLite vs PostgreSQL Security Comparison

**Comparison:**

| Feature | SQLite | PostgreSQL |
|---------|--------|------------|
| Multi-user concurrency | Limited | Excellent |
| Security features | File-system based | Row-level security, encryption |
| Scalability | Limited | Highly scalable |
| HIPAA compliance | Challenging | Native support |
| Production readiness | Development only | Production-grade |
| Backup/restore | File copy | Advanced tools |

**Recommendation:**
- **Development**: SQLite (already used, easy setup)
- **Production**: PostgreSQL with SSL/TLS encryption
- **Migration path**: SQLAlchemy ORM allows easy database switching

### 1.5 Role-Based Access Control (RBAC)

**Source:** Oso RBAC Guide, Python RBAC Implementation

**Key Concepts:**
- **Role**: Groups permissions (e.g., "Admin", "Caregiver", "Viewer")
- **Permission**: Action on a resource (e.g., "view_patient_data", "manage_users")
- **Resource**: Protected entity (e.g., patient records, system settings)

**Recommended RBAC Structure for Patient Care Monitor:**

```
Roles:
├── Administrator (Full access)
│   ├── Manage users
│   ├── Configure system
│   ├── View all patient data
│   └── Access audit logs
├── Caregiver (Clinical access)
│   ├── View assigned patient data
│   ├── Start/stop monitoring
│   ├── View alerts
│   └── Add notes
└── Viewer (Read-only)
    ├── View assigned patient data
    └── View alerts (no action)
```

### 1.6 HIPAA Compliance Requirements

**Source:** HHS.gov HIPAA Security Rule, Rublon HIPAA Compliance Guide

**Technical Safeguards Required:**

1. **Access Control**
   - Restrict access based on need-to-know
   - Establish unique user identification
   - Emergency access procedure
   - Automatic logoff (inactivity timeout)
   - Audit controls (access logging)

2. **Authentication**
   - Multi-factor authentication (MFA) recommended
   - Secure password storage (hashing)
   - Session timeout
   - Failed login tracking

3. **Encryption**
   - Data in transit: TLS 1.2 or higher
   - Data at rest: AES-256 or equivalent
   - Key management procedures

4. **Audit Controls**
   - Log all access to ePHI
   - Monitor for inappropriate access
   - Retain logs for 6 years minimum

**Implementation Requirements:**
- All patient monitoring data is considered ePHI
- User authentication is mandatory
- Audit logging for all data access
- Automatic session timeout (15-30 minutes)
- Emergency access procedure for urgent situations

### 1.7 Encryption Requirements

**Source:** Censinet HIPAA Encryption Standards, Healthcare IT Security

**Data in Transit:**
- **Protocol**: TLS 1.3 (minimum TLS 1.2)
- **Cipher suites**: Only strong, modern ciphers
- **Certificate**: Valid SSL/TLS certificate
- **Applications**: All API calls, dashboard access, real-time monitoring data

**Data at Rest:**
- **Algorithm**: AES-256 (FIPS 140-2 compliant)
- **Scope**: Database, session logs, any stored patient data
- **Key management**: Secure key storage, regular rotation
- **Backup encryption**: All backups must be encrypted

**Implementation:**
```python
# Database encryption (PostgreSQL)
# Use pgcrypto extension or application-level encryption
# Session logs: Encrypt sensitive fields before storage
# API endpoints: Enforce HTTPS with HSTS header
```

---

## 2. Architecture Design

### 2.1 System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Patient Care Monitor                        │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │  Streamlit   │  │   Gradio     │  │   Monitor    │        │
│  │  Dashboard   │  │   Dashboard  │  │   (CLI)      │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
│         │                  │                  │                 │
│         └──────────────────┴──────────────────┘                 │
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Authentication Middleware                     │   │
│  │  - JWT Validation                                        │   │
│  │  - Session Management                                    │   │
│  │  - RBAC Authorization                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 API Layer (FastAPI)                       │   │
│  │  - /auth/login                                          │   │
│  │  - /auth/logout                                         │   │
│  │  - /auth/register                                       │   │
│  │  - /users/*                                             │   │
│  │  - /patients/*                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Business Logic Layer                        │   │
│  │  - User Management                                       │   │
│  │  - Patient Data Management                              │   │
│  │  - Monitoring Pipeline                                   │   │
│  │  - Alert System                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 Data Access Layer                        │   │
│  │  - SQLAlchemy ORM                                        │   │
│  │  - Database Operations                                   │   │
│  │  - Encryption/Decryption                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              PostgreSQL Database (Production)             │   │
│  │  - Users Table                                           │   │
│  │  - Roles Table                                           │   │
│  │  - Permissions Table                                     │   │
│  │  - Patients Table                                        │   │
│  │  - Sessions Table                                        │   │
│  │  - Audit Logs Table                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Database Schema

```sql
-- Users Table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    role_id INTEGER REFERENCES roles(id),
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP NULL,
    last_login TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Roles Table
CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Permissions Table
CREATE TABLE permissions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    resource VARCHAR(50),
    action VARCHAR(50)
);

-- Role Permissions Junction Table
CREATE TABLE role_permissions (
    role_id INTEGER REFERENCES roles(id),
    permission_id INTEGER REFERENCES permissions(id),
    PRIMARY KEY (role_id, permission_id)
);

-- Patient Assignments (Caregiver to Patient)
CREATE TABLE patient_assignments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    patient_id VARCHAR(50) NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by INTEGER REFERENCES users(id),
    UNIQUE(user_id, patient_id)
);

-- Sessions Table (for dashboard sessions)
CREATE TABLE sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    session_token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address INET,
    user_agent TEXT
);

-- Audit Logs Table (HIPAA requirement)
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(100),
    ip_address INET,
    user_agent TEXT,
    success BOOLEAN NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Password Reset Tokens
CREATE TABLE password_reset_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Email Verification Tokens
CREATE TABLE email_verification_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.3 Authentication Flow

```
┌─────────────┐
│   User      │
└──────┬──────┘
       │
       │ 1. Login Request (username, password)
       ▼
┌─────────────────────────────────┐
│   Streamlit Dashboard / API    │
└──────┬──────────────────────────┘
       │
       │ 2. POST /auth/login
       ▼
┌─────────────────────────────────┐
│   Authentication Service       │
│   - Validate credentials       │
│   - Check account status        │
│   - Rate limiting              │
└──────┬──────────────────────────┘
       │
       │ 3. Query database
       ▼
┌─────────────────────────────────┐
│   Database                     │
│   - Verify password hash        │
│   - Get user role              │
│   - Check lock status           │
└──────┬──────────────────────────┘
       │
       │ 4. User data + role
       ▼
┌─────────────────────────────────┐
│   JWT Token Generation          │
│   - Create access token         │
│   - Create refresh token        │
│   - Store session in DB         │
└──────┬──────────────────────────┘
       │
       │ 5. JWT tokens
       ▼
┌─────────────────────────────────┐
│   Client                       │
│   - Store tokens (secure)      │
│   - Include in Authorization   │
└─────────────────────────────────┘
```

---

## 3. Implementation Plan

### 3.1 Phase 1: Core Authentication Infrastructure (Week 1-2)

**Objectives:**
- Set up database models with SQLAlchemy
- Implement password hashing with bcrypt
- Create user registration and login endpoints
- Implement JWT token generation and validation
- Add basic rate limiting

**Tasks:**

1. **Database Setup**
   - Install SQLAlchemy and PostgreSQL adapter
   - Create database models (User, Role, Permission, Session)
   - Set up database migrations (Alembic)
   - Create initial roles and permissions

2. **Password Management**
   ```python
   # auth/password_manager.py
   from passlib.context import CryptContext
   
   pwd_context = CryptContext(
       schemes=["bcrypt"],
       deprecated="auto",
       bcrypt__rounds=12
   )
   
   def hash_password(password: str) -> str:
       return pwd_context.hash(password)
   
   def verify_password(plain_password: str, hashed_password: str) -> bool:
       return pwd_context.verify(plain_password, hashed_password)
   ```

3. **JWT Token Management**
   ```python
   # auth/jwt_manager.py
   from jose import JWTError, jwt
   from datetime import datetime, timedelta
   
   SECRET_KEY = os.getenv("JWT_SECRET_KEY")
   ALGORITHM = "HS256"
   ACCESS_TOKEN_EXPIRE_MINUTES = 30
   
   def create_access_token(data: dict) -> str:
       to_encode = data.copy()
       expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
       to_encode.update({"exp": expire})
       return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
   
   def decode_token(token: str) -> dict:
       try:
           payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
           return payload
       except JWTError:
           return None
   ```

4. **User Registration Endpoint**
   ```python
   # api/routes/auth.py
   @router.post("/register")
   async def register(user: UserCreate):
       # Validate email format
       # Check if email already exists
       # Hash password
       # Create user record
       # Generate email verification token
       # Send verification email
       # Return success
   ```

5. **Login Endpoint**
   ```python
   @router.post("/login")
   async def login(credentials: UserLogin):
       # Rate limiting check
       # Find user by email/username
       # Check if account is locked
       # Verify password
       # Check if account is verified
       # Generate JWT tokens
       # Create session record
       # Log successful login
       # Return tokens
   ```

**Deliverables:**
- Working user registration
- Working login with JWT tokens
- Database models and migrations
- Password hashing implementation
- Basic rate limiting

### 3.2 Phase 2: Role-Based Access Control (Week 3)

**Objectives:**
- Implement RBAC system
- Create permission decorators
- Add role assignment functionality
- Implement authorization middleware

**Tasks:**

1. **RBAC Implementation**
   ```python
   # auth/rbac.py
   class RBAC:
       def __init__(self, db: Session):
           self.db = db
       
       def has_permission(self, user_id: int, permission: str) -> bool:
           user = self.db.query(User).get(user_id)
           user_permissions = self._get_user_permissions(user)
           return permission in user_permissions
       
       def _get_user_permissions(self, user: User) -> set:
           # Get permissions from user's role
           # Return set of permission names
   ```

2. **Authorization Decorator**
   ```python
   # auth/decorators.py
   from functools import wraps
   
   def require_permission(permission: str):
       def decorator(func):
           @wraps(func)
           async def wrapper(*args, **kwargs):
               # Get user from JWT token
               # Check permission
               # Proceed or raise HTTPException
               return await func(*args, **kwargs)
           return wrapper
       return decorator
   ```

3. **Role Management Endpoints**
   ```python
   @router.post("/users/{user_id}/role")
   @require_permission("manage_users")
   async def assign_role(user_id: int, role_id: int):
       # Assign role to user
       # Log action
   ```

**Deliverables:**
- Working RBAC system
- Permission decorators
- Role assignment endpoints
- Authorization middleware

### 3.3 Phase 3: Streamlit Dashboard Integration (Week 4)

**Objectives:**
- Integrate authentication with Streamlit dashboard
- Implement login/logout UI
- Add session management
- Implement automatic logout

**Tasks:**

1. **Streamlit Authentication Integration**
   ```python
   # dashboard_auth.py
   import streamlit as st
   from auth.jwt_manager import decode_token
   
   def authenticate_user():
       token = st.session_state.get("auth_token")
       if not token:
           return None
       
       payload = decode_token(token)
       if not payload:
           st.session_state.clear()
           return None
       
       return payload.get("user_id")
   
   def login_page():
       st.title("Patient Care Monitor - Login")
       username = st.text_input("Username")
       password = st.text_input("Password", type="password")
       
       if st.button("Login"):
           # Call login API
           # Store token in session state
           # Redirect to dashboard
   ```

2. **Session Management**
   ```python
   def check_session_expiry():
       token = st.session_state.get("auth_token")
       if token:
           payload = decode_token(token)
           if payload and datetime.utcnow() > datetime.fromtimestamp(payload["exp"]):
               st.session_state.clear()
               st.rerun()
   ```

3. **Protected Dashboard Pages**
   ```python
   def dashboard_page():
       user_id = authenticate_user()
       if not user_id:
           login_page()
           return
       
       check_session_expiry()
       
       # Show dashboard content
   ```

**Deliverables:**
- Streamlit login page
- Session management
- Automatic logout
- Protected dashboard pages

### 3.4 Phase 4: Security Enhancements (Week 5)

**Objectives:**
- Implement MFA support
- Add email verification
- Implement password reset
- Add security headers
- Enable HTTPS enforcement

**Tasks:**

1. **Multi-Factor Authentication**
   ```python
   # auth/mfa.py
   import pyotp
   
   def generate_totp_secret():
       return pyotp.random_base32()
   
   def verify_totp(secret: str, token: str) -> bool:
       totp = pyotp.TOTP(secret)
       return totp.verify(token)
   ```

2. **Email Verification**
   ```python
   # auth/email_verification.py
   def send_verification_email(user_email: str, token: str):
       # Generate verification link
       # Send email via SMTP
       # Log sending attempt
   ```

3. **Password Reset**
   ```python
   @router.post("/auth/reset-password")
   async def request_password_reset(email: str):
       # Generate reset token
       # Store in database
       # Send reset email
   
   @router.post("/auth/reset-password/{token}")
   async def reset_password(token: str, new_password: str):
       # Validate token
       # Update password
       # Invalidate all sessions
   ```

4. **Security Headers**
   ```python
   # middleware/security.py
   from fastapi import Response
   
   def add_security_headers(response: Response) -> Response:
       response.headers["X-Content-Type-Options"] = "nosniff"
       response.headers["X-Frame-Options"] = "DENY"
       response.headers["X-XSS-Protection"] = "1; mode=block"
       response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
       response.headers["Content-Security-Policy"] = "default-src 'self'"
       return response
   ```

**Deliverables:**
- MFA implementation
- Email verification
- Password reset flow
- Security headers
- HTTPS enforcement

### 3.5 Phase 5: HIPAA Compliance Features (Week 6)

**Objectives:**
- Implement audit logging
- Add automatic logoff
- Implement emergency access
- Add data encryption
- Create compliance reports

**Tasks:**

1. **Audit Logging**
   ```python
   # auth/audit.py
   def log_audit_event(
       user_id: int,
       action: str,
       resource_type: str,
       resource_id: str,
       success: bool,
       ip_address: str,
       user_agent: str
   ):
       # Create audit log entry
       # Store in database
       # Ensure log retention (6 years minimum)
   ```

2. **Automatic Logoff**
   ```python
   # middleware/session_timeout.py
   def check_session_timeout(session: dict):
       last_activity = session.get("last_activity")
       timeout = 30 * 60  # 30 minutes
       
       if last_activity and (time.time() - last_activity) > timeout:
           session.clear()
           return True
       
       session["last_activity"] = time.time()
       return False
   ```

3. **Emergency Access**
   ```python
   # auth/emergency_access.py
   def request_emergency_access(requester_id: int, reason: str):
       # Log emergency access request
       # Notify administrators
       # Grant temporary elevated access
       # Set expiration (e.g., 1 hour)
       # Require justification
   ```

4. **Data Encryption**
   ```python
   # utils/encryption.py
   from cryptography.fernet import Fernet
   
   def encrypt_data(data: str, key: bytes) -> str:
       fernet = Fernet(key)
       return fernet.encrypt(data.encode()).decode()
   
   def decrypt_data(encrypted_data: str, key: bytes) -> str:
       fernet = Fernet(key)
       return fernet.decrypt(encrypted_data.encode()).decode()
   ```

**Deliverables:**
- Comprehensive audit logging
- Automatic session timeout
- Emergency access procedure
- Data encryption at rest
- HIPAA compliance documentation

### 3.6 Phase 6: Testing & Documentation (Week 7)

**Objectives:**
- Write comprehensive tests
- Create security tests
- Document API endpoints
- Create user guides
- Perform security audit

**Tasks:**

1. **Unit Tests**
   ```python
   # tests/test_auth.py
   def test_password_hashing():
       password = "test_password_123"
       hashed = hash_password(password)
       assert verify_password(password, hashed)
       assert not verify_password("wrong_password", hashed)
   
   def test_jwt_generation():
       user_id = 1
       token = create_access_token({"sub": str(user_id)})
       payload = decode_token(token)
       assert payload["sub"] == str(user_id)
   ```

2. **Integration Tests**
   ```python
   # tests/test_api_integration.py
   def test_login_flow():
       # Register user
       # Login with credentials
       # Verify JWT token
       # Access protected endpoint
   ```

3. **Security Tests**
   ```python
   # tests/test_security.py
   def test_rate_limiting():
       # Attempt multiple rapid logins
       # Verify rate limiting kicks in
   
   def test_sql_injection_protection():
       # Test SQL injection attempts
       # Verify ORM protects against injection
   ```

4. **Documentation**
   - API documentation (OpenAPI/Swagger)
   - User authentication guide
   - Administrator guide
   - HIPAA compliance documentation

**Deliverables:**
- Comprehensive test suite
- Security test results
- API documentation
- User guides
- Security audit report

---

## 4. Security Configuration

### 4.1 Environment Variables

```bash
# .env.example
JWT_SECRET_KEY=your-secret-key-here-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

DATABASE_URL=postgresql://user:password@localhost/patient_monitor
DATABASE_SSL_MODE=require

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
EMAIL_FROM=noreply@patientmonitor.com

MFA_ENABLED=true
SESSION_TIMEOUT_MINUTES=30
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION_MINUTES=30

ENCRYPTION_KEY=your-encryption-key-32-bytes-long
AUDIT_LOG_RETENTION_DAYS=2190  # 6 years
```

### 4.2 Password Policy

**Requirements:**
- Minimum 12 characters (recommended for 2026)
- At least 1 uppercase letter
- At least 1 lowercase letter
- At least 1 number
- At least 1 special character
- Cannot contain username
- Cannot be common password (check against breach list)

**Implementation:**
```python
# auth/password_policy.py
import re

def validate_password(password: str, username: str) -> tuple[bool, str]:
    if len(password) < 12:
        return False, "Password must be at least 12 characters"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least 1 uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least 1 lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least 1 number"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least 1 special character"
    
    if username.lower() in password.lower():
        return False, "Password cannot contain username"
    
    # Check against common passwords
    if is_common_password(password):
        return False, "Password is too common. Choose a stronger password."
    
    return True, "Password is valid"
```

### 4.3 Rate Limiting Configuration

```python
# auth/rate_limiting.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Specific endpoints
@limiter.limit("5 per hour")
@router.post("/auth/login")
async def login(credentials: UserLogin):
    pass

@limiter.limit("3 per hour")
@router.post("/auth/register")
async def register(user: UserCreate):
    pass
```

---

## 5. Deployment Considerations

### 5.1 Production Checklist

**Security:**
- [ ] Change all default passwords
- [ ] Use strong JWT secret keys (minimum 32 bytes)
- [ ] Enable HTTPS with valid SSL certificate
- [ ] Configure firewall rules
- [ ] Enable database encryption
- [ ] Set up regular backups
- [ ] Configure log monitoring
- [ ] Enable intrusion detection

**Database:**
- [ ] Use PostgreSQL in production
- [ ] Enable SSL/TLS for database connections
- [ ] Configure regular database backups
- [ ] Set up database replication (if needed)
- [ ] Configure connection pooling

**Application:**
- [ ] Set environment variables securely
- [ ] Enable security headers
- [ ] Configure CORS properly
- [ ] Set up monitoring and alerting
- [ ] Configure automatic log rotation
- [ ] Set up error tracking (Sentry, etc.)

**HIPAA Compliance:**
- [ ] Implement audit logging
- [ ] Configure automatic logoff (30 minutes)
- [ ] Set up emergency access procedure
- [ ] Document all security measures
- [ ] Conduct security risk assessment
- [ ] Implement business associate agreements
- [ ] Set up breach notification procedures

### 5.2 Monitoring & Alerting

**Key Metrics to Monitor:**
- Failed login attempts (alert on threshold)
- Successful logins from unusual locations
- API error rates
- Database query performance
- Session creation/deletion rates
- Token validation failures
- Rate limiting triggers

**Alerting Configuration:**
```python
# monitoring/alerts.py
def check_security_alerts():
    # Check for suspicious activity
    # Send alerts to administrators
    # Example: 10+ failed logins from same IP
```

### 5.3 Backup & Recovery

**Backup Strategy:**
- Database: Daily full backups + hourly incremental
- Application logs: Daily rotation, 6-year retention (HIPAA)
- Configuration: Version control
- Encryption keys: Offline secure storage

**Recovery Procedures:**
1. Documented recovery steps
2. Regular recovery testing
3. Point-in-time recovery capability
4. Disaster recovery plan

---

## 6. Cost & Resource Estimation

### 6.1 Development Effort

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| Phase 1: Core Authentication | 2 weeks | User registration, login, JWT tokens |
| Phase 2: RBAC | 1 week | Role management, permissions |
| Phase 3: Streamlit Integration | 1 week | Dashboard authentication |
| Phase 4: Security Enhancements | 1 week | MFA, email verification, password reset |
| Phase 5: HIPAA Compliance | 1 week | Audit logging, encryption |
| Phase 6: Testing & Documentation | 1 week | Tests, documentation |
| **Total** | **7 weeks** | **Complete multi-user system** |

### 6.2 Infrastructure Costs (Monthly)

| Service | Cost Range | Notes |
|---------|------------|-------|
| PostgreSQL Database | $15-50 | Managed service (e.g., AWS RDS) |
| Email Service | $10-30 | SendGrid, AWS SES, etc. |
| SSL Certificate | $0-50 | Let's Encrypt (free) or commercial |
| Monitoring Service | $0-50 | Sentry, Datadog, etc. |
| Backup Storage | $5-20 | S3, Glacier, etc. |
| **Total** | **$30-200/month** | Depending on scale |

### 6.3 Maintenance Requirements

**Ongoing Tasks:**
- Monitor security logs (daily)
- Review failed login attempts (daily)
- Update dependencies (monthly)
- Rotate encryption keys (quarterly)
- Security audit (annually)
- HIPAA compliance review (annually)

---

## 7. Risk Assessment & Mitigation

### 7.1 Security Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Password breach | Medium | High | bcrypt hashing, rate limiting |
| Session hijacking | Low | High | HTTPS, secure cookies, short token expiry |
| SQL injection | Low | High | ORM, parameterized queries |
| XSS attacks | Low | Medium | Input validation, CSP headers |
| CSRF attacks | Low | Medium | CSRF tokens, SameSite cookies |
| Unauthorized access | Medium | High | RBAC, audit logging |
| Data breach | Low | Critical | Encryption, access controls |

### 7.2 HIPAA Compliance Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Incomplete audit logging | Medium | High | Comprehensive logging, regular review |
| Missing encryption | Low | Critical | Encrypt at rest and in transit |
| No emergency access | Low | High | Documented emergency procedure |
| Inadequate training | Medium | Medium | Staff training programs |
| Third-party breaches | Low | High | BAAs, vendor due diligence |

---

## 8. Recommendations Summary

### 8.1 Technical Recommendations

1. **Authentication Stack**
   - Use JWT tokens for API authentication
   - Use database sessions for Streamlit dashboard
   - Implement bcrypt with cost factor 12-14
   - Add rate limiting on all auth endpoints

2. **Database**
   - Use PostgreSQL for production
   - Implement SQLAlchemy ORM
   - Enable SSL/TLS for database connections
   - Use pgcrypto for encryption

3. **Authorization**
   - Implement RBAC with 3-tier roles
   - Use permission decorators
   - Add authorization middleware
   - Implement need-to-know access

4. **Security**
   - Enable HTTPS with HSTS
   - Add security headers
   - Implement MFA for admin access
   - Add automatic session timeout

5. **HIPAA Compliance**
   - Comprehensive audit logging
   - Data encryption at rest and in transit
   - Emergency access procedure
   - 6-year log retention

### 8.2 Implementation Priorities

**Must-Have (Phase 1-3):**
- User registration and login
- JWT token authentication
- Basic RBAC system
- Streamlit dashboard integration
- Password hashing with bcrypt

**Should-Have (Phase 4-5):**
- Email verification
- Password reset
- MFA support
- Audit logging
- Session timeout

**Nice-to-Have (Future):**
- OAuth/Social login
- Advanced RBAC (resource-level)
- Biometric authentication
- Advanced analytics

### 8.3 Next Steps

1. **Immediate Actions**
   - Review and approve this plan
   - Set up development environment
   - Begin Phase 1 implementation

2. **Short-term (1-2 weeks)**
   - Complete Phase 1: Core Authentication
   - Set up PostgreSQL database
   - Implement user registration and login

3. **Medium-term (3-6 weeks)**
   - Complete Phases 2-5
   - Integrate with Streamlit dashboard
   - Implement HIPAA compliance features

4. **Long-term (7+ weeks)**
   - Complete Phase 6: Testing & Documentation
   - Security audit
   - Production deployment
   - Ongoing maintenance

---

## 9. References

### 9.1 Security Standards
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- NIST Digital Identity Guidelines: SP 800-63B

### 9.2 HIPAA Regulations
- HHS HIPAA Security Rule: https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html
- HIPAA Encryption Requirements: https://www.censinet.com/perspectives/hipaa-encryption-rules-for-data-in-transit

### 9.3 Python Authentication
- FastAPI Security Documentation: https://fastapi.tiangolo.com/tutorial/security/
- WorkOS Python Auth Guide: https://workos.com/blog/python-authentication-guide-2026
- Passlib Documentation: https://passlib.readthedocs.io/

### 9.4 Libraries & Tools
- SQLAlchemy: https://docs.sqlalchemy.org/
- PyJWT: https://pyjwt.readthedocs.io/
- Passlib: https://passlib.readthedocs.io/
- Streamlit-Authenticator: https://github.com/mkhorasani/Streamlit-Authenticator

---

## Appendix A: Sample Code

### A.1 Complete User Model

```python
# models/user.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100))
    role_id = Column(Integer, ForeignKey("roles.id"))
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime)
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    role = relationship("Role", back_populates="users")
    
    def set_password(self, password: str):
        self.password_hash = pwd_context.hash(password)
    
    def verify_password(self, password: str) -> bool:
        return pwd_context.verify(password, self.password_hash)
    
    def is_locked(self) -> bool:
        if self.locked_until:
            return datetime.utcnow() < self.locked_until
        return False
```

### A.2 Authentication Service

```python
# services/auth_service.py
from datetime import datetime, timedelta
from jose import JWTError, jwt
from models.user import User
from schemas.user import UserLogin, Token
from utils.rate_limiting import check_rate_limit

class AuthService:
    def __init__(self, db: Session):
        self.db = db
    
    async def login(self, credentials: UserLogin, ip_address: str) -> Token:
        # Rate limiting check
        if not check_rate_limit(ip_address, "login"):
            raise HTTPException(401, "Too many login attempts")
        
        # Find user
        user = self.db.query(User).filter(
            User.email == credentials.email
        ).first()
        
        if not user:
            raise HTTPException(401, "Invalid credentials")
        
        # Check if locked
        if user.is_locked():
            raise HTTPException(403, "Account locked. Try again later.")
        
        # Verify password
        if not user.verify_password(credentials.password):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=30)
            self.db.commit()
            raise HTTPException(401, "Invalid credentials")
        
        # Check if verified
        if not user.is_verified:
            raise HTTPException(403, "Email not verified")
        
        # Check if active
        if not user.is_active:
            raise HTTPException(403, "Account deactivated")
        
        # Reset failed attempts
        user.failed_login_attempts = 0
        user.last_login = datetime.utcnow()
        self.db.commit()
        
        # Generate tokens
        access_token = self._create_access_token(user.id)
        refresh_token = self._create_refresh_token(user.id)
        
        # Log successful login
        self._log_audit_event(user.id, "login", success=True, ip_address=ip_address)
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer"
        )
    
    def _create_access_token(self, user_id: int) -> str:
        expire = datetime.utcnow() + timedelta(minutes=30)
        to_encode = {"sub": str(user_id), "exp": expire}
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
```

### A.3 Streamlit Authentication Integration

```python
# dashboard/auth.py
import streamlit as st
import requests

API_BASE_URL = "http://localhost:8000/api"

def login_page():
    st.title("Patient Care Monitor")
    st.subheader("Login")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        
        if submit:
            try:
                response = requests.post(
                    f"{API_BASE_URL}/auth/login",
                    json={"email": username, "password": password}
                )
                
                if response.status_code == 200:
                    token_data = response.json()
                    st.session_state["auth_token"] = token_data["access_token"]
                    st.session_state["refresh_token"] = token_data["refresh_token"]
                    st.session_state["logged_in"] = True
                    st.rerun()
                else:
                    st.error("Invalid credentials")
            except Exception as e:
                st.error(f"Login failed: {str(e)}")

def check_authentication():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        login_page()
        return False
    
    # Verify token is still valid
    token = st.session_state.get("auth_token")
    if not token:
        login_page()
        return False
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/auth/verify",
            headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code != 200:
            login_page()
            return False
    except:
        login_page()
        return False
    
    return True

def logout():
    st.session_state.clear()
    st.rerun()
```

---

## Appendix B: Testing Checklist

### B.1 Functional Tests
- [ ] User registration with valid data
- [ ] User registration with invalid email
- [ ] User registration with weak password
- [ ] User registration with duplicate email
- [ ] Login with valid credentials
- [ ] Login with invalid credentials
- [ ] Login with locked account
- [ ] Login with unverified account
- [ ] Password reset flow
- [ ] Email verification flow
- [ ] Token refresh flow
- [ ] Logout functionality

### B.2 Security Tests
- [ ] SQL injection attempts
- [ ] XSS attempts
- [ ] CSRF protection
- [ ] Rate limiting enforcement
- [ ] Session timeout
- [ ] Token expiration
- [ ] Password hashing verification
- [ ] Permission checks
- [ ] Unauthorized access attempts
- [ ] Brute force protection

### B.3 HIPAA Compliance Tests
- [ ] Audit logging for all access
- [ ] Automatic logoff after timeout
- [ ] Emergency access procedure
- [ ] Data encryption verification
- [ ] Log retention (6 years)
- [ ] Access control enforcement

---

**Document End**

This implementation plan provides a comprehensive roadmap for adding multi-user authentication and security to the Patient Care Monitor system. The plan is based on extensive research into security best practices, HIPAA compliance requirements, and Python authentication patterns.

For questions or clarifications, please refer to the research sources cited in Section 9.
