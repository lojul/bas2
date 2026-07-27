"""AI Assistant — LangGraph ReAct agent for content ingest.

Handles Knowledge articles, Property Listings, and CRM leads (future).
Channel-agnostic: same agent serves dashboard and WhatsApp.
"""

import contextvars
import os
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langsmith import traceable

from src.utils.file_cache import cache_file, clear_cached_file, get_cached_file
from src.utils.job_queue import enqueue_pipeline_job, format_completion as _format_completion
from src.utils.session_storage import clear_session, get_session, save_session

# File bytes passed via context var so tools can access without going through tool args
_pending_file: contextvars.ContextVar[tuple[str, bytes] | None] = contextvars.ContextVar(
    "pending_file", default=None
)
_pending_media_url: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "pending_media_url", default=None
)
_pending_user_key: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "pending_user_key", default=None
)
# Set to True by _dispatch_pipeline_async so handle_message can return a
# processing ack instead of an error when the LLM final-response call fails.
_pipeline_dispatched: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "pipeline_dispatched", default=False
)

# Pending files are cached via src.utils.file_cache (blob-backed) so follow-up
# messages ("yes"/"3" after a prompt) survive process restarts and scale-out.

_SYSTEM_PROMPT_BASE = """{language_rule}

You are the C21 Property Intelligence Assistant — an AI helper for the Century 21 Hong Kong real estate team.

On first contact (no prior messages), greet the user and show this menu:
  1 · Knowledge — Save market news, research, or transaction records as Knowledge articles in Odoo
  2 · CRM — Create a CRM lead for a client inquiry
  3 · Property Listing — Process a property listing PDF (OCR, extract, index to search, sync to Odoo)
  4 · Property Search — Ask about available properties, rents, districts
  5 · Market News — Latest Hong Kong property market trends, forecasts, and news
  6 · Contacts — Scan a name card to save to Odoo, or look up a saved contact

Users can type 1/2/3/4/5/6 OR describe what they need in natural language — both work.

Tool selection — choose based on the user's INTENT, not keywords:

search_properties: the user wants information about a specific property, building, district,
  rent, or available listings. This is the default tool for any property-related question.
  Use it FIRST before anything else when the user asks about specific buildings or availability.

search_market_news: the user asks about market conditions, rental trends, forecasts, economic
  outlook, or recent news — anything requiring up-to-date information beyond our listings.
  Examples: "2025年租金走勢", "office market outlook", "市場最新消息", "latest news".
  Use this INSTEAD OF search_properties when the question is about the market, not a specific property.
  You can also call it AFTER search_properties to add market context to a property answer.

search_contacts: the user wants to look up a person, agent, or company from saved name cards.
  Use when the user asks for someone's phone, email, or company — or types a person or company name.
  Examples: "陳大文的電話", "find ABC Properties contact", "search for John Smith", "誰係觀塘代理".
  Returns saved contact details (name, company, phone, mobile, email).

query_odoo_listings: ONLY when the user explicitly wants to check what records exist in
  Odoo or the CRM system itself. The user must mention Odoo, CRM, or 放盤管理 by name.

create_crm_lead: ONLY when the user explicitly asks to log, record, or create a client
  inquiry. This is a deliberate action — do not suggest or trigger it unless asked.

create_knowledge_article / process_property_listing: only when the user sends content
  to be saved or processed (text, image, PDF).

Handling incomplete search results:
- IMPORTANT: when the user asks about a specific building, the system AUTOMATICALLY logs
  their inquiry to CRM in the background. You do NOT need to mention CRM logging or ask
  permission — it's already done silently. Do not offer "log your interest" as an option.
- Results include a content_preview field. If structured fields (rent, size, address) are
  missing, USE content_preview to give the user a meaningful summary of what the document
  says. Never say "no data" when content_preview has text — summarise it instead.
- NEVER mention PDF filenames or file names to the user — they mean nothing to them.
- If search_properties returns 0 results, or content_preview is also empty, say so honestly.
- When details are incomplete, tell the user WHAT is known (from content_preview) and offer these next steps:
  1) find_similar_properties — search alternatives in the same district (size/rent optional)
  2) contact_staff — a Century 21 representative will be notified and reach out to them

Contact staff behavior:
- When you call contact_staff, the tool sends the staff member a WhatsApp notification
  with the user's number and inquiry summary. Tell the user their inquiry has been
  forwarded and staff will contact them — do not just give the number and stop.

Manual CRM lead — only when the user is logging a DIFFERENT client's inquiry (not their
own), use create_crm_lead and collect the client's name/phone. Not for self-inquiries.

Follow-up actions — when the user replies "yes", "sure", "contact staff", "connect me",
"talk to someone", "有冇同事", "聯繫", or similar, ACT on the last offer you made:
- Last offer was staff contact → call contact_staff immediately with the reason
- Last offer was CRM lead → start collecting client details for create_crm_lead
- Last offer was similar properties → call find_similar_properties
Never just re-ask the same question. Take the action.

Attachments — pick the right tool by content, do NOT ask for confirmation first:
- News screenshots, market reports, transaction records → create_knowledge_article
- Property listing ads/flyers (for rent/sale, 招租, 放售, 盤源) → process_property_listing
- Name cards / business cards (名片) → process_property_listing (pipeline auto-classifies as contact,
  saves to Odoo Contacts, and notifies the user with extracted name/company/phone/email)
- Unclear which → process_property_listing (the pipeline classifier will decide the type)
All run the full pipeline in the background and notify the user on WhatsApp when complete.
If the user pastes news/market text with no attachment and wants it saved, call create_knowledge_article with that text.
If the user confirms (yes/是/確認) after a duplicate warning, call create_knowledge_article again with force=true.
PDF attachments with no text: ask whether it is a Knowledge article or a Property Listing before proceeding.
CRM — when the user selects option 2 or asks to log a client inquiry, collect: client name (required), phone, email, preferred district, property type, and any notes. Then call create_crm_lead. Ask for missing details one at a time.

Rules:
- Be concise and conversational — this is a chat interface
- Ask one clarifying question at a time if something is unclear
- Always confirm before taking irreversible actions (creating articles, processing listings)
- For duplicates, show what already exists and ask whether to proceed
- Never fabricate information — only report what tools actually return
- When a task completes, show the result URL so the user can verify
- If the user says "reset" or "重新開始" or "start over", clear the conversation and show the menu again
- IMPORTANT: Never use Markdown formatting. No bold (**text**), no italics, no headers (#), no Markdown links [text](url). Output plain text and bare URLs only."""

_LANGUAGE_RULES = {
    "whatsapp": "CRITICAL: Always reply in the same language the user writes in. If they write English, your reply MUST be in English. If they write Traditional Chinese (繁體中文), reply in Chinese. This applies to ALL your output including when presenting tool results — never paste tool output verbatim, always reformulate it in the user's language. Professional tone — clear and concise.",
    "dashboard": "CRITICAL: Always reply in the same language the user writes in. If they write English, your reply MUST be in English. If they write Traditional Chinese (繁體中文), reply in Chinese. This applies to ALL your output including when presenting tool results — never paste tool output verbatim, always reformulate it in the user's language. Professional tone — clear and concise.",
}

