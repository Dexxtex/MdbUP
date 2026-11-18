# Brief operativi per le lane backend

Questi brief integrano `docs/phase2/IMPLEMENTATION.md`. Ogni agente deve leggere entrambi.

---

## Lane B — Backend data/API (dopo la fondazione)

### Obiettivo
Implementare la prima verticale reale TMDb: provider, collezioni, acquisizione, snapshot, anteprima. Nessuna scrittura MDBList.

### File ownership
- `app/integrations/tmdb/client.py`, `models.py`
- `app/connectors/registry.py`, `app/connectors/tmdb/connector.py`
- `app/connectors/manual_csv/connector.py` (opzionale, stub onesto)
- `app/services/acquisition.py`, `normalization.py`, `snapshots.py`, `dashboard.py`
- `app/repositories/providers.py`, `sources.py`, `collections.py`, `snapshots.py`, `media.py`
- `app/api/routers/dashboard.py`, `providers.py`, `sources.py`, `collections.py`, `snapshots.py`
- aggiornare `app/api/router.py`
- estendere `app/cli.py` / `app/seed.py` con seed provider e collezioni TMDb

### TMDb client
- Base URL `https://api.themoviedb.org/3`, Bearer token.
- Metodi: `healthcheck`, `list_movie_providers(country)`, `list_tv_providers(country)`, `discover_movies(provider_id, country, page)`, `discover_tv(...)`, `external_ids(media_type, tmdb_id)`, `find_by_imdb(imdb_id, media_type)`.
- `discover` usa `watch_region=IT`, `with_watch_providers`, `with_watch_monetization_types=flatrate`, `page`, `sort_by=popularity.desc`.
- Rispettare `429` con `Retry-After`; timeout 20s; `follow_redirects=False`.
- Non inventare endpoint: usare solo quelli verificati in `docs/phase1/01-source-matrix.md`.

### Connettore TMDb
- `TMDbConnector` implementa `SourceConnector`.
- Capabilities: `catalog=True`, `recently_added=False`, `upcoming=False`, `charts=False`, `ordering=False`, `added_dates=False`, `seasons_episodes=True`, `full_pagination=False`, `requires_credentials=True`, `requires_contract=False`.
- `list_providers` restituisce i provider IT con ID TMDb.
- `list_collections` restituisce, per provider, una collezione movie e una show:
  - `kind=CATALOG`, `origin=AGGREGATOR`, `date_basis=UNKNOWN`, `offer_types={"FLATRATE"}`.
- `fetch_collection_page` usa discover; `next_cursor` = numero pagina successivo; `total_pages` dal payload; stop a 500 pagine.
- `normalize_item` converte `RawItem` in `NormalizedItem`; `date_basis=UNKNOWN`; `source_date_created=None`.
- Se manca `tmdb_id`, usa `imdb_id`; se manca tutto, `UNRESOLVED`.

### Acquisizione
- `acquire_collection(session, collection_id, connector, actor) -> snapshot_id`.
- Crea `CollectionSnapshot(RUNNING)`, loop pagine, normalizza, dedup, crea/risolve `Media`, scrive `SnapshotItem`.
- `pages_expected`/`pages_fetched`, `items_count`, `resolved_count`, `unresolved_count`, `duplicate_count`, `error_count`.
- `is_valid` solo se `COMPLETE` + `CLEAN` + item > 0 + 0 errori + 0 unresolved.
- `checksum` SHA-256 degli ID normalizzati.
- Aggiorna `collection.last_valid_snapshot_id` solo se valido.
- Non usare HTTP nel processo API: il router enqueue `app.jobs.tasks.acquire_collection_task`; in `APP_ENV=test`/`CELERY_TASK_ALWAYS_EAGER` il task può girare inline.

### API
- `GET /api/dashboard`: contatori, ultimi run, alert (fonti non configurate, snapshot invalidi, JustWatch disabilitato).
- `GET /api/providers?country=IT`: provider con mapping TMDb e numero collezioni.
- `GET /api/sources`: fonte TMDb con capabilities e status; fonte JustWatch `DISABLED`/`requires_contract`.
- `GET /api/collections`: filtri provider/media_type/origin.
- `GET /api/collections/{id}`: dettaglio + ultimo snapshot valido.
- `GET /api/collections/{id}/snapshots`: storico.
- `GET /api/snapshots/{id}/items`: paginazione.
- `POST /api/collections/{id}/acquire`: `202 {job_id}`; se manca credenziale TMDb → `409 CREDENTIAL_MISSING`.
- `POST /api/sources/{id}/healthcheck`: `202` o `200` con esito; non deve simulare una fonte non configurata.

### Seed
Provider IT con ID TMDb verificati:
- Netflix 8, Amazon Prime Video 119, Disney+ 337, NOW 39, Timvision 109, Infinity+ 110, Rakuten TV 35, MUBI 11.
Creare source `tmdb` (`type=API`, `is_official=false`, `origin_default=AGGREGATOR`, `requires_contract=false`) e source `justwatch_partner` (`type=API`, `is_official=false`, `origin_default=AGGREGATOR`, `requires_contract=true`, `status=DISABLED`).
Creare collezioni movie/show per ogni provider con `origin=AGGREGATOR`, `date_basis=UNKNOWN`.

