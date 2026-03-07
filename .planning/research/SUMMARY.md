# Project Research Summary

**Project:** Gmail Auto-Triage
**Domain:** Email automation with LLM classification (personal tool)
**Researched:** 2026-03-07
**Confidence:** MEDIUM

## Executive Summary

Gmail Auto-Triage e' uno script Python standalone che classifica automaticamente le email non lette applicando label Gmail, usando Gemini Flash come LLM leggero. Il dominio e' ben definito: Gmail API per l'accesso email, un LLM per la classificazione, e cron per l'automazione. Non ci sono framework complessi o architetture distribuite — e' una pipeline lineare che legge, classifica, etichetta.

Lo stack raccomandato e' minimale: Python 3.11+, `google-api-python-client` per Gmail, `google-generativeai` per Gemini Flash, PyYAML per la configurazione, pydantic per la validazione, tenacity per i retry. Gestione pacchetti con uv. Nessun database — le label Gmail sono l'unico stato persistente.

I due rischi piu' critici sono: (1) il token OAuth2 che scade dopo 7 giorni in modalita' "Testing" di Google Cloud, uccidendo silenziosamente l'automazione, e (2) la complessita' sottovalutata del parsing MIME delle email. Entrambi vanno affrontati nella prima fase.

## Key Findings

### Recommended Stack

Python + librerie Google ufficiali per Gmail e Gemini. Stack intenzionalmente minimale (~8 dipendenze core).

**Core technologies:**
- **google-api-python-client**: Gmail API v1 — unica opzione solida per accesso Gmail con OAuth2
- **google-generativeai**: Gemini Flash API diretta — free tier generoso (1M tokens/giorno), piu' che sufficiente per uso personale
- **PyYAML + pydantic**: Config categories in YAML, validazione con pydantic sia per config che per risposte LLM
- **tenacity**: Retry con backoff esponenziale — essenziale per uno script cron non supervisionato
- **uv**: Package manager (convenzione progetto)

**Non usare:** langchain (overkill), litellm (un solo provider), imaplib (deprecato per Gmail), beautifulsoup4 (LLM gestisce HTML meglio).

### Expected Features

