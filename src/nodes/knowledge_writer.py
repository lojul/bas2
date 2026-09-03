"""Odoo Knowledge article creation — used by the AI assistant ingest flow."""

import base64
import hashlib
import os
import xmlrpc.client
from datetime import datetime, timezone

import httpx
from langsmith import traceable

from src.utils.json_parser import parse_json_response
from src.utils.llm import chat_complete

ODOO_URL = os.environ.get("ODOO_URL", "https://c21net.odoo.com")
ODOO_DB = os.environ.get("ODOO_DB", "c21net")
ODOO_USERNAME = os.environ.get("ODOO_USERNAME", "admin@c21net.com")
ODOO_API_KEY = os.environ.get("ODOO_API_KEY", "")

_odoo_uid_cache: int | None = None

def _get_uid() -> int:
    """Authenticate and return UID dynamically, cached per process."""
    global _odoo_uid_cache
    if _odoo_uid_cache is not None:
        return _odoo_uid_cache
    common = xmlrpc.client.ServerProxy(
        f"{ODOO_URL}/xmlrpc/2/common",
        transport=_TimeoutTransport(10),
    )
    uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_API_KEY, {})
    if not uid:
        raise RuntimeError(f"Odoo authentication failed for {ODOO_USERNAME}")
    _odoo_uid_cache = uid
    return uid

KNOWLEDGE_PARENT_ID = 39   # Marketing News
DOCUMENTS_FOLDER_ID = 50   # Marketing News folder in Documents app
STEPHEN_PARTNER_ID = 30    # Stephen Wong

ARTICLE_PROMPT = """You are a C21 property intelligence assistant. Generate a structured Odoo Knowledge article in HTML.

LANGUAGE: Always write in Traditional Chinese (繁體中文). Never use Simplified Chinese characters.
Examples: 辦公室 not 办公室, 房地產 not 房地产, 概覽 not 概览, 業主 not 业主, 發展 not 发展.

Today: {today}

OUTPUT FORMAT — follow exactly, only include sections that have relevant content:

<h1>[Concise headline without date — match source language]</h1>
<p>來源：[source name, author if known] ｜ 日期：[date from content or {today}]</p>
<hr/>
<h2>摘要</h2>
<p>[One short factual summary paragraph]</p>
<h2>主要數據</h2>
<table style="border-collapse:collapse;width:100%"><tr style="background-color:#374151;color:white;"><th style="border:1px solid #374151;padding:8px 12px;text-align:left">項目</th><th style="border:1px solid #374151;padding:8px 12px;text-align:left">詳情</th></tr><tr><td style="border:1px solid #d1d5db;padding:8px 12px">[field name, e.g. 成交日期]</td><td style="border:1px solid #d1d5db;padding:8px 12px">[value FROM SOURCE CONTENT ONLY]</td></tr></table>
<h2>市場背景</h2>
<ul><li>[point]</li></ul>
<h2>各方回應</h2>
<p>[direct quotes from agents, buyers, or officials — OMIT this section entirely if no quotes are present]</p>
<hr/>
<p>原文來源：[source] </p>

CRITICAL RULES for 主要數據:
- You MUST use a <table> element exactly as shown above, including ALL inline styles
- Each data field goes in its own <tr> with styled <td> cells — copy the style attributes exactly
- Do NOT use bold text, plain paragraphs, or line breaks for the data fields
- Payment terms and transaction details belong in the table, NOT in 各方回應
- 各方回應 is ONLY for direct quotes from named people — omit it if there are none

Other rules:
- Title (name field): {today} | [same concise headline as H1]
- Match source language (Chinese or English)
- Factual only — no embellishment, no hallucination
- The example values in the OUTPUT FORMAT above (dates, unit numbers, figures) are placeholders
  showing structure ONLY — never copy them into your output. Every fact in your article must
  trace back to something literally present in the source content below.
- Omit any section that has no relevant content
- Do NOT add a Documents download link — it will be appended automatically
- The <hr/> footer line must always end with a space after the source (the link is appended there)

CRITICAL — insufficient content check:
If the source content below is just a source citation and/or a bare link (e.g. "來源：X｜https://...")
with no actual article body, summary, or facts to report, do NOT invent an article. Instead return
exactly: {{"insufficient_content": true}}

Source content:
---
{content}
---

Return ONLY valid JSON:
{{"title": "{today} | ...", "body": "<h1>...</h1>..."}}"""


class _TimeoutTransport(xmlrpc.client.SafeTransport):
    """HTTPS transport with a hard socket timeout so xmlrpc calls never hang forever."""
    def __init__(self, timeout: int = 10):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


