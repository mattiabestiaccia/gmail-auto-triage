# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-03-09
**Phases:** 4 | **Plans:** 9 | **Timeline:** 3 days

### What Was Built
- Pipeline input completo: OAuth2 + token persistence + Gmail fetch paginato con time-window filter
- Motore classificazione Gemini Flash: structured JSON output, confidence scoring, fuzzy matching (rapidfuzz)
- Label management Gmail: `AutoTriage/*` namespace, auto-create, idempotenza piena, `--dry-run`
- Resilienza produzione: retry tenacity per Gmail API e LLM, structured dual-handler logging
- Summary email HTML+text con per-category stats, error count, token usage reale
- 134 test passanti con coverage su tutti i moduli

### What Worked
- **GSD pipeline completa** (new-project → discuss → plan-phase → execute-phase-teams → verify → audit) senza deviazioni — ogni fase ha prodotto artefatti verificabili
- **Audit-driven tech debt** — v1.0-MILESTONE-AUDIT identificato 8 items di tech debt, Phase 4 ne ha chiusi 7 (1 residuo accettabile), nessuna regressione
- **TDD applicato** — test scritti prima o contestualmente all'implementazione, suite verde prima di ogni commit
- **Separazione concerns** — gmail.py provably read-only (AST-verified), retry decorators importabili da qualsiasi modulo, ClassificationResult esteso con None-safe defaults
- **UAT E2E manuale** (Phase 2) — testato su inbox reale con 17 email: 14 classificate, 3 ambigue — ha rivelato necessità del 4s delay che la suite automatica non cattura

### What Was Inefficient
- **Phase 3 agent 02-03 fallito 2x** su permessi (completato dall'orchestratore) — agenti paralleli su file sovrapposti creano conflitti; la wave detection nel workflow ha funzionato ma il fallback ha rallentato
- **CONF-04 droppato tardi** — rimosso durante Phase 1 execution invece di during discuss; avrebbe salvato tempo di ricerca
- **gsd-tools summary-extract** non ha estratto one_liners dalle SUMMARY perché i file usano formato dependency-graph, non frontmatter con `one_liner:` — tool non adattato a questo stile di SUMMARY

### Patterns Established
- **Belt-and-suspenders per filtri temporali**: `after:` query Gmail + `internalDate` code-side — doppia protezione su dati non controllati
- **None guards sui campi opzionali SDK**: usage_metadata e campi interni possono essere None su runs parziali — testare esplicitamente il caso None
- **Best-effort per notifiche**: operazioni di notifica non devono influenzare exit code — try/except wide con log warning
- **LABEL_PREFIX hardcoded come costante testabile**: evita magic strings sparse nel codice

### Key Lessons
1. **UAT su inbox reale rivela rate limits invisibili ai test unitari** — il 4s delay era necessario ma solo l'UAT l'ha dimostrato; pianificare UAT live anche per Phase 1 in future milestones
2. **Audit milestone prima di complete è obbligatorio**: i 5 items risolti in Phase 4 erano reali (test fallenti, N/A token usage) — senza audit sarebbero stati shipped come debt invisibile
3. **Gemini Flash free tier (1500 req/day) regge per uso personale** con 4s delay — nessun 429 in produzione dopo il fix
4. **gsd:execute-phase-teams con wave detection** ha funzionato correttamente su fasi con piani disjoint (02-01 + 02-02 in parallel) — usare per default

### Cost Observations
- Model mix: ~100% Sonnet 4.6 (balanced profile)
- Sessions: ~6 sessioni (una per fase + audit + milestone)
- Notable: 9 piani in 35 min di execution time totale — velocità elevata grazie a parallelizzazione wave 2 in Phase 2

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | ~6 | 4 | Prima milestone — baseline stabilito |

### Cumulative Quality

| Milestone | Tests | Coverage | Notes |
|-----------|-------|----------|-------|
| v1.0 | 134 | all modules | 29/29 requirements, audit passed |

### Top Lessons (Verified Across Milestones)

1. **Audit prima di complete** — identifica tech debt reale vs. percepito
2. **UAT su dati reali** — rivela comportamenti (rate limits, latency) invisibili ai test unitari
