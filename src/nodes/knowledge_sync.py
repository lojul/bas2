"""Knowledge sync node — creates an Odoo Knowledge article for news documents.

Runs after the index node (news branch of the sync stage). Fully non-blocking:
any Odoo failure is logged and the pipeline continues — indexing is never affected.

Reuses knowledge_writer for HTML generation, duplicate detection (image hash +
headline), image upload to Odoo Documents, and knowledge.article creation.
"""

import logging

from langsmith import traceable

from src.state import DocumentState, DocumentType

logger = logging.getLogger(__name__)

_IMAGE_EXTS = ("jpg", "jpeg", "png", "gif", "webp")


@traceable(name="knowledge_sync", run_type="chain")
def knowledge_sync(state: DocumentState) -> DocumentState:
    """Create an Odoo Knowledge article from a processed news document. Non-blocking."""
    if state.document_type != DocumentType.NEWS:
        state.odoo_sync_status = "skipped"
        state.file_bytes = None
        return state

    try:
        from src.nodes.knowledge_writer import create_knowledge_article
        from src.nodes.odoo_sync import _patch_search_doc

        text = state.ocr.text if state.ocr else ""

        # Pass original file to article for upload to Odoo Documents + download link.
        # Images: use image_bytes path (enables hash-based dedup).
        # PDFs and other docs: use file_bytes path (no hash dedup, but link is added).
        image_bytes = None
        image_filename = None
        file_bytes_doc = None
        file_name_doc = None
        ext = state.file_name.rsplit(".", 1)[-1].lower() if "." in state.file_name else ""
        if state.file_bytes and ext in _IMAGE_EXTS:
            image_bytes = state.file_bytes
            image_filename = state.file_name
        elif state.file_bytes:
            file_bytes_doc = state.file_bytes
            file_name_doc = state.file_name

        result = create_knowledge_article(
            text=text,
            image_bytes=image_bytes,
            image_filename=image_filename,
            file_bytes=file_bytes_doc,
            file_name=file_name_doc,
            source=state.source,
            skip_duplicate_check=state.skip_duplicate_check,
        )

        if result.get("success"):
            state.odoo_sync_status = "synced"
            state.odoo_record_id = str(result["article_id"])
        elif result.get("duplicate"):
            state.odoo_sync_status = "duplicate"
            state.odoo_record_id = str(result.get("article_id") or "")
        else:
            state.odoo_sync_status = "error"

        _patch_search_doc(state.index_id, state.odoo_record_id, state.odoo_sync_status, None)
        logger.info(
            "Knowledge sync for '%s': %s (article %s)",
            state.file_name, state.odoo_sync_status, state.odoo_record_id or "none",
        )

    except Exception as e:
        logger.error("Knowledge sync error for '%s': %s", state.file_name, e)
        state.odoo_sync_status = "error"

    state.file_bytes = None
    return state