GREETING = """您好，我是 C21 智能助理。請選擇所需服務：

1 · 知識文章 — 儲存市場資訊、研究報告或成交記錄至 Odoo
2 · CRM — 建立客戶查詢
3 · 物業盤源 — 處理物業資料 PDF（OCR、提取、索引及同步至 Odoo）
4 · 物業查詢 — 搜尋物業、租金、地區資料
5 · 市場資訊 — 最新香港物業市場趨勢及新聞
6 · 聯絡人 — 掃描名片儲存至 Odoo，或搜尋已儲存的聯絡人

請輸入 1–6，或直接描述您的需要（例如「觀塘有咩盤?」）。如有附件，系統將自動建議最合適的處理方式。"""


def _detect_language(text: str) -> str | None:
    """Detect language from a single message. Returns 'en', 'zh', or None
    (None = no alphabetic content, e.g. "2", "yes"/"是" too short, emoji-only).
    Caller should fall back to conversation history on None."""
    if not text:
        return None
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
    if cjk == 0 and ascii_letters == 0:
        return None  # digits/emoji/symbols only — inherit from history
    # Short all-ASCII messages are often menu picks or option labels ("Forward",
    # "Save", "Yes", "3") typed by users whose primary language is Chinese.
    # Don't treat them as English — inherit from session history instead.
    if cjk == 0 and len(text.strip()) < 20:
        return None
    return "en" if ascii_letters > cjk else "zh"


def _resolve_language(current_message: str, session_messages: list) -> str:
    """Detect the current language, falling back to the most recent user message
    in session history that had actual alphabetic content. Default 'zh' if nothing found."""
    lang = _detect_language(current_message)
    if lang:
        return lang
    # Walk back through history for a message with clear language
    for msg in reversed(session_messages or []):
        if msg.get("role") == "user":
            lang = _detect_language(msg.get("content", ""))
            if lang:
                return lang
    return "zh"  # default


def _build_system_prompt(channel: str, user_message: str = "", session_messages: list | None = None) -> str:
    rule = _LANGUAGE_RULES.get(channel, _LANGUAGE_RULES["dashboard"])
    # Hard language override — detect from the CURRENT message. For short numeric/emoji
    # replies ("2", "yes"), inherit from the most recent alphabetic user message in history.
    lang = _resolve_language(user_message, session_messages or [])
    if lang == "en":
        override = (
            "MANDATORY LANGUAGE OVERRIDE: The user's current message is in English. "
            "You MUST reply in English only. Ignore the language of any previous messages in this conversation."
        )
    else:
        override = (
            "MANDATORY LANGUAGE OVERRIDE: The user's current message is in Chinese. "
            "You MUST reply in Traditional Chinese (繁體中文) only."
        )
    return override + "\n\n" + _SYSTEM_PROMPT_BASE.format(language_rule=rule)


def _build_llm():
    """Prefer Azure OpenAI (gpt-5-mini / gpt-5.4 in Sweden Central) — much stronger
    tool routing and multilingual than Llama 3.3. Falls back to OpenRouter Llama.

    GPT-5 series are reasoning models: they only accept temperature=1 (default) and
    use max_completion_tokens instead of max_tokens. We detect from the deployment
    name and adjust accordingly.
    """
    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    azure_key = os.environ.get("AZURE_OPENAI_KEY", "")
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-5-mini")

    if azure_endpoint and azure_key:
        # GPT-5 / o1 / o3 style reasoning models: minimal params
        is_reasoning_model = deployment.startswith(("gpt-5", "o1", "o3"))
        kwargs = {
            "azure_endpoint": azure_endpoint,
            "api_key": azure_key,
            "api_version": "2025-04-01-preview",
            "azure_deployment": deployment,
        }
        if is_reasoning_model:
            # Do NOT set temperature (must be default 1). Use max_completion_tokens.
            kwargs["model_kwargs"] = {"max_completion_tokens": 1500}
        else:
            kwargs["temperature"] = 0.3
            kwargs["max_tokens"] = 1200
        return AzureChatOpenAI(**kwargs)

    # Fallback: OpenRouter Llama
    return ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        model="meta-llama/llama-3.3-70b-instruct",
        temperature=0.3,
        max_tokens=1000,
    )


# ── Tools ─────────────────────────────────────────────────────────────────────

_NEWS_DUP_MARKER = "⚠️ 此內容似乎已建立過文章"

_PROCESSING_REPLY = (
    "✅ 已收到，正在後台處理（OCR → 分類 → 提取 → 索引 → 同步 Odoo），通常需要 1-3 分鐘。\n\n"
    "完成後會透過 WhatsApp 通知您處理結果及分類。您現在可以繼續傳送其他內容。"
)

def _dispatch_pipeline_async(
    file_bytes: bytes | None,
    file_name: str | None,
    text: str = "",
    forced_type=None,
    skip_duplicate_check: bool = False,
    notify_user: str | None = None,
    notify_channel: str = "",
) -> None:
    """Dispatch the full pipeline; notify the user on WhatsApp when done.

    Prefers the durable Storage Queue (consumed by the Function App — survives
    App Service restarts, gets retries). Falls back to a daemon thread when the
    queue is not configured.
    """
    import threading

    _pipeline_dispatched.set(True)

    sender_number = notify_user if notify_channel == "whatsapp" else ""

    if enqueue_pipeline_job(
        file_bytes, file_name, text,
        forced_type=forced_type,
        skip_duplicate_check=skip_duplicate_check,
        notify_user=notify_user,
        notify_channel=notify_channel,
        sender_number=sender_number,
    ):
        return

    def _run():
        try:
            from src.graph import process_file_from_bytes
            from src.state import OCRResult

            if file_bytes and file_name:
                pre_ocr = OCRResult(text=text) if text and len(text.strip()) >= 60 else None
                final = process_file_from_bytes(
                    file_bytes, file_name, "assistant",
                    precomputed_ocr=pre_ocr,
                    forced_type=forced_type,
                    skip_duplicate_check=skip_duplicate_check,
                    whatsapp_number=sender_number,
                )
            else:
                from datetime import datetime, timezone
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                final = process_file_from_bytes(
                    text.encode("utf-8"), f"whatsapp-news-{stamp}.txt", "assistant",
                    precomputed_ocr=OCRResult(text=text),
                    forced_type=forced_type,
                    skip_duplicate_check=skip_duplicate_check,
                    whatsapp_number=sender_number,
                )
            message = _format_completion(final)
        except Exception as e:
            message = f"❌ 處理失敗：{file_name or '文字內容'}\n原因：{str(e)[:120]}"

        if notify_user and notify_channel == "whatsapp":
            from src.utils.whatsapp_notify import send_whatsapp
            send_whatsapp(notify_user, message)

    threading.Thread(target=_run, daemon=True).start()


