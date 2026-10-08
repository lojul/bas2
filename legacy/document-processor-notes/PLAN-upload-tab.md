# Upload Tab Feature Plan

**Status:** Planning
**Created:** 2026-05-27
**Decision:** Pending

---

## Overview

Add an Upload tab to the dashboard that allows users to upload PDF files directly to OneDrive `/Document Processor/In` folder, triggering automatic document processing without opening OneDrive.

**User Flow:**
```
Dashboard Upload Tab → OneDrive /In → Azure Functions Timer → Processing → /Processed
```

---

## Current Architecture

### What Exists
| Component | Status | Location |
|-----------|--------|----------|
| OneDrive auth (Service Principal) | ✅ Ready | `src/nodes/onedrive.py` |
| Token acquisition | ✅ Ready | `get_access_token()` |
| File listing | ✅ Ready | `list_onedrive_files()` |
| File move | ✅ Ready | `move_to_processed()` |
| **File upload** | ❌ Missing | Need to add |
| Dashboard tabs | ✅ Ready | `dashboard.py` |

### Environment Variables (Already Configured)
```
MS_GRAPH_CLIENT_ID=<Azure App Client ID>
MS_GRAPH_TENANT_ID=<Azure AD Tenant ID>
MS_GRAPH_CLIENT_SECRET=<Client Secret>
MS_GRAPH_DRIVE_ID=<OneDrive Drive ID>
MS_GRAPH_INBOX_FOLDER=/Document Processor/In
```

---

## Design Options

### Option A: Direct Upload from Dashboard (Recommended)
```
User → Streamlit file_uploader → Python → Microsoft Graph API → OneDrive
```

**Pros:**
- Simple architecture
- No additional Azure costs
- Reuses existing auth
- Instant upload feedback

**Cons:**
- Streamlit Cloud has 200MB file limit
- Requires MS Graph secrets in Streamlit

### Option B: Upload via Azure Functions
```
User → Streamlit file_uploader → Azure Function HTTP endpoint → OneDrive
```

**Pros:**
- Secrets stay in Azure
- Can handle larger files
- Better for production security

**Cons:**
- More complex
- Additional latency
- Need new Azure Function endpoint

### Option C: Presigned URL Upload
```
User → Get presigned URL from backend → Direct upload to OneDrive
```

**Pros:**
- Large file support
- Reduced server load

**Cons:**
- OneDrive presigned uploads are complex
- More implementation effort

**Recommendation:** Start with **Option A** for simplicity, migrate to Option B if needed.

---

## Implementation Plan

### Phase 1: OneDrive Upload Function

**File:** `src/nodes/onedrive.py`

```python
@traceable(name="upload_to_onedrive", run_type="tool")
def upload_to_onedrive(
    file_bytes: bytes,
    file_name: str,
    folder_path: str = None  # Defaults to MS_GRAPH_INBOX_FOLDER
) -> dict:
    """Upload file to OneDrive folder.

    Uses Microsoft Graph API simple upload (< 4MB) or
    resumable upload session (> 4MB).

    Args:
        file_bytes: File content as bytes
        file_name: Name for the file in OneDrive
        folder_path: Target folder (default: /Document Processor/In)

    Returns:
        dict with: id, name, webUrl, size
    """
    # Microsoft Graph API endpoint:
    # PUT /drives/{drive-id}/root:/{folder-path}/{filename}:/content
```

**Upload Logic:**
```python
# For files < 4MB: Simple upload
PUT /drives/{driveId}/root:/{path}/{filename}:/content
Content-Type: application/octet-stream
Body: <file bytes>

# For files > 4MB: Resumable upload session
POST /drives/{driveId}/root:/{path}/{filename}:/createUploadSession
# Then upload in chunks
```

### Phase 2: Dashboard Upload Tab

**File:** `dashboard.py`

```python
# Add new tab
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Search", "Chat", "Upload", "Document Process", "Vector"
])

with tab3:  # Upload tab
    st.header("Upload Documents")
    st.caption("Upload PDFs to start processing automatically")

    # File uploader
    uploaded_files = st.file_uploader(
        "Drop PDF files here",
        type=["pdf"],
        accept_multiple_files=True,
        help="Files will be uploaded to OneDrive and processed automatically"
    )

    if uploaded_files:
        for file in uploaded_files:
            with st.spinner(f"Uploading {file.name}..."):
                result = upload_to_onedrive(
                    file_bytes=file.read(),
                    file_name=file.name
                )
                if result:
                    st.success(f"✅ {file.name} uploaded")
                else:
                    st.error(f"❌ {file.name} failed")

        st.info("Files will be processed within 5 minutes by the timer trigger.")
```

