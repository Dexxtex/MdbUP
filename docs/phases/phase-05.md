# Fase 05 — Estensione multi-fonte

> Report consolidato della fase. Le fonti originali sono state unite in questo documento.


---

## Fonte: `phase-05.md`

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


---

## Fonte: `phase-05.md`

# Fase 5 — Estensione provider, serie TV, snapshot diffing e UI

**Data:** 2026-11-17
**Stato:** completata e verificata live sul server Ubuntu (`http://192.0.2.10:8088`).

---

## 1. Provider verificati live (TMDb, `watch_region=IT`)

Verifica eseguita con `/watch/providers/movie` e `/watch/providers/tv`; gli ID sono
salvati separatamente per film e serie in `provider_mapping.metadata_json`.

| Provider | Film TMDb | Serie TMDb | Note |
|---|---:|---:|---|
| Netflix | 8 | 8 | |
| Amazon Prime Video | 119 | 119 | esclusa la variante "with Ads" |
| Disney+ | 337 | 337 | |
| NOW | 39 | 39 | nome TMDb "Now TV" |
| Timvision | 109 | 109 | |
| Infinity+ | 110 | — | nessuna copertura TV in IT; collezione TV rimossa |
| Rakuten TV | 35 | 35 | |
| MUBI | 11 | 11 | |
| Apple TV+ | 350 | 350 | nome TMDb "Apple TV" |
| Paramount+ | 531 | 531 | nome TMDb "Paramount Plus" |
| RaiPlay | 222 | 222 | nome TMDb "Rai Play" |
| Mediaset Infinity | 359 | 359 | |

La verifica ha anche disattivato/rimosso la collezione `infinity-plus-show`
(obsoleta). Le altre collezioni seed restano attive e possono essere acquisite
dalla UI.

---

## 2. Serie TV

- Il flusso `media_type=SHOW` usa `/discover/tv` con `with_watch_monetization_types=flatrate`.
- Gli ID film e serie sono separati da `(tmdb_id, media_type)`; lo stesso ID TMDb
  può esistere come film e come serie senza collisioni.
- Le nuove stagioni/episodi **non** creano righe `media` e **non** vengono inviati
  a MDBList come entità separate. Il task `detect_tv_changes` (coda `maintenance`,
  settimanale, limite 50 serie per run) confronta `number_of_seasons` /
  `number_of_episodes` e registra eventi `tv_season_added` / `tv_episode_added`
  nell'audit log, associati alla serie madre.
- Live: **Apple TV+ IT — Serie TV** acquisita (226 serie, 12/12 pagine, 0
  duplicati, 0 unresolved) e sincronizzata su MDBList con 226 ADD, 0 errori.

---

## 3. Collezioni "Appena rilevati"

- Durante l'acquisizione viene popolata `availability` con `first_seen_at` e
  `last_seen_at` per provider/paese/offerta.
- Una collezione derivata ha `kind=RECENTLY_ADDED`, `origin=CUSTOM`,
  `date_basis=APP_FIRST_SEEN` e filtri `derivation=RECENTLY_DETECTED`,
  `source_collection_id`, `window_days`.
- **Baseline:** la prima acquisizione della collezione catalogo sorgente è la
  base. I titoli con `first_seen_at` uguale o precedente alla baseline non sono
  "nuovi"; solo le osservazioni successive e dentro la finestra entrano nella
  lista.
- Etichetta UI: "Appena rilevati (Fonte: TMDb/JustWatch)" / "derivata
  dall'osservazione dell'app"; **mai** "aggiunti ufficialmente oggi".
- Live creata `Mediaset Infinity IT — Film appena rilevati (14 giorni)` con
  baseline vuota (`invalid_reason=baseline_empty`), come previsto alla prima
  acquisizione. Si popolerà quando TMDb segnalerà titoli nuovi.

---

## 4. Riutilizzo snapshot condiviso

- Una collezione può dichiarare `shared_snapshot_collection_id`.
- L'acquisizione usa lo snapshot valido della collezione condivisa, filtra per
  `with_genres` sui `genre_ids` del payload TMDb e crea un nuovo snapshot senza
  chiamare TMDb.
