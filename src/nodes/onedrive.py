"""Microsoft Graph API / OneDrive integration node."""

import httpx
from msal import ConfidentialClientApplication
from langsmith import traceable

from src.config import get_config
from src.state import DocumentState, ProcessingStatus


def get_access_token() -> str:
    """Get access token for Microsoft Graph API."""
    config = get_config()

    app = ConfidentialClientApplication(
        client_id=config.msgraph.client_id,
        client_credential=config.msgraph.client_secret,
        authority=config.msgraph.authority,
    )

    result = app.acquire_token_for_client(scopes=config.msgraph.scope)

    if "access_token" not in result:
        raise Exception(f"Failed to get access token: {result.get('error_description', 'Unknown error')}")

    return result["access_token"]


@traceable(name="list_onedrive_files")
def list_onedrive_files(
    drive_id: str,
    folder_path: str = "/",
    file_extensions: list[str] | None = None,
    recursive: bool = True,
) -> list[dict]:
    """List files in a OneDrive/SharePoint folder.

    Args:
        drive_id: The drive ID (from SharePoint site or user's OneDrive)
        folder_path: Path to folder (e.g., "/Documents/Inbox")
        file_extensions: Filter by extensions (e.g., [".pdf", ".jpg"])
        recursive: If True, scan subfolders recursively

    Returns:
        List of file metadata dicts
    """
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    return _list_files_recursive(
        drive_id=drive_id,
        folder_path=folder_path,
        file_extensions=file_extensions,
        recursive=recursive,
        headers=headers,
    )


def _list_files_recursive(
    drive_id: str,
    folder_path: str,
    file_extensions: list[str] | None,
    recursive: bool,
    headers: dict,
) -> list[dict]:
    """Internal recursive file listing function.

    Args:
        drive_id: The drive ID
        folder_path: Path to folder
        file_extensions: Filter by extensions
        recursive: If True, scan subfolders
        headers: Auth headers to reuse

    Returns:
        List of file metadata dicts
    """
    # Build URL for folder contents
    if folder_path == "/":
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"
    else:
        # Remove leading slash and encode path
        path = folder_path.lstrip("/")
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{path}:/children"

    with httpx.Client() as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

    files = []
    subfolders = []

    for item in data.get("value", []):
        name = item.get("name", "")

        # Collect subfolders for recursive scan
        if "folder" in item:
            if recursive:
                subfolder_path = f"{folder_path.rstrip('/')}/{name}"
                subfolders.append(subfolder_path)
            continue

        # Filter by extension if specified
        if file_extensions:
            if not any(name.lower().endswith(ext.lower()) for ext in file_extensions):
                continue

        files.append({
            "id": item["id"],
            "name": name,
            "size": item.get("size", 0),
            "created": item.get("createdDateTime"),
            "modified": item.get("lastModifiedDateTime"),
            "web_url": item.get("webUrl"),
            "download_url": item.get("@microsoft.graph.downloadUrl"),
            "folder_path": folder_path,  # Track which folder the file came from
        })

    # Recursively scan subfolders
    for subfolder in subfolders:
        files.extend(_list_files_recursive(
            drive_id=drive_id,
            folder_path=subfolder,
            file_extensions=file_extensions,
            recursive=recursive,
            headers=headers,
        ))

    return files


@traceable(name="create_share_link")
def create_share_link(drive_id: str, item_id: str) -> str:
    """Create a sharing link for a file that Document Intelligence can access.

    Args:
        drive_id: The drive ID
        item_id: The file's item ID

    Returns:
        Share URL that can be used for OCR
    """
    token = get_access_token()

    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/createLink"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "type": "view",
        "scope": "anonymous",  # Anyone with link can view
    }

    with httpx.Client() as client:
        response = client.post(url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()

    # Get the web URL from the share link
    share_url = data.get("link", {}).get("webUrl", "")

    # Convert share URL to direct download URL for Document Intelligence
    # SharePoint share links need to be converted to download format
    if share_url:
        # Add download parameter to get direct file access
        if "?" in share_url:
            share_url += "&download=1"
        else:
            share_url += "?download=1"

    return share_url


def get_download_url(drive_id: str, item_id: str) -> str:
    """Get a temporary download URL for a file.

    This URL is pre-authenticated and can be used directly by Document Intelligence.

    Args:
        drive_id: The drive ID
        item_id: The file's item ID

    Returns:
        Direct download URL (pre-authenticated, temporary)
    """
    token = get_access_token()

    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}"
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client() as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

    # The @microsoft.graph.downloadUrl is a pre-authenticated URL
    download_url = data.get("@microsoft.graph.downloadUrl", "")

    return download_url