**Must have (table stakes):**
- Fetch email non lette via Gmail API con paginazione e batch
- Classificazione LLM con output strutturato JSON
- Categorie configurabili in YAML con descrizioni
- Applicazione label Gmail con auto-creazione
- Idempotenza via label check (nessun DB locale)
- Label "ambiguo" per fallback
- Comportamento conservativo (solo label, mai mark-as-read, mai archive)
- Email di log riepilogativa
- Gestione errori per-email (un'email rotta non blocca il batch)
- OAuth2 con persistenza token

**Should have (operabilita'):**
- Dry-run mode per tuning categorie
- Config validation all'avvio
- Processing window (solo email recenti)
- Label namespacing (prefisso `AutoTriage/`)
- Logging strutturato con livelli

**Defer (v2+):**
- Multi-label support
- Confidence threshold configurabile
- Thread-aware classification
- Custom LLM prompt template
- Category examples nel config

### Architecture Approach

Pipeline lineare single-process: config → auth → fetch → filter (idempotenza) → classify → label → notify → exit. Ogni componente e' un modulo Python separato con responsabilita' chiara. Layout `src/` standard.

**Major components:**
1. **config.py** — caricamento e validazione YAML
2. **auth.py** — OAuth2 flow e token refresh
3. **gmail_client.py** — tutte le interazioni Gmail API (fetch, label, send)
4. **classifier.py** — costruzione prompt LLM, chiamata API, parsing risposta
5. **notifier.py** — costruzione e invio email di riepilogo
6. **cli.py** — entry point, orchestrazione pipeline

### Critical Pitfalls

1. **OAuth2 token expiry (#1)** — In modalita' "Testing" Google Cloud, il refresh token scade dopo 7 giorni. Soluzione: pubblicare la consent screen OAuth2 prima del deploy su cron.
2. **MIME parsing complexity (#4)** — Le email hanno strutture MIME complesse e variabili. Soluzione: usare subject + from + snippet (primi ~200 char), evitare il parsing del body completo.
3. **Prompt injection via email (#2)** — Il contenuto email e' input non fidato passato all'LLM. Soluzione: output strutturato, validazione strict delle categorie, delimitazione chiara del contenuto email nel prompt.
4. **Gmail label management (#3)** — Case sensitivity, nested labels, limite 500 label. Soluzione: fetch-and-cache all'avvio, normalizzazione nomi, prefisso comune.
5. **Cron environment mismatch (#7)** — PATH diverso, no env vars. Soluzione: wrapper script con path assoluti, test da ambiente pulito.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Foundation — Gmail API + Config + Auth
**Rationale:** Niente funziona senza OAuth2 e accesso Gmail. L'auth e' il gate per tutto il resto.
**Delivers:** Script che si connette a Gmail, recupera email non lette, e le stampa. Config YAML caricato e validato.
**Addresses:** OAuth2 auth, fetch emails, YAML config, models/dataclasses
**Avoids:** Pitfall #1 (OAuth2 token expiry), Pitfall #3 (label management), Pitfall #4 (MIME parsing)

### Phase 2: Classification — LLM + Label Application
**Rationale:** Il core value: classificare email. Dipende da Phase 1 (email disponibili).
**Delivers:** Email classificate e etichettate in Gmail. Dry-run mode per testing.
**Uses:** Gemini Flash API, pydantic per validazione risposte
**Implements:** classifier.py, label_applier, idempotency check
**Avoids:** Pitfall #2 (prompt injection), Pitfall #6 (classification inconsistency)

### Phase 3: Operability — Notifiche + Cron + Polish
**Rationale:** La pipeline funziona, ora renderla operativa e affidabile per uso quotidiano.
**Delivers:** Email di log, setup cron, gestione errori robusta, logging strutturato.
**Implements:** notifier.py, cron wrapper, error handling
**Avoids:** Pitfall #7 (cron env mismatch), Pitfall #13 (summary email loop), Pitfall #8 (idempotency edge cases)

### Phase Ordering Rationale

- **Auth → Fetch → Classify → Automate**: ogni fase produce un artifact testabile e utile da solo
- La pipeline e' lineare per design — ogni fase dipende dalla precedente
- Le pitfall critiche (#1 OAuth2, #4 MIME) sono affrontate nella prima fase, prima di investire nella classificazione
- La notifica e il cron sono l'ultimo passo perche' richiedono che la pipeline sia gia' funzionante

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** Gmail API specifics (batch API, pagination, label creation) — verificare contro docs attuali
- **Phase 2:** Gemini Flash structured output / JSON mode — verificare API e capabilities attuali

Phases with standard patterns (skip research-phase):
- **Phase 3:** Cron setup, logging, email sending — pattern ben documentati

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Librerie Google sono stabili, ma versioni e Gemini free tier da verificare |
| Features | HIGH | Requisiti chiari dal brainstorm, pattern ben noti nel dominio |
| Architecture | HIGH | Pipeline lineare semplice, nessuna ambiguita' architetturale |
| Pitfalls | MEDIUM-HIGH | Pitfall ben noti nel dominio, ma dettagli specifici (quota, token expiry) da verificare |

**Overall confidence:** MEDIUM

### Gaps to Address

- **Gemini free tier limits**: verificare limiti attuali su https://ai.google.dev/pricing prima dell'implementazione
- **OAuth2 Testing vs Published**: verificare comportamento attuale della consent screen Google Cloud
- **google-generativeai SDK version**: SDK in rapida evoluzione, verificare versione e API surface attuale
- **Gmail API batch modify**: verificare se `messages.batchModify` esiste o se serve batch HTTP request

## Sources

### Primary (HIGH confidence)
- Gmail API documentation (developers.google.com/gmail/api) — API stabile, ben documentata
- Python project structure conventions — standard consolidati
- LLM prompt injection patterns — ricerca di sicurezza consolidata

### Secondary (MEDIUM confidence)
- Gemini API pricing/limits — basato su training data, potrebbe essere cambiato
- google-generativeai SDK — SDK in rapida evoluzione
- Gmail API quota numbers — da verificare contro docs attuali

### Tertiary (LOW confidence)
- OAuth2 Testing mode 7-day expiry — comportamento specifico da verificare

---
*Research completed: 2026-03-07*
*Ready for roadmap: yes*