- Live test: `Mediaset Infinity — Film Azione (shared test)` ha prodotto 11
  titoli in 1 pagina, 0 chiamate TMDb, poi è stata rimossa.
- La UI Collezioni espone il campo "Snapshot condiviso" nel form.

---

## 5. Dashboard e quote API

- `TMDbClient` e `MdbListClient` incrementano un contatore Redis
  (`mdbup:api_calls:*`) per ora e per giorno, con fallback in memoria.
- La Dashboard mostra richieste reali di oggi/ultima ora e una stima
  giornaliera/oraria basata sui binding attivi, sulla schedule e sulla dimensione
  degli snapshot.
- Con i binding attuali tutti `MANUAL`, la stima è 0; il contatore reale ha
  registrato le chiamate di acquisizione/sync.

---

## 6. Frontend

- Form completo **Collezioni → Nuova collezione / Modifica**:
  provider verificato, tipo media, generi TMDb, monetizzazione, finestra
  "Appena rilevati", snapshot condiviso, attivo/pausa.
- Filtri Collezioni: provider, tipo media, origine, tipo (CATALOG/RECENTLY_ADDED),
  stato attivo/disattivato.
- Nuova pagina **Run** con filtri provider, stato e tipo media.
- Footer con attribuzione TMDb/JustWatch e nota sulle liste "Appena rilevati".
- Provider page con ID film/serie separati e flag di verifica.

---

## 7. Test

- Backend: **184 passed**, `ruff check` e `ruff format --check` verdi.
- Frontend: **42 passed**, build Vite e ESLint verdi.
- Nuovi test:
  - separazione film/serie con lo stesso `tmdb_id`;
  - mapping provider movie/tv separati e disattivazione copertura mancante;
  - `flatrate` di default nel connector;
  - baseline "Appena rilevati" (baseline esclusa, finestra rispettata, baseline vuota);
  - riutilizzo snapshot condiviso con filtro genere;
  - `tv_details` e eventi stagioni/episodi senza nuove righe `media`;
  - create/update collezione da API e generi TMDb;
  - filtri Run per provider/stato/tipo media;
  - contatore API e stima dashboard.

---

## 8. Verifica live

| Elemento | Esito |
|---|---|
| Stack Docker | 7/7 healthy |
| Provider verificati | 12/12 (Infinity+ solo film) |
| Apple TV+ IT — Serie TV | 226 serie, sync `SUCCEEDED`, 226 ADD, 0 errori |
| Mediaset Infinity IT — Film | 146 film, sync `SUCCEEDED`, 146 ADD, 0 errori |
| Confronto ID TMDb ↔ MDBList | Apple TV+ 226/226, Mediaset 146/146, 0 missing/extra |
| Dry-run successivo | tutti i 5 binding: `to_add=0`, `to_remove=0` |
| Liste Netflix IT | Azione 755, Avventura 428, Horror 365, invariate |
| Derived collection | baseline vuota `baseline_empty` |
| Shared snapshot | 11 titoli, 1 pagina, 0 chiamate TMDb |
| Dashboard API usage | contatori reali TMDb/MDBList popolati |

---

## 9. Fonti editoriali secondarie

Valutate ComingSoon e Movieplayer:
- `robots.txt` di ComingSoon disallows AI/LLM bot e `/rss/`; Movieplayer
  disallows `/api/`, ricerca e filtri, e i termini non autorizzano la
  riproduzione sistematica dei contenuti.
- Non è stato implementato alcun scraping/connettore editoriale. JustWatch
  Partner resta **disabilitato** finché non ci sono credenziali ufficiali.

---

## 10. Limiti noti / prossimi passi

1. Le liste sono pubbliche; la visibilità è modificabile dalla pagina Binding.
2. I binding sono `MANUAL` per default; la modifica permette `INTERVAL`/`CRON`.
3. Le stagioni/episodi sono eventi audit-only, non entità MDBList.
4. La stima API è indicativa; il conteggio reale è per ora/giorno.
5. Restano da fare E2E Playwright, metriche Prometheus e HTTPS/TLS.
6. JustWatch Partner e una fonte ufficiale Top 10 restano bloccati da contratto/fonte.