def _check_news_duplicate(image_bytes: bytes | None) -> str | None:
    """Fast image-hash duplicate check against Odoo. Returns warning message or None."""
    if not image_bytes:
        return None
    import hashlib
    from src.nodes.knowledge_writer import ODOO_URL, check_duplicate

    image_hash = hashlib.md5(image_bytes).hexdigest()
    existing = check_duplicate("", image_hash=image_hash)
    if existing:
        return (
            f"{_NEWS_DUP_MARKER}：\n{existing['name']}\n"
            f"{ODOO_URL}/knowledge/article/{existing['id']}\n\n"
            "回覆 yes 繼續處理，或 no 取消。"
        )
    return None


def _cached_file_from_context() -> tuple[str, bytes] | None:
    """Look up the user's pending file (blob-backed cache) from the request context."""
    user_id, channel = _notify_target()
    if user_id:
        return get_cached_file(user_id, channel)
    return None


def _notify_target() -> tuple[str | None, str]:
    """Resolve (user_id, channel) for completion notifications from the request context."""
    cache_key = _pending_user_key.get()
    if cache_key and ":" in cache_key:
        user_id, channel = cache_key.rsplit(":", 1)
        return user_id, channel
    return None, ""


@tool
def create_knowledge_article(text: str, force: bool = False) -> str:
    """Create a Knowledge article in Odoo from the provided text or attached image.
    Runs the full pipeline in the background: OCR, article generation, Odoo Knowledge
    creation, and indexing to the search database. Notifies the user when complete.
    Set force=True ONLY when the user confirms to proceed after a duplicate warning.
    """
    file_data = _pending_file.get()
    # Fall back to cached file from a previous message (e.g. user replies "yes" to a
    # duplicate warning without re-attaching the image).
    if not file_data:
        file_data = _cached_file_from_context()

    fname, fbytes = file_data if file_data else (None, None)

    if not fbytes and not text.strip():
        return "請附上圖片或提供文字內容。"

    if not force:
        warning = _check_news_duplicate(fbytes)
        if warning:
            return warning

    from src.state import DocumentType
    notify_user, notify_channel = _notify_target()
    _dispatch_pipeline_async(
        fbytes, fname, text,
        forced_type=DocumentType.NEWS,  # user explicitly chose Knowledge
        skip_duplicate_check=force,
        notify_user=notify_user, notify_channel=notify_channel,
    )
    return _PROCESSING_REPLY


@tool
def process_property_listing(notes: str = "") -> str:
    """Process the attached property listing file through the full pipeline.
    Runs OCR, classification, extraction, indexes to Azure AI Search, and syncs to Odoo.
    Requires a file to be attached — PDF, image, DOCX, or PPTX.
    The notes parameter is optional context the user provided about the file.
    """
    file_data = _pending_file.get()
    if not file_data:
        file_data = _cached_file_from_context()
    if not file_data:
        return "No file attached. Please send a property listing PDF or image first."

    filename, file_bytes = file_data

    # Run pipeline in background — the full OCR + extract + index flow takes
    # 1-3 minutes, which exceeds the Azure SWA proxy timeout (70s). Return
    # immediately; the user is notified on WhatsApp when processing completes.
    notify_user, notify_channel = _notify_target()
    _dispatch_pipeline_async(
        file_bytes, filename,
        notify_user=notify_user, notify_channel=notify_channel,
    )
    return _PROCESSING_REPLY


@tool
def check_listing_duplicate(filename: str) -> str:
    """Check if a property listing with this filename already exists in Azure AI Search."""
    import hashlib
    import os
    import httpx

    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT", "")
    index = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY", "")
    if not all([endpoint, api_key]):
        return "Search service not configured — cannot check for duplicates."

    doc_id = hashlib.md5(filename.encode()).hexdigest()
    url = f"{endpoint}/indexes/{index}/docs/{doc_id}?api-version=2024-07-01&$select=file_name,processed_at"
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, headers={"api-key": api_key})
        if resp.status_code == 404:
            return f"No existing record found for '{filename}' — safe to process."
        if resp.status_code == 200:
            doc = resp.json()
            return (
                f"⚠️ '{filename}' was already processed on {doc.get('processed_at', 'unknown date')}.\n"
                "Reply *yes* to reprocess, or *no* to skip."
            )
        return "Could not check for duplicates — proceeding."
    except Exception:
        return "Could not check for duplicates — proceeding."


@tool
def search_properties(query: str) -> str:
    """Search the property document database (vector DB) for listings, buildings,
    or market documents matching the user's question.
    Use this when the user asks about available properties, rents, districts,
    or anything like "觀塘有咩盤" / "any office in Central".
    Returns structured JSON data — you must format this into a natural reply for the user.
    """
    import json as _json
    try:
        from src.nodes.chatbot import search_documents
        docs = search_documents(query, top_k=8, hybrid=True)
    except Exception as e:
        return _json.dumps({"error": str(e)[:80]})

    if not docs:
        return _json.dumps({"count": 0, "results": []})

    # Semantic reranker scores 0-4. Filter to meaningful matches (>=1.0).
    # If no results pass threshold (semantic unavailable), take top 3 by score.
    reranked = [d for d in docs if d.get("reranker_score", 0) >= 1.0]
    docs = reranked if reranked else docs[:3]

    # For short queries (likely a specific building name), further filter to only
    # results where the query term appears in the building name or file name.
    query_lower = query.lower().strip()
    is_specific = len(query_lower.split()) <= 4 and "?" not in query_lower and "有" not in query_lower
    matched_specific = False
    if is_specific:
        keyword_matched = [
            d for d in docs
            if query_lower in ((d.get("extracted_data") or {}).get("building_name") or "").lower()
            or query_lower in ((d.get("extracted_data") or {}).get("project_name") or "").lower()
            or query_lower in (d.get("file_name") or "").lower()
        ]
        if keyword_matched:
            docs = keyword_matched
            matched_specific = True

    docs = docs[:3]

    # Auto-log CRM inquiry when user asks about a SPECIFIC building via WhatsApp.
    # Silent — no ask, no permission. Broad district browsing does NOT auto-log.
    if matched_specific and docs:
        _auto_log_inquiry(query, docs[0])

    results = []
    for doc in docs:
        ex = doc.get("extracted_data") or {}
        units = ex.get("units") or []
        doc_type = doc.get("document_type", "")

        # Avoid surfacing raw filenames as building names — they're meaningless to users.
        _raw_name = ex.get("building_name") or ex.get("project_name") or ex.get("title") or ""
        _file_name = doc.get("file_name", "")
        _is_plain_filename = not _raw_name and bool(_file_name) and (
            _file_name.rsplit(".", 1)[-1].lower() in ("pdf", "jpg", "jpeg", "png", "docx", "pptx")
            if "." in _file_name else False
        )
        building_name = _raw_name if _raw_name else (None if _is_plain_filename else _file_name)

        # Include a content preview so the LLM can describe documents that have no
        # structured extracted_data (e.g. raw PDFs, news articles without field extraction).
        content_raw = doc.get("content") or ""
        content_preview = content_raw[:400].strip() if content_raw else None

        results.append({
            "building_name": building_name,
            "document_type": doc_type,
            "district": ex.get("district"),
            "address": ex.get("address"),
            "size_sqft": ex.get("size_sqft"),
            "rent_monthly": ex.get("rent_monthly"),
            "sell_price": ex.get("sell_price"),
            "floor_unit": ex.get("floor_unit"),
            "contact_name": ex.get("contact_name"),
            "contact_phone": ex.get("contact_phone"),
            # News / article fields
            "title": ex.get("title"),
            "date": ex.get("date"),
            "source": ex.get("source"),
            "summary": ex.get("summary"),
            "units": [
                {k: u.get(k) for k in ("building_name", "floor", "unit", "size", "rent", "price") if u.get(k)}
                for u in units[:5]
            ] if units else [],
            "content_preview": content_preview,
        })

    return _json.dumps({"count": len(results), "results": results}, ensure_ascii=False)


