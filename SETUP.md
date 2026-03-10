# Setup Guide

Complete step-by-step guide to set up Gmail Auto-Triage from scratch.

## Prerequisites

- Python 3.11+ — check with `python --version`
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- A Google account with Gmail

---

## Step 1 — Clone and install

```bash
git clone https://github.com/mattiabestiaccia/gmail-auto-triage.git
cd gmail-auto-triage
uv sync
```

---

## Step 2 — Get a Gemini API key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Click **Create API key**
3. Copy the key

Create a `.env` file in the project root:

```bash
echo "GEMINI_API_KEY=your_key_here" > .env
```

The free tier supports ~1,500 requests/day — more than enough for personal use.

---

## Step 3 — Set up Google Cloud (Gmail API)

You need a Google Cloud project with the Gmail API enabled and OAuth2 credentials.

### 3a — Create a project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown (top left) → **New Project**
3. Name it (e.g., `gmail-auto-triage`) → **Create**
4. Make sure the new project is selected

### 3b — Enable the Gmail API

1. In the search bar, search for **"Gmail API"**
2. Click **Enable**

### 3c — Configure the OAuth consent screen

1. Go to **APIs & Services** → **OAuth consent screen** (or **Google Auth Platform** in newer UI)
2. Click **Pubblico** / **Audience** in the sidebar
3. Set **User type** to **External**
4. Fill in the required fields:
   - **App name**: `Gmail Auto-Triage` (or anything)
   - **Support email**: your Gmail address
   - **Developer contact email**: your Gmail address
5. Click **Save and Continue** through the remaining steps

> **Publishing status:** Set to **"In produzione" / "Published"** (not Testing).
> In Testing mode, the OAuth token expires after 7 days, which breaks unattended cron runs.
> For personal use you don't need Google's verification — Published + Unverified is fine.

### 3d — Add Gmail API scopes

1. Go to **Accesso ai dati** / **Data Access** in the sidebar
2. Click **Add or remove scopes**
3. Search for and add: `https://www.googleapis.com/auth/gmail.modify`
4. Click **Update** → **Save and Continue**

### 3e — Create OAuth2 credentials

1. Go to **Client** / **Clients** in the sidebar (or **APIs & Services** → **Credentials**)
2. Click **Create credentials** → **OAuth client ID**
3. Application type: **Desktop app**
4. Name it (e.g., `gmail-auto-triage-desktop`) → **Create**
5. Click **Download JSON**
6. Rename the downloaded file to `credentials.json` and move it to the `credentials/` folder:

```bash
mkdir -p credentials
mv ~/Downloads/client_secret_*.json credentials/credentials.json
```

---

## Step 4 — First run (browser authorization)

```bash
uv run email-triage --dry-run
```

On first run:
- A browser window opens asking you to sign in with your Google account
- You'll see a warning "This app isn't verified" — click **Advanced** → **Go to Gmail Auto-Triage (unsafe)**
- Grant the requested permissions
- A `credentials/token.json` file is saved — you won't need to authorize again

The `--dry-run` flag classifies emails but doesn't apply any labels. Use it to verify everything works.

---

## Step 5 — Configure your categories

Edit `categories.yaml` to match your inbox:

```yaml
categories:
  - name: Finance
    description: "Banking notifications, invoices, receipts"
    examples:
      - "Your credit card statement is ready"
      - "Payment received: Invoice #1234"

  - name: Newsletter
    description: "Periodic newsletters and content digests"
    examples:
      - "Your weekly Python digest"

fetch:
  processing_window_hours: 24   # How far back to look on each run
  max_emails: 100               # Safety limit
```

Tips:
- Be specific in descriptions — the LLM uses them directly
- Add 3-5 representative examples per category
- Categories overlap? Add a note in the description (e.g., "NOT job platform alerts")

---

## Step 6 — Run for real

```bash
uv run email-triage
```

Check Gmail — you should see `AutoTriage/<Category>` labels applied to your unread emails.

---

## Step 7 — Automate with cron (optional)

```bash
crontab -e
```

Add a line (runs every hour):

```
0 * * * * cd /path/to/gmail-auto-triage && uv run email-triage --log-file email_triage.log 2>>err.log
```

Replace `/path/to/gmail-auto-triage` with the absolute path to the project directory.

To also receive a summary email after each run:

```
0 * * * * cd /path/to/gmail-auto-triage && uv run email-triage --notify --log-file email_triage.log 2>>err.log
```

---

## Troubleshooting

**`invalid_grant` error after a week**
The OAuth consent screen is in Testing mode. Switch to Published (Step 3c) and re-run the first authorization.

**`credentials/credentials.json not found`**
The credentials file is missing or in the wrong location. Re-download from Google Cloud Console → Clients and place it at `credentials/credentials.json`.

**`GEMINI_API_KEY not set`**
The `.env` file is missing or the key name is wrong. Check that `.env` contains `GEMINI_API_KEY=...`.

**Low classification accuracy**
Improve your category descriptions and examples in `categories.yaml`. The more specific, the better.

**An email wasn't classified**
- It might be in `AutoTriage/_Ambiguous` (low confidence)
- Emails with corrupted `Date:` headers (showing 1969) are silently skipped by Gmail's `after:` filter — known limitation