def _models(timeout: int = 10):
    return xmlrpc.client.ServerProxy(
        f"{ODOO_URL}/xmlrpc/2/object",
        transport=_TimeoutTransport(timeout),
    )


def _exec(model: str, method: str, args: list, kwargs: dict | None = None, timeout: int = 10):
    uid = _get_uid()
    return _models(timeout).execute_kw(ODOO_DB, uid, ODOO_API_KEY, model, method, args, kwargs or {})


@traceable(name="check_knowledge_duplicate", run_type="retriever")
def check_duplicate(title: str, image_hash: str | None = None) -> dict | None:
    """Return existing article dict if duplicate found under Marketing News, else None.

    Checks image hash first (most reliable), then falls back to exact title match.
    """
    if not ODOO_API_KEY:
        return None
    try:
        # Short timeout (5s) — this runs in the assistant hot path before replying to the user.
        # If Odoo is slow, return None so the user gets a reply instead of a hang.
        if image_hash:
            results = _exec(
                "knowledge.article", "search_read",
                [[["body", "ilike", f"image_hash:{image_hash}"], ["parent_id", "=", KNOWLEDGE_PARENT_ID]]],
                {"fields": ["id", "name"]},
                timeout=5,
            )
            if results:
                return results[0]

        headline = title.split(" | ", 1)[-1] if " | " in title else title
        if not headline.strip():
            return None
        results = _exec(
            "knowledge.article", "search_read",
            [[["name", "ilike", headline], ["parent_id", "=", KNOWLEDGE_PARENT_ID]]],
            {"fields": ["id", "name"]},
            timeout=5,
        )
        return results[0] if results else None
    except Exception:
        return None


@traceable(name="upload_image_to_odoo", run_type="tool")
def upload_image(image_bytes: bytes, filename: str) -> str | None:
    """Upload image to Odoo Documents (Marketing News folder). Returns attachment URL or None."""
    if not ODOO_API_KEY:
        return None
    try:
        encoded = base64.b64encode(image_bytes).decode()
        doc_id = _exec("documents.document", "create", [{
            "name": filename,
            "folder_id": DOCUMENTS_FOLDER_ID,
            "datas": encoded,
        }])
        return f"{ODOO_URL}/web/content/documents.document/{doc_id}/datas/{filename}"
    except Exception as e:
        print(f"[upload_image] FAILED for {filename}: {e}")
        return None


def _download_url(url: str) -> bytes | None:
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.content
    except Exception:
        return None


@traceable(name="extract_text_from_image", run_type="llm")
def extract_text_from_image(image_bytes: bytes, image_filename: str) -> str:
    """Use Qwen VL vision model to extract all text content from an image."""
    ext = image_filename.rsplit(".", 1)[-1].lower() if "." in image_filename else "jpeg"
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/jpeg")
    b64 = base64.b64encode(image_bytes).decode()

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    payload = {
        "model": "qwen/qwen2.5-vl-72b-instruct",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Extract ALL text content from this image accurately and completely. "
                            "Include all numbers, names, dates, prices, and details exactly as shown. "
                            "Preserve the original language (Chinese/English). "
                            "Output the raw extracted text only — no commentary."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
    }

    with httpx.Client(timeout=60) as client:
        resp = client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


