"""Streamlit Dashboard for Document Processor."""

# Version for deployment verification
__version__ = "2026.05.23.v5"

import os
import json
import streamlit as st
from datetime import datetime, timedelta, timezone
from typing import Any

st.set_page_config(
    page_title="Document Processor",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============ Load Secrets into Environment ============
# Streamlit Cloud stores secrets in st.secrets, but some libraries (like LangSmith)
# expect environment variables. Load them early before any imports that use them.

def load_secrets_to_env():
    """Load Streamlit secrets into environment variables."""
    secret_keys = [
        "LANGCHAIN_API_KEY",
        "LANGCHAIN_PROJECT",
        "LANGCHAIN_TRACING_V2",
        "AZURE_SEARCH_ENDPOINT",
        "AZURE_SEARCH_API_KEY",
        "AZURE_SEARCH_INDEX",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_KEY",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
        "OPENROUTER_API_KEY",
        "AZURE_FUNCTION_URL",
        "TAVILY_API_KEY",
    ]
    try:
        for key in secret_keys:
            if key in st.secrets and key not in os.environ:
                os.environ[key] = st.secrets[key]
    except Exception:
        pass  # Secrets not available (local dev)

load_secrets_to_env()

# ============ Authentication ============

def auth_is_configured():
    """Check if authentication is configured in secrets."""
    try:
        # Auth is configured if passwords or OAuth providers are set
        return "passwords" in st.secrets or "auth" in st.secrets
    except Exception:
        return False


def check_authentication():
    """Check if user is authenticated. Returns True if auth passes or not required."""
    # Skip auth for explicit local development
    if os.environ.get("STREAMLIT_LOCAL_DEV") == "true":
        return True

    # Skip auth if no auth is configured (local dev without secrets)
    if not auth_is_configured():
        return True

    # Check password-based login (session state)
    if st.session_state.get("authenticated"):
        return True

    # Check if st.user is available and has is_logged_in (OAuth)
    try:
        if st.user.is_logged_in:
            return True
    except (AttributeError, KeyError):
        pass

    return False


def check_password_login(username: str, password: str) -> bool:
    """Verify username/password against secrets."""
    try:
        if "passwords" in st.secrets:
            stored_password = st.secrets["passwords"].get(username)
            if stored_password and stored_password == password:
                return True
    except Exception:
        pass
    return False


def render_login_page():
    """Render the login page."""
    # Center the login box with responsive margins
    _, center, _ = st.columns([1, 2, 1])

    with center:
        st.write("")
        st.write("")
        st.title("Document Processor")
        st.subheader("Century 21 Property Intelligence")
        st.write("")
        st.write("Please sign in to access the dashboard.")
        st.write("")

        # Password login form
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

            if submitted:
                if check_password_login(username, password):
                    st.session_state["authenticated"] = True
                    st.session_state["auth_user"] = username
                    st.rerun()
                else:
                    st.error("Invalid username or password")

        st.write("")
        st.caption("Access is restricted to authorized users only.")


# Check authentication before loading the rest of the app
if not check_authentication():
    render_login_page()
    st.stop()

# ============ Load Dependencies After Auth ============

from dotenv import load_dotenv
load_dotenv()

from langsmith import Client
import httpx


HK_TZ = timezone(timedelta(hours=8))

# Display names for document types
DOC_TYPE_LABELS = {
    "listing": "Single Listing",
    "listing_list": "Multi Listing",
    "pitching_deck": "Pitching Deck",
    "news": "News",
    "contact": "Contact",
    "unknown": "Unknown",
}

def format_doc_type(doc_type: str) -> str:
    """Convert internal doc type to display label."""
    return DOC_TYPE_LABELS.get(doc_type, doc_type.replace("_", " ").title())


def render_image_gallery(image_urls: list, max_images: int = 5):
    """Render a horizontal image gallery with thumbnails.

    Args:
        image_urls: List of image URLs
        max_images: Maximum images to display
    """
    if not image_urls:
        return

    urls = image_urls[:max_images]
    cols = st.columns(min(len(urls), 5))

    for idx, url in enumerate(urls):
        with cols[idx % len(cols)]:
            st.image(url, use_container_width=True)


# ============ LangSmith Functions ============

@st.cache_data(ttl=30)  # Cache for 30 seconds
def get_langsmith_runs(hours: int = 72) -> list:
    # Get API key from secrets or environment
    try:
        api_key = st.secrets.get("LANGCHAIN_API_KEY", None)
    except Exception:
        api_key = None
    api_key = api_key or os.environ.get("LANGCHAIN_API_KEY")

    # Debug: show key source (remove after fixing)
    if api_key:
        key_preview = api_key[:10] + "..." if len(api_key) > 10 else api_key
        st.caption(f"Debug: Using API key starting with: {key_preview}")
    else:
        st.caption("Debug: No API key found!")

    client = Client(api_key=api_key)
    try:
        project_name = st.secrets.get("LANGCHAIN_PROJECT", None)
    except Exception:
        project_name = None
    project_name = project_name or os.environ.get("LANGCHAIN_PROJECT", "document-processor")
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Get parent runs (process_file)
    runs = list(client.list_runs(
        project_name=project_name,
        filter='eq(name, "process_file")',
        start_time=start_time,
        limit=100,
    ))

    # Convert to serializable format for caching
    # Only include completed runs (have outputs or error)
    # Note: Per-file token tracking requires fetching grandchild runs which hits API limits
    # Token aggregate stats are fetched separately in get_token_stats()
    return [{
        "inputs": r.inputs,
        "outputs": r.outputs,
        "error": r.error,
        "start_time": r.start_time,
        "end_time": r.end_time,
        "id": str(r.id),
    } for r in runs if r.outputs is not None or r.error is not None]


@st.cache_data(ttl=30)  # Cache for 30 seconds
def get_token_stats(hours: int = 72) -> dict:
    """Get aggregate token usage from LLM runs."""
    try:
        api_key = st.secrets.get("LANGCHAIN_API_KEY", None)
    except Exception:
        api_key = None
    api_key = api_key or os.environ.get("LANGCHAIN_API_KEY")

    if not api_key:
        return {"total": 0, "prompt": 0, "completion": 0}

    client = Client(api_key=api_key)
    try:
        project_name = st.secrets.get("LANGCHAIN_PROJECT", None)
    except Exception:
        project_name = None
    project_name = project_name or os.environ.get("LANGCHAIN_PROJECT", "document-processor")
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Get LLM runs (classifier and extractor)
    llm_runs = list(client.list_runs(
        project_name=project_name,
        filter='eq(run_type, "llm")',
        start_time=start_time,
        limit=100,
    ))

    total_tokens = 0
    prompt_tokens = 0
    completion_tokens = 0

    for r in llm_runs:
        # Check direct attributes first
        total = getattr(r, 'total_tokens', 0) or 0
        prompt = getattr(r, 'prompt_tokens', 0) or 0
        completion = getattr(r, 'completion_tokens', 0) or 0

        # Also check extra.usage_metadata (where we store it from OpenRouter)
        extra = getattr(r, 'extra', {}) or {}
        usage_meta = extra.get('usage_metadata', {})
        if usage_meta:
            total = total or usage_meta.get('total_tokens', 0)
            prompt = prompt or usage_meta.get('input_tokens', 0)
            completion = completion or usage_meta.get('output_tokens', 0)

        total_tokens += total
        prompt_tokens += prompt
        completion_tokens += completion

    return {
        "total": total_tokens,
        "prompt": prompt_tokens,
        "completion": completion_tokens,
    }


def parse_run(run: dict) -> dict[str, Any]:
    inputs = run.get("inputs") or {}
    outputs = run.get("outputs") or {}
    file_name = inputs.get("file_name", "Unknown")
    doc_type = "unknown"
    status = "error" if run.get("error") else "success"
    extracted_data: dict[str, Any] = {}
    confidence = 0.0

    output = outputs.get("output")
    if output:
        doc_type = output.get("document_type", "unknown") or "unknown"
        confidence = output.get("classification_confidence", 0.0) or 0.0
        extracted = output.get("extracted")
        if extracted:
            extracted_data = extracted.get("raw", {}) or {}
        state_status = output.get("status")
        if state_status and state_status.lower() == "error":
            status = "error"
        elif output.get("error_message"):
            status = "error"

    duration_ms = 0
    start_time = run.get("start_time")
    end_time = run.get("end_time")
    if end_time and start_time:
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

    return {
        "file_name": file_name,
        "document_type": doc_type,
        "confidence": confidence,
        "status": status,
        "extracted_data": extracted_data,
        "duration_ms": duration_ms,
        "processed_at": start_time,
        "run_id": run.get("id", ""),
    }


# ============ Vector DB Functions ============

@st.cache_data(ttl=30)  # Cache for 30 seconds
def get_vector_db_data() -> dict[str, Any]:
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    index = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")

    if not all([endpoint, api_key]):
        return {"error": "Azure Search not configured"}

    headers = {"api-key": api_key, "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=10) as client:
            count_url = f"{endpoint}/indexes/{index}/docs/$count?api-version=2024-07-01"
            count_resp = client.get(count_url, headers=headers)
            total_count = int(count_resp.text) if count_resp.status_code == 200 else 0

            search_url = f"{endpoint}/indexes/{index}/docs/search?api-version=2024-07-01"
            body = {
                "search": "*",
                "top": 1000,
                "select": "id,file_name,document_type,processed_at,extracted_data,image_urls",
                "orderby": "processed_at desc"
            }
            search_resp = client.post(search_url, headers=headers, json=body)
            docs = search_resp.json().get("value", []) if search_resp.status_code == 200 else []

            files: dict[str, dict] = {}
            by_type: dict[str, int] = {}
            for doc in docs:
                fname = doc.get("file_name", "Unknown")
                dtype = doc.get("document_type", "unknown")
                if fname not in files:
                    files[fname] = {
                        "file_name": fname,
                        "document_type": dtype,
                        "processed_at": doc.get("processed_at"),
                        "extracted_data": doc.get("extracted_data"),
                        "image_urls": doc.get("image_urls", []),
                        "chunk_count": 1,
                        "chunk_ids": [doc.get("id")]
                    }
                    by_type[dtype] = by_type.get(dtype, 0) + 1
                else:
                    files[fname]["chunk_count"] += 1
                    files[fname]["chunk_ids"].append(doc.get("id"))
                    # Merge image URLs from chunks
                    existing_urls = set(files[fname].get("image_urls", []))
                    new_urls = doc.get("image_urls", [])
                    files[fname]["image_urls"] = list(existing_urls | set(new_urls))

            return {
                "total_chunks": total_count,
                "total_files": len(files),
                "by_type": by_type,
                "files": list(files.values())
            }
    except Exception as e:
        return {"error": str(e)}


# ============ Processing Tab ============

def render_processing_tab():
    st.caption("Real-time data from LangSmith")

    try:
        runs = get_langsmith_runs(hours=72)
        parsed_runs = [parse_run(r) for r in runs]
        # Filter out hidden runs
        hidden = st.session_state.get("hidden_runs", set())
        parsed_runs = [r for r in parsed_runs if r["run_id"] not in hidden]
    except Exception as e:
        st.error(f"Failed to fetch from LangSmith: {e}")
        parsed_runs = []

    # Sort by time (newest first) then group by filename
    parsed_runs.sort(key=lambda x: x["processed_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    files_grouped: dict[str, dict] = {}
    for r in parsed_runs:
        name = r["file_name"]
        if name not in files_grouped:
            files_grouped[name] = {**r, "run_count": 1, "had_error": r["status"] == "error"}
        else:
            files_grouped[name]["run_count"] += 1
            if r["status"] == "error":
                files_grouped[name]["had_error"] = True
            # Prefer run with complete data if current entry has unknown type
            if files_grouped[name]["document_type"] == "unknown" and r["document_type"] != "unknown":
                files_grouped[name]["document_type"] = r["document_type"]
                files_grouped[name]["confidence"] = r["confidence"]
                files_grouped[name]["extracted_data"] = r["extracted_data"]

    grouped_runs = list(files_grouped.values())

    # Stats
    total = len(parsed_runs)
    success = sum(1 for r in parsed_runs if r["status"] == "success")
    errors = total - success
    today_hk = datetime.now(HK_TZ).date()
    today_count = sum(1 for r in parsed_runs if r["processed_at"] and r["processed_at"].astimezone(HK_TZ).date() == today_hk)

    # Token stats from LLM runs
    token_stats = get_token_stats(hours=72)
    total_tokens = token_stats["total"]
    total_prompt = token_stats["prompt"]
    total_completion = token_stats["completion"]

    # Cost estimate (DeepSeek via OpenRouter pricing - approximate)
    # Input: $0.14/1M tokens, Output: $0.28/1M tokens
    COST_PER_1M_INPUT = 0.14
    COST_PER_1M_OUTPUT = 0.28
    estimated_cost = (total_prompt / 1_000_000 * COST_PER_1M_INPUT +
                      total_completion / 1_000_000 * COST_PER_1M_OUTPUT)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("Today", today_count, f"{success} success" if today_count > 0 else None)
    with col2:
        st.metric("Total Processed", total)
    with col3:
        success_rate = (success / total * 100) if total > 0 else 100
        st.metric("Success Rate", f"{success_rate:.0f}%")
    with col4:
        st.metric("Errors", errors, delta_color="inverse")
    with col5:
        st.metric("Total Tokens", f"{total_tokens:,}")
    with col6:
        st.metric("Est. Cost", f"${estimated_cost:.4f}")

    st.divider()
    st.subheader("Recent Files")

    if not grouped_runs:
        st.info("No files processed yet.")
    else:
        # Pagination
        page_size = 20
        total_files = len(grouped_runs)
        total_pages = (total_files + page_size - 1) // page_size

        if "proc_page" not in st.session_state:
            st.session_state["proc_page"] = 0

        current_page = st.session_state["proc_page"]
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, total_files)
        page_runs = grouped_runs[start_idx:end_idx]

        h1, h2, h3, h4, h5 = st.columns([2.5, 1.2, 0.8, 0.5, 0.5])
        with h1: st.caption("**File Name**")
        with h2: st.caption("**Type**")
        with h3: st.caption("**Updated**")
        with h4: st.caption("**Status**")
        with h5: st.caption("**Data**")

        for idx, record in enumerate(page_runs):
            row_id = start_idx + idx  # Unique ID across pages
            run_count = record.get("run_count", 1)
            had_error = record.get("had_error", False)

            if record["status"] == "success":
                if run_count > 1 and had_error:
                    status_text, status_color = "Fixed", "blue"
                elif run_count > 1:
                    status_text, status_color = f"x{run_count}", "orange"
                else:
                    status_text, status_color = "OK", "green"
            else:
                status_text, status_color = "ERR", "red"

            doc_type = format_doc_type(record["document_type"])
            confidence = record.get("confidence", 0) * 100
            has_data = bool(record["extracted_data"])

            c1, c2, c3, c4, c5 = st.columns([2.5, 1.2, 0.8, 0.5, 0.5])
            with c1: st.markdown(f"**{record['file_name']}**")
            with c2: st.write(f"{doc_type} ({confidence:.0f}%)")
            with c3:
                if record["processed_at"]:
                    hk_time = record["processed_at"].astimezone(HK_TZ)
                    st.write(hk_time.strftime("%m/%d %H:%M"))
            with c4: st.markdown(f":{status_color}[{status_text}]")
            with c5:
                if has_data:
                    if st.button("View", key=f"view_{row_id}"):
                        st.session_state[f"show_data_{row_id}"] = not st.session_state.get(f"show_data_{row_id}", False)
                        st.rerun()
                else:
                    st.write("-")

            # Show data below if toggled
            if st.session_state.get(f"show_data_{row_id}", False) and has_data:
                st.json(record["extracted_data"])

        # Pagination controls
        if total_pages > 1:
            st.write("")
            p1, p2, p3 = st.columns([1, 2, 1])
            with p1:
                if current_page > 0:
                    if st.button("< Prev"):
                        st.session_state["proc_page"] = current_page - 1
                        st.rerun()
            with p2:
                st.write(f"Page {current_page + 1} of {total_pages} ({total_files} files)")
            with p3:
                if current_page < total_pages - 1:
                    if st.button("Next >"):
                        st.session_state["proc_page"] = current_page + 1
                        st.rerun()

    # Footer
    st.divider()
    col_btn1, col_btn2, _ = st.columns([1, 1.5, 2])
    with col_btn1:
        if st.button("Refresh"):
            st.cache_data.clear()
            st.rerun()
    with col_btn2:
        if st.button("Process Now"):
            function_url = os.environ.get("AZURE_FUNCTION_URL")
            if function_url:
                try:
                    with st.spinner("Processing..."):
                        response = httpx.post(f"{function_url}/api/process", timeout=300)
                        result = response.json()
                        if result.get("processed", 0) > 0:
                            st.success(f"Processed {result['processed']} file(s)")
                        else:
                            st.info("No files to process")
                        st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")


# ============ Vector DB Tab ============

def render_vector_db_tab():
    st.caption("Azure AI Search - Indexed Documents")

    data = get_vector_db_data()

    if "error" in data:
        st.error(f"Error: {data['error']}")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Files", data.get("total_files", 0))
    with col2:
        st.metric("Total Chunks", data.get("total_chunks", 0))
    with col3:
        avg = data["total_chunks"] / data["total_files"] if data["total_files"] > 0 else 0
        st.metric("Avg Chunks/File", f"{avg:.1f}")

    st.divider()

    by_type = data.get("by_type", {})
    if by_type:
        st.subheader("By Document Type")
        type_cols = st.columns(len(by_type))
        for i, (dtype, count) in enumerate(by_type.items()):
            with type_cols[i]:
                st.metric(format_doc_type(dtype), count)

    st.divider()
    st.subheader("Indexed Files")

    # Create filter options with formatted labels
    type_options = {format_doc_type(k): k for k in by_type.keys()}
    filter_label = st.selectbox("Filter by type", ["All"] + list(type_options.keys()), index=0)

    files = data.get("files", [])
    if filter_label != "All":
        filter_type = type_options[filter_label]
        files = [f for f in files if f.get("document_type") == filter_type]

    if not files:
        st.info("No documents found")
    else:
        # Pagination
        page_size = 20
        total_files = len(files)
        total_pages = (total_files + page_size - 1) // page_size

        if "vdb_page" not in st.session_state:
            st.session_state["vdb_page"] = 0

        current_page = st.session_state["vdb_page"]
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, total_files)
        page_files = files[start_idx:end_idx]

        h1, h2, h3, h4, h5 = st.columns([2.5, 1, 0.6, 0.8, 0.5])
        with h1: st.caption("**File Name**")
        with h2: st.caption("**Type**")
        with h3: st.caption("**Chunks**")
        with h4: st.caption("**Indexed**")
        with h5: st.caption("**Data**")

        for idx, f in enumerate(page_files):
            row_id = start_idx + idx
            fname = f.get("file_name", "?")
            ftype = format_doc_type(f.get("document_type", "unknown"))
            chunks = f.get("chunk_count", 1)
            proc_at = f.get("processed_at", "")
            extracted = f.get("extracted_data")
            image_urls = f.get("image_urls", [])

            if proc_at:
                try:
                    dt = datetime.fromisoformat(proc_at.replace("Z", "+00:00"))
                    proc_at = dt.astimezone(HK_TZ).strftime("%m/%d %H:%M")
                except Exception:
                    proc_at = proc_at[:16]

            c1, c2, c3, c4, c5 = st.columns([2.5, 1, 0.6, 0.8, 0.5])
            with c1: st.write(fname)
            with c2: st.write(ftype)
            with c3: st.write(chunks)
            with c4: st.write(proc_at)
            with c5:
                if extracted:
                    if st.button("View", key=f"vdb_view_{row_id}"):
                        st.session_state[f"vdb_show_{row_id}"] = not st.session_state.get(f"vdb_show_{row_id}", False)
                        st.rerun()
                else:
                    st.write("-")

            # Show data below if toggled
            if st.session_state.get(f"vdb_show_{row_id}", False):
                if extracted:
                    try:
                        if isinstance(extracted, str):
                            extracted = json.loads(extracted)
                        st.json(extracted)
                    except Exception:
                        st.code(str(extracted))
                if image_urls:
                    st.write("**Images:**")
                    render_image_gallery(image_urls)

        # Pagination controls
        if total_pages > 1:
            st.write("")
            p1, p2, p3 = st.columns([1, 2, 1])
            with p1:
                if current_page > 0:
                    if st.button("< Prev", key="vdb_prev"):
                        st.session_state["vdb_page"] = current_page - 1
                        st.rerun()
            with p2:
                st.write(f"Page {current_page + 1} of {total_pages} ({total_files} files)")
            with p3:
                if current_page < total_pages - 1:
                    if st.button("Next >", key="vdb_next"):
                        st.session_state["vdb_page"] = current_page + 1
                        st.rerun()


# ============ Chat Tab ============

def render_chat_tab():
    """Render the Property Intelligence chatbot tab."""
    import uuid
    from src.nodes.chatbot import chat

    # Initialize thread_id for LangGraph memory (persists within session)
    if "chat_thread_id" not in st.session_state:
        st.session_state["chat_thread_id"] = str(uuid.uuid4())

    # Initialize chat messages for display
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Header
    st.caption("Property Intelligence Assistant | 物業智能助理")

    # Chat input at TOP
    prompt = st.text_input(
        "Ask about properties... 詢問物業資訊...",
        key="chat_input",
        placeholder="e.g. 中環有什麼寫字樓？ / What offices in Central?"
    )

    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        send_clicked = st.button("Send / 發送", type="primary", use_container_width=True)
    with col2:
        if st.button("Clear / 清除", use_container_width=True):
            # Reset both display messages and create new thread for memory
            st.session_state["chat_messages"] = []
            st.session_state["chat_thread_id"] = str(uuid.uuid4())
            st.session_state["last_prompt"] = None
            st.rerun()

    st.divider()

    # Process new message
    if (send_clicked or prompt) and prompt and prompt.strip():
        # Check if this is a new message (not already processed)
        if not st.session_state.get("last_prompt") == prompt:
            st.session_state["last_prompt"] = prompt
            thread_id = st.session_state["chat_thread_id"]

            # Add user message to display history
            st.session_state["chat_messages"].append({"role": "user", "content": prompt})

            # Show user message immediately
            with st.chat_message("user"):
                st.markdown(prompt)

            # Generate assistant response (non-streaming for reliability)
            with st.chat_message("assistant"):
                try:
                    with st.spinner("🔍 Searching and generating response... 搜尋並生成回覆中..."):
                        # Call non-streaming chat
                        result = chat(prompt, thread_id=thread_id)

                    answer = result.answer
                    sources = result.sources

                    # Display answer
                    st.markdown(answer)

                    # Show sources
                    if sources:
                        with st.expander("Sources / 資料來源", expanded=False):
                            for src in sources:
                                if src.get("type") == "web":
                                    st.write(f"🌐 [{src['file_name']}]({src.get('url', '')})")
                                else:
                                    st.write(f"📄 **{src['file_name']}** ({format_doc_type(src.get('document_type', 'unknown'))})")

                except Exception as e:
                    answer = f"Error: {str(e)}"
                    sources = []
                    st.error(f"Chat error: {str(e)}")

            # Add assistant response to display history
            st.session_state["chat_messages"].append({
                "role": "assistant",
                "content": answer,
                "sources": sources
            })

            # Rerun to update display
            st.rerun()

    # Display chat history (newest first near chat box, oldest at bottom)
    if not st.session_state["chat_messages"]:
        st.info("💬 Start a conversation by asking about Hong Kong commercial properties.")
        st.caption("**Examples:**")
        st.caption("• What offices are available in Central?")
        st.caption("• 中環有什麼寫字樓出租？")
        st.caption("• Recommend a 2000 sqft office under HK$50,000")
        st.caption("• 比較銅鑼灣和尖沙咀的租金")
    else:
        # Group messages into Q&A pairs, then reverse pairs (newest first)
        # Each pair: [user question, assistant answer]
        messages = st.session_state["chat_messages"]
        pairs = []
        i = 0
        while i < len(messages):
            if messages[i]["role"] == "user":
                pair = [messages[i]]
                # Check if next message is assistant response
                if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                    pair.append(messages[i + 1])
                    i += 2
                else:
                    i += 1
                pairs.append(pair)
            else:
                # Orphan assistant message (shouldn't happen normally)
                pairs.append([messages[i]])
                i += 1

        # Display pairs in reverse order (newest first), but Q then A within each pair
        for pair in reversed(pairs):
            for msg in pair:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
                    if msg.get("sources") and msg["role"] == "assistant":
                        with st.expander("Sources / 資料來源", expanded=False):
                            for src in msg["sources"]:
                                if src.get("type") == "web":
                                    st.write(f"🌐 [{src['file_name']}]({src.get('url', '')})")
                                else:
                                    st.write(f"📄 **{src['file_name']}** ({format_doc_type(src.get('document_type', 'unknown'))})")


# ============ Search Tab ============

def render_search_tab():
    """Render direct search tab - keyword search without LLM."""
    from src.nodes.chatbot import keyword_search

    st.caption("Direct Property Search | 直接物業搜尋")

    # Common HK districts for filtering (English names used as keys, display both)
    HK_DISTRICTS = [
        ("All Districts", "All Districts"),
        ("Central", "Central 中環"),
        ("Admiralty", "Admiralty 金鐘"),
        ("Wan Chai", "Wan Chai 灣仔"),
        ("Causeway Bay", "Causeway Bay 銅鑼灣"),
        ("North Point", "North Point 北角"),
        ("Quarry Bay", "Quarry Bay 鰂魚涌"),
        ("Tsim Sha Tsui", "Tsim Sha Tsui 尖沙咀"),
        ("Mong Kok", "Mong Kok 旺角"),
        ("Kowloon Bay", "Kowloon Bay 九龍灣"),
        ("Kwun Tong", "Kwun Tong 觀塘"),
        ("Cheung Sha Wan", "Cheung Sha Wan 長沙灣"),
        ("Lai Chi Kok", "Lai Chi Kok 荔枝角"),
        ("Tsuen Wan", "Tsuen Wan 荃灣"),
        ("Kwai Chung", "Kwai Chung 葵涌"),
    ]

    # Search form - 4 columns
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])

    with col1:
        search_query = st.text_input(
            "Search keywords 搜尋關鍵字",
            placeholder="e.g. building name / address",
            key="search_query"
        )

    with col2:
        doc_type_filter = st.selectbox(
            "Type 類型",
            options=["All", "listing", "listing_list", "pitching_deck", "news", "contact"],
            format_func=lambda x: {
                "All": "All Types",
                "listing": "Single Listing",
                "listing_list": "Multi Listing",
                "pitching_deck": "Pitching Deck",
                "news": "News",
                "contact": "Contact"
            }.get(x, x),
            key="search_doc_type"
        )

    with col3:
        district_filter = st.selectbox(
            "District 地區",
            options=[d[0] for d in HK_DISTRICTS],
            format_func=lambda x: dict(HK_DISTRICTS).get(x, x),
            key="search_district"
        )

    with col4:
        st.write("")  # Spacing
        search_clicked = st.button("Search 搜尋", type="primary", use_container_width=True)

    st.divider()

    # Perform search
    if search_clicked or search_query or district_filter != "All Districts":
        filters = {}
        if doc_type_filter != "All":
            filters["document_type"] = doc_type_filter
        if district_filter != "All Districts":
            filters["district"] = district_filter

        with st.spinner("Searching... 搜尋中..."):
            results = keyword_search(
                query=search_query,
                filters=filters,
                top_k=100  # Fetch more to allow for client-side filtering
            )

        if not results:
            st.info("No results found. 找不到結果。")
        else:
            st.success(f"Found {len(results)} results 找到 {len(results)} 個結果")

            # Display results as cards
            for doc in results:
                doc_type = doc.get("document_type", "unknown")
                file_name = doc.get("file_name", "Unknown")
                extracted = doc.get("extracted_data", {})
                image_urls = doc.get("image_urls", [])

                with st.container():
                    # Header with document type badge
                    type_colors = {
                        "listing": "🏢",
                        "listing_list": "🏗️",
                        "pitching_deck": "📊",
                        "news": "📰",
                        "contact": "👤"
                    }
                    icon = type_colors.get(doc_type, "📄")

                    st.markdown(f"### {icon} {file_name}")

                    if doc_type == "listing":
                        col_a, col_b, col_c = st.columns(3)
                        with col_a:
                            st.write(f"**Building:** {extracted.get('building_name', 'N/A')}")
                            st.write(f"**Address:** {extracted.get('address', 'N/A')}")
                        with col_b:
                            st.write(f"**Size:** {extracted.get('size_sqft', 'N/A')} sqft")
                            st.write(f"**Rent:** HK${extracted.get('rent_monthly', 'N/A')}/mo")
                        with col_c:
                            st.write(f"**Type:** {extracted.get('property_type', 'N/A')}")
                            st.write(f"**Contact:** {extracted.get('contact_phone', 'N/A')}")

                    elif doc_type == "listing_list":
                        # listing_list stores data in items array
                        items = extracted.get("items", [])
                        if items:
                            st.write(f"**Properties:** {len(items)} buildings")
                            # Show each building with its units
                            for i, item in enumerate(items[:5]):  # Show max 5 buildings
                                building = item.get('building_name', 'N/A')
                                district = item.get('district', '')
                                address = item.get('address', '')
                                units = item.get('units', [])

                                with st.expander(f"{building} ({district})" if district else building, expanded=(i==0)):
                                    if address:
                                        st.write(f"**Address:** {address}")
                                    if units:
                                        unit_data = []
                                        for u in units[:10]:
                                            unit_data.append({
                                                "Floor": u.get("floor", ""),
                                                "Unit": u.get("unit", ""),
                                                "Size (sqft)": u.get("size", ""),
                                                "Rent (HK$)": u.get("rent", ""),
                                            })
                                        if unit_data:
                                            st.dataframe(unit_data, use_container_width=True, hide_index=True)
                            if len(items) > 5:
                                st.caption(f"... and {len(items) - 5} more buildings")
                        else:
                            st.write("No property data extracted")

                    elif doc_type == "pitching_deck":
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.write(f"**Project:** {extracted.get('project_name', 'N/A')}")
                            st.write(f"**Developer:** {extracted.get('developer', 'N/A')}")
                            st.write(f"**Address:** {extracted.get('address', 'N/A')}")
                            st.write(f"**District:** {extracted.get('district', 'N/A')}")
                        with col_b:
                            summary = extracted.get("project_summary", {})
                            if summary:
                                st.write(f"**Retail:** {summary.get('retail_area_sqft', 'N/A')} sqft")
                                st.write(f"**Office:** {summary.get('office_area_sqft', 'N/A')} sqft")
                                st.write(f"**Residential:** {summary.get('residential_units', 'N/A')} units")
                            st.write(f"**Availability:** {extracted.get('availability_date', 'N/A')}")

                        # Show available units if any
                        available_units = extracted.get("available_units", [])
                        if available_units:
                            st.write(f"**Available Units:** {len(available_units)}")
                            unit_data = []
                            for u in available_units[:10]:
                                unit_data.append({
                                    "Unit": u.get("unit", ""),
                                    "Floor": u.get("floor", ""),
                                    "Size (sqft)": u.get("size_sqft", ""),
                                    "Facing": u.get("facing", ""),
                                    "Features": u.get("features", ""),
                                })
                            if unit_data:
                                st.dataframe(unit_data, use_container_width=True, hide_index=True)

                        # Show key features
                        features = extracted.get("key_features", [])
                        if features:
                            st.write(f"**Key Features:** {', '.join(features[:5])}")

                    elif doc_type == "news":
                        st.write(f"**Title:** {extracted.get('title', '')} {extracted.get('title_zh', '')}")
                        st.write(f"**Date:** {extracted.get('date', 'N/A')} | **Source:** {extracted.get('source', 'N/A')}")
                        if extracted.get("summary"):
                            st.write(f"**Summary:** {extracted.get('summary', '')[:200]}...")

                    elif doc_type == "contact":
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.write(f"**Name:** {extracted.get('name', 'N/A')}")
                            st.write(f"**Company:** {extracted.get('company', 'N/A')}")
                        with col_b:
                            st.write(f"**Phone:** {extracted.get('phone', 'N/A')}")
                            st.write(f"**Email:** {extracted.get('email', 'N/A')}")

                    else:
                        # Generic display
                        st.json(extracted)

                    # Display images if available
                    if image_urls:
                        with st.expander(f"Images ({len(image_urls)})", expanded=False):
                            render_image_gallery(image_urls)

                    st.divider()
    else:
        # Show instructions
        st.info("🔍 Enter keywords to search the property database directly.")
        st.caption("**Tips:**")
        st.caption("• Search by building name, address, or district")
        st.caption("• Filter by document type for specific results")
        st.caption("• Results show extracted data - no LLM processing")
        st.caption("• For AI-powered answers, use the Chat tab")


