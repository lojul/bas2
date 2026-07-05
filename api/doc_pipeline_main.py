"""Document Pipeline API — triage, upload, process, admin, monitoring."""

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
from api.routes.admin import router as admin_router
from api.routes.assistant import router as assistant_router
from api.routes.billing import router as billing_router
from api.routes.monitoring import router as monitoring_router
from api.routes.pipeline import router as pipeline_router

# ── Startup warmup ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-import heavy modules so the first user request isn't slow.
    try:
        from src.nodes.assistant import handle_message  # noqa: F401
        print("[startup] assistant module loaded")
    except Exception as e:
        print(f"[startup] assistant import warning: {e}")
    yield

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Document Pipeline API",
    description="C21 Document Pipeline — triage, upload, OCR, classify, extract, index",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────

_allowed_origins = [
    "http://localhost:3000",
    "https://localhost:3000",
]
for _env_var in ("FRONTEND_URL", "DOC_PIPELINE_CORS_ORIGIN"):
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

app.include_router(admin_router, prefix="/api")
app.include_router(assistant_router, prefix="/api")
app.include_router(billing_router, prefix="/api")
app.include_router(monitoring_router, prefix="/api")
app.include_router(pipeline_router, prefix="/api")

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
    return {"service": "doc-pipeline-api", "docs": "/docs"}


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "doc-pipeline-api", "deploy": os.environ.get("DEPLOY_TS", "unknown")}