@traceable(name="move_to_processed")
def move_to_processed(
    drive_id: str,
    item_id: str,
    processed_folder_id: str,
) -> dict:
    """Move a file to the processed folder.

    Args:
        drive_id: The drive ID
        item_id: The file's item ID
        processed_folder_id: The ID of the "Processed" folder

    Returns:
        Updated file metadata
    """
    token = get_access_token()

    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "parentReference": {
            "id": processed_folder_id,
        },
        # Replace existing file with same name instead of failing
        "@microsoft.graph.conflictBehavior": "replace"
    }

    with httpx.Client() as client:
        response = client.patch(url, headers=headers, json=body)
        response.raise_for_status()
        return response.json()


@traceable(name="get_file_from_onedrive")
def get_file_from_onedrive(state: DocumentState, drive_id: str) -> DocumentState:
    """Get a file from OneDrive and prepare it for OCR.

    This node:
    1. Gets the download URL for the file
    2. Updates state with the URL for Document Intelligence

    Args:
        state: Document state with file_path containing the item ID
        drive_id: The OneDrive drive ID

    Returns:
        Updated state with blob_url (actually OneDrive download URL)
    """
    state.update_status(ProcessingStatus.DOWNLOADING)

    try:
        # file_path contains the item ID in this context
        item_id = state.file_path

        # Get pre-authenticated download URL
        download_url = get_download_url(drive_id, item_id)

        if not download_url:
            return state.set_error(f"Could not get download URL for item: {item_id}")

        # Store in blob_url field (reusing existing field)
        state.blob_url = download_url
        state.update_status(ProcessingStatus.UPLOADED)

        return state

    except Exception as e:
        return state.set_error(f"OneDrive error: {str(e)}")


@traceable(name="list_sites")
def list_sites() -> list[dict]:
    """List SharePoint sites accessible to the app.

    Returns:
        List of site metadata
    """
    token = get_access_token()

    url = "https://graph.microsoft.com/v1.0/sites?search=*"
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client() as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

    sites = []
    for site in data.get("value", []):
        sites.append({
            "id": site["id"],
            "name": site.get("displayName", site.get("name", "")),
            "web_url": site.get("webUrl"),
        })

    return sites


@traceable(name="list_drives")
def list_drives(site_id: str) -> list[dict]:
    """List drives in a SharePoint site.

    Args:
        site_id: The SharePoint site ID

    Returns:
        List of drive metadata
    """
    token = get_access_token()

    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client() as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

    drives = []
    for drive in data.get("value", []):
        drives.append({
            "id": drive["id"],
            "name": drive.get("name", ""),
            "web_url": drive.get("webUrl"),
        })

    return drives


@traceable(name="upload_to_onedrive")
def upload_to_onedrive(
    drive_id: str,
    folder_path: str,
    file_name: str,
    file_content: bytes,
) -> dict:
    """Upload a file to OneDrive folder.

    Uses simple upload for files < 4MB. For larger files, use resumable upload.

    Args:
        drive_id: The drive ID
        folder_path: Path to folder (e.g., "/Document Processor/In")
        file_name: Name for the uploaded file
        file_content: File content as bytes

    Returns:
        Uploaded file metadata including id, name, webUrl
    """
    token = get_access_token()

    # Build URL: PUT /drives/{drive-id}/root:/{folder-path}/{filename}:/content
    # Remove leading slash from folder_path for URL construction
    path = folder_path.strip("/")
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{path}/{file_name}:/content"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
    }

    with httpx.Client(timeout=60) as client:
        response = client.put(url, headers=headers, content=file_content)
        response.raise_for_status()
        data = response.json()

    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "size": data.get("size"),
        "web_url": data.get("webUrl"),
        "created": data.get("createdDateTime"),
    }
