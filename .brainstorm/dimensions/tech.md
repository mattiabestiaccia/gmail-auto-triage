# Tech — Gmail Auto-Triage

> Stack essenziale per un prototipo rapido che validi il triage automatico, espandibile in seguito.

## Linguaggio e Runtime

Python come linguaggio principale. La scelta è guidata dalla libreria ufficiale Google `google-api-python-client`, che gestisce in modo trasparente il ciclo OAuth2 — in particolare il refresh automatico dei token. L'alternativa bash+curl è stata scartata perché il refresh dei token scaduti (~1 ora di vita) andrebbe implementato a mano, rendendo fragile uno script che gira via cron con token sempre scaduti tra un'esecuzione e l'altra.

## Gmail API

Accesso via `google-api-python-client` con OAuth2. Progetto Google Cloud già esistente (usato per test), da sostituire con uno dedicato in futuro. La query di ricerca email combina più filtri in un'unica chiamata:
- `is:unread` — solo email non lette
- `after:2025/12/31` — cutoff al 2026, lo storico viene ignorato
- `-label:lavoro -label:pubblicita -label:ambiguo -label:email-fetch-log ...` — escludi email già categorizzate e email di log dello script

Nessuno stato locale: le label Gmail sono il marker di "già processato". Un'email etichettata non viene mai riprocessata, salvo azione esplicita dell'utente.

## Classificazione LLM

Gemini Flash via Google AI Gemini API diretta (non Vertex AI). Motivazioni:
- **Setup minimo**: una API key da Google AI Studio, nessuna configurazione GCP complessa
- **Free tier generoso**: ~1000 richieste/giorno, più che sufficiente per il volume di email personali
- **Sufficiente per il task**: classificare email non richiede un modello pesante

Vertex AI scartato per ora — aggiunge complessità (service account, IAM, billing) senza benefici per un tool personale. La migrazione futura è un cambio di SDK, non una riscrittura.

## Automazione

Cron con frequenza multipla giornaliera (non solo una volta al mattino). Il rischio di riprocessamento è eliminato dal filtro query: email già etichettate non compaiono nei risultati.

## Gestione Ambiguita e Notifiche

- Email non classificabili ricevono la label "ambiguo"
- Lo script invia un'email di notifica riepilogativa alla stessa inbox, con label "email-fetch/log"
- Le email con label "email-fetch/log" sono escluse dalla query di triage (evita che lo script categorizzi le proprie notifiche)
- Il meccanismo di notifica e' espandibile: altri tipi di eventi (errori, anomalie) saranno aggiunti in futuro

## Principi di Design

- **Prototipo first**: l'obiettivo immediato e' validare che la categorizzazione LLM funziona sulla inbox reale
- **Conservativo**: lo script tocca solo le label, mai lo stato di lettura, mai archivia
- **Idempotente**: rieseguire lo script non cambia nulla se non ci sono email nuove
- **Nessuna ricategorizzazione automatica**: nuove categorie non retro-applicano su email gia' etichettate

## Decisioni Aperte

- Categorie esatte da definire analizzando la inbox reale
- Tipi di eventi aggiuntivi per le notifiche email-fetch/log
- API key Gemini da creare su Google AI Studio
- Frequenza esatta del cron da calibrare dopo i primi test

---
*Explored via /brain:explore tech on 2026-03-07*
