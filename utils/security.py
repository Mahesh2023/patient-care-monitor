"""
Security Utilities
==================
Security enhancements for the application.

Features:
- Rate limiting
- Content Security Policy
- Security headers
- CORS configuration
- CSRF protection
- Consistent error response format
"""

import logging
import time
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable, Any
from functools import wraps
from collections import defaultdict

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter using token bucket algorithm.
    
    Limits the number of requests from a client within a time window.
    """
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        """
        Initialize rate limiter.
        
        Args:
            max_requests: Maximum requests per window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
        logger.info(f"Rate limiter initialized: {max_requests} requests per {window_seconds}s")
    
    def is_allowed(self, client_id: str) -> bool:
        """
        Check if request is allowed for client.
        
        Args:
            client_id: Unique client identifier (IP address, user ID, etc.)
            
        Returns:
            True if request is allowed, False otherwise
        """
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old requests
        self.requests[client_id] = [
            timestamp for timestamp in self.requests[client_id]
            if timestamp > window_start
        ]
        
        # Check if under limit
        if len(self.requests[client_id]) < self.max_requests:
            self.requests[client_id].append(now)
            return True
        
        logger.warning(f"Rate limit exceeded for client {client_id}")
        return False
    
    def get_remaining(self, client_id: str) -> int:
        """
        Get remaining requests for client.
        
        Args:
            client_id: Unique client identifier
            
        Returns:
            Number of remaining requests
        """
        now = time.time()
        window_start = now - self.window_seconds
        
        self.requests[client_id] = [
            timestamp for timestamp in self.requests[client_id]
            if timestamp > window_start
        ]
        
        return max(0, self.max_requests - len(self.requests[client_id]))
    
    def reset(self, client_id: str) -> None:
        """Reset rate limit for client."""
        self.requests[client_id] = []
        logger.info(f"Rate limit reset for client {client_id}")


class SecurityHeaders:
    """
    Security headers for HTTP responses.
    """
    
    @staticmethod
    def get_headers() -> Dict[str, str]:
        """
        Get standard security headers.
        
        Returns:
            Dictionary of security headers
        """
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()"
        }
    
    @staticmethod
    def get_csp_directives() -> str:
        """
        Get Content Security Policy directives.
        
        Returns:
            CSP header value
        """
        directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "form-action 'self'",
            "base-uri 'self'"
        ]
        return "; ".join(directives)
    
    @staticmethod
    def get_cors_headers(allowed_origins: Optional[list] = None) -> Dict[str, str]:
        """
        Get CORS headers.
        
        Args:
            allowed_origins: List of allowed origins
            
        Returns:
            Dictionary of CORS headers
        """
        if allowed_origins is None:
            allowed_origins = ["*"]
        
        return {
            "Access-Control-Allow-Origin": ", ".join(allowed_origins),
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
            "Access-Control-Max-Age": "86400",
            "Access-Control-Allow-Credentials": "true" if "*" not in allowed_origins else "false"
        }


class CSRFProtection:
    """
    CSRF token generation and validation.
    """
    
    def __init__(self, secret_key: Optional[str] = None):
        """
        Initialize CSRF protection.
        
        Args:
            secret_key: Secret key for token signing (auto-generated if None)
        """
        self.secret_key = secret_key or secrets.token_hex(32)
        self.tokens = {}
        logger.info("CSRF protection initialized")
    
    def generate_token(self, session_id: str) -> str:
        """
        Generate CSRF token for session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            CSRF token
        """
        # Create token with timestamp
        timestamp = int(time.time())
        data = f"{session_id}:{timestamp}".encode('utf-8')
        
        # Sign with HMAC
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            data,
            hashlib.sha256
        ).hexdigest()
        
        token = f"{timestamp}:{signature}"
        self.tokens[session_id] = token
        
        logger.debug(f"Generated CSRF token for session {session_id}")
        return token
    
    def validate_token(self, session_id: str, token: str, max_age_seconds: int = 3600) -> bool:
        """
        Validate CSRF token.
        
        Args:
            session_id: Session identifier
            token: CSRF token to validate
            max_age_seconds: Maximum token age in seconds
            
        Returns:
            True if token is valid, False otherwise
        """
        try:
            # Parse token
            timestamp_str, signature = token.split(':')
            timestamp = int(timestamp_str)
            
            # Check age
            if time.time() - timestamp > max_age_seconds:
                logger.warning("CSRF token expired")
                return False
            
            # Verify signature
            data = f"{session_id}:{timestamp}".encode('utf-8')
            expected_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                data,
                hashlib.sha256
            ).hexdigest()
            
            is_valid = hmac.compare_digest(signature, expected_signature)
            
            if not is_valid:
                logger.warning("Invalid CSRF token signature")
            
            return is_valid
        except (ValueError, AttributeError) as e:
            logger.error(f"Error validating CSRF token: {e}")
            return False
    
    def revoke_token(self, session_id: str) -> None:
        """Revoke CSRF token for session."""
        if session_id in self.tokens:
            del self.tokens[session_id]
            logger.info(f"Revoked CSRF token for session {session_id}")


