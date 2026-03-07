# Gmail Auto-Triage

## What This Is

Uno script standalone che categorizza automaticamente le email Gmail non lette applicando etichette, usando un LLM leggero per la classificazione. Gira via cron senza intervento manuale, cosicche' la inbox sia gia' organizzata quando viene aperta. Tool personale, per un singolo utente.

## Core Value

Aprire Gmail e trovare le email gia' organizzate per categoria, senza alcuno sforzo manuale.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Lo script si connette a Gmail via API e recupera le email non lette
- [ ] Ogni email viene classificata in una categoria tramite LLM
- [ ] Le categorie sono definite in un file di configurazione YAML
- [ ] Le label corrispondenti vengono applicate in Gmail
- [ ] Email non classificabili ricevono una label "ambiguo"
- [ ] Lo script invia un'email di log riepilogativa alla stessa inbox
- [ ] Le email gia' etichettate non vengono riprocessate (idempotenza)
- [ ] Lo script e' eseguibile via cron con frequenza multipla giornaliera
- [ ] Comportamento conservativo: solo label, mai segnare come letto, mai archiviare

### Out of Scope

- Azioni distruttive automatiche (archiviazione, cancellazione) — il tool categorizza, l'utente decide
- Interfaccia web o GUI — e' uno script da terminale/cron
- Supporto multi-utente — tool personale
- Ricategorizzazione retroattiva — nuove categorie non retro-applicano su email gia' etichettate

## Context

- L'idea e' nata come comando dentro Claude ed e' evoluta verso uno script standalone per indipendenza e risparmio token
- Il brainstorming ha esplorato la dimensione tech (Python, Gmail API, Gemini Flash, cron) ma le scelte sono indicative, non vincolanti — la ricerca potra' suggerire alternative
- Le categorie esatte vanno definite analizzando la inbox reale dell'utente
- Esiste gia' un progetto Google Cloud utilizzabile per le credenziali OAuth2
- Il prompt di categorizzazione per l'LLM e' da definire in fase di ricerca

## Constraints

- **Budget**: il tool deve essere gratuito o quasi — modelli con free tier generoso preferiti
- **Autonomia**: deve girare senza intervento manuale dopo la configurazione iniziale
- **Sicurezza**: mai operazioni distruttive sulle email senza conferma esplicita

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Script standalone (non integrazione Claude) | Indipendenza, risparmio token, automazione via cron | — Pending |
| Categorie in file YAML esterno | Flessibilita', facile modifica senza toccare il codice | — Pending |
| Label Gmail come unico stato (no DB locale) | Semplicita', idempotenza naturale, nessuna sincronizzazione | — Pending |

---
*Last updated: 2026-03-07 after initialization*