### Phase 3: Immediate Processing Option

Add optional "Process Now" after upload:

```python
if st.button("🚀 Process Now"):
    # Call Azure Function HTTP trigger
    response = httpx.post(
        os.environ["AZURE_FUNCTION_URL"],
        timeout=300
    )
    if response.status_code == 200:
        st.success("Processing started!")
```

---

## UI Design

### Upload Tab Layout

```
┌─────────────────────────────────────────────────────────┐
│  Upload Documents                                        │
│  Upload PDFs to start processing automatically           │
├─────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────┐  │
│  │                                                   │  │
│  │     📄 Drop PDF files here or click to browse     │  │
│  │                                                   │  │
│  │           Supported: PDF (max 50MB)               │  │
│  └───────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│  Uploaded Files:                                         │
│  ✅ document1.pdf (2.3 MB) - Uploaded                   │
│  ✅ document2.pdf (1.1 MB) - Uploaded                   │
│  ⏳ document3.pdf (5.2 MB) - Uploading...              │
├─────────────────────────────────────────────────────────┤
│  [🚀 Process Now]  or wait for auto-processing (5 min)  │
└─────────────────────────────────────────────────────────┘
```

---

## Technical Considerations

### File Size Limits

| Platform | Limit | Handling |
|----------|-------|----------|
| Streamlit Cloud | 200MB | OK for most PDFs |
| Microsoft Graph Simple Upload | 4MB | Use resumable for larger |
| Microsoft Graph Resumable | 60GB | Chunk upload |

### Conflict Handling

Reuse existing pattern:
```python
"@microsoft.graph.conflictBehavior": "replace"
```
- Same filename = overwrite existing
- No duplicate errors

### Error Handling

```python
try:
    result = upload_to_onedrive(file_bytes, file_name)
except httpx.HTTPStatusError as e:
    if e.response.status_code == 401:
        st.error("Authentication failed - check credentials")
    elif e.response.status_code == 507:
        st.error("OneDrive storage full")
    else:
        st.error(f"Upload failed: {e}")
```

### Security

- MS Graph credentials already in Streamlit secrets
- Service Principal has write access to `/Document Processor/In`
- No user credentials exposed
- Files go directly to controlled folder

---

## Secrets Required

Already in Streamlit Cloud secrets (verify these exist):
```toml
MS_GRAPH_CLIENT_ID = "..."
MS_GRAPH_TENANT_ID = "..."
MS_GRAPH_CLIENT_SECRET = "..."
MS_GRAPH_DRIVE_ID = "..."
```

---

## Implementation Phases

### Phase 1: Core Upload (MVP)
- [ ] Add `upload_to_onedrive()` function to `onedrive.py`
- [ ] Handle simple upload (< 4MB)
- [ ] Add Upload tab to dashboard
- [ ] Basic file uploader UI
- [ ] Success/error feedback
- [ ] Deploy and test

**Estimated:** ~200 lines of code

### Phase 2: Large File Support
- [ ] Implement resumable upload session
- [ ] Progress bar for large files
- [ ] Chunk upload with retry

### Phase 3: Enhanced UX
- [ ] Drag-and-drop styling
- [ ] Upload history in session
- [ ] "Process Now" button
- [ ] Link to Document Process tab after upload

### Phase 4: Advanced Features
- [ ] Duplicate detection (warn if file exists)
- [ ] File preview before upload
- [ ] Batch upload progress
- [ ] Cancel upload option

---

## Testing Plan

### Test Cases

1. **Single small PDF** (< 4MB)
   - Upload → Check OneDrive → Verify in /In folder

2. **Multiple files**
   - Upload 3 PDFs → All appear in OneDrive

3. **Large file** (> 4MB)
   - Upload 10MB PDF → Resumable upload works

4. **Duplicate filename**
   - Upload same file twice → Overwrites (no error)

5. **Invalid file type**
   - Try .docx → Rejected by uploader

6. **Process Now**
   - Upload → Click Process Now → Check LangSmith for trace

---

## Open Questions

1. Should we show upload history across sessions? (Requires database)
2. Maximum files per upload batch?
3. Should duplicate files show a warning before overwriting?
4. Add email notification when processing completes?

---

## Dependencies

No new dependencies required:
- `httpx` - Already installed (for API calls)
- `streamlit` - Already installed (file_uploader widget)
- `msal` - Already installed (authentication)

---

## References

- Current OneDrive code: `src/nodes/onedrive.py`
- Microsoft Graph Upload API: https://learn.microsoft.com/en-us/graph/api/driveitem-put-content
- Streamlit file_uploader: https://docs.streamlit.io/library/api-reference/widgets/st.file_uploader