@tool
def search_market_news(query: str) -> str:
    """Search the web for Hong Kong property market news, trends, forecasts, or any
    real-time market information the user is asking about.
    Use this when the user asks about market conditions, rental trends, economic outlook,
    recent news, or anything that requires up-to-date information beyond our document database.
    Examples: "2025年租金走勢", "office market outlook", "市場最新消息".
    Returns a list of web results — summarise them naturally for the user.
    """
    import json as _json
    try:
        from src.nodes.chatbot import web_search
        results = web_search(query, max_results=4)
    except Exception as e:
        return _json.dumps({"error": str(e)[:80]})

    if not results:
        return _json.dumps({"count": 0, "results": []})

    return _json.dumps({
        "count": len(results),
        "results": [
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "content": r.get("content"),
            }
            for r in results
        ],
    }, ensure_ascii=False)


@tool
def query_odoo_listings(keyword: str = "", district: str = "") -> str:
    """Query active property listings in the Odoo 放盤管理 database (x_c21_listing).
    Use this when the user asks what listings are currently in Odoo / the CRM,
    or wants listings filtered by building name or district.
    keyword: building name or address text to match (optional).
    district: Hong Kong district in Chinese, e.g. 觀塘, 中環 (optional).
    Returns a plain-text list of matching records.
    """
    import xmlrpc.client
    from src.nodes.odoo_sync import ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_MODEL, _map_district
    from src.nodes.knowledge_writer import _TimeoutTransport

    api_key = os.environ.get("ODOO_API_KEY", "")
    if not api_key:
        return "Odoo 連線未設定（ODOO_API_KEY 缺失）。"

    try:
        _tx = _TimeoutTransport(10)
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", transport=_tx)
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, api_key, {})
        if not uid:
            return "Odoo 登入失敗。"
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", transport=_tx)

        # When a keyword is given, search all statuses (not just active) so records
        # like GARDENEAST (rent=0, possibly non-active) are still found.
        domain: list = [] if keyword.strip() else [["x_c21_status", "=", "active"]]
        if keyword.strip():
            # Correct Odoo prefix notation: | applies to exactly the next two conditions
            domain += ["|", ["x_name", "ilike", keyword.strip()], ["x_c21_address", "ilike", keyword.strip()]]
        district_key = _map_district(district) if district.strip() else None
        if district_key:
            domain.append(["x_c21_district", "=", district_key])

        records = models.execute_kw(
            ODOO_DB, uid, api_key, ODOO_MODEL, "search_read",
            [domain],
            {
                "fields": [
                    "x_name", "x_c21_address", "x_c21_district", "x_c21_floor_unit",
                    "x_c21_property_type", "x_c21_size_sqft", "x_c21_rent_net",
                    "x_c21_contact_name", "x_c21_contact_phone",
                ],
                "limit": 5,
                "order": "id desc",
            },
        )
    except Exception as e:
        return f"Odoo 查詢失敗：{str(e)[:80]}"

    if not records:
        return "Odoo 放盤管理中找不到符合條件的盤源。"

    lines = []
    for r in records:
        parts = [r.get("x_name") or ""]
        if r.get("x_c21_address"):
            parts.append(f"地址: {r['x_c21_address']}")
        if r.get("x_c21_size_sqft"):
            parts.append(f"面積: {r['x_c21_size_sqft']:,.0f}呎")
        if r.get("x_c21_rent_net"):
            parts.append(f"月租: ${r['x_c21_rent_net']:,.0f}")
        contact = " ".join(str(x) for x in (r.get("x_c21_contact_name"), r.get("x_c21_contact_phone")) if x)
        if contact:
            parts.append(f"聯絡: {contact}")
        lines.append(" | ".join(parts))

    return f"Odoo 放盤管理中找到 {len(records)} 個盤源：\n\n" + "\n".join(lines)


@tool
def create_crm_lead(
    contact_name: str,
    phone: str = "",
    email: str = "",
    inquiry: str = "",
    district: str = "",
    property_type: str = "",
) -> str:
    """Create a CRM lead in Odoo for a client property inquiry received via WhatsApp.
    Use this when a user (option 2) wants to log a client enquiry.
    contact_name: the client's name (required).
    phone: client's phone number.
    email: client's email.
    inquiry: free-text description of what the client is looking for.
    district: preferred district in Chinese (optional).
    property_type: type of property in Chinese (optional, e.g. 寫字樓, 商舖).
    Returns the Odoo CRM lead URL on success.
    """
    import xmlrpc.client
    from src.nodes.odoo_sync import ODOO_URL, ODOO_DB, ODOO_USERNAME
    from src.nodes.knowledge_writer import _TimeoutTransport

    api_key = os.environ.get("ODOO_API_KEY", "")
    if not api_key:
        return "Odoo 連線未設定（ODOO_API_KEY 缺失）。"

    try:
        _tx = _TimeoutTransport(10)
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", transport=_tx)
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, api_key, {})
        if not uid:
            return "Odoo 登入失敗。"
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", transport=_tx)

        parts = []
        if district:
            parts.append(f"地區：{district}")
        if property_type:
            parts.append(f"物業類型：{property_type}")
        if inquiry:
            parts.append(inquiry)
        description = "\n".join(parts) if parts else ""

        title_parts = []
        if district:
            title_parts.append(district)
        if property_type:
            title_parts.append(property_type)
        name = f"WhatsApp 查詢 — {contact_name}" + (f" ({' '.join(title_parts)})" if title_parts else "")

        vals: dict = {
            "name": name,
            "partner_name": contact_name,
            "team_id": 1,    # Sales team
            "source_id": 20, # WhatsApp
        }
        if phone:
            vals["phone"] = phone
        if email:
            vals["email_from"] = email
        if description:
            vals["description"] = description

        lead_id = models.execute_kw(ODOO_DB, uid, api_key, "crm.lead", "create", [vals])
        return f"CRM 客戶查詢已建立（ID: {lead_id}）：\n{ODOO_URL}/odoo/crm/{lead_id}"
    except Exception as e:
        return f"建立 CRM 失敗：{str(e)[:120]}"


