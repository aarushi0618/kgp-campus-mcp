# KGP Campus Intelligence - 24/7 Cloud Webhook

An isolated, 24/7 asynchronous FastAPI webhook service designed to listen for campus WhatsApp notifications from Android (MacroDroid), extract structured event details via Google Gemini, and persist them into a PostgreSQL (or SQLite) database.

---

## 1. Project Setup & Environment Configuration

Create a `.env` file in the `cloud_webhook/` directory:

```bash
# Gemini API Key for event parsing
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Database Connection URL
# Option A: Local SQLite (default for testing):
DATABASE_URL=sqlite+aiosqlite:///./webhook.db

# Option B: Supabase PostgreSQL:
# Supabase provides: postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
# The service automatically transforms postgresql:// into postgresql+asyncpg://
# DATABASE_URL=postgresql+asyncpg://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres

# Option C: Neon PostgreSQL:
# Neon provides: postgresql://[user]:[password]@[endpoint].neon.tech/neondb?sslmode=require
# The service automatically transforms it to postgresql+asyncpg:// and ssl=require
# DATABASE_URL=postgresql+asyncpg://[user]:[password]@[endpoint].neon.tech/neondb?ssl=require

# Option D: Render / Railway internal PostgreSQL:
# DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname
```

---

## 2. Running Locally

1. Open your terminal and navigate to the `cloud_webhook` directory:
   ```bash
   cd cloud_webhook
   ```

2. (Optional) Create and activate a dedicated virtual environment:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Start the server with Uvicorn:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

5. Test the health check endpoint:
   ```bash
   curl http://localhost:8000/
   # Response: {"status": "healthy"}
   ```

6. Test event posting:
   ```bash
   curl -X POST http://localhost:8000/webhook/whatsapp \
     -H "Content-Type: application/json" \
     -d '{
       "group_name": "IIT KGP Batch of 2027",
       "message": "Hey everyone! The Data Science Society is conducting an introductory workshop on Deep Learning on 2026-11-05 at 5:00 PM in Kalidas Auditorium. Register before tomorrow!"
     }'
   ```

---

## 3. Deploying to Render.com

1. **Create a GitHub Repository**:
   - Push this codebase to GitHub.

2. **Provision PostgreSQL Database on Render**:
   - On your Render dashboard, click **New +** -> **PostgreSQL**.
   - Note the **Internal Database URL** (or External URL if deploying across accounts).

3. **Deploy the Web Service**:
   - Click **New +** -> **Web Service**.
   - Connect your GitHub repository.
   - Configure the service settings:
     - **Root Directory**: `cloud_webhook`
     - **Runtime**: `Python 3`
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
     - **Health Check Path**: `/`

4. **Add Environment Variables**:
   Under the **Environment** tab in Render:
   - `GEMINI_API_KEY`: `<Your Google Gemini API Key>`
   - `DATABASE_URL`: `<Render PostgreSQL Internal/External URL>`
   - `GEMINI_MODEL`: `gemini-2.5-flash`

---

## 4. Deploying to Railway.app

1. **New Project**:
   - In Railway, click **New Project** -> **Deploy from GitHub repo**.
   - Choose your repository.

2. **Configure Service Settings**:
   - In the service **Settings**:
     - **Root Directory**: `cloud_webhook`
     - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

3. **Add PostgreSQL (Optional if using Supabase/Neon)**:
   - Click **New** -> **Database** -> **Add PostgreSQL**.
   - Connect the database variable by setting `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`.

4. **Set Variables**:
   - `GEMINI_API_KEY`: `<Your Google Gemini API Key>`
   - `DATABASE_URL`: `<Your Railway, Supabase, or Neon Postgres URL>`

---

## 5. MacroDroid Android Configuration

[MacroDroid](https://macrodroid.com/) captures incoming notifications on your Android device and posts them directly to your webhook.

### Step 1: Create a Macro
- Name: `Forward KGP WhatsApp to Webhook`

### Step 2: Configure Trigger
- **Category**: `Device Events` -> `Notification` -> `Notification Received`
- **Select Application**: Choose `WhatsApp` (and/or `WhatsApp Business`)
- **Text Content**: Select `Any Content`
- *(Optional)* Match specific campus groups: Enter group name filters (e.g., `*KGP*`, `*Notice*`, `*Hall*`).

### Step 3: Configure Action
- **Category**: `Connectivity` -> `HTTP Request`
- **Request Method**: `POST`
- **URL**: `https://<your-render-app-name>.onrender.com/webhook/whatsapp`
- **Content Type**: `application/json`
- **Request Body (JSON Text)**:
  ```json
  {
    "group_name": "[not_title]",
    "message": "[not_text]"
  }
  ```
  *(Note: `[not_title]` is the MacroDroid magic text token for notification title/sender, and `[not_text]` is the message content).*
- **Block Next Actions**: Checked
- **Timeout**: `30 seconds`

### Step 4: Test & Verify
1. Send a test message in a monitored WhatsApp group.
2. Check MacroDroid's System Log to verify the HTTP POST was dispatched.
3. Check Render's runtime logs to see the incoming message, Gemini's structured extraction, and the database insert.
