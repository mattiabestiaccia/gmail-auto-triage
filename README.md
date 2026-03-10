# Gmail Auto-Triage

Automatically classify your unread Gmail emails using an LLM and apply labels — runs unattended via cron.

```
Fetching unread emails (window: 720h, max: 100)...
Fetched 17 emails.

Classifying...
  ✓ Newsletter    — Your weekly Python digest
  ✓ Recruiting    — Re: Colloquio tecnico — Mattia Bruscia
  ✓ Finance       — Il tuo estratto conto di marzo è pronto
  ✓ Job Alerts    — 12 nuove offerte per AI Engineer a Milano
  ~ _Ambiguous    — Aggiornamento importante sul tuo account
  ...

Results: 14 classified, 3 ambiguous, 0 errors
Labels applied in Gmail under AutoTriage/
```

## What it does

- Fetches unread emails from Gmail via the Gmail API
- Classifies each email using **Gemini Flash** (sender, subject, snippet)
- Applies `AutoTriage/<Category>` labels in Gmail
- Ambiguous emails get `AutoTriage/_Ambiguous`
- Already-labeled emails are skipped (idempotent)
- Optionally sends a summary email after each run (`--notify`)

Categories are fully configurable via a YAML file — no code changes needed.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A Google account with Gmail
- A [Gemini API key](https://aistudio.google.com/app/apikey) (free tier is sufficient)
- A Google Cloud project with the Gmail API enabled

> **First time?** Follow the [Setup Guide](SETUP.md) to configure Google Cloud and get your credentials.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/mattiabestiaccia/gmail-auto-triage.git
cd gmail-auto-triage

# Install dependencies
uv sync

# Configure (see SETUP.md for credentials setup)
cp .env.example .env
# edit .env and set your GEMINI_API_KEY

# First run — opens browser for Gmail authorization
uv run email-triage --dry-run

# Run for real
uv run email-triage
```

## Configuration

Edit `categories.yaml` to define your categories:

```yaml
categories:
  - name: Finance
    description: "Banking notifications, invoices, receipts, and financial statements"
    examples:
      - "Your credit card statement is ready"
      - "Payment received: Invoice #1234"

  - name: Recruiting
    description: "Direct communications with recruiters, HR, interview scheduling"
    examples:
      - "Re: Colloquio tecnico — Mattia Bruscia"

fetch:
  processing_window_hours: 24   # How far back to look
  max_emails: 100               # Max emails per run
```

The more specific your descriptions and examples, the better the classification.

## CLI Options

```
uv run email-triage [options]

  --config, -c PATH       Categories YAML file (default: categories.yaml)
  --dry-run               Classify emails but do not apply labels
  --verbose, -v           Show email previews during classification
  --notify                Send summary email after each run
  --window-hours N        Override processing window (hours)
  --max-emails N          Override max emails per run
  --log-file PATH         Write structured JSON logs to file
  --log-level LEVEL       DEBUG / INFO / WARNING / ERROR
```

## Running on a Schedule (cron)

```bash
# Edit crontab
crontab -e

# Run every hour, log to file
0 * * * * cd /path/to/gmail-auto-triage && uv run email-triage --log-file email_triage.log
```

Exit codes: `0` success · `1` fatal error · `130` interrupted

## Labels in Gmail

The tool creates labels under the `AutoTriage/` namespace:

| Label | Meaning |
|---|---|
| `AutoTriage/Finance` | Classified as Finance |
| `AutoTriage/Newsletter` | Classified as Newsletter |
| `AutoTriage/_Ambiguous` | Low confidence, needs manual review |

Labels are created automatically on first run.

## Project Structure

```
├── categories.yaml          # Your category definitions
├── credentials/             # OAuth2 credentials (gitignored)
│   ├── credentials.json     # Downloaded from Google Cloud Console
│   └── token.json           # Auto-generated on first run
├── .env                     # GEMINI_API_KEY (gitignored)
└── src/email_triage/        # Source code
```

## Tech Stack

- **Gmail API** — fetch and label emails
- **Gemini Flash** — LLM classification with structured JSON output
- **google-genai** — Gemini SDK with response schema validation
- **rapidfuzz** — fuzzy category matching for edge cases
- **tenacity** — retry logic for API rate limits
- **python-json-logger** — structured logging

## Setup

See [SETUP.md](SETUP.md) for the complete step-by-step guide.

---

*Built with [Claude Code](https://claude.ai/claude-code)*
