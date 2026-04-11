# Brainstorming Session

**Idea:** Script standalone per categorizzare automaticamente le email Gmail non lette con Gemini Flash e cron
**Started:** 2026-03-05
**Last updated:** 2026-03-05
**Status:** initial-brainstorm

## Explored Dimensions

| Dimension | Status | Date | Notes |
|-----------|--------|------|-------|
| product | not started | - | - |
| tech | explored | 2026-03-07 | Stack definito: Python + google-api-python-client, Gemini Flash via API diretta, cron multiplo, label come stato |
| market | not started | - | - |
| business | not started | - | - |
| competitors | not started | - | - |
| users | not started | - | - |

## Session Notes

- Initial brainstorming session via /brain:new
- L'idea è partita come comando dentro Claude ed è evoluta verso uno script standalone con Gemini Flash — la motivazione chiave è l'indipendenza da Claude e il risparmio di token
- Il comportamento conservativo (mai segnare come letto, mai archiviare) è un requisito forte emerso dalla paura di perdere email
- Le categorie esatte sono ancora da definire analizzando la inbox reale
- Suggested next: tech — lo stack tecnico (Gmail API, Gemini Flash, script shell, cron) è già abbastanza delineato e merita un approfondimento per capire come collegare i pezzi
- Tech exploration completata (2026-03-07): Python scelto per refresh OAuth2 automatico, Gemini API diretta per semplicita e free tier, nessuno stato locale
- Suggested next: product — definire categorie analizzando inbox reale e chiarire il flusso UX end-to-end

## Idea Evolution

L'idea è partita come "comando dentro una sessione Claude" ed è evoluta in "script standalone con Gemini Flash e cron". Il pivot è avvenuto quando è emerso il desiderio di indipendenza — non dover aprire Claude ogni volta, non consumare token, e poter automatizzare via cron.
