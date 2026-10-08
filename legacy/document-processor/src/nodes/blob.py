"""Azure Blob Storage upload node."""

import os
from datetime import datetime, timedelta
from urllib.parse import quote

from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from langsmith import traceable

from src.config import get_config
from src.state import DocumentState, ProcessingStatus


@traceable(name="upload_to_blob")
def upload_to_blob(state: DocumentState) -> DocumentState:
    """Upload a file to Azure Blob Storage.

    Args:
        state: Document state with file_path to upload

    Returns:
        Updated state with blob_url
    """
    state.update_status(ProcessingStatus.DOWNLOADING)

    config = get_config()

    # Check if file exists
    if not os.path.exists(state.file_path):
        return state.set_error(f"File not found: {state.file_path}")

    # Create blob client
    blob_service = BlobServiceClient(
        account_url=config.blob.account_url,
        credential=config.blob.read_sas,
    )

    container_client = blob_service.get_container_client(config.blob.container)

    # Generate unique blob name with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    blob_name = f"{timestamp}_{state.file_name}"

    # Upload file
    blob_client = container_client.get_blob_client(blob_name)

    with open(state.file_path, "rb") as f:
        blob_client.upload_blob(f, overwrite=True)

    # Generate blob URL with SAS token for reading
    blob_url = f"{config.blob.account_url}/{config.blob.container}/{quote(blob_name)}?{config.blob.read_sas}"

    state.blob_url = blob_url
    state.update_status(ProcessingStatus.UPLOADED)

    return state


@traceable(name="upload_bytes_to_blob")
def upload_bytes_to_blob(
    file_bytes: bytes,
    file_name: str,
    content_type: str = "application/pdf",
) -> str:
    """Upload bytes directly to Azure Blob Storage.

    Args:
        file_bytes: File content as bytes
        file_name: Name for the blob
        content_type: MIME type of the file

    Returns:
        Blob URL with SAS token
    """
    config = get_config()

    blob_service = BlobServiceClient(
        account_url=config.blob.account_url,
        credential=config.blob.read_sas,
    )

    container_client = blob_service.get_container_client(config.blob.container)

    # Generate unique blob name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    blob_name = f"{timestamp}_{file_name}"

    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(
        file_bytes,
        overwrite=True,
        content_settings={"content_type": content_type},
    )

    blob_url = f"{config.blob.account_url}/{config.blob.container}/{quote(blob_name)}?{config.blob.read_sas}"

    return blob_url
