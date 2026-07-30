"""Environment-driven configuration only — no business logic here."""

import os

# Odoo (own XML-RPC connection, independent of document-processor / odoo-bas-sync)
ODOO_URL = os.environ.get("ODOO_URL", "https://c21net.odoo.com")
ODOO_DB = os.environ.get("ODOO_DB", "c21net")
ODOO_USERNAME = os.environ.get("ODOO_USERNAME", "admin@c21net.com")
ODOO_API_KEY = os.environ.get("ODOO_API_KEY")

# BAS's properties-index (read-only access — Search Index Data Reader role)
BAS_SEARCH_ENDPOINT = os.environ.get(
    "BAS_SEARCH_ENDPOINT", "https://c21net-bas-srch-ea-prod.search.windows.net"
)
BAS_SEARCH_INDEX = os.environ.get("BAS_SEARCH_INDEX", "properties-index")
BAS_OPENAI_ENDPOINT = os.environ.get(
    "BAS_OPENAI_ENDPOINT", "https://c21net-bas-oai-fc-ea-prod.openai.azure.com"
)
BAS_EMBEDDING_DEPLOYMENT = os.environ.get("BAS_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")

# LLM for the agent itself (OpenRouter, same provider as the rest of the org's stack)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
AGENT_MODEL = os.environ.get("AGENT_MODEL", "qwen/qwen-2.5-72b-instruct")

# Optional
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

# Per-channel API keys for authenticating inbound requests to /api/v1/chat.
# Format: comma-separated "channel:key" pairs, e.g. "slack:abc123,web:def456"
CHANNEL_API_KEYS = os.environ.get("CHANNEL_API_KEYS", "")
