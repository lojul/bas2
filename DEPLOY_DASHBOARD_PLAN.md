# Deploy Dashboard to Streamlit Community Cloud

## Overview
Deploy the Streamlit dashboard with Google and Microsoft authentication.

**Cost: FREE**

---

## Step 1: Push Code to GitHub

Your repo should have these files:
```
langgraph/
├── dashboard.py                 # Main app (updated with auth)
├── requirements-dashboard.txt   # Dependencies for cloud
├── secrets.toml.example         # Template (don't commit real secrets!)
├── .streamlit/
│   └── config.toml              # Theme config
└── src/
    └── nodes/
        └── chatbot.py           # Chatbot with streaming
```

```bash
cd langgraph
git add .
git commit -m "Add Streamlit Cloud deployment with OAuth"
git push origin main
```

---

## Step 2: Set Up Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)

2. Create or select a project

3. Enable OAuth:
   - Go to **APIs & Services** → **Credentials**
   - Click **Configure Consent Screen**
   - Choose **External** → Create
   - Fill in:
     - App name: `C21 Document Processor`
     - User support email: your email
     - Developer email: your email
   - Save and Continue (skip scopes, test users for now)

4. Create OAuth Client:
   - Go to **Credentials** → **Create Credentials** → **OAuth client ID**
   - Application type: **Web application**
   - Name: `Streamlit Dashboard`
   - Authorized redirect URIs: (add after deployment, see Step 5)
   - Click **Create**

5. Copy and save:
   - **Client ID**: `xxxxx.apps.googleusercontent.com`
   - **Client Secret**: `GOCSPX-xxxxx`

---

## Step 3: Set Up Microsoft OAuth

1. Go to [Azure Portal](https://portal.azure.com/)

2. Navigate to **Microsoft Entra ID** (formerly Azure AD)

3. Go to **App registrations** → **New registration**
   - Name: `C21 Document Processor`
   - Supported account types: **Personal Microsoft accounts only**
     (or "Accounts in any organizational directory" for work accounts)
   - Redirect URI: Leave blank for now
   - Click **Register**

4. Copy the **Application (client) ID**

5. Go to **Certificates & secrets** → **New client secret**
   - Description: `Streamlit`
   - Expires: 24 months
   - Click **Add**
   - **Copy the Value immediately** (you can't see it again!)

6. Save:
   - **Client ID**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
   - **Client Secret**: `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

---

## Step 4: Deploy to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io/)

2. Sign in with GitHub

3. Click **New app**

4. Select your repository:
   - Repository: `your-username/document-processor`
   - Branch: `main`
   - Main file path: `langgraph/dashboard.py`

5. Click **Advanced settings** → **Secrets**

6. Paste your secrets (see template below)

7. Click **Deploy**

8. Note your app URL: `https://your-app-name.streamlit.app`

---

## Step 5: Update OAuth Redirect URIs

After deployment, update redirect URIs with your actual app URL:

### Google Cloud Console:
1. Go to **APIs & Services** → **Credentials**
2. Click your OAuth client
3. Add Authorized redirect URI:
   ```
   https://YOUR-APP-NAME.streamlit.app/oauth2callback
   ```
4. Save

### Azure Portal:
1. Go to **App registrations** → Your app
2. Go to **Authentication**
3. Add platform → **Web**
4. Redirect URI:
   ```
   https://YOUR-APP-NAME.streamlit.app/oauth2callback
   ```
5. Save

### Streamlit Secrets:
Update `redirect_uri` in your secrets to match:
```toml
[auth]
redirect_uri = "https://YOUR-APP-NAME.streamlit.app/oauth2callback"
```

---

## Step 6: Secrets Configuration

In Streamlit Cloud **App Settings** → **Secrets**, paste:

```toml
# ============ Authentication ============
[auth]
redirect_uri = "https://YOUR-APP-NAME.streamlit.app/oauth2callback"
cookie_secret = "your-random-32-character-string-here"

[auth.google]
client_id = "xxxxx.apps.googleusercontent.com"
client_secret = "GOCSPX-xxxxx"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[auth.microsoft]
client_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
client_secret = "your-microsoft-client-secret"
server_metadata_url = "https://login.microsoftonline.com/consumers/v2.0/.well-known/openid-configuration"

# ============ LangSmith ============
LANGCHAIN_API_KEY = "ls__your-key"
LANGCHAIN_PROJECT = "document-processor"
LANGCHAIN_TRACING_V2 = "true"

# ============ Azure AI Search ============
AZURE_SEARCH_ENDPOINT = "https://aisearch-eastasia-basic.search.windows.net"
AZURE_SEARCH_API_KEY = "your-search-key"
AZURE_SEARCH_INDEX = "processed-documents"

# ============ Azure OpenAI ============
AZURE_OPENAI_ENDPOINT = "https://your-openai.openai.azure.com"
AZURE_OPENAI_KEY = "your-openai-key"

# ============ OpenRouter ============
OPENROUTER_API_KEY = "sk-or-your-key"

# ============ Azure Functions ============
AZURE_FUNCTION_URL = "https://doc-processor-c21.azurewebsites.net"
```

### Generate cookie_secret:
```bash
python -c "import secrets; print(secrets.token_hex(16))"
```

---

## Step 7: Test Authentication

1. Open your app URL: `https://your-app-name.streamlit.app`

2. You should see the login page with:
   - "Sign in with Google" button
   - "Sign in with Microsoft" button

3. Test both login methods

4. After login, verify:
   - Dashboard loads with 3 tabs
   - Sidebar shows your email + logout button
   - Chat works with streaming

---

## Optional: Restrict Access to Specific Users

Edit `dashboard.py` and uncomment the email restriction:

```python
def check_authentication():
    # ... existing code ...

    # Uncomment and customize:
    allowed_emails = ["admin@c21hk.com", "user@c21hk.com"]
    allowed_domains = ["c21hk.com"]
    email = st.user.email or ""
    domain = email.split("@")[-1] if "@" in email else ""
    if email not in allowed_emails and domain not in allowed_domains:
        st.error("Access denied. Contact admin for access.")
        if st.button("Logout"):
            st.logout()
        st.stop()

    return True
```

---

## Troubleshooting

### "Invalid redirect URI" error
- Make sure redirect URI in Google/Microsoft matches exactly:
  `https://YOUR-APP-NAME.streamlit.app/oauth2callback`
- No trailing slash!

### "App not verified" warning (Google)
- Normal during testing
- Click "Advanced" → "Go to app (unsafe)" to proceed
- To remove: Submit app for Google verification

### Login works but dashboard shows error
- Check secrets are correctly formatted in Streamlit Cloud
- Check Azure API keys are valid
- View logs in Streamlit Cloud dashboard

### Local development with auth
- Set environment variable: `STREAMLIT_LOCAL_DEV=true`
- Or auth will be skipped automatically when not on cloud

---

## Architecture After Deployment

```
User → Streamlit Cloud (FREE)
         ↓
    Login (Google/Microsoft)
         ↓
    Dashboard (dashboard.py)
         ├── LangSmith API (traces)
         ├── Azure AI Search (vector DB)
         └── OpenRouter (LLM for chat)
```

---

## Costs

| Service | Cost |
|---------|------|
| Streamlit Cloud | **FREE** |
| Google OAuth | **FREE** |
| Microsoft OAuth | **FREE** |
| Azure AI Search | ~$70/mo (existing) |
| OpenRouter | Pay-per-use (existing) |
| LangSmith | Free tier |
