"""Property Chat API — RAG chatbot and search."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from api.auth import LoginRequest, TokenResponse, login_with_rate_limit
from api.routes.chat import router as chat_router
from api.routes.search import router as search_router

# ── Startup warmup ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from src.nodes.chatbot import chat  # noqa: F401
        print("[startup] chatbot module loaded")
    except Exception as e:
        print(f"[startup] chatbot import warning: {e}")
    yield

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Property Chat API",
    description="C21 Property Intelligence — RAG chatbot, hybrid search, PDF report generation",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────

_allowed_origins = [
    "http://localhost:3000",
    "https://localhost:3000",
]
for _env_var in ("FRONTEND_URL", "PROP_CHAT_CORS_ORIGIN"):
    _val = os.environ.get(_env_var, "")
    if _val:
        _allowed_origins.append(f"https://{_val}" if not _val.startswith("http") else _val)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(chat_router, prefix="/api")
app.include_router(search_router, prefix="/api")

# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login", response_model=TokenResponse)
def login(request: Request, body: LoginRequest):
    return login_with_rate_limit(request, body)


# ── Root / Health ─────────────────────────────────────────────────────────────

@app.get("/")
def root():
    frontend = os.environ.get("FRONTEND_URL", "")
    if frontend:
        return RedirectResponse(url=frontend)
    return {"service": "prop-chat-api", "docs": "/docs"}


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "prop-chat-api", "deploy": os.environ.get("DEPLOY_TS", "unknown")}
