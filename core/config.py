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

# LLM for the agent itself (OpenRouter). moonshotai/kimi-k2 chosen over k3/k2.6+
# (those are reasoning variants — ~50x more expensive, no benefit for
# straightforward tool-calling Q&A, and silently return empty content if
# max_tokens is too low for the hidden reasoning pass) and over Azure OpenAI
# gpt-5-mini (would need a new deployment + managed identity; OpenRouter matches
# what the old chatbot.py already used and is already proven HK-compatible).
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
AGENT_MODEL = os.environ.get("AGENT_MODEL", "moonshotai/kimi-k2")

# Optional
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

# Per-channel API keys for authenticating inbound requests to /api/v1/chat.
# Format: comma-separated "channel:key" pairs, e.g. "slack:abc123,web:def456"
CHANNEL_API_KEYS = os.environ.get("CHANNEL_API_KEYS", "")
