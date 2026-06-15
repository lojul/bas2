"""FastAPI app for the Property Intelligence Dashboard."""

import os
import sys

# Ensure the langgraph package root is on the path when run from api/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from api.auth import LoginRequest, TokenResponse, login_with_rate_limit
from api.routes.admin import router as admin_router
from api.routes.chat import router as chat_router
from api.routes.search import router as search_router

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Property Intelligence API",
    description="FastAPI backend for the C21 Property Intelligence Dashboard",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allow Next.js dev server and Vercel production URL
_allowed_origins = [
    "http://localhost:3000",
    "https://localhost:3000",
]
_vercel_url = os.environ.get("VERCEL_URL", "")
if _vercel_url:
    _allowed_origins.append(f"https://{_vercel_url}")
_frontend_url = os.environ.get("FRONTEND_URL", "")
if _frontend_url:
    _allowed_origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(admin_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(search_router, prefix="/api")

# ── Auth endpoints ────────────────────────────────────────────────────────────

@app.post("/api/auth/login", response_model=TokenResponse)
def login(request: Request, body: LoginRequest):
    """Exchange username + password for a JWT (rate-limited: 5 attempts/minute)."""
    return login_with_rate_limit(request, body)


# ── Root redirect ─────────────────────────────────────────────────────────────

@app.get("/")
def root():
    frontend = os.environ.get("FRONTEND_URL", "")
    if frontend:
        return RedirectResponse(url=frontend)
    return {"service": "property-intelligence-api", "docs": "/docs"}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "property-intelligence-api"}
