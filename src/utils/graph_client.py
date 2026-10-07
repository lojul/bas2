"""Microsoft Graph API client for the OneDrive delta sync.

Delta-based (not full folder listing) — only ever asks Graph for what changed
since the last saved token. See src/utils/onedrive_delta_store.py for the
persisted token and function_app.py's onedrive_sync for the guard around it.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from msal import ConfidentialClientApplication

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_DELTA_SELECT = "id,name,file,folder,lastModifiedDateTime,parentReference,webUrl,@microsoft.graph.downloadUrl"


class DeltaLinkExpiredError(Exception):
    """Raised when Graph returns 410 Gone — the delta link is no longer valid."""


class MissingDeltaLinkError(Exception):
    """Raised when a delta traversal finishes without an @odata.deltaLink.

    Must never be swallowed into an empty token — an empty token read back
    from storage looks like "no baseline" and sends the next run down the
    full-traversal path (re-OCRs the whole drive). Failing loudly here is
    strictly cheaper than that.
    """


class GraphClient:
    def __init__(self):
        from src.config import get_config

        msgraph = get_config().msgraph
        self._app = ConfidentialClientApplication(
            client_id=msgraph.client_id,
            client_credential=msgraph.client_secret,
            authority=msgraph.authority,
        )
        self._scope = msgraph.scope
        self._token: str | None = None
        self._token_expiry: datetime | None = None

    def _get_token(self) -> str:
        now = datetime.now(timezone.utc)
        if self._token and self._token_expiry and now < self._token_expiry:
            return self._token

        result = self._app.acquire_token_for_client(scopes=self._scope)
        if "access_token" not in result:
            raise Exception(
                f"Failed to get MS Graph token: {result.get('error_description', 'Unknown error')}"
            )
        self._token = result["access_token"]
        self._token_expiry = now + timedelta(seconds=int(result.get("expires_in", 3600)) - 60)
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    def get(self, url: str) -> dict:
        with httpx.Client(timeout=60) as client:
            resp = client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def download(self, download_url: str) -> bytes:
        # @microsoft.graph.downloadUrl is pre-authenticated — no auth header needed
        with httpx.Client(timeout=120) as client:
            resp = client.get(download_url)
            resp.raise_for_status()
            return resp.content

    def download_item(self, drive_id: str, item_id: str) -> bytes:
        """Download via the authenticated /content endpoint (302 to a pre-signed URL).
        Fallback for items where Graph omits @microsoft.graph.downloadUrl."""
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            resp = client.get(
                f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content", headers=self._headers()
            )
            resp.raise_for_status()
            return resp.content

    def iter_delta_changes(
        self,
        drive_id: str,
        item_id: str,
        delta_link: str | None,
        since: datetime | None = None,
        require_delta_link: bool = True,
    ) -> tuple[list[dict], str]:
        """Runs a delta query on the watched folder.

        Returns (changed_items, new_delta_link). On first run (no delta_link),
        Graph returns every current item — filtered by `since` if given.

        `require_delta_link=False` is for one-off/diagnostic callers that
        discard the token (no state to corrupt). Any caller that persists the
        token must leave it True.
        """
        url = delta_link or (
            f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/delta?$select={_DELTA_SELECT}"
        )

        items: list[dict] = []
        new_delta_link = ""
        while url:
            try:
                data = self.get(url)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 410:
                    raise DeltaLinkExpiredError(
                        "Graph returned 410 Gone — delta link has expired."
                    ) from exc
                raise

            for item in data.get("value", []):
                if "file" not in item:
                    continue  # folders, or deleted items with no file facet
                modified_at = item.get("lastModifiedDateTime")
                if not modified_at:
                    logger.warning(
                        "Skipping delta item without lastModifiedDateTime: id=%s",
                        item.get("id", "unknown"),
                    )
                    continue
                if since:
                    modified = datetime.fromisoformat(modified_at.replace("Z", "+00:00"))
                    if modified < since:
                        continue
                items.append(item)

            url = data.get("@odata.nextLink")
            if not url:
                new_delta_link = data.get("@odata.deltaLink", "")

        if require_delta_link and not new_delta_link.strip():
            raise MissingDeltaLinkError(
                "Delta traversal completed without an @odata.deltaLink; "
                "refusing to return an empty token."
            )

        return items, new_delta_link

    def iter_new_files(self, drive_id: str, folder_id: str, since: datetime) -> list[dict]:
        """List files under a folder modified strictly after `since`, descending only into
        top-level subfolders whose own timestamp is after `since`.

        Replaces /delta for the live sync: Graph delta is only reliable on the
        drive root for OneDrive for Business, and silently missed new files in
        a subfolder. Plain children listing has no such restriction.
        """
        found: list[dict] = []
        stack = [(folder_id, True)]
        while stack:
            current, is_top = stack.pop()
            url = (
                f"{GRAPH_BASE}/drives/{drive_id}/items/{current}/children"
                f"?$top=200&$select={_DELTA_SELECT},size"
            )
            while url:
                data = self.get(url)
                for item in data.get("value", []):
                    if "folder" in item:
                        # Top-level folders are the unit of change (one per building):
                        # skip any not created/modified since the watermark, so we never
                        # walk the whole backlog. Inside a changed folder, walk fully.
                        if is_top:
                            f_mod = item.get("lastModifiedDateTime")
                            if not f_mod or datetime.fromisoformat(f_mod.replace("Z", "+00:00")) <= since:
                                continue
                        stack.append((item["id"], False))
                    elif "file" in item:
                        modified_at = item.get("lastModifiedDateTime")
                        if not modified_at:
                            continue
                        modified = datetime.fromisoformat(modified_at.replace("Z", "+00:00"))
                        if modified > since:
                            found.append(item)
                url = data.get("@odata.nextLink")
        return found

    def get_item_id_by_path(self, drive_id: str, folder_path: str) -> str:
        """Resolve a folder path (e.g. '/Document Processor/In') to its item ID.

        Only needed once, to establish the delta baseline — see
        scripts/onedrive_baseline_delta.py. The live sync never calls this:
        once a delta link exists, it fully encodes drive+item and is used
        as-is.
        """
        path = folder_path.strip("/")
        data = self.get(f"{GRAPH_BASE}/drives/{drive_id}/root:/{path}?$select=id")
        return data["id"]

    def get_download_url(self, drive_id: str, item_id: str) -> str:
        """Fetch the download URL for a specific item — delta pages on shared
        drives sometimes omit @microsoft.graph.downloadUrl."""
        data = self.get(f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}?$select=id,@microsoft.graph.downloadUrl")
        return data.get("@microsoft.graph.downloadUrl", "")

    def get_item_path(self, item: dict) -> str:
        """Build a human-readable relative path from parentReference, for logging."""
        raw_path = item.get("parentReference", {}).get("path", "")
        folder = raw_path.split("root:", 1)[1].lstrip("/") if "root:" in raw_path else ""
        name = item.get("name", "")
        return f"{folder}/{name}" if folder else name
