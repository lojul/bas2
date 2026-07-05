"""AI Assistant — LangGraph ReAct agent for content ingest.

Handles Knowledge articles, Property Listings, and CRM leads (future).
Channel-agnostic: same agent serves dashboard and WhatsApp.
"""

import contextvars
import os
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
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

_SYSTEM_PROMPT_BASE = """You are the C21 Property Intelligence Assistant — an AI helper for the Century 21 Hong Kong real estate team.

On first contact (no prior messages), greet the user and show this menu:
  1 · Knowledge — Save market news, research, or transaction records as Knowledge articles in Odoo
  2 · CRM — Create a CRM lead for a client inquiry (coming soon)
  3 · Property Listing — Process a property listing PDF (OCR, extract, index to search, sync to Odoo)
  4 · Property Search — Ask about available properties, rents, districts

Users can type 1/2/3/4 OR describe what they need in natural language — both work.

CRITICAL — Natural language queries: if the user asks ANYTHING about properties, districts,
buildings, rentals, news, market trends, transactions, or any real estate topic, IMMEDIATELY
call search_properties. Do NOT show the menu again. Do NOT ask for clarification first.
Examples that MUST call search_properties immediately:
  "有冇觀塘新聞?" → search_properties(query="觀塘新聞")
  "觀塘有咩盤?" → search_properties(query="觀塘物業出租")
  "any office in Central?" → search_properties(query="Central office for rent")
  "尖沙咀最新成交?" → search_properties(query="尖沙咀成交")
  "市場近況?" → search_properties(query="香港物業市場")
Use query_odoo_listings when the user specifically asks what is currently listed in Odoo
放盤管理 or the CRM. If unsure, use search_properties.

Attachments — pick the right tool by content, do NOT ask for confirmation first:
- News screenshots, market reports, transaction records → create_knowledge_article
- Property listing ads/flyers (for rent/sale, 招租, 放售, 盤源) → process_property_listing
- Unclear which → process_property_listing (the pipeline classifier will decide the type)
Both run the full pipeline in the background and notify the user on WhatsApp when complete.
If the user pastes news/market text with no attachment and wants it saved, call create_knowledge_article with that text.
If the user confirms (yes/是/確認) after a duplicate warning, call create_knowledge_article again with force=true.
PDF attachments with no text: ask whether it is a Knowledge article or a Property Listing before proceeding.

Rules:
- {language_rule}
- Be concise and conversational — this is a chat interface
- Ask one clarifying question at a time if something is unclear
- Always confirm before taking irreversible actions (creating articles, processing listings)
- For duplicates, show what already exists and ask whether to proceed
- Never fabricate information — only report what tools actually return
- When a task completes, show the result URL so the user can verify
- If the user says "reset" or "重新開始" or "start over", clear the conversation and show the menu again
- IMPORTANT: Never use Markdown formatting. No bold (**text**), no italics, no headers (#), no Markdown links [text](url). Output plain text and bare URLs only."""

_LANGUAGE_RULES = {
    "whatsapp": "Always reply in Traditional Chinese (繁體中文). Use a professional business tone — clear, concise, and courteous. Avoid overly casual expressions, slang, or excessive punctuation.",
    "dashboard": "Always reply in Traditional Chinese (繁體中文). Use a professional business tone — clear, concise, and courteous. Avoid overly casual expressions, slang, or excessive punctuation.",
}

GREETING = """您好，我是 C21 智能助理。請選擇所需服務：

1 · 知識文章 — 儲存市場資訊、研究報告或成交記錄至 Odoo
2 · CRM — 建立客戶查詢（即將推出）
3 · 物業盤源 — 處理物業資料 PDF（OCR、提取、索引及同步至 Odoo）
4 · 物業查詢 — 搜尋物業、租金、地區資料

請輸入 1、2、3 或 4，或直接描述您的需要（例如「觀塘有咩盤?」）。如有附件，系統將自動建議最合適的處理方式。"""


def _build_system_prompt(channel: str) -> str:
    rule = _LANGUAGE_RULES.get(channel, _LANGUAGE_RULES["dashboard"])
    return _SYSTEM_PROMPT_BASE.format(language_rule=rule)


