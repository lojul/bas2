"""Shared utilities for API route modules."""

import os

import httpx
from msal import ConfidentialClientApplication

SUPPORTED_FORMATS = {"pdf", "jpg", "jpeg", "png", "docx", "pptx"}

_CONFIG_BLOB = "config/settings.json"
_DEFAULT_CONFIG = {
    "inbox_folder": "/Document Processor/In",
    "processed_folder": "/Document Processor/Processed",
    "move_when_done": False,
    "timer_enabled": True,
    "ms_client_id": "",
    "ms_tenant_id": "",
    "ms_client_secret": "",
    "ms_drive_id": "",
}


def _blob_url() -> str | None:
    account = os.environ.get("AZURE_BLOB_ACCOUNT")
    container = os.environ.get("AZURE_BLOB_CONTAINER", "property-pdf")
    sas = os.environ.get("AZURE_BLOB_WRITE_SAS", "")
    if not account:
        return None
    return f"https://{account}.blob.core.windows.net/{container}/{_CONFIG_BLOB}?{sas}"


def read_config() -> dict:
    url = _blob_url()
    if not url:
        return _DEFAULT_CONFIG.copy()
    try:
        with httpx.Client(timeout=5) as client:
            r = client.get(url)
            if r.status_code == 200:
                return {**_DEFAULT_CONFIG, **r.json()}
            if r.status_code == 404:
                return _DEFAULT_CONFIG.copy()
    except Exception:
        pass
    return _DEFAULT_CONFIG.copy()


def write_config(cfg: dict) -> None:
    url = _blob_url()
    if not url:
        raise RuntimeError("Blob storage not configured")
    with httpx.Client(timeout=10) as client:
        r = client.put(
            url,
            content=__import__("json").dumps(cfg, ensure_ascii=False).encode(),
            headers={"x-ms-blob-type": "BlockBlob", "Content-Type": "application/json"},
        )
        r.raise_for_status()


def get_drive_id() -> str | None:
    cfg = read_config()
    return os.environ.get("MS_GRAPH_DRIVE_ID") or cfg.get("ms_drive_id") or None


def get_graph_token() -> str:
    cfg = read_config()
    client_id = os.environ.get("MS_GRAPH_CLIENT_ID") or cfg.get("ms_client_id", "")
    tenant_id = os.environ.get("MS_GRAPH_TENANT_ID") or cfg.get("ms_tenant_id", "")
    client_secret = os.environ.get("MS_GRAPH_CLIENT_SECRET") or cfg.get("ms_client_secret", "")
    if not all([client_id, tenant_id, client_secret]):
        raise ValueError("OneDrive credentials not configured — set them in Settings or as environment variables.")
    app = ConfidentialClientApplication(
        client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        raise ValueError(result.get("error_description", "Token acquisition failed"))
    return result["access_token"]


def patch_onedrive_env() -> None:
    """Back-fill MS Graph credentials from blob config into os.environ when env vars are absent."""
    if os.environ.get("MS_GRAPH_CLIENT_ID"):
        return
    cfg = read_config()
    for env_key, cfg_key in (
        ("MS_GRAPH_CLIENT_ID", "ms_client_id"),
        ("MS_GRAPH_TENANT_ID", "ms_tenant_id"),
        ("MS_GRAPH_CLIENT_SECRET", "ms_client_secret"),
        ("MS_GRAPH_DRIVE_ID", "ms_drive_id"),
    ):
        val = cfg.get(cfg_key, "")
        if val:
            os.environ[env_key] = val
