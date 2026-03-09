# V2 Ideas & Directions

*Brainstorming post-v1.0. Non è un piano — è uno spazio per raccogliere idee prima di decidere cosa vale la pena fare.*

*Aggiornare man mano che emergono nuove intuizioni dall'uso reale.*

---

## Tech Debt Residuo da v1.0

Piccoli fix che non hanno giustificato una fase a sé ma andrebbero chiusi prima o durante v2.

| Item | File | Fix |
|------|------|-----|
| `FetchConfig.fields` dichiarato ma non consumato da `build_classification_prompt()` — hardcoda sender/subject/snippet | `config.py`, `classifier.py` | Leggere `fields` dalla config e passarli al prompt builder |
| `notify.py` usa `.execute()` raw su 2 call sites (getProfile, messages.send) senza `_execute_with_retry` | `notify.py` | Wrappare con `_execute_with_retry` — già disponibile in `gmail.py` |

---

## Idee per V2

### A — Feedback loop (v2 "intelligente")

**Problema:** Se il modello classifica male un'email, non c'è modo di correggerlo se non modificare il YAML manualmente. Nel tempo la qualità non migliora.

**Idea:** Rilevare quando l'utente sposta manualmente un'email da una label `AutoTriage/*` a un'altra (o la rimuove) e usarlo come segnale negativo/positivo nel prompt.

**Approccio possibile:**
- Gmail API: `history.list` per vedere label changes successive al run
- Salvare un log locale (`~/.config/email_triage/corrections.jsonl`) con `{email_id, original_label, corrected_label, date}`
- Nel prompt: iniettare esempi di correzioni recenti come "negative examples"

**Complessità:** Alta — richiede stato locale, logica di diff tra label pre/post, prompt engineering più sofisticato.
**Valore:** Alto se il tool gira davvero ogni giorno — si adatta alla inbox reale.
**Prerequisito:** Usare il tool abbastanza da accumulare correzioni (almeno 2-3 settimane di uso reale).

---

### B — Attachment-aware classification (CLASS-07)

**Problema:** Un'email con allegato PDF "Fattura_Marzo.pdf" dovrebbe essere classificata diversamente da una senza allegato, anche con lo stesso testo.

**Idea:** Non parsare il contenuto dell'allegato (rischio sicurezza, costo token) ma rilevare *presenza* e *tipo* dell'allegato dagli header MIME e includerlo nel prompt.

**Approccio possibile:**
- `format="full"` o leggere `payload.parts` per trovare `mimeType` degli allegati
- Aggiungere campo `attachments: ["application/pdf", "image/jpeg"]` a `EmailData`
- Includere nel prompt: "Allegati: PDF (1)"

**Complessità:** Media — cambia il fetch (oggi `format="metadata"`) e il modello EmailData.
**Valore:** Medio — utile se si hanno categorie tipo "Fatture" o "Documenti".
**Nota:** Valutare se cambiare `format` impatta performance/quota.

---

### C — Hardening operativo (v2 "robusta")

Piccoli miglioramenti a basso effort per chi usa il tool in produzione continuativa.

| Feature | Req | Effort | Note |
|---------|-----|--------|------|
| Log rotation | OPS-08 | Basso | `logging.handlers.RotatingFileHandler` — max 5MB × 3 file |
| Systemd timer | OPS-07 | Basso | Unit file + timer come alternativa a crontab |
| Fallback modello LLM | — | Medio | Se Gemini quota esaurita, fallback a altro provider o skip graceful |
| Soglia categorie configurabile per-categoria | — | Basso | Oggi `confidence_threshold` è globale — alcune categorie potrebbero volere soglie diverse |

---

### D — Retroactive re-classification (fuori scope attuale)

**Problema:** Se aggiungi una nuova categoria YAML, tutte le email già etichettate rimangono sotto le vecchie label. Non c'è modo di ri-classificare retroattivamente.

**Idea:** Flag `--reclassify` che processa email già etichettate (ignorando l'idempotency check) in un range di date.

**Complessità:** Bassa architetturalmente (togliere il check idempotenza + aggiungere flag), ma rischiosa: potrebbe sovrascrivere label corrette.
**Approccio sicuro:** `--reclassify --dry-run` prima, poi conferma esplicita.
**Valore:** Alto — il primo pain point reale quando si vuole raffinare le categorie.

---

### E — Multi-account

**Problema:** Tool personale oggi, ma chi ha più account Gmail (lavoro + personale) dovrebbe girare due istanze separate con config diverse.

**Idea:** Config directory-based invece di file singolo: `~/.config/email_triage/accounts/{nome}/categories.yaml` + token separati.

**Complessità:** Media — refactor del config loading e del token path.
**Valore:** Basso per ora (use case non verificato).

---

## Priorità Suggerita

Basata su effort/valore e su "cosa emerge dall'uso reale":

1. **Tech debt residuo** — chiudere prima di qualsiasi nuova feature
2. **D: Retroactive re-classification** — primo pain point atteso dopo deploy
3. **B: Attachment-aware** — valore medio, effort contenuto, non rompe nulla
4. **C: Hardening operativo** — log rotation + systemd se il tool gira ogni giorno
5. **A: Feedback loop** — solo dopo 2-4 settimane di uso reale con dati sufficienti

---

## Domande Aperte

- CLASS-05 (thread-aware classification) era nei requirements ma non verificato in UAT — funziona già? Va testato su thread lunghi.
- Gemini Flash free tier regge 1.500 req/day. Con quante email/giorno si raggiunge il limite? (oggi: ~9s/email)
- Vale la pena esporre una config `--config-dir` per supportare più profili senza multi-account completo?

---

*Creato: 2026-03-09 — post v1.0 milestone*
