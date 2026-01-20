"""
Security Middleware for EasyScale API

Protects against common security threats:
- Blocks suspicious path traversal attempts
- Rate limiting per IP
- Blocks known vulnerability scanners
- Logs security events
"""

import time
from typing import Dict, Optional
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


# ============================================================================
# SUSPICIOUS PATTERNS
# ============================================================================

SUSPICIOUS_PATHS = [
    ".git", ".env", "aws", "terraform", "docker", "wp-admin", "wp-content",
    "phpinfo", "config", "credentials", ".aws", "root/", "admin", ".ssh",
    "backup", "database", ".sql", ".tar", ".zip", "passwd", "shadow"
]

SUSPICIOUS_EXTENSIONS = [
    ".php", ".asp", ".aspx", ".jsp", ".cgi", ".sh", ".bat", ".cmd"
]

# Known vulnerability scanner user agents
BLOCKED_USER_AGENTS = [
    "nikto", "sqlmap", "nmap", "masscan", "nessus", "openvas",
    "acunetix", "burp", "zaproxy", "metasploit"
]


# ============================================================================
# RATE LIMITER
# ============================================================================

class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests: Dict[str, list] = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        """Check if request from IP is allowed."""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)

        # Clean old requests
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip]
            if req_time > minute_ago
        ]

        # Check limit
        if len(self.requests[client_ip]) >= self.requests_per_minute:
            return False

        # Record request
        self.requests[client_ip].append(now)
        return True

    def get_remaining(self, client_ip: str) -> int:
        """Get remaining requests for IP."""
        return max(0, self.requests_per_minute - len(self.requests[client_ip]))


# ============================================================================
# SECURITY MIDDLEWARE
# ============================================================================

class SecurityMiddleware(BaseHTTPMiddleware):
    """Middleware to protect against common attacks."""

    def __init__(self, app, rate_limit: int = 60):
        super().__init__(app)
        self.rate_limiter = RateLimiter(requests_per_minute=rate_limit)
        self.blocked_ips: Dict[str, datetime] = {}

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        path = request.url.path.lower()
        user_agent = request.headers.get("user-agent", "").lower()

        # 1. Check if IP is temporarily blocked
        if client_ip in self.blocked_ips:
            if datetime.now() < self.blocked_ips[client_ip]:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "IP temporarily blocked due to suspicious activity"}
                )
            else:
                del self.blocked_ips[client_ip]

        # 2. Check for suspicious paths
        if any(suspicious in path for suspicious in SUSPICIOUS_PATHS):
            self._block_ip(client_ip, minutes=30)
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Access denied"}
            )

        # 3. Check for suspicious extensions
        if any(path.endswith(ext) for ext in SUSPICIOUS_EXTENSIONS):
            self._block_ip(client_ip, minutes=30)
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Access denied"}
            )

        # 4. Check user agent
        if any(blocked in user_agent for blocked in BLOCKED_USER_AGENTS):
            self._block_ip(client_ip, minutes=60)
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Access denied"}
            )

        # 5. Rate limiting (only for API endpoints)
        if path.startswith("/v1/") or path.startswith("/api/"):
            if not self.rate_limiter.is_allowed(client_ip):
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": "Rate limit exceeded. Please try again later.",
                        "retry_after": 60
                    },
                    headers={"Retry-After": "60"}
                )

        # 6. Process request
        response = await call_next(request)

        # 7. Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # 8. Add rate limit headers for API endpoints
        if path.startswith("/v1/") or path.startswith("/api/"):
            remaining = self.rate_limiter.get_remaining(client_ip)
            response.headers["X-RateLimit-Limit"] = str(self.rate_limiter.requests_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response

    def _block_ip(self, ip: str, minutes: int):
        """Temporarily block an IP address."""
        block_until = datetime.now() + timedelta(minutes=minutes)
        self.blocked_ips[ip] = block_until
        print(f"🚨 SECURITY: Blocked IP {ip} until {block_until}")


# ============================================================================
# LOGGING MIDDLEWARE
# ============================================================================

class AccessLogMiddleware(BaseHTTPMiddleware):
    """Middleware for better access logging."""

    def __init__(self, app, log_level: str = "INFO"):
        super().__init__(app)
        self.log_level = log_level

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Log only relevant requests (ignore static files and health checks)
        path = request.url.path
        if self._should_log(path, response.status_code):
            print(
                f"📊 {request.method} {path} "
                f"→ {response.status_code} "
                f"({duration*1000:.0f}ms) "
                f"[{request.client.host}]"
            )

        return response

    def _should_log(self, path: str, status_code: int) -> bool:
        """Determine if request should be logged."""
        # Always log errors
        if status_code >= 400:
            return True

        # Log API endpoints
        if path.startswith("/v1/") or path.startswith("/api/"):
            return True

        # Ignore common noise
        if path in ["/favicon.ico", "/robots.txt", "/"]:
            return False

        return False


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_client_ip(request: Request) -> str:
    """Get client IP from request, handling proxies."""
    # Check X-Forwarded-For header (from proxies)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fallback to direct connection
    return request.client.host
