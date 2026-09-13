"""AI Assistant — LangGraph ReAct agent for content ingest.

Handles Knowledge articles, Property Listings, and CRM leads (future).

Channel-agnostic core: handle_message() and every fast path below make
decisions purely from message shape (has a file? how long is the text? does
it contain a URL?) — never from `channel`. `channel` exists only to know how
to notify the user back (see src/utils/channel_notify.py) and to key session/
file-cache storage. The one exception is transport-level text quirks (e.g.
Slack's mrkdwn link encoding), normalized once via `_BODY_NORMALIZERS` before
any of the shape-based logic runs. To add a new channel (e.g. Teams): give
its adapter a `channel` string, register a notifier in channel_notify.py if
it needs async completion pushes, and register a body normalizer here only if
its transport encodes text unusually. No other changes needed.
"""

import contextvars
import os
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import AzureChatOpenAI, ChatOpenAI
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

You are the C21 Document Ingest Assistant — a document upload helper for the Century 21 Hong Kong internal team.

YOUR ONLY JOB IS TO RECEIVE AND PROCESS DOCUMENTS. You are NOT a property search engine, NOT a listing recommendation service, and NOT a general real estate assistant.

On first contact (no prior messages), greet the user and show this menu:
  1 · 知識文章 — Save market news, research, or transaction records as Knowledge articles in Odoo
  2 · 物業盤源 — Process a property listing PDF/image (OCR, extract, sync to Odoo)
  3 · 名片 — Scan a name card to save to Odoo Contacts

Users can type 1/2/3 OR send a file directly.

Tool selection:

create_knowledge_article: user sends market news, research, or a transaction record to save.
process_property_listing: user sends a property listing PDF, image, or flyer.
check_listing_duplicate: check if a file was already processed before re-running.

Attachments — pick the right tool by content, do NOT ask for confirmation first:
- News screenshots, market reports, transaction records → create_knowledge_article
- Property listing ads/flyers (招租, 放售, 盤源) → process_property_listing
- Name cards / business cards (名片) → process_property_listing (pipeline auto-classifies as contact)
- Unclear → process_property_listing (the pipeline classifier will decide the type)

STRICT RULES — you MUST follow these:
- NEVER search for properties, recommend listings, or answer questions about available units
- NEVER ask users what type of property they want, their budget, or their requirements
- NEVER pretend you can search the database or find listings
- If the user asks to search for properties, find listings, or browse the database, reply: "這個助理只負責處理文件上傳。如需查詢放盤，請聯絡我們的同事。" (English: "This assistant only handles document upload. For property enquiries, please contact our team.")
- If the user sends text about wanting to rent or buy, reply with the above message and show the menu
- Be concise — this is a chat interface, not a search portal
- If the user says "reset" or "重新開始", show the menu again
- NEVER use Markdown formatting. No bold, no italics, no headers. Plain text only."""

# Same rule for every channel — language behavior doesn't vary by transport.
_LANGUAGE_RULE = "CRITICAL: Always reply in the same language the user writes in. If they write English, your reply MUST be in English. If they write Traditional Chinese (繁體中文), reply in Chinese. This applies to ALL your output including when presenting tool results — never paste tool output verbatim, always reformulate it in the user's language. Professional tone — clear and concise."

# ── Channel input normalization ──────────────────────────────────────────────
# Transport-specific quirks in how a channel encodes incoming text. This is the
# ONLY place channel identity should affect message content before it reaches
# the (channel-blind) core logic below. To add a new channel's quirk, register
# a function here — don't add another `if channel == "..."` inline further down.

def _normalize_slack_body(body: str) -> str:
    """Slack sends links as mrkdwn <url> or <url|label> — normalize to a plain URL
    so downstream URL detection/Tavily extraction/article generation see a clean link."""
    import re as _re_slack_link
    return _re_slack_link.sub(r"<(https?://[^|>]+)(?:\|[^>]*)?>", r"\1", body)


_BODY_NORMALIZERS = {
    "slack": _normalize_slack_body,
    # whatsapp/dashboard/teams send plain text already — no normalizer needed.
}


def _normalize_body_for_channel(channel: str, body: str) -> str:
    normalizer = _BODY_NORMALIZERS.get(channel)
    return normalizer(body) if (normalizer and body) else body


GREETING = """您好，我是 C21 文件助理。請選擇所需服務：

1 · 知識文章 — 儲存市場資訊、研究報告或成交記錄至 Odoo
2 · 物業盤源 — 處理物業資料 PDF（OCR、提取及同步至 Odoo）
3 · 名片 — 掃描名片儲存至 Odoo 聯絡人