def clear_file_cache(user_id: str, channel: str) -> None:
    """Remove cached file for this user+channel (called on session reset)."""
    clear_cached_file(user_id, channel)


@tool
def log_property_inquiry(
    property_name: str,
    district: str = "",
    budget_hkd: int = 0,
    notes: str = "",
) -> str:
    """Log a WhatsApp user's property interest as a CRM lead in Odoo, using their
    WhatsApp number as the contact. Use this when the user is interested in a specific
    property and wants to be followed up, WITHOUT asking them for name/phone/email.
    property_name: the building or listing the user asked about.
    district: HK district (optional).
    budget_hkd: monthly rent budget in HKD (optional).
    notes: any additional context from the conversation.
    Returns the Odoo CRM lead URL on success.
    """
    import xmlrpc.client
    import json as _json
    from src.nodes.odoo_sync import ODOO_URL, ODOO_DB, ODOO_USERNAME

    # Pull the WhatsApp sender number from the context set by handle_message
    user_key = _pending_user_key.get() or ""
    whatsapp_number = ""
    channel = ""
    if ":" in user_key:
        whatsapp_number, channel = user_key.rsplit(":", 1)

    if channel != "whatsapp" or not whatsapp_number:
        return _json.dumps({
            "success": False,
            "message": "This shortcut only works for WhatsApp users. Use create_crm_lead and ask for their name/phone instead.",
        })

    api_key = os.environ.get("ODOO_API_KEY", "")
    if not api_key:
        return _json.dumps({"success": False, "message": "Odoo not configured (ODOO_API_KEY missing)."})

    try:
        from src.nodes.knowledge_writer import _TimeoutTransport
        _tx = _TimeoutTransport(10)
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", transport=_tx)
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, api_key, {})
        if not uid:
            return _json.dumps({"success": False, "message": "Odoo authentication failed."})
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", transport=_tx)

        desc_parts = [f"Property of interest: {property_name}"]
        if district:
            desc_parts.append(f"District: {district}")
        if budget_hkd:
            desc_parts.append(f"Budget: HKD {budget_hkd:,}/month")
        if notes:
            desc_parts.append(f"Notes: {notes}")
        desc_parts.append(f"Source: WhatsApp {whatsapp_number}")

        vals = {
            "name": f"WhatsApp inquiry — {property_name}",
            "partner_name": f"WhatsApp {whatsapp_number}",
            "phone": whatsapp_number,
            "team_id": 1,
            "source_id": 20,  # WhatsApp
            "description": "\n".join(desc_parts),
        }
        lead_id = models.execute_kw(ODOO_DB, uid, api_key, "crm.lead", "create", [vals])
        return _json.dumps({
            "success": True,
            "lead_id": lead_id,
            "url": f"{ODOO_URL}/odoo/crm/{lead_id}",
            "message": f"Inquiry logged. A Century 21 agent will follow up on {whatsapp_number}.",
        }, ensure_ascii=False)
    except Exception as e:
        return _json.dumps({"success": False, "message": f"Odoo error: {str(e)[:120]}"})


def _auto_log_inquiry(query: str, top_doc: dict) -> None:
    """Silently log a WhatsApp user's property inquiry to Odoo CRM. Errors are
    swallowed — this is a background best-effort action, never blocks the reply."""
    try:
        user_key = _pending_user_key.get() or ""
        if ":" not in user_key:
            return
        whatsapp_number, channel = user_key.rsplit(":", 1)
        if channel != "whatsapp" or not whatsapp_number:
            return

        api_key = os.environ.get("ODOO_API_KEY", "")
        if not api_key:
            return

        ex = top_doc.get("extracted_data") or {}
        building = ex.get("building_name") or ex.get("project_name") or top_doc.get("file_name", query)
        district = ex.get("district") or ""

        import xmlrpc.client
        from src.nodes.odoo_sync import ODOO_URL, ODOO_DB, ODOO_USERNAME
        from src.nodes.knowledge_writer import _TimeoutTransport
        _tx = _TimeoutTransport(5)  # 5s hard limit — never block a search reply
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", transport=_tx)
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, api_key, {})
        if not uid:
            return
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", transport=_tx)

        desc = (
            f"Property of interest: {building}\n"
            f"District: {district}\n"
            f"User query: {query}\n"
            f"Source: WhatsApp {whatsapp_number} (auto-logged)"
        )
        models.execute_kw(ODOO_DB, uid, api_key, "crm.lead", "create", [{
            "name": f"WhatsApp inquiry — {building}",
            "partner_name": f"WhatsApp {whatsapp_number}",
            "phone": whatsapp_number,
            "team_id": 1,
            "source_id": 20,
            "description": desc,
        }])
    except Exception:
        pass  # best-effort — never break the search reply


@tool
def contact_staff(reason: str = "") -> str:
    """Redirect the user to a live Century 21 staff representative. Sends the staff
    member a WhatsApp notification about this user's inquiry AND returns the staff
    contact info to the user so they can reach out directly too.
    Use when the user asks to talk to a person, be connected to staff, or when the
    property data is too thin to be useful and the user wants human help.
    reason: short summary of what the user needs help with (optional).
    Returns JSON — format it in the user's language.
    """
    import json as _json
    staff_phone = os.environ.get("STAFF_WHATSAPP", "").strip()
    staff_name = os.environ.get("STAFF_NAME", "Century 21 leasing team").strip()
    if not staff_phone:
        return _json.dumps({
            "available": False,
            "message": "Staff contact not configured. Please try again later or leave your details as a CRM lead.",
        })

    # Get the user's WhatsApp number so staff knows who to reach
    user_key = _pending_user_key.get() or ""
    user_whatsapp = ""
    if ":" in user_key:
        user_whatsapp, channel = user_key.rsplit(":", 1)
        if channel != "whatsapp":
            user_whatsapp = ""

    # Fire-and-forget: send the staff notification in a background thread.
    # The n8n → Twilio round trip takes 1-5s and would block the whole assistant reply.
    notified = False
    if user_whatsapp:
        import threading, logging
        _log = logging.getLogger(__name__)
        def _notify():
            try:
                from src.utils.whatsapp_notify import send_whatsapp
                msg = (
                    f"新 WhatsApp 查詢 / New WhatsApp inquiry\n"
                    f"From: {user_whatsapp}\n"
                    f"About: {reason[:300] if reason else 'general property inquiry'}\n\n"
                    f"Reply direct: https://wa.me/{''.join(c for c in user_whatsapp if c.isdigit())}"
                )
                send_whatsapp(staff_phone, msg)
                _log.info("staff notify sent to %s about %s", staff_phone, user_whatsapp)
            except Exception as e:
                _log.warning("staff notify failed (Twilio daily cap or n8n error): %s", e)
        threading.Thread(target=_notify, daemon=True).start()
        notified = True

    digits = "".join(c for c in staff_phone if c.isdigit())
    return _json.dumps({
        "available": True,
        "staff_name": staff_name,
        "whatsapp_number": staff_phone,
        "whatsapp_link": f"https://wa.me/{digits}",
        "staff_notified": notified,
        "message": (
            f"{staff_name} has been notified about your inquiry and will reach out to you shortly."
            if notified else
            f"Please contact {staff_name} directly using the WhatsApp link."
        ),
        "reason_summary": reason[:200],
    }, ensure_ascii=False)


