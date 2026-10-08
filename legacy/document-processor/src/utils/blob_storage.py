"""Azure Blob Storage utilities for image upload."""

import os
from typing import Optional
from azure.storage.blob import BlobServiceClient, ContentSettings
from langsmith import traceable


def get_blob_service_client() -> Optional[BlobServiceClient]:
    """Get Azure Blob Service client using write SAS token.

    Returns:
        BlobServiceClient or None if not configured
    """
    account = os.environ.get("AZURE_BLOB_ACCOUNT")
    write_sas = os.environ.get("AZURE_BLOB_WRITE_SAS")

    if not account or not write_sas:
        return None

    account_url = f"https://{account}.blob.core.windows.net"
    return BlobServiceClient(account_url=account_url, credential=write_sas)


@traceable(name="upload_image", run_type="tool")
def upload_image(
    image_data: bytes,
    blob_name: str,
    content_type: str = "image/png",
    container_name: Optional[str] = None
) -> Optional[str]:
    """Upload image to Azure Blob Storage.

    Args:
        image_data: Image bytes
        blob_name: Name for the blob (e.g., "doc123/page1.png")
        content_type: MIME type of the image
        container_name: Container name (defaults to AZURE_BLOB_IMAGES_CONTAINER)

    Returns:
        Public URL of uploaded image, or None if upload failed
    """
    client = get_blob_service_client()
    if not client:
        return None

    container = container_name or os.environ.get("AZURE_BLOB_IMAGES_CONTAINER", "document-images")

    try:
        # Get container client (create if not exists)
        container_client = client.get_container_client(container)
        if not container_client.exists():
            container_client.create_container(public_access="blob")

        # Upload blob
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(
            image_data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type)
        )

        # Return public URL
        return blob_client.url

    except Exception as e:
        print(f"Failed to upload image {blob_name}: {e}")
        return None


@traceable(name="upload_images_batch", run_type="tool")
def upload_images_batch(
    images: list[tuple[bytes, str]],
    doc_id: str,
    container_name: Optional[str] = None
) -> list[str]:
    """Upload multiple images for a document.

    Args:
        images: List of (image_data, extension) tuples
        doc_id: Document ID for folder structure
        container_name: Container name (defaults to AZURE_BLOB_IMAGES_CONTAINER)

    Returns:
        List of public URLs for uploaded images
    """
    urls = []
    for idx, (image_data, ext) in enumerate(images):
        blob_name = f"{doc_id}/{idx}.{ext}"
        content_type = f"image/{ext}" if ext in ("png", "jpeg", "jpg", "gif") else "application/octet-stream"

        url = upload_image(
            image_data=image_data,
            blob_name=blob_name,
            content_type=content_type,
            container_name=container_name
        )

        if url:
            urls.append(url)

    return urls
