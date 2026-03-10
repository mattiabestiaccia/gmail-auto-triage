# V2 Ideas & Directions

*Brainstorming post-v1.0. Non è un piano — è uno spazio per raccogliere idee prima di decidere cosa vale la pena fare.*

*Aggiornare man mano che emergono nuove intuizioni dall'uso reale.*

---

## F — Deploy Cloud / Esecuzione Persistente

**Problema:** Il tool gira solo quando il PC è acceso e WSL2 è attivo. Se il PC è spento, le email si accumulano non triaggiate.

**Idea:** Spostare l'esecuzione su infrastruttura always-on, eliminando la dipendenza dalla macchina locale.

**Opzioni:**

| Opzione | Costo stimato | Complessità | Note |
|---------|--------------|-------------|------|
| **Google Cloud Run** (job schedulato) | ~€0 free tier | Bassa | Container Docker, Cloud Scheduler al posto del cron, OAuth2 token su Secret Manager |
| **Railway / Render** (cron job) | ~€0-5/mese | Bassa | Deploy da GitHub, variabili env native, cron built-in |
| **VPS entry-level** (Hetzner CX11, €4/mese) | ~€4/mese | Media | Piena libertà, systemd, più servizi sullo stesso server |
| **Raspberry Pi** (già in casa) | €0 | Bassa | Always-on, locale, nessun costo cloud |

**Sfida principale:** OAuth2 token — il token attuale è legato alla macchina locale (`credentials/token.json`). In cloud serve:
- Storico del token su persistent storage (Secret Manager, volume montato, ecc.)
- Primo login interattivo fatto una volta e token salvato, poi solo refresh automatico

**Prerequisito:** Usare il tool localmente abbastanza da essere sicuri che funziona prima di migrare.

---

## Tech Debt Residuo da v1.0

Piccoli fix che non hanno giustificato una fase a sé ma andrebbero chiusi prima o durante v2.

| Item | File | Fix |
|------|------|-----|
| `FetchConfig.fields` dichiarato ma non consumato da `build_classification_prompt()` — hardcoda sender/subject/snippet | `config.py`, `classifier.py` | Leggere `fields` dalla config e passarli al prompt builder |
| `notify.py` usa `.execute()` raw su 2 call sites (getProfile, messages.send) senza `_execute_with_retry` | `notify.py` | Wrappare con `_execute_with_retry` — già disponibile in `gmail.py` |
| **Email con `Date:` header corrotto (es. 1969) non vengono fetchate** — il filtro `after:` lato Gmail usa il `Date:` header, non la data di ricezione reale. Email valide con timestamp zero/malformato vengono escluse silenziosamente dalla query `is:unread after:YYYY/MM/DD`. Fix: rimuovere `after_date` dalla query Gmail e delegare tutto il filtraggio temporale a `filter_by_window` (che usa `internalDate`). | `cli.py` riga 142-152, `gmail.py` `fetch_unread_ids` | Rimuovere `after_date` param dalla query; `internalDate` è sufficiente e accurato |

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

### G — Scheduled Email Send (outbox queue)

**Problema:** La Gmail API non espone la funzione "schedule send" della web UI (limitazione confermata da Google su StackOverflow). Non è possibile programmare un invio futuro via API.

**Idea:** Implementare una outbox locale. Il comando salva l'email in un file JSON con timestamp di invio desiderato. Il cron che già gira ogni minuto controlla la coda e invia quando il momento arriva.

**Approccio:**
```
email-triage send-later \
  --to "nome@email.com" \
  --subject "Oggetto" \
  --body "Testo" \
  --at "2026-03-15 09:00"
```
- Scrive in `~/.config/email_triage/outbox.json`
- Il cron controlla: `if scheduled_at <= now → send via Gmail API → remove from queue`
- Stessa auth Gmail già configurata (`notify.py` fa già `messages.send`)

**Complessità:** Bassa — `notify.py` ha già l'infrastruttura di invio, manca solo la queue e il CLI.
**Limite:** Funziona solo quando WSL2 è attivo. Risolto con opzione F (cloud deploy).
**Valore:** Alto — utile per promemoria, follow-up programmati, email "da non dimenticare".

---

### H — Gmail Suite: Personal AI Email Assistant

**Visione:** Evolvere il tool da "auto-tagger" a suite completa per gestire Gmail tramite Claude Code. Il triage automatico rimane il cuore; le feature si aggiungono come sottocomandi.

**Contesto di mercato:** Strumenti come Superhuman, Lindy, Mailmaestro, e il recente Gmail Gemini (gennaio 2026) stanno trasformando la gestione email con AI — ma sono tutti cloud-based, closed source, e passano i tuoi dati da terze parti. Questo progetto può offrire la stessa potenza rimanendo **locale, gratuito e sotto il tuo controllo**.

**Differenziatori chiave vs soluzioni commerciali:**
- Dati email non escono da Google + macchina locale (eccetto Gemini Flash per il triage)
- Configurazione YAML — massima personalizzazione
- Integrazione nativa Claude Code — nessuna UI da installare
- Costo zero (Gmail API free + Gemini Flash free tier)

---

#### H.1 — Thread Summarization

**Idea:** Dato un thread lungo (recruiting, supporto, discussione), generare un riassunto in italiano con: argomento, decisioni prese, chi deve fare cosa, ultima azione.