# ============ Main ============

def main():
    # Reduce top padding and enlarge tabs
    st.markdown("""
        <style>
        .block-container { padding-top: 1rem; }
        .stTabs [data-baseweb="tab-list"] { gap: 2rem; }
        .stTabs [data-baseweb="tab"] {
            font-size: 1.1rem;
            font-weight: 500;
            padding: 0.75rem 1.5rem;
        }
        </style>
    """, unsafe_allow_html=True)

    # Sidebar with user info and logout
    is_oauth_logged_in = False
    try:
        is_oauth_logged_in = st.user.is_logged_in
    except (AttributeError, KeyError):
        pass

    is_password_logged_in = st.session_state.get("authenticated", False)

    if is_oauth_logged_in or is_password_logged_in:
        with st.sidebar:
            st.write("**Logged in as:**")
            if is_oauth_logged_in:
                st.write(st.user.email or "User")
            else:
                st.write(st.session_state.get("auth_user", "User"))
            st.write("")
            if st.button("Logout", use_container_width=True):
                if is_password_logged_in:
                    st.session_state["authenticated"] = False
                    st.session_state["auth_user"] = None
                    st.rerun()
                else:
                    st.logout()

    st.title("Document Processor")

    tab1, tab2, tab3, tab4 = st.tabs(["Processing Status", "Vector Database", "Search", "Chat"])

    with tab1:
        render_processing_tab()

    with tab2:
        render_vector_db_tab()

    with tab3:
        render_search_tab()

    with tab4:
        render_chat_tab()

    # Footer
    st.divider()
    hk_now = datetime.now(HK_TZ)
    st.caption(f"Last updated: {hk_now.strftime('%Y-%m-%d %H:%M:%S')} (HKT) | Version: {__version__}")


if __name__ == "__main__":
    main()
