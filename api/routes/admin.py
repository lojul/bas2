"""Admin routes — runtime configuration."""

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import get_current_user
from api.common import read_config, write_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


# ── Config ─────────────────────────────────────────────────────────────────────

class ConfigBody(BaseModel):
    inbox_folder: str | None = None
    processed_folder: str | None = None
    move_when_done: bool | None = None
    timer_enabled: bool | None = None
    ms_client_id: str | None = None
    ms_tenant_id: str | None = None
    ms_client_secret: str | None = None
    ms_drive_id: str | None = None


def _config_response(cfg: dict) -> dict:
    return {
        "inbox_folder": cfg.get("inbox_folder", ""),
        "processed_folder": cfg.get("processed_folder", "/Document Processor/Processed"),
        "move_when_done": cfg.get("move_when_done", False),
        "timer_enabled": cfg.get("timer_enabled", True),
        "ms_client_id": os.environ.get("MS_GRAPH_CLIENT_ID") or cfg.get("ms_client_id", ""),
        "ms_tenant_id": os.environ.get("MS_GRAPH_TENANT_ID") or cfg.get("ms_tenant_id", ""),
        "ms_client_secret_configured": bool(
            os.environ.get("MS_GRAPH_CLIENT_SECRET") or cfg.get("ms_client_secret", "")
        ),
        "ms_drive_id": os.environ.get("MS_GRAPH_DRIVE_ID") or cfg.get("ms_drive_id", ""),
    }


@router.get("/config")
def get_config(username: Annotated[str, Depends(get_current_user)] = None):
    """Read runtime configuration."""
    return _config_response(read_config())


@router.put("/config")
def update_config(
    body: ConfigBody,
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """Update runtime configuration."""
    cfg = read_config()
    if body.inbox_folder is not None:
        cfg["inbox_folder"] = body.inbox_folder.strip()
    if body.processed_folder is not None:
        cfg["processed_folder"] = body.processed_folder.strip()
    if body.move_when_done is not None:
        cfg["move_when_done"] = body.move_when_done
    if body.timer_enabled is not None:
        cfg["timer_enabled"] = body.timer_enabled
    if body.ms_client_id is not None:
        cfg["ms_client_id"] = body.ms_client_id.strip()
    if body.ms_tenant_id is not None:
        cfg["ms_tenant_id"] = body.ms_tenant_id.strip()
    if body.ms_client_secret is not None and body.ms_client_secret.strip():
        cfg["ms_client_secret"] = body.ms_client_secret.strip()
    if body.ms_drive_id is not None:
        cfg["ms_drive_id"] = body.ms_drive_id.strip()
    try:
        write_config(cfg)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    return _config_response(cfg)