請輸入 1–3，或直接傳送附件，系統將自動處理。"""


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


def _build_system_prompt(user_message: str = "", session_messages: list | None = None) -> str:
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
    return override + "\n\n" + _SYSTEM_PROMPT_BASE.format(language_rule=_LANGUAGE_RULE)


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
    # Channel-neutral wording — the completion notify pushes back into whichever
    # conversation the user is already in (WhatsApp/Slack/Teams), so naming one
    # channel here was simply wrong for the other two (found 2026-09-12 testing
    # Teams: the reply claimed "WhatsApp" even in a Teams chat).
    "完成後會在此通知您處理結果及分類。您現在可以繼續傳送其他內容。"
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

        from src.utils.channel_notify import notify
        notify(notify_channel, notify_user, message)

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
    """Check if a property listing with this filename already exists in Odoo."""
    import xmlrpc.client
    from src.nodes.odoo_sync import ODOO_URL, ODOO_DB, ODOO_USERNAME, DOCUMENTS_FOLDER_ID
    from src.nodes.knowledge_writer import _TimeoutTransport

    api_key = os.environ.get("ODOO_API_KEY", "")
    if not api_key:
        return "Odoo 連線未設定（ODOO_API_KEY 缺失）— cannot check for duplicates."

    try:
        _tx = _TimeoutTransport(10)
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", transport=_tx)
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, api_key, {})
        if not uid:
            return "Could not check for duplicates — proceeding."
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", transport=_tx)

        existing = models.execute_kw(
            ODOO_DB, uid, api_key, "documents.document", "search_read",
            [[["name", "=", filename], ["folder_id", "=", DOCUMENTS_FOLDER_ID]]],
            {"fields": ["create_date"], "limit": 1},
        )
        if not existing:
            return f"No existing record found for '{filename}' — safe to process."
        return (
            f"⚠️ '{filename}' was already processed on {existing[0].get('create_date', 'unknown date')}.\n"
            "Reply *yes* to reprocess, or *no* to skip."
        )
    except Exception:
        return "Could not check for duplicates — proceeding."


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


# ── Agent ─────────────────────────────────────────────────────────────────────

_TOOLS = [
    create_knowledge_article,
    process_property_listing,
    check_listing_duplicate,
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

    body = _normalize_body_for_channel(channel, body)

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

    # Fast path: bare URL message (body is a URL, or a short caption + URL).
    # Catches bare URLs like https://share.google/... AND short link-preview captions
    # like "來源：on.cc https://..." where a channel's link-preview card adds
    # surrounding text. Auto-dispatch as news — pipeline fetches content via Tavily
    # (with redirect following). Applies to every channel — a forwarded link is a
    # forwarded link regardless of transport.
    if not file_name and not media_url:
        import re as _re_url
        _body_s = body.strip()
        _has_url = bool(_re_url.search(r'https?://\S+', _body_s))
        # Trigger when body IS a bare URL, or when body is short and URL-dominant
        _is_url_msg = _has_url and (
            bool(_re_url.match(r'^https?://\S+$', _body_s))  # bare URL
            or len(_body_s) < 80  # short caption + URL (e.g. link preview)
        )
        if _is_url_msg:
            from src.state import DocumentType
            _dispatch_pipeline_async(
                None, None, text=_body_s,
                forced_type=DocumentType.NEWS,  # a forwarded URL is always a news article
                notify_user=user_id, notify_channel=channel,
            )
            reply = _PROCESSING_REPLY
            session["messages"].append({"role": "user", "content": _body_s})
            session["messages"].append({"role": "assistant", "content": reply})
            session["messages"] = session["messages"][-10:]
            save_session(user_id, channel, session)
            return reply

    # Fast path: text-only forwarded post (≥60 chars, no file).
    # Long text-only messages are almost always forwarded articles/ads, on any
    # channel. Dispatch directly — pipeline classifier decides news vs listing.
    # Avoids the ReAct agent's 3-LLM-call chain, which easily exceeds proxy idle
    # timeouts (n8n's HTTP timeout for WhatsApp/Slack; Azure's 60s idle timeout
    # for everyone else).
    if not file_name and not media_url and len(body.strip()) >= 60:
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

    # Fast path: property search queries — instant rejection, no LLM needed.
    # Users typing property search intent should be redirected immediately.
    _SEARCH_SIGNALS = {
        "有咩盤", "有冇盤", "搵盤", "查盤", "睇盤", "有冇", "推介",
        "recommend", "search", "find", "查詢放盤", "查詢",
        "放租", "放售", "出租", "出售", "租樓", "買樓", "賣樓",
    }
    if not file_name and not media_url and any(sig in body for sig in _SEARCH_SIGNALS):
        _lang = _resolve_language(body, session.get("messages", []))
        if _lang == "en":
            reply = "This assistant only handles document upload (listings, news, name cards). For property enquiries, please contact our team directly."
        else:
            reply = "這個助理只負責處理文件上傳（放盤資料、新聞、名片）。如需查詢或搜尋放盤，請直接聯絡我們的同事。"
        session["messages"].append({"role": "user", "content": body.strip()})
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
    input_messages = [SystemMessage(content=_build_system_prompt(body, _clean_history))] + history + [HumanMessage(content=user_content)]

    try:
        llm = _build_llm()
        agent = create_agent(llm, _TOOLS)
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
