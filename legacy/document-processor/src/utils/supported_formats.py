"""Single source of truth for ingest-supported file extensions.

Lives under src/ (not api/) because the Function App's .funcignore excludes
the entire api/ package — anything the Function App needs at runtime
(onedrive_sync included) must not import from api.*.
"""

SUPPORTED_FORMATS = {"pdf", "jpg", "jpeg", "png", "docx", "pptx"}