```
email-triage summarize --thread <thread_id>
email-triage summarize --subject "Re: Candidatura"
```

**Approccio:** `format="full"` per leggere il body del thread → Gemini Flash per il summary → output su console o file.
**Complessità:** Media (parsing MIME multi-part body).
**Riferimento commerciale:** Superhuman, Gmail AI Overviews, Lindy.

---

#### H.2 — Smart Reply Drafting

**Idea:** Dato un'email in arrivo, generare 2-3 bozze di risposta in stile personale (tono configurabile: formale / informale / breve).

```
email-triage draft-reply --message-id <id> --tone formal
```

**Approccio:** Legge thread + email originale → prompt contestuale con tono → output in `drafts/` o push come Gmail draft.
**Complessità:** Media — il draft può essere creato via `messages.create` con label `DRAFT`.
**Riferimento commerciale:** Mailmaestro, GPT for Gmail, Gmail "Help Me Write".

---

#### H.3 — Follow-up Reminders

**Idea:** Rilevare email che hai inviato senza risposta dopo N giorni e generare un reminder (console o re-email).

```
email-triage follow-up --days 3 --label Sent
```

**Approccio:** Cerca in SENT le email senza risposta nel thread → lista con subject + giorni trascorsi → opzione di creare draft di follow-up.
**Complessità:** Media — richiede `history.list` o query Gmail `in:sent -has:userlabels older_than:3d`.
**Riferimento commerciale:** Remail, Lindy.
**Valore:** Alto per recruiting e comunicazioni business.

---

#### H.4 — Bulk Unsubscribe Assistant

**Idea:** Identificare mittenti di newsletter/promo frequenti e aiutare a disiscrizione o archiviazione massiva.

**Approccio:** Analizza ultimi 90 giorni → raggruppa per mittente → mostra top senders per volume → per ogni sender: opzione unsubscribe (legge header `List-Unsubscribe`) o archivia tutto.
**Complessità:** Alta (parsing header, sicurezza dei link).
**Riferimento commerciale:** Inbox Zero (open source, 7.6k ⭐ su GitHub), Clean Email.
**Nota:** Valutare solo click su `mailto:` unsubscribe (sicuro), non URL esterni.

---

#### H.5 — Natural Language Inbox Search

**Idea:** Chiedere a Claude "trova tutte le fatture di marzo" o "mostrami le email di recruiting degli ultimi 30 giorni" e ottenere un risultato strutturato.

**Approccio:** Claude traduce la query in Gmail search syntax → `messages.list` → parsing → output formattato.
**Complessità:** Bassa — la traduzione query→Gmail syntax è il cuore, il resto usa API già note.
**Valore:** Alto — differenziatore rispetto a tutti i tool commerciali che richiedono UI.
**Esempio:**
```
email-triage search "fatture ricevute questo mese"
# → query: label:Finance after:2026/03/01 before:2026/03/31
```

---

#### H.6 — Task Extraction

**Idea:** Rilevare action items nelle email e esportarli come lista di TODO (stdout, file, o futuro integrazione con task manager).

**Approccio:** Dopo classificazione → secondo pass LLM con prompt "estrai azioni richieste o promesse" → output `[mittente] → [azione] (scadenza se presente)`.
**Complessità:** Bassa — riusa pipeline classificazione, aggiunge solo un secondo prompt.
**Riferimento commerciale:** Lindy, Microsoft Copilot per Outlook.

---

## Priorità Suggerita

Basata su effort/valore e su "cosa emerge dall'uso reale":

1. **Tech debt residuo** — chiudere prima di qualsiasi nuova feature
2. **D: Retroactive re-classification** — primo pain point atteso dopo deploy
3. **G: Scheduled send** — utile subito, bassa complessità, riusa infrastruttura esistente
4. **B: Attachment-aware** — valore medio, effort contenuto, non rompe nulla
5. **C: Hardening operativo** — log rotation + systemd se il tool gira ogni giorno
6. **H.5: Natural language search** — alta utilità, bassa complessità, buon entry point per la suite
7. **H.1: Thread summarization** — feature "wow", utile per thread lunghi recruiting/supporto
8. **H.3: Follow-up reminders** — utile per chi usa Gmail per lavoro
9. **H.2: Smart reply drafting** — effort medio, valore dipende dall'uso
10. **H.6: Task extraction** — riusa pipeline, poco effort
11. **A: Feedback loop** — solo dopo 2-4 settimane di uso reale con dati sufficienti
12. **H.4: Bulk unsubscribe** — complessità alta, rischi sicurezza, solo dopo consolidamento

---

## Domande Aperte

- CLASS-05 (thread-aware classification) era nei requirements ma non verificato in UAT — funziona già? Va testato su thread lunghi.
- Gemini Flash free tier regge 1.500 req/day. Con quante email/giorno si raggiunge il limite? (oggi: ~9s/email)
- Vale la pena esporre una config `--config-dir` per supportare più profili senza multi-account completo?
- Per la suite H: sottocomandi dello stesso CLI (`email-triage summarize`, `email-triage search`) o tool separato (`gmail-suite`)?
- H.2 (smart reply): scrivere nel proprio stile richiede few-shot con email passate — come campionarle senza over-fitting?

---

*Creato: 2026-03-09 — post v1.0 milestone*
*Aggiornato: 2026-03-09 — aggiunta G (scheduled send) e H (Gmail suite) post-ricerca*
