# Gmail Auto-Triage

## What This Is

Uno script standalone che categorizza automaticamente le email Gmail non lette applicando etichette `AutoTriage/*`, usando Gemini Flash per la classificazione LLM. Gira via cron senza intervento manuale — la inbox e' gia' organizzata quando viene aperta. Tool personale, per un singolo utente, con 134 test, retry robusto e summary email dopo ogni run.

## Core Value

Aprire Gmail e trovare le email gia' organizzate per categoria, senza alcuno sforzo manuale.

## Requirements

### Validated

- ✓ Lo script si connette a Gmail via API e recupera le email non lette — v1.0
- ✓ Ogni email viene classificata in una categoria tramite LLM (Gemini Flash) — v1.0
- ✓ Le categorie sono definite in un file di configurazione YAML — v1.0
- ✓ Le label corrispondenti vengono applicate in Gmail sotto `AutoTriage/` — v1.0
- ✓ Email non classificabili ricevono la label `AutoTriage/_Ambiguous` — v1.0
- ✓ Lo script invia un'email di log riepilogativa alla stessa inbox — v1.0
- ✓ Le email gia' etichettate non vengono riprocessate (idempotenza) — v1.0
- ✓ Lo script e' eseguibile via cron con frequenza multipla giornaliera — v1.0
- ✓ Comportamento conservativo: solo label, mai segnare come letto, mai archiviare — v1.0

### Active

(None — fresh requirements defined with `/gsd:new-milestone` for v1.1)

### Out of Scope

- Azioni distruttive automatiche (archiviazione, cancellazione) — il tool categorizza, l'utente decide
- Interfaccia web o GUI — e' uno script da terminale/cron
- Supporto multi-utente — tool personale
- Ricategorizzazione retroattiva — nuove categorie non retro-applicano su email gia' etichettate
- Prompt template override via config (CONF-04) — droppato da v1: le categorie YAML bastano come customizzazione

## Context

- Shipped v1.0 con ~4.300 LOC Python (src layout, uv, lockfile)
- Tech stack: Python 3.11, Gmail API, Gemini Flash (google-genai), tenacity, pydantic, rapidfuzz, python-json-logger
- 134 test passanti (pytest), copertura: config, auth, gmail, classifier, labels, cli, logging, retry, notify
- Deployment: cron job, `uv run python -m email_triage`, OAuth2 token in `~/.config/email_triage/token.json`
- Consent screen deve essere "Published" (non "Testing") per refresh token indefinito
- 4s delay tra chiamate LLM per rate limiting Gemini Flash free tier
- GEMINI_API_KEY (o GOOGLE_API_KEY fallback) via `.env`

## Constraints

- **Budget**: il tool deve essere gratuito o quasi — Gemini Flash free tier (1500 req/day)
- **Autonomia**: deve girare senza intervento manuale dopo la configurazione iniziale
- **Sicurezza**: mai operazioni distruttive sulle email senza conferma esplicita

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Script standalone (non integrazione Claude) | Indipendenza, risparmio token, automazione via cron | ✓ Corretto — zero dipendenze da Claude in runtime |
| Categorie in file YAML esterno | Flessibilita', facile modifica senza toccare il codice | ✓ Funziona bene — few-shot examples in YAML |
| Label Gmail come unico stato (no DB locale) | Semplicita', idempotenza naturale, nessuna sincronizzazione | ✓ Corretto — list_triage_labels su ogni run e' leggero |
| gmail.modify scope fin da Phase 1 | Evita ri-autorizzazione quando labeling aggiunto in Phase 2 | ✓ Corretto — nessun reauth necessario |
| EmailData come plain dataclass (non pydantic) | Rappresenta response API, non config validata | ✓ Corretto — semplicita' senza overhead |
| format="metadata" per Gmail fetch | Evita parsing MIME, basta subject/sender/snippet | ✓ Corretto — token LLM ridotti, nessun MIME overhead |
| Gemini Flash con structured JSON output | Costo zero (free tier), veloce, output deterministico | ✓ Corretto — ~9s/email (4s delay + 5s API), 14/17 classificate correttamente in UAT |
| rapidfuzz threshold=70 per fuzzy matching | Tollera typo/varianti nei nomi categoria | ✓ Corretto — nessun false positive in test |
| CONF-04 droppato (prompt template override) | Le categorie YAML bastano — override troppo complesso per v1 | ✓ Corretto — nessun utente ha chiesto questa feature |
| Pydantic models per GenAI response_schema | google-genai SDK richiede Pydantic per structured output | ✓ Necessario — plain dataclass non funziona con SDK |
| tenacity per retry con predicate su status code | Separare errori retriable (429/5xx) da non-retriable (400/401/403) | ✓ Corretto — nessun retry infinito su auth errors |
| Summary email best-effort (failure non cambia exit code) | cron non deve fallire per problemi di notifica | ✓ Corretto — operazione separable dal core flow |
| Token usage da usage_metadata con None guards | SDK puo' restituire None su runs parziali | ✓ Corretto — 134 test passano dopo fix |

---
*Last updated: 2026-03-09 after v1.0 milestone*