def _build_llm() -> ChatOpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    return ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        model="qwen/qwen-2.5-72b-instruct",
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

    if enqueue_pipeline_job(
        file_bytes, file_name, text,
        forced_type=forced_type,
        skip_duplicate_check=skip_duplicate_check,
        notify_user=notify_user,
        notify_channel=notify_channel,
    ):
        return

    def _run():
        try:
            from src.graph import process_file_from_bytes
            from src.state import OCRResult

            if file_bytes and file_name:
                pre_ocr = OCRResult(text=text) if len(text.strip()) >= 60 else None
                final = process_file_from_bytes(
                    file_bytes, file_name, "assistant",
                    precomputed_ocr=pre_ocr,
                    forced_type=forced_type,
                    skip_duplicate_check=skip_duplicate_check,
                )
            else:
                from datetime import datetime, timezone
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                final = process_file_from_bytes(
                    text.encode("utf-8"), f"whatsapp-news-{stamp}.txt", "assistant",
                    precomputed_ocr=OCRResult(text=text),
                    forced_type=forced_type,
                    skip_duplicate_check=skip_duplicate_check,
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
    Returns a plain-text summary of the top matches.
    """
    try:
        from src.nodes.chatbot import search_documents
        docs = search_documents(query, top_k=3, hybrid=True)
    except Exception as e:
        return f"搜尋暫時無法使用：{str(e)[:80]}"

    if not docs:
        return "資料庫中找不到相關物業文件。"

    lines = []
    for doc in docs:
        ex = doc.get("extracted_data") or {}
        name = ex.get("building_name") or ex.get("project_name") or doc.get("file_name", "")
        parts = [str(name)]
        if ex.get("district"):
            parts.append(f"地區: {ex['district']}")
        if ex.get("address"):
            parts.append(f"地址: {ex['address']}")
        if ex.get("size_sqft"):
            parts.append(f"面積: {ex['size_sqft']}呎")
        if ex.get("rent_monthly"):
            parts.append(f"月租: ${ex['rent_monthly']:,.0f}" if isinstance(ex["rent_monthly"], (int, float)) else f"月租: {ex['rent_monthly']}")
        # listing_list: show first units
        units = ex.get("units") or []
        unit_lines = []
        for u in units[:3]:
            u_desc = " ".join(str(x) for x in (u.get("building_name"), u.get("floor"), u.get("unit")) if x)
            u_bits = [u_desc] if u_desc else []
            if u.get("size"):
                u_bits.append(f"{u['size']}呎")
            if u.get("rent"):
                u_bits.append(f"租${u['rent']}")
            if u.get("price"):
                u_bits.append(f"售${u['price']}")
            if u_bits:
                unit_lines.append("  - " + " | ".join(u_bits))
        if ex.get("contact_name") or ex.get("contact_phone"):
            parts.append(f"聯絡: {ex.get('contact_name') or ''} {ex.get('contact_phone') or ''}".strip())
        entry = " | ".join(parts)
        if unit_lines:
            entry += "\n" + "\n".join(unit_lines)
        lines.append(entry)

    return f"找到 {len(docs)} 份相關文件：\n\n" + "\n\n".join(lines)


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

    api_key = os.environ.get("ODOO_API_KEY", "")
    if not api_key:
        return "Odoo 連線未設定（ODOO_API_KEY 缺失）。"

    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, api_key, {})
        if not uid:
            return "Odoo 登入失敗。"
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

        domain: list = [["x_c21_status", "=", "active"]]
        if keyword.strip():
            domain.insert(0, "|")
            domain.append(["x_name", "ilike", keyword.strip()])
            domain.append(["x_c21_address", "ilike", keyword.strip()])
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


def clear_file_cache(user_id: str, channel: str) -> None:
    """Remove cached file for this user+channel (called on session reset)."""
    clear_cached_file(user_id, channel)


# ── Agent ─────────────────────────────────────────────────────────────────────

_TOOLS = [
    create_knowledge_article,
    process_property_listing,
    check_listing_duplicate,
    search_properties,
    query_odoo_listings,
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
    if file_name and file_bytes and len(body.strip()) >= 60:
        warning = _check_news_duplicate(file_bytes)
        if warning:
            reply = warning
        else:
            _dispatch_pipeline_async(
                file_bytes, file_name, text=body.strip(),
                notify_user=user_id, notify_channel=channel,
            )
            reply = _PROCESSING_REPLY
        session["messages"].append({"role": "user", "content": f"[Attached file: {file_name}]\n{body.strip()[:300]}"})
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

    # Enrich user message with file hint so agent knows a file was attached
    user_content = body.strip() or ""
    if file_name and not user_content:
        user_content = f"[Attached file: {file_name}]"
    elif file_name:
        user_content = f"{user_content}\n[Attached file: {file_name}]"
    elif media_url and not user_content:
        user_content = "[Attached media]"

    # Build message history for the agent
    history = _messages_to_lc(session["messages"])
    input_messages = [SystemMessage(content=_build_system_prompt(channel))] + history + [HumanMessage(content=user_content)]

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