### Test minimi
- `normalize_item` con TMDB ID, solo IMDb, unresolved.
- dedup film vs serie con lo stesso ID.
- snapshot valido/incompleto/vuoto.
- contract TMDb con `respx` (discover, watch providers, 429).
- API providers/collections con TestClient e SQLite.

### Divieti
- Non scrivere su MDBList.
- Non dichiarare TMDb verificato live senza API key.
- Non creare collezioni `OFFICIAL`.
- Non usare `BackgroundTasks`.

---

## Lane C — Backend sync (dopo Lane B)

### Obiettivo
Implementare target MDBList, binding, preview/dry-run, sync MIRROR/APPEND_ONLY, lock, soglie, retry, riconciliazione, Celery.

### File ownership
- `app/integrations/mdblist/client.py`, `models.py`
- `app/services/planning.py`, `thresholds.py`, `sync.py`, `reconciliation.py`
- `app/repositories/targets.py`, `bindings.py`, `runs.py`
- `app/api/routers/targets.py`, `bindings.py`, `previews.py`, `runs.py`
- `app/jobs/celery_app.py`, `tasks.py`, `scheduler.py`
- aggiornare `app/api/router.py`

### Client MDBList
- Base URL `https://api.mdblist.com`, API key `apikey`.
- Metodi: `get_user_lists`, `get_list(list_id)`, `get_items(list_id, cursor, limit)`, `create_list(name, private)`, `add_items(list_id, movies, shows)`, `remove_items(...)`, `reorder(list_id, items, position/after/before)`, `membership(mediatype, tmdb/imdb)`.
- Cursor: `next_cursor`; header `X-Has-More`.
- Rate limit: 1.000 read / 300 write per 5 min; `Retry-After` su 429.
- Timeout: sollevare `MdbListTimeout`; il chiamante riconcilia.
- Errori: `MdbListAuthError`, `MdbListPermissionError`, `MdbListRateLimitError`, `MdbListNotFoundError`, `MdbListServerError`.
- Non usare endpoint non documentati.

### Planning
- `plan_sync(collection, snapshot, remote_items, binding, policy) -> SyncPlan`.
- Campi: `to_add`, `to_remove`, `unchanged`, `unresolved`, `unmapped_remote`, `remote_duplicates`, `reorder_needed`, `plan_hash`, `snapshot_hash`, `order_enforced`.
- MIRROR: add + remove; APPEND_ONLY: solo add.
- Ordine: ADD → REMOVE → REORDER.
- Snapshot non valido/vuoto → `blocked`.
- Soglie assolute/percentuali; `AWAITING_APPROVAL` se superate.
- `plan_hash = sha256(mode|snapshot_hash|sorted(to_add)|sorted(to_remove)|policy_version)`.

### Sync executor
- Crea `SyncRun` e `SyncOperation` prima dell'invio.
- Lock: `pg_try_advisory_lock` su PostgreSQL; per SQLite un lock in-process nel test.
- Batch 100; throttle; `Retry-After`.
- Dopo timeout: `UNCERTAIN`, rileggi remoto, poi decidi.
- Riconciliazione finale: rileggi lista e verifica.
- Reorder opzionale; fallimento → `SUCCEEDED` con warning `ORDER_NOT_ENFORCED`.
- `PARTIAL` per add/remove falliti/incerti.
- `not_found` per media, con soppressione dopo 3 rifiuti.

### API
- `GET /api/targets`, `POST /api/targets` (crea lista MDBList; richiede credenziale).
- `GET /api/bindings`, `POST /api/bindings`, `GET /api/bindings/{id}`.
- `POST /api/previews` → calcola piano; nessuna scrittura; richiede snapshot valido e target.
- `GET /api/runs`, `GET /api/runs/{id}`, `GET /api/runs/{id}/operations`.
- `POST /api/bindings/{id}/runs` → `202 {run_id}`; dry-run non scrive.
- `POST /api/runs/{id}/approve` → richiede `plan_hash`.
- `POST /api/runs/{id}/reconcile`, `POST /api/runs/{id}/resume`.

### Celery
- `app/jobs/celery_app.py`: Celery con broker Redis; `task_always_eager` da config.
- `acquire_collection_task(collection_id)` chiama il servizio di Lane B.
- `run_sync_task(run_id)` chiama il sync executor.
- `enqueue_due_bindings` periodico (beat) e `cleanup_old_data`.
- Scheduler: `celery -A app.jobs.celery_app beat`.

### Test minimi
- planner MIRROR/APPEND_ONLY, soglie, snapshot vuoto/incompleto, unresolved.
- MDBList contract con `respx`: items cursor, add/remove, 429, timeout.
- idempotenza e lock.
- reorder chunking e warning.
- API preview/run con TestClient e SQLite/eager Celery.

### Divieti
- Non cancellare/ricreare liste MDBList.
- Non fare retry cieco dopo timeout.
- Non dichiarare MDBList verificato live senza API key.
- Non usare `BackgroundTasks`.