@traceable(name="create_knowledge_article", run_type="chain")
def create_knowledge_article(
    text: str,
    image_bytes: bytes | None = None,
    image_url: str | None = None,
    image_filename: str | None = None,
    file_bytes: bytes | None = None,
    file_name: str | None = None,
    source: str = "assistant",
    skip_duplicate_check: bool = False,
) -> dict:
    """Generate article via LLM, check duplicates, create in Odoo Knowledge.

    Returns dict with keys: success, duplicate, article_id, title, url, message
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Resolve image bytes from URL if needed (do this early so vision can use them)
    if image_bytes is None and image_url:
        image_bytes = _download_url(image_url)

    # Compute image hash for reliable duplicate detection across different days
    image_hash: str | None = None
    if image_bytes:
        image_hash = hashlib.md5(image_bytes).hexdigest()

    # If no text but image is present, extract text via vision LLM
    if not text.strip() and image_bytes and image_filename:
        try:
            text = extract_text_from_image(image_bytes, image_filename)
        except Exception:
            text = f"[Image: {image_filename}]"

    # Guard: a bare source citation / link (no real article body) isn't enough to write
    # from — skip the LLM call entirely rather than risk it inventing facts to fill the
    # template. Threshold is well under any real article's length.
    if len(text.strip()) < 60:
        return {
            "success": False,
            "duplicate": False,
            "message": "⚠️ 內容不足，未能生成知識文章（僅收到來源引用/連結，沒有實際文章內容）。",
        }

    # Generate article HTML via Qwen on OpenRouter — better HTML format compliance than Azure o-series
    prompt = ARTICLE_PROMPT.format(content=text[:6000], today=today)
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={"model": "qwen/qwen-2.5-72b-instruct", "messages": [{"role": "user", "content": prompt}], "max_tokens": 2000, "temperature": 0},
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"] or ""
    except Exception:
        raw = ""
    try:
        generated = parse_json_response(raw)
    except Exception:
        generated = {}

    if generated.get("insufficient_content"):
        return {
            "success": False,
            "duplicate": False,
            "message": "⚠️ 內容不足，未能生成知識文章（來源內容缺乏實際文章內容）。",
        }

    title = generated.get("title") or f"{today} | Article"
    body = generated.get("body") or f"<p>{text[:4000]}</p>"

    # The LLM writes "原文來源：<url>" as plain text — wrap any bare URL in that line
    # with a real <a href> so it's actually clickable (previously only file-upload
    # articles got a clickable link, via the docs_link injection below).
    import re as _re_link

    def _linkify_source_line(m: "_re_link.Match") -> str:
        prefix, content, suffix = m.group(1), m.group(2), m.group(3)
        # Printable-ASCII only, not [^\s<>"')]+ — that also matches CJK characters
        # appended directly with no separator (e.g. "http://on.cc東網", a source
        # citation like "on.cc東網" that isn't a real link, just text that happens
        # to start with "http://"). Real URLs don't contain raw literal CJK.
        content = _re_link.sub(
            r'https?://[!-~]+',
            lambda u: f'<a href="{u.group(0)}" target="_blank" rel="noopener">{u.group(0)}</a>',
            content,
        )
        return prefix + content + suffix

    body = _re_link.sub(
        r"(<p>原文來源：)(.*?)(</p>)", _linkify_source_line, body, count=1, flags=_re_link.S
    )

    # Duplicate check — image hash first, then title
    existing = None if skip_duplicate_check else check_duplicate(title, image_hash=image_hash)
    if existing:
        return {
            "success": False,
            "duplicate": True,
            "article_id": existing["id"],
            "title": existing["name"],
            "url": f"{ODOO_URL}/knowledge/article/{existing['id']}",
            "message": (
                f"⚠️ Already exists:\n{existing['name']}\n"
                f"{ODOO_URL}/knowledge/article/{existing['id']}\n\n"
                "Reply *yes* to process anyway, or *no* to cancel."
            ),
        }

    # Upload source file (image or PDF) to Odoo Documents, inject download link into footer.
    # upload_image() accepts any file type despite its name.
    _upload_bytes = image_bytes or file_bytes
    _upload_name = image_filename or file_name
    if _upload_bytes and _upload_name:
        img_url = upload_image(_upload_bytes, _upload_name)
        if img_url:
            import re
            _ext = _upload_name.rsplit(".", 1)[-1].lower() if "." in _upload_name else ""
            _link_label = "下載原始圖片（Documents）" if _ext in ("jpg", "jpeg", "png", "gif", "webp") else "下載原始文件（Documents）"
            docs_link = f' ｜ <a href="{img_url}">{_link_label}</a>'
            # Use regex so it works regardless of whether body has newlines
            new_body = re.sub(
                r'(<p>原文來源：[^<]*?)\s*(</p>)',
                lambda m: m.group(1) + docs_link + m.group(2),
                body,
                count=1,
            )
            body = new_body if new_body != body else body + f'\n<p>{docs_link.strip()}</p>'

    # Embed image hash as hidden comment so future duplicate checks find it
    if image_hash:
        body += f'\n<!-- image_hash:{image_hash} -->'

    # Create article
    article_id = _exec("knowledge.article", "create", [{
        "name": title,
        "icon": False,
        "parent_id": KNOWLEDGE_PARENT_ID,
        "body": body,
    }])

    # Set visible to all internal users
    _exec("knowledge.article", "write", [[article_id], {"is_article_visible_by_everyone": True}])

    # Add Stephen as member
    _exec("knowledge.article.member", "create", [{
        "article_id": article_id,
        "partner_id": STEPHEN_PARTNER_ID,
        "permission": "write",
    }])

    url = f"{ODOO_URL}/knowledge/article/{article_id}"
    return {
        "success": True,
        "duplicate": False,
        "article_id": article_id,
        "title": title,
        "url": url,
        "message": f"✅ Article created:\n{title}\n{url}",
    }