class ConsentManager:
    """
    Consent management with HMAC-signed tokens per DPDP Act 2023.
    """
    
    def __init__(self, secret_key: Optional[str] = None, token_ttl_hours: int = 24):
        """
        Initialize consent manager.
        
        Args:
            secret_key: Secret key for token signing
            token_ttl_hours: Token time-to-live in hours
        """
        self.secret_key = secret_key or secrets.token_hex(32)
        self.token_ttl = timedelta(hours=token_ttl_hours)
        self.consents = {}
        logger.info(f"Consent manager initialized with {token_ttl_hours}h TTL")
    
    def generate_consent_token(self, user_id: str, consent_type: str, data: Optional[Dict] = None) -> str:
        """
        Generate HMAC-signed consent token.
        
        Args:
            user_id: User identifier
            consent_type: Type of consent (e.g., "data_processing", "health_data")
            data: Additional consent data
            
        Returns:
            Signed consent token
        """
        timestamp = datetime.now().isoformat()
        expiry = (datetime.now() + self.token_ttl).isoformat()
        
        payload = {
            "user_id": user_id,
            "consent_type": consent_type,
            "timestamp": timestamp,
            "expiry": expiry,
            "data": data or {}
        }
        
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        token = f"{signature}:{payload_str}"
        
        # Store consent
        self.consents[user_id] = {
            "token": token,
            "consent_type": consent_type,
            "granted_at": timestamp,
            "expires_at": expiry,
            "data": data or {}
        }
        
        logger.info(f"Generated consent token for user {user_id}, type {consent_type}")
        return token
    
    def validate_consent_token(self, user_id: str, token: str) -> Dict:
        """
        Validate consent token and check expiry.
        
        Args:
            user_id: User identifier
            token: Consent token to validate
            
        Returns:
            Dictionary with validation result
        """
        try:
            # Parse token
            signature_str, payload_str = token.split(':', 1)
            
            # Verify signature
            expected_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                payload_str.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature_str, expected_signature):
                return {"valid": False, "reason": "Invalid signature"}
            
            # Parse payload
            payload = json.loads(payload_str)
            
            # Check expiry
            expiry = datetime.fromisoformat(payload["expiry"])
            if datetime.now() > expiry:
                return {"valid": False, "reason": "Token expired"}
            
            # Check user ID match
            if payload["user_id"] != user_id:
                return {"valid": False, "reason": "User ID mismatch"}
            
            return {
                "valid": True,
                "consent_type": payload["consent_type"],
                "granted_at": payload["timestamp"],
                "expires_at": payload["expiry"],
                "data": payload.get("data", {})
            }
        except (ValueError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error validating consent token: {e}")
            return {"valid": False, "reason": "Invalid token format"}
    
    def refresh_consent_token(self, user_id: str) -> Optional[str]:
        """
        Refresh consent token (auto-refresh on expiry).
        
        Args:
            user_id: User identifier
            
        Returns:
            New consent token or None if no existing consent
        """
        if user_id not in self.consents:
            return None
        
        existing = self.consents[user_id]
        return self.generate_consent_token(
            user_id,
            existing["consent_type"],
            existing["data"]
        )
    
    def withdraw_consent(self, user_id: str) -> bool:
        """
        Withdraw user consent.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if consent was withdrawn
        """
        if user_id in self.consents:
            del self.consents[user_id]
            logger.info(f"Consent withdrawn for user {user_id}")
            return True
        return False


class ErrorHandler:
    """
    Consistent error response format.
    """
    
    @staticmethod
    def format_error(
        error_code: str,
        message: str,
        details: Optional[Dict] = None,
        status_code: int = 500
    ) -> Dict:
        """
        Format error response consistently.
        
        Args:
            error_code: Application-specific error code
            message: Human-readable error message
            details: Additional error details
            status_code: HTTP status code
            
        Returns:
            Formatted error dictionary
        """
        return {
            "error": {
                "code": error_code,
                "message": message,
                "details": details or {},
                "timestamp": datetime.now().isoformat(),
                "status_code": status_code
            }
        }
    
    @staticmethod
    def format_success(
        data: Any,
        message: Optional[str] = None,
        status_code: int = 200
    ) -> Dict:
        """
        Format success response consistently.
        
        Args:
            data: Response data
            message: Optional success message
            status_code: HTTP status code
            
        Returns:
            Formatted success dictionary
        """
        return {
            "success": True,
            "data": data,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "status_code": status_code
        }


def rate_limit(max_requests: int = 100, window_seconds: int = 60):
    """
    Decorator for rate limiting function calls.
    
    Args:
        max_requests: Maximum requests per window
        window_seconds: Time window in seconds
        
    Returns:
        Decorator function
    """
    limiter = RateLimiter(max_requests, window_seconds)
    
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Use first argument as client_id if it's a string, otherwise use 'default'
            client_id = args[0] if args and isinstance(args[0], str) else 'default'
            
            if not limiter.is_allowed(client_id):
                raise Exception("Rate limit exceeded")
            
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator


# Global instances
rate_limiter = RateLimiter(max_requests=100, window_seconds=60)
csrf_protection = CSRFProtection()
consent_manager = ConsentManager()