@tool
def find_similar_properties(
    district: str = "",
    size_sqft: int = 0,
    max_rent: int = 0,
    exclude_building: str = "",
) -> str:
    """Find properties similar to a reference — by district, size, or rent budget.
    Use after search_properties returns thin details, to recommend alternatives.
    district: HK district in Chinese or English (e.g. "灣仔", "Wan Chai").
    size_sqft: target size; matches within +/- 30%.
    max_rent: maximum monthly rent in HKD.
    exclude_building: building name to skip (the one the user already saw).
    Returns JSON — format in the user's language.
    """
    import json as _json
    try:
        from src.nodes.chatbot import search_documents
        # Build a broad query so vector search casts a wide net
        query_parts = []
        if district:
            query_parts.append(district)
        query_parts.append("commercial property office retail listing")
        docs = search_documents(" ".join(query_parts), top_k=15, hybrid=True)
    except Exception as e:
        return _json.dumps({"error": str(e)[:80]})

    exclude_lower = exclude_building.strip().lower()
    results = []
    for doc in docs:
        ex = doc.get("extracted_data") or {}
        name = ex.get("building_name") or ex.get("project_name") or doc.get("file_name", "")
        if exclude_lower and exclude_lower in str(name).lower():
            continue

        # District filter
        if district:
            d_ex = str(ex.get("district") or "").lower()
            if district.lower() not in d_ex and d_ex not in district.lower():
                continue

        # Size filter (+/- 30%)
        if size_sqft > 0:
            s = ex.get("size_sqft")
            if isinstance(s, (int, float)):
                if not (0.7 * size_sqft <= s <= 1.3 * size_sqft):
                    continue

        # Rent filter
        if max_rent > 0:
            r = ex.get("rent_monthly")
            if isinstance(r, (int, float)) and r > max_rent:
                continue

        results.append({
            "building_name": name,
            "district": ex.get("district"),
            "address": ex.get("address"),
            "size_sqft": ex.get("size_sqft"),
            "rent_monthly": ex.get("rent_monthly"),
            "contact_name": ex.get("contact_name"),
            "contact_phone": ex.get("contact_phone"),
        })
        if len(results) >= 5:
            break

    return _json.dumps({
        "count": len(results),
        "criteria": {"district": district, "size_sqft": size_sqft, "max_rent": max_rent},
        "results": results,
    }, ensure_ascii=False)


@tool
def search_contacts(query: str) -> str:
    """Search saved name cards and contacts by person name, company, phone number, or email.
    Use when the user asks for someone's contact details, phone, or email, or types a person
    or company name to look up.
    Returns saved contact details — name, title, company, phone, mobile, email.
    """
    import json as _json
    try:
        from src.nodes.chatbot import keyword_search
        results = keyword_search(query=query, filters={"document_type": "contact"}, top_k=5)
    except Exception as e:
        return _json.dumps({"error": str(e)[:80]})

    if not results:
        return _json.dumps({"count": 0, "results": []})

    contacts = []
    for doc in results:
        ex = doc.get("extracted_data") or {}
        # Skip entries with no useful contact data
        if not any(ex.get(f) for f in ("name", "name_zh", "phone", "mobile", "email")):
            continue
        contacts.append({
            "name": ex.get("name_zh") or ex.get("name"),
            "title": ex.get("title"),
            "company": ex.get("company_zh") or ex.get("company"),
            "phone": ex.get("phone"),
            "mobile": ex.get("mobile"),
            "email": ex.get("email"),
            "address": ex.get("address"),
        })

    return _json.dumps({"count": len(contacts), "results": contacts}, ensure_ascii=False)


# ── Agent ─────────────────────────────────────────────────────────────────────

_TOOLS = [
    create_knowledge_article,
    process_property_listing,
    check_listing_duplicate,
    search_properties,
    search_market_news,
    find_similar_properties,
    search_contacts,
    query_odoo_listings,
    create_crm_lead,
    log_property_inquiry,
    contact_staff,
]


def _messages_to_lc(messages: list[dict]) -> list:
    """Convert stored plain-dict messages to LangChain message objects."""
    result = []
    for m in messages:
        if m.get("role") == "user":
            result.append(HumanMessage(content=m["content"]))
        elif m.get("role") == "assistant":
            result.append(AIMessage(content=m["content"]))
    return result


def _lc_to_messages(lc_messages: list) -> list[dict]:
    """Convert LangChain message objects back to plain dicts for storage."""
    result = []
    for m in lc_messages:
        if isinstance(m, HumanMessage):
            result.append({"role": "user", "content": m.content if isinstance(m.content, str) else str(m.content)})
        elif isinstance(m, AIMessage) and m.content:
            result.append({"role": "assistant", "content": m.content if isinstance(m.content, str) else str(m.content)})
    return result


