"""JWT authentication for the FastAPI dashboard."""

import logging
import os
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from time import time

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── JWT secret ────────────────────────────────────────────────────────────────
# Use env var in production. If missing, generate a random key per process
# (tokens expire on restart — acceptable for dev; never uses a known public string).
_env_secret = os.environ.get("JWT_SECRET_KEY")
if _env_secret:
    SECRET_KEY = _env_secret
else:
    SECRET_KEY = secrets.token_hex(32)
    logger.warning(
        "JWT_SECRET_KEY not set — using a random key. "
        "Tokens will be invalidated on every restart. Set JWT_SECRET_KEY in production."
    )

ALGORITHM = "HS256"
TOKEN_TTL_HOURS = 720  # 30 days

bearer_scheme = HTTPBearer()

# ── Rate limiting (in-memory, per IP) ─────────────────────────────────────────
_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_WINDOW_SECS = 60
_RATE_MAX_ATTEMPTS = 5


def _check_rate_limit(ip: str) -> bool:
    """Return False if this IP has exceeded the login rate limit."""
    now = time()
    recent = [t for t in _login_attempts[ip] if now - t < _RATE_WINDOW_SECS]
    _login_attempts[ip] = recent
    if len(recent) >= _RATE_MAX_ATTEMPTS:
        return False
    _login_attempts[ip].append(now)
    return True


# ── Models ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── User store ────────────────────────────────────────────────────────────────

def _get_users() -> dict[str, str]:
    """Load username→password/hash from DASHBOARD_USERS env var.

    Supports both formats:
      - Plaintext:  admin:mypassword        (legacy, logs a warning)
      - Bcrypt hash: admin:$2b$12$...       (recommended)

    Multi-user format: "admin:pass1,user2:pass2"
    Single-user fallback: DASHBOARD_ADMIN_PASSWORD env var.
    """
    raw = os.environ.get("DASHBOARD_USERS", "")
    if raw:
        users = {}
        for pair in raw.split(","):
            if ":" in pair:
                u, p = pair.split(":", 1)
                users[u.strip()] = p.strip()
        return users

    password = os.environ.get("DASHBOARD_ADMIN_PASSWORD", "")
    if password:
        return {"admin": password}

    return {}


def verify_credentials(username: str, password: str) -> bool:
    users = _get_users()
    stored = users.get(username)
    if not stored:
        return False

    if stored.startswith("$2b$") or stored.startswith("$2a$"):
        return bcrypt.checkpw(password.encode(), stored.encode())

    # Plaintext fallback — warn so operator knows to migrate
    logger.warning(
        "User '%s' has a plaintext password in DASHBOARD_USERS. "
        "Replace with a bcrypt hash: python -c \"import bcrypt; "
        "print(bcrypt.hashpw(b'YOUR_PASSWORD', bcrypt.gensalt()).decode())\"",
        username,
    )
    return stored == password


# ── Token helpers ─────────────────────────────────────────────────────────────

def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """Dependency — validates Bearer JWT and returns username."""
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise JWTError("no sub")
        return username
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Login endpoint helper (rate-limit check lives here so main.py stays clean) ─

def login_with_rate_limit(request: Request, body: LoginRequest) -> TokenResponse:
    """Verify credentials with rate limiting. Raise 429 if limit exceeded."""
    client_ip = request.client.host if request.client else "unknown"

    if not _check_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again in 60 seconds.",
        )

    if not verify_credentials(body.username, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    return TokenResponse(access_token=create_token(body.username))
