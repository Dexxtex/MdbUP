# Fonti editoriali secondarie — valutazione

**Data:** 2026-11-17
**Decisione:** nessun connettore editoriale automatico in Fase 5.

## ComingSoon

- `https://www.comingsoon.it/robots.txt` disallows crawler AI/LLM (AnthropicBot,
  Claude, ClaudeBot, OAI-SearchBot, ChatGPT-User, GPTBot, SentiBot) e `/rss/`,
  oltre a molte aree tecniche.
- Non è stata trovata una API pubblica stabile con termini d'uso compatibili con
  un'acquisizione automatica continuativa.
- **Non implementato**: nessuno scraping di pagine o RSS.

## Movieplayer

- `https://www.movieplayer.it/robots.txt` consente le pagine articolo ma
  disallows `/api/`, ricerca, filtri, gallerie e video.
- I termini editoriali non autorizzano esplicitamente la riproduzione
  sistematica dei contenuti; non c'è una API pubblica documentata.
- **Non implementato**: nessuno scraping.

## Conseguenza

- Le collezioni restano basate su TMDb (AGGREGATOR) e sulle derivazioni
  `APP_FIRST_SEEN`.
- JustWatch Partner resta **DISABLED** finché non vengono fornite credenziali
  ufficiali e un contratto autorizzato.
- Se in futuro sarà disponibile un feed/API editoriale con licenza, il connettore
  dovrà essere aggiunto come fonte separata, con `origin` e `date_basis` espliciti.