@traceable(name="assistant_handle_message", run_type="chain")
def handle_message(
    user_id: str,
    body: str,
    channel: str,
    file_bytes: bytes | None = None,
    file_name: str | None = None,
    media_url: str | None = None,
) -> str:
    """Process one user message and return a plain-text reply.

    Loads session, runs the LangGraph ReAct agent, saves updated session.
    """
    # Set file context for tools
    cache_key = f"{user_id}:{channel}"
    _pending_user_key.set(cache_key)

    if file_bytes and file_name:
        _pending_file.set((file_name, file_bytes))
        # Cache so follow-up messages ("yes" on duplicate confirm) can reuse the file
        cache_file(user_id, channel, file_name, file_bytes)
    else:
        _pending_file.set(None)
    _pending_media_url.set(media_url)

    # Load session
    session = get_session(user_id, channel)

    # A new image with no text is always a fresh forwarded attachment — clear history
    # so the LLM can't hallucinate based on previous article/listing creation context.
    _IMAGE_EXTS_SET = {"jpg", "jpeg", "png", "gif", "webp"}
    if file_bytes and file_name and not body.strip():
        ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        if ext in _IMAGE_EXTS_SET:
            session["messages"] = []
            save_session(user_id, channel, session)

    _SIMPLE_OPENERS = {"", "hi", "hello", "你好", "您好", "嗨", "hey", "哈囉", "start", "開始", "menu", "菜單"}

    # Greeting/menu request — return menu instantly regardless of session history,
    # and reset the session so stale context can't affect what follows.
    if not file_name and not media_url and body.strip().lower() in _SIMPLE_OPENERS:
        session["messages"] = [{"role": "assistant", "content": GREETING}]
        save_session(user_id, channel, session)
        return GREETING

    if not session["messages"]:
        # User typed something meaningful (e.g. "1") before seeing the menu —
        # inject the greeting as synthetic context so the LLM knows what 1/2/3 means
        session["messages"] = [{"role": "assistant", "content": GREETING}]

    # Negative feedback fast path — user says "wrong"/"錯" after an answer
    _WRONG_SIGNALS = {"wrong", "錯", "不對", "incorrect", "bad answer", "錯誤"}
    if not file_bytes and body.strip().lower() in _WRONG_SIGNALS and len(session["messages"]) >= 2:
        msgs = session["messages"]
        last_assistant = next((m["content"] for m in reversed(msgs) if m.get("role") == "assistant"), "")
        last_user = next((m["content"] for m in reversed(msgs) if m.get("role") == "user"), "")
        if last_assistant:
            try:
                from src.utils.table_storage import log_feedback
                log_feedback(
                    thread_id=f"{channel}:{user_id}",
                    question=last_user,
                    answer=last_assistant,
                    rating="down",
                    channel=channel,
                )
            except Exception:
                pass
        ack = "謝謝反饋，已記錄。🙏 我會持續改進答案質素。" if any(ord(c) > 127 for c in body) else "Thanks for the feedback — noted! 🙏 I'll work on improving my answers."
        session["messages"].append({"role": "user", "content": body.strip()})
        session["messages"].append({"role": "assistant", "content": ack})
        session["messages"] = session["messages"][-10:]
        save_session(user_id, channel, session)
        return ack

    # Fast paths for attachments with no text — no LLM needed:
    #   image → dup check + dispatch pipeline (classifier decides news vs listing)
    #   PDF/other → ask whether it is a Knowledge article or Property Listing
    _IMAGE_EXTS = ("jpg", "jpeg", "png", "gif", "webp")
    if file_name and not body.strip():
        ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        if ext in _IMAGE_EXTS and file_bytes:
            warning = _check_news_duplicate(file_bytes)
            if warning:
                reply = warning
            else:
                _dispatch_pipeline_async(
                    file_bytes, file_name,
                    notify_user=user_id, notify_channel=channel,
                )
                reply = _PROCESSING_REPLY
            session["messages"].append({"role": "user", "content": f"[Attached image: {file_name}]"})
            session["messages"].append({"role": "assistant", "content": reply})
            session["messages"] = session["messages"][-10:]
            save_session(user_id, channel, session)
            return reply
        if ext not in _IMAGE_EXTS:
            reply = f"已收到 {file_name}。請問這是知識文章還是物業盤源？"
            session["messages"].append({"role": "user", "content": f"[Attached file: {file_name}]"})
            session["messages"].append({"role": "assistant", "content": reply})
            session["messages"] = session["messages"][-10:]
            save_session(user_id, channel, session)
            return reply

    # Fast path: user confirms "yes" after a news duplicate warning — force-process
    # the cached image through the news pipeline. Must run BEFORE the listing
    # trigger check below, which also matches "yes".
    _CONFIRM_WORDS = {"yes", "是", "確認", "confirm", "好", "ok"}
    body_lower = body.strip().lower()
    cached_file = get_cached_file(user_id, channel)
    _last_assistant = next(
        (m["content"] for m in reversed(session["messages"]) if m.get("role") == "assistant"), ""
    )
    if (not file_name and body_lower in _CONFIRM_WORDS
            and _last_assistant.startswith(_NEWS_DUP_MARKER) and cached_file):
        fname, fbytes = cached_file
        _dispatch_pipeline_async(
            fbytes, fname, skip_duplicate_check=True,
            notify_user=user_id, notify_channel=channel,
        )
        reply = _PROCESSING_REPLY
        session["messages"].append({"role": "user", "content": body.strip()})
        session["messages"].append({"role": "assistant", "content": reply})
        session["messages"] = session["messages"][-10:]
        save_session(user_id, channel, session)
        return reply

    # Fast path: skip LLM entirely for clear property-listing confirmations.
    # The ReAct agent makes 3 LLM calls (each 15-20s) which hits the 60s Azure
    # idle timeout. When the user already uploaded a file and now confirms "3" or
    # "物業盤源", we know exactly what to do — no reasoning loop needed.
    _LISTING_TRIGGERS = {
        "3", "物業盤源", "property listing", "listing", "盤源",
        "yes", "yes process it", "process it", "confirm", "確認", "是",
    }
    # Case A: new file sent together with a listing trigger (e.g. PDF + "3" in one WhatsApp message)
    if file_name and file_bytes and body_lower in _LISTING_TRIGGERS:
        _dispatch_pipeline_async(
            file_bytes, file_name,
            notify_user=user_id, notify_channel=channel,
        )
        reply = _PROCESSING_REPLY
        session["messages"].append({"role": "user", "content": f"{body.strip()}\n[Attached file: {file_name}]"})
        session["messages"].append({"role": "assistant", "content": reply})
        session["messages"] = session["messages"][-10:]
        save_session(user_id, channel, session)
        return reply
    # Fast path: attachment + long pasted text = forwarded article/ad (very common:
    # news post forwarded from another chat arrives as image + full article text).
    # No LLM — dispatch straight to the pipeline, its classifier picks news vs listing.
    # Short text (questions like "咩價錢?") still goes to the agent below.
    #
    # Guard: Twilio echoes the PDF filename as the WhatsApp Body when a file is forwarded
    # with no caption. Body == filename → do NOT treat it as document content (precomputed
    # OCR). Pass text=None so Document Intelligence runs on the actual file bytes.
    #
    # URL shortcut: image + URL caption (e.g. on.cc share link) is always a news article —
    # auto-dispatch even when body < 60 chars so the LLM doesn't ask unnecessary questions.
    import re as _re
    _body_has_url = bool(_re.search(r'https?://', body))
    _is_image_ext = file_name.rsplit(".", 1)[-1].lower() if file_name and "." in file_name else ""
    _is_image_ext = _is_image_ext in ("jpg", "jpeg", "png", "gif", "webp")
    if file_name and file_bytes and (len(body.strip()) >= 60 or (_body_has_url and _is_image_ext)):
        body_is_filename = body.strip() == file_name.strip()
        text_for_ocr = None if body_is_filename else body.strip()
        warning = _check_news_duplicate(file_bytes)
        if warning:
            reply = warning
        else:
            _dispatch_pipeline_async(
                file_bytes, file_name, text=text_for_ocr,
                notify_user=user_id, notify_channel=channel,
            )
            reply = _PROCESSING_REPLY
        session["messages"].append({"role": "user", "content": f"[Attached file: {file_name}]\n{body.strip()[:300]}"})
        session["messages"].append({"role": "assistant", "content": reply})
        session["messages"] = session["messages"][-10:]
        save_session(user_id, channel, session)
        return reply

    # Fast path: WhatsApp URL message (body is a URL, or a short caption + URL).
    # Catches bare URLs like https://share.google/... AND short link-preview captions
    # like "來源：on.cc https://..." where the WhatsApp card adds surrounding text.
    # Auto-dispatch as news — pipeline fetches content via Tavily (with redirect following).
    if channel == "whatsapp" and not file_name and not media_url:
        import re as _re_url
        _body_s = body.strip()
        _has_url = bool(_re_url.search(r'https?://\S+', _body_s))
        # Trigger when body IS a bare URL, or when body is short and URL-dominant
        _is_url_msg = _has_url and (
            bool(_re_url.match(r'^https?://\S+$', _body_s))  # bare URL
            or len(_body_s) < 80  # short caption + URL (e.g. WhatsApp link preview)
        )
        if _is_url_msg:
            from src.state import DocumentType
            _dispatch_pipeline_async(
                None, None, text=_body_s,
                forced_type=DocumentType.NEWS,  # URLs forwarded on WhatsApp are always news articles
                notify_user=user_id, notify_channel=channel,
            )
            reply = _PROCESSING_REPLY
            session["messages"].append({"role": "user", "content": _body_s})
            session["messages"].append({"role": "assistant", "content": reply})
            session["messages"] = session["messages"][-10:]
            save_session(user_id, channel, session)
            return reply

    # Fast path: WhatsApp text-only forwarded post (≥60 chars, no file).
    # On WhatsApp, long text-only messages are almost always forwarded articles/ads.
    # Dispatch directly — pipeline classifier decides news vs listing. Avoids the
    # ReAct agent's 3-LLM-call chain which easily exceeds n8n's HTTP timeout.
    # Dashboard users are NOT caught here (they use the chat UI and ask questions).
    if channel == "whatsapp" and not file_name and not media_url and len(body.strip()) >= 60:
        _dispatch_pipeline_async(
            None, None, text=body.strip(),
            notify_user=user_id, notify_channel=channel,
        )
        reply = _PROCESSING_REPLY
        session["messages"].append({"role": "user", "content": body.strip()[:300]})
        session["messages"].append({"role": "assistant", "content": reply})
        session["messages"] = session["messages"][-10:]
        save_session(user_id, channel, session)
        return reply

    # Fast path: user confirms cached file as a Knowledge article.
    # Triggered by "1" / knowledge words, OR by any confirmation word when the
    # last agent message was asking "是否繼續？確認/否" (context-aware confirm).
    # Works even when the blob cache missed — falls back to "re-send" message.
    _KNOWLEDGE_TRIGGERS = {
        "1", "知識文章", "知識", "market report", "市場報告", "新聞", "news", "report",
        "research", "研究", "成交", "transaction", "article", "文章",
    }
    _CONFIRM_ANY = {"yes", "是", "確認", "confirm", "好", "ok", "繼續", "continue"}
    _agent_asked_confirm = any(kw in _last_assistant for kw in ("是否繼續", "確認/否", "保存為知識文章"))
    _is_knowledge_confirm = (
        body_lower in _KNOWLEDGE_TRIGGERS
        or (body_lower in _CONFIRM_ANY and _agent_asked_confirm)
    )
    if not file_name and not media_url and _is_knowledge_confirm and cached_file:
        from src.state import DocumentType
        fname, fbytes = cached_file
        _dispatch_pipeline_async(
            fbytes, fname,
            forced_type=DocumentType.NEWS,
            notify_user=user_id, notify_channel=channel,
        )
        reply = _PROCESSING_REPLY
        session["messages"].append({"role": "user", "content": body.strip()})
        session["messages"].append({"role": "assistant", "content": reply})
        session["messages"] = session["messages"][-10:]
        save_session(user_id, channel, session)
        return reply

    # Case B: text-only confirm for a previously cached file
    if not file_name and not media_url and body_lower in _LISTING_TRIGGERS and cached_file:
        fname, fbytes = cached_file
        _pending_file.set(cached_file)
        _dispatch_pipeline_async(
            fbytes, fname,
            notify_user=user_id, notify_channel=channel,
        )
        reply = _PROCESSING_REPLY
        session["messages"].append({"role": "user", "content": body.strip()})
        session["messages"].append({"role": "assistant", "content": reply})
        session["messages"] = session["messages"][-10:]
        save_session(user_id, channel, session)
        return reply

    # (Fast path for search queries removed — all search now goes through the ReAct
    # agent so the LLM can reply in the user's language and reason about what's missing.)

    # Enrich user message with file hint so agent knows a file was attached
    user_content = body.strip() or ""
    if file_name and not user_content:
        user_content = f"[Attached file: {file_name}]"
    elif file_name:
        user_content = f"{user_content}\n[Attached file: {file_name}]"
    elif media_url and not user_content:
        user_content = "[Attached media]"

    # Build message history for the agent.
    # Filter out _PROCESSING_REPLY ack messages — they represent pipeline dispatches,
    # not real conversation turns. Leaving them in causes the LLM to misread the next
    # message as another content submission rather than a fresh query (e.g. a building
    # name search arriving after a URL dispatch ack).
    _clean_history = [
        m for m in session["messages"]
        if m.get("content") != _PROCESSING_REPLY
    ]
    history = _messages_to_lc(_clean_history)
    input_messages = [SystemMessage(content=_build_system_prompt(channel, body, _clean_history))] + history + [HumanMessage(content=user_content)]

    try:
        llm = _build_llm()
        agent = create_react_agent(llm, _TOOLS)
        result = agent.invoke({"messages": input_messages})

        # Extract final AI reply
        reply = ""
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                reply = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

        reply = reply.strip() or "Sorry, I couldn't process that. Please try again."

    except Exception as e:
        if _pipeline_dispatched.get():
            # Pipeline was already dispatched by a tool — return the ack instead of
            # the LLM error (e.g. 504 on the final response call after tool succeeded).
            reply = _PROCESSING_REPLY
        else:
            reply = f"Assistant error: {str(e)[:100]}. Please try again."
        result = {"messages": input_messages}

    # Save updated session (store plain dicts, not LangChain objects)
    all_messages = _lc_to_messages(result.get("messages", input_messages))
    session["messages"] = all_messages[-10:]
    save_session(user_id, channel, session)

    return reply
