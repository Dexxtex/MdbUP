# Fase 02 — Contratto di implementazione e stato

> Report consolidato della fase. Le fonti originali sono state unite in questo documento.


---

## Fonte: `phase-02.md`

# Brief operativi per le lane backend

Questi brief integrano `docs/phases/phase-02.md`. Ogni agente deve leggere entrambi.

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
- Non inventare endpoint: usare solo quelli verificati in `docs/phases/phase-01.md`.

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


---

## Fonte: `phase-02.md`

# Fase 2 — Contratto di implementazione

**Obiettivo:** rendere il progetto eseguibile con Docker Compose, database, migrazioni, autenticazione, API e frontend shell. Includere il codice dei connettori TMDb/MDBList e del motore di sync, ma **non dichiararli verificati live** senza API key reali.

**Riferimenti obbligatori:** `docs/phases/phase-01.md`, `03-architecture.md`, `04-data-model.md`, `05-sync-engine.md`, `06-security.md`, `07-frontend-api.md`, `08-ops-tests-risks.md`, `schema.sql`.

---

## 1. Regole condivise

- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (sincrono), Alembic, PostgreSQL 16, HTTPX.
- Frontend React 18 + TypeScript + Vite + TanStack Query + React Hook Form + Zod + Tailwind.
- UI e documentazione in italiano; identificatori in inglese.
- Nessun segreto nel repository, nei log, nelle risposte API o nel browser.
- Nessun connettore mock in produzione. I test usano fixture sintetiche e `respx`.
- Non usare `BackgroundTasks` per job lunghi. Le API enqueue task Celery e rispondono `202`.
- Non usare il titolo come chiave: identità `(media_type, tmdb_id)` con fallback `(media_type, imdb_id)`.
- Film e serie separati in ogni chiave, target, binding e run.
- `OFFICIAL` solo con fonte ufficiale; TMDb è `AGGREGATOR`.
- `date_basis` sempre esplicito; TMDb non ha data di aggiunta.
- Se una funzionalità non è verificabile senza credenziali, restituire `503`/`BLOCKED` con messaggio chiaro, non un risultato finto.

---

## 2. Ownership dei file

### Agente A — Backend foundation (cwd `backend/`)
- `app/core/config.py`, `logging.py`, `crypto.py`, `security.py`, `time.py`
- `app/db/base.py`, `session.py`, `models/*.py`
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_initial.py`
- `app/api/deps.py`, `errors.py`, `schemas.py`, `router.py`
- `app/api/routers/auth.py`, `health.py`, `settings.py`, `credentials.py`
- `app/repositories/users.py`, `settings.py`, `credentials.py`, `audit.py`
- `app/services/auth.py`, `credentials.py`
- `app/main.py`
- `app/cli.py` (bootstrap admin, seed providers)
- stub per router/servizi delle feature (le altre lane li sostituiscono)

### Agente B — Backend data/API (cwd `backend/`, dopo A)
- `app/repositories/providers.py`, `sources.py`, `collections.py`, `snapshots.py`, `media.py`
- `app/services/acquisition.py`, `normalization.py`, `snapshots.py`, `dashboard.py`
- `app/connectors/registry.py`, `connectors/tmdb/*`, `connectors/manual_csv/*`
- `app/integrations/tmdb/*`
- `app/api/routers/dashboard.py`, `providers.py`, `sources.py`, `collections.py`, `snapshots.py`
- aggiornare `app/api/router.py` per includere i router
- seed provider/collezioni TMDb in `app/cli.py` o in un modulo `app/seed.py`

### Agente C — Backend sync (cwd `backend/`, dopo B)
- `app/integrations/mdblist/*`
- `app/services/planning.py`, `thresholds.py`, `sync.py`, `reconciliation.py`
- `app/repositories/targets.py`, `bindings.py`, `runs.py`
- `app/api/routers/targets.py`, `bindings.py`, `previews.py`, `runs.py`
- `app/jobs/celery_app.py`, `tasks.py`, `scheduler.py`
- aggiornare `app/api/router.py` per includere i router

### Agente D — Frontend (cwd `frontend/`)
- tutto `frontend/` (package.json, Vite, TS, Tailwind, pagine, client API, test)
- non modificare `backend/`

### Agente E — Deploy/CI (cwd `deploy/`, con accesso a root per `.github` e `scripts/`)
- `deploy/docker-compose.yml`, `Caddyfile`, `Dockerfile.api`
- `frontend/Dockerfile` (coordinare con D: D può crearlo; E lo valida)
- `deploy/scripts/backup.sh`, `restore.sh`
- `.github/workflows/ci.yml`
- `.dockerignore`
- non modificare `backend/` o `frontend/src/`

### Agente F — Test (cwd `backend/`, dopo C)
- `tests/unit/*`, `tests/integration/*`, `tests/contract/*`, `tests/fixtures/*`
- `tests/conftest.py`
- può correggere bug trovati, ma non riscrivere interi moduli

---

## 3. Configurazione

`app/core/config.py` usa `pydantic-settings`. Variabili principali:

```text
APP_ENV=dev|test|production
APP_BASE_URL=http://localhost:8000
APP_TIMEZONE=Europe/Rome
LOG_LEVEL=INFO
LOG_FORMAT=json
DATABASE_URL=sqlite:///./mdbup.db   # produzione: postgresql+psycopg://...
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
CELERY_TASK_ALWAYS_EAGER=false
APP_ENCRYPTION_KEY=<base64 32 byte>
APP_ENCRYPTION_KEY_VERSION=1
BOOTSTRAP_TOKEN=<token monouso>
SESSION_COOKIE_NAME=mdbsync-session
CSRF_COOKIE_NAME=mdbsync-csrf
COOKIE_SECURE=false
SESSION_TTL_DAYS=7
SESSION_IDLE_HOURS=12
LOGIN_MAX_ATTEMPTS=5
LOGIN_WINDOW_MINUTES=15
SYNC_BATCH_SIZE=100
SYNC_MAX_REMOVAL_ABSOLUTE=50
SYNC_MAX_REMOVAL_PERCENT=10
SYNC_MAX_ADDITION_PERCENT=50
```

In produzione i segreti possono arrivare da file (`*_FILE`). Implementare un helper `read_secret(name)` che legge `NAME_FILE` se presente, altrimenti `NAME`.

---

## 4. Modelli DB (SQLAlchemy)

Usare tipi generici per compatibilità SQLite nei test:
- `Uuid` SQLAlchemy per le PK.
- `JSON` per JSONB.
- `String` per CITEXT/INET/array.
- `DateTime(timezone=True)`.
- `Numeric(5,2)` per percentuali.
- `String` + `CheckConstraint` per gli enum.

Tabelle minime (vedi `schema.sql` per i campi):
`app_user`, `session`, `app_setting`, `credential`, `source`, `provider`, `provider_mapping`, `collection`, `media`, `availability`, `collection_snapshot`, `snapshot_item`, `mdblist_target`, `sync_binding`, `sync_run`, `sync_operation`, `sync_run_event`, `episode_event`, `job_execution`, `audit_log`, `source_healthcheck`.

Vincoli importanti:
- `media` unique `(tmdb_id, media_type)` e `(imdb_id, media_type)`.
- `collection_snapshot` un solo `RUNNING` per collection.
- `sync_binding` unique `(collection_id, target_id)` e un solo binding attivo per target.
- `sync_run` un solo run attivo per binding e per target.
- `sync_operation.idempotency_key` unique.
- `credential` unique `(scope, source_id, key)`.
- `audit_log` append-only a livello applicativo (trigger non necessario in SQLite).

Migrazione `0001_initial`: può usare `Base.metadata.create_all(op.get_bind())` e `drop_all` nel downgrade, oppure `op.create_table` espliciti. Documentare la scelta. Deve funzionare su SQLite (test) e PostgreSQL (produzione).

---

## 5. Auth e sicurezza

- Bootstrap: `POST /api/auth/bootstrap` con `{token,email,password}`. Se esistono utenti → `409`. Token da `BOOTSTRAP_TOKEN`, confronto `secrets.compare_digest`. Password Argon2id.
- Login: `POST /api/auth/login` con `{email,password}`. Rate limit per IP+email. Cookie sessione HttpOnly + cookie CSRF non HttpOnly. Risposta `{user, csrf_token}`.
- `GET /api/auth/session` → `{user, csrf_token}`.
- `POST /api/auth/logout` → revoca sessione.
- CSRF: per `POST/PUT/PATCH/DELETE` (eccetto login/bootstrap) richiedere `X-CSRF-Token` uguale al token della sessione; verificare `Origin`/`Referer` se presenti.
- Sessioni: token opaco 32 byte, hash SHA-256 in DB, scadenza assoluta e idle.
- Credenziali: AES-256-GCM, nonce 12 byte, AAD `scope|source_id|key|version`, `masked_hint` ultimi 4 caratteri. Nessun endpoint restituisce il plaintext.
- Log: JSON, redazione di `password`, `token`, `apikey`, `authorization`, `cookie`, `secret`.
- Errori API: envelope `{"error":{"code","category","message","retryable","request_id","details"}}`.

---

## 6. API minime

Tutte sotto `/api`. Risposte JSON. Errori con envelope.

### Health
- `GET /api/health` → `{status:"ok", version}`
- `GET /api/ready` → `{status, checks:{db,redis,encryption_key}}`; 503 se DB non pronto.

### Auth
- `POST /api/auth/bootstrap`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/session`

### Dashboard / providers / sources
- `GET /api/dashboard` → contatori, ultimi run, alert, stato fonti.
- `GET /api/providers?country=IT` → lista provider con mapping.
- `GET /api/sources` → fonti con `capabilities`, `status`.
- `POST /api/sources/{id}/healthcheck` → `202 {job_id}` (può essere stub in Fase 2).

### Collections / snapshots
- `GET /api/collections?provider_id=&media_type=&origin=`
- `GET /api/collections/{id}`
- `GET /api/collections/{id}/snapshots`
- `GET /api/snapshots/{id}/items?page=&page_size=`
- `POST /api/collections/{id}/acquire` → `202 {job_id}`; se manca credenziale TMDb → `409 CREDENTIAL_MISSING`.

### Targets / bindings / previews / runs
- `GET /api/targets`
- `POST /api/targets` → crea lista MDBList (richiede credenziale MDBList)
- `GET /api/bindings`
- `POST /api/bindings`
- `GET /api/bindings/{id}`
- `POST /api/previews` → calcola piano da snapshot valido + lista remota; nessuna scrittura.
- `GET /api/runs`
- `GET /api/runs/{id}`
- `GET /api/runs/{id}/operations`
- `POST /api/bindings/{id}/runs` → `202 {run_id}`; dry-run non scrive.
- `POST /api/runs/{id}/approve` → `202`; richiede `plan_hash`.

### Settings / credentials
- `GET /api/settings`, `PATCH /api/settings`
- `GET /api/credentials` → solo `kind`, `configured`, `masked_hint`, `key_version`, `last_verified_at`
- `PUT /api/credentials/{kind}` → salva cifrato
- `DELETE /api/credentials/{kind}`
- `POST /api/credentials/{kind}/verify` → test connessione (TMDb/MDBList); `202` o `200` con esito.

---

## 7. Connettore TMDb

- Base URL `https://api.themoviedb.org/3`, Bearer token.
- `discover/movie` e `discover/tv` con `watch_region=IT`, `with_watch_providers=<id>`, `with_watch_monetization_types=flatrate`, `page`.
- `watch/providers/movie|tv?watch_region=IT` per mapping provider.
- `movie/{id}/external_ids`, `tv/{id}/external_ids` per IMDb.
- Capability: `catalog=True`, `recently_added=False`, `added_dates=False`, `full_pagination=False` (cap 500 pagine), `seasons_episodes=True` (metadati), `requires_credentials=True`.
- `normalize_item` non inventa ID; se manca TMDB, usa IMDb; se manca tutto → `UNRESOLVED`.
- `date_basis=UNKNOWN`, `source_date_created=None`.
- Rispettare `429` con `Retry-After` e backoff.

## 8. Client MDBList

- Base URL `https://api.mdblist.com`, API key query `apikey`.
- `GET /lists/user`, `GET /lists/{id}`, `GET /lists/{id}/items?cursor=&limit=`, `POST /lists/user/add`, `POST /lists/{id}/items/add|remove`, `POST /lists/{id}/items/reorder`.
- Cursor: `next_cursor`; header `X-Has-More`.
- Rate limit: 1.000 read / 300 write per 5 min; `Retry-After` su 429.
- Add/remove body `{movies:[{tmdb,imdb?}], shows:[{tmdb,imdb?}]}`; risposta `{added, removed, existing, not_found}`.
- Reorder body `{items:[{mediatype,ids}], position|after|before}`; max 1.000.
- Timeout: non ritentare cieco; il chiamante riconcilia.

## 9. Sync engine

- `plan_sync(collection, snapshot, remote_items, binding) -> SyncPlan`.
- `to_add`, `to_remove`, `unchanged`, `unresolved`, `unmapped_remote`, `remote_duplicates`.
- MIRROR: add + remove; APPEND_ONLY: solo add.
- Ordine: ADD → REMOVE → REORDER.
- Soglie: assolute/percentuali; se superate → `AWAITING_APPROVAL` (o `BLOCKED` se policy).
- Snapshot non valido/vuoto → `BLOCKED`.
- `plan_hash` = SHA-256 di mode, snapshot checksum, to_add/to_remove ordinati, policy version.
- Lock: `pg_try_advisory_lock` in produzione; per SQLite usare un lock in-process nel test.
- Idempotenza: `sync_operation.idempotency_key` unique.
- Riconciliazione: dopo timeout, rileggere la lista; non retry cieco.
- Reorder fallito → `SUCCEEDED` con warning `ORDER_NOT_ENFORCED`.

## 10. Frontend

Pagine minime:
- `/login`, `/bootstrap`
- `/app` dashboard
- `/app/providers`
- `/app/collections`, `/app/collections/:id`
- `/app/bindings`, `/app/bindings/new` (wizard semplificato ma con gli 8 step logici)
- `/app/runs/:id`
- `/app/settings`

Requisiti:
- `apiFetch` con `credentials: "include"`, CSRF header, parsing error envelope.
- TanStack Query per dashboard, provider, collezioni, binding, run; polling 2s sui run attivi.
- Form login/bootstrap con RHF + Zod.
- Badge `OriginBadge` e `DateBasisBadge`.
- Stati loading/empty/error/stale.
- Nessun segreto in localStorage/sessionStorage.
- Tailwind, layout responsive, accessibilità di base (label, focus, tastiera).
- `npm run build` deve passare.

## 11. Deploy

- `deploy/docker-compose.yml`: `proxy`, `frontend`, `api`, `worker`, `scheduler`, `migrate`, `postgres`, `redis`.
- `proxy` Caddy: TLS, `/api/*` → `api:8000`, resto → `frontend:8080`.
- `postgres`/`redis` senza `ports`, rete `internal`.
- `api` dipende da `migrate` completato.
- Healthcheck per tutti i servizi.
- Volumi `pgdata`, `redisdata`, `caddy_data`, `caddy_config`, `backups`.
- `Dockerfile.api` multi-stage, non-root, `read_only` dove possibile.
- `frontend/Dockerfile` build Node + Nginx.
- `deploy/scripts/backup.sh` con `pg_dump -Fc` + `age`; `restore.sh`.
- `.github/workflows/ci.yml`: lint, typecheck, test, build, migrations, security scan.

## 12. Test e accettazione

Comandi:
```bash
cd backend
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run python -m compileall app
```

Test minimi:
- crypto round-trip, AAD errata, key version.
- password hash/verify, session token, CSRF.
- media key: film vs serie, IMDb fallback, unresolved.
- planner: MIRROR, APPEND_ONLY, soglie, snapshot vuoto/incompleto, reorder.
- API auth: bootstrap una volta, login, sessione, logout, CSRF.
- API health/ready.
- contract MDBList con `respx`: items cursor, add/remove, 429, timeout.
- contract TMDb con `respx`: discover, watch providers, 429.

Accettazione Fase 2:
- `uv run pytest` verde (o test DB skippati con motivo se PostgreSQL non disponibile).
- `uv run ruff check .` verde.
- `npm run build` verde.
- `docker compose config` non eseguibile qui (Docker assente), ma YAML valido.
- Nessun segreto nei file.
- README aggiornato con stato reale e comandi.

---

## 13. Cosa non fare

- Non dichiarare TMDb/MDBList "funzionanti live" senza API key e test reale.
- Non usare dati simulati in produzione.
- Non creare collezioni `OFFICIAL` senza fonte ufficiale.
- Non usare `BackgroundTasks` per job lunghi.
- Non cancellare/ricreare liste MDBList.
- Non inserire segreti in `.env.example`, log, risposte API o frontend.
- Non modificare i documenti di Fase 1 per farli combaciare con il codice: il codice si allinea ai documenti, non il contrario.


---

## Fonte: `phase-02.md`

# Fase 2 — Stato di implementazione

**Data:** 2026-11-17
**Stato:** Fase 2 completa e **Fase 3 verificata live** su server Ubuntu con Docker Compose. Le lane A (fondazione), B (catalogo TMDb), C (sync MDBList), D (frontend) ed E (deploy/CI) sono complete.

> **Verificato live:** stack Docker avviato (PostgreSQL 16, Redis 7, API, worker, scheduler, Caddy, frontend); TMDb e MDBList chiamati con credenziali reali; tre collezioni Netflix Italia per genere (Azione, Avventura, Horror) acquisite in snapshot validi; tre liste statiche MDBList create e popolate con **755 / 428 / 365** film; confronto TMDb ↔ MDBList con **0 mancanti e 0 extra**. I test automatici restano 168 backend + 42 frontend. La Fase 4 (automazione e robustezza) è documentata in [`docs/phases/phase-04.md`](phase-04.md).

---

## 1. Cosa è implementato

### Backend — fondazione
- FastAPI con router sotto `/api`, OpenAPI, error envelope unico, request-id e security headers.
- Config `pydantic-settings` con supporto `*_FILE` (Docker secrets).
- Logging structlog JSON con redazione centralizzata.
- Cifratura AES-256-GCM delle credenziali, AAD per scope/source/key/version, masking.
- Auth: bootstrap con `BOOTSTRAP_TOKEN`, login, logout, sessione HttpOnly, CSRF double-submit, rate limit Redis con fallback in-memory, Argon2id.
- Modelli SQLAlchemy per 21 tabelle, migrazione Alembic `0001_initial`, upgrade/downgrade su SQLite e PostgreSQL.
- CLI `bootstrap-admin` e `seed-providers`.
- Test: 45 test iniziali (poi estesi a 92 con la lane B, 168 totali dopo lane C, fix e Fase 4).

### Backend — catalogo TMDb
- Client TMDb sincrono con API key v3 (`api_key`) o Bearer v4, timeout, `follow_redirects=False`, retry 429 limitato, filtro `with_genres`.
- Connettore TMDb con capability flags, discover movie/tv, watch providers, normalizzazione, cap 500 pagine.
- Acquisizione: snapshot immutabile, paginazione, dedup `(media_type, tmdb_id)`, risoluzione/creazione `Media`, `SnapshotItem`, checksum, validità esplicita, `last_valid_snapshot_id` solo se valido.
- API: dashboard, providers, sources, collections, snapshots, acquire.
- Seed: 8 provider IT, mapping TMDb (marcati `is_verified=False`), 16 collezioni movie/show `AGGREGATOR`/`UNKNOWN`/`FLATRATE`.
- Test: 47 nuovi test (unit, contract TMDb, integration), totale 92 verdi.

### Backend — sync MDBList
- Client MDBList con cursor e fallback offset (API live), add/remove, reorder, errori tipizzati, `Retry-After`.
- Planning MIRROR/APPEND_ONLY, soglie, `plan_hash`, `snapshot_hash`.
- Sync executor con operation ledger, lock per target, ADD→REMOVE→REORDER, retry, riconciliazione post-timeout, warning `ORDER_NOT_ENFORCED`.
- API targets/bindings/previews/runs, job Celery.
- Test: contract MDBList, planner, executor, retry, scheduler, lock PostgreSQL (pgserver).

### Frontend
- React 18 + TypeScript + Vite + TanStack Query + RHF + Zod + Tailwind + React Router.
- Pagine: login, bootstrap, dashboard, provider, collezioni, dettaglio collezione, binding, wizard, dettaglio run, impostazioni.
- Client API tipizzato, CSRF, error envelope, polling run attivi, stati loading/empty/error/stale.
- Build Vite, typecheck, ESLint e 41 test Vitest verdi.
- Allineamento ai payload reali del backend in corso.

### Deploy / CI
- `deploy/docker-compose.yml` con proxy Caddy, frontend Nginx, api, worker, scheduler, migrate, PostgreSQL 16, Redis 7.
- Reti `edge`/`internal`/`egress`, PostgreSQL/Redis non pubblicati, secrets, healthcheck, limiti, non-root/read-only.
- `deploy/Caddyfile`, `deploy/Dockerfile.api`, `frontend/Dockerfile`, `frontend/nginx.conf`.
- `deploy/scripts/backup.sh`, `deploy/scripts/restore.sh` con `pg_dump`, `age`, checksum, retention, restore.
- `.github/workflows/ci.yml` con lint/typecheck/test/migrations/build/security.
- Stack avviato e verificato su Ubuntu; `docker compose config` valido.

---

## 1.1 Verifica live (2026-11-17)

| Elemento | Valore verificato |
|---|---|
| Server | Ubuntu, Docker 29.9.3, Compose v5.7.1 |
| URL | `http://192.0.2.10:8088` |
| Stack | 7/7 servizi healthy, 0 restart |
| TMDb | API key v3 valida; `healthcheck` OK |
| MDBList | API key valida; 20 liste account lette |
| Snapshot Azione | `COMPLETE`/`CLEAN`/valido, 755 item, 38/38 pagine, 0 unresolved |
| Snapshot Avventura | `COMPLETE`/`CLEAN`/valido, 428 item, 22/22 pagine, 0 unresolved |
| Snapshot Horror | `COMPLETE`/`CLEAN`/valido, 365 item, 19/19 pagine, 0 unresolved |
| Run Azione | `SUCCEEDED`, 755 added, 0 failed/uncertain |
| Run Avventura | `SUCCEEDED`, 428 added, 0 failed/uncertain |
| Run Horror | `SUCCEEDED`, 365 added, 0 failed/uncertain |
| Confronto ID TMDb | Azione 755/755, Avventura 428/428, Horror 365/365; missing=0, extra=0 |
| Liste pubbliche | `mdblist.com/lists/netflix-it-film-azione/`, `…-avventura/`, `…-horror/` → 200 |

**Nota:** le liste sono pubbliche e i binding sono `MANUAL` (nessuna schedulazione automatica). Il primo popolamento ha richiesto alcuni minuti per il throttle di scrittura MDBList (240 item/5 min).

---

## 2. Comandi di sviluppo

### Backend
```bash
cd backend
uv sync --extra dev
export APP_ENV=dev
export APP_ENCRYPTION_KEY="$(python -c 'import base64,os; print(base64.b64encode(os.urandom(32)).decode())')"
export BOOTSTRAP_TOKEN="dev-bootstrap-token"
uv run alembic upgrade head
uv run python -m app.cli seed-providers
uv run python -m app.cli bootstrap-admin --email admin@example.com
uv run uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# http://localhost:5173, proxy /api -> http://localhost:8000 (vedi vite.config.ts)
```

### Test
```bash
cd backend
REDIS_URL="" APP_ENV=test uv run pytest -q
uv run ruff check .
uv run python -m compileall app

cd ../frontend
npm run build
npm test
npm run lint
```

### Docker Compose (previsto, non eseguito qui)
```bash
cp .env.example .env
mkdir -p secrets
# creare secrets/postgres_password, secrets/app_encryption_key,
# secrets/bootstrap_token, secrets/backup_age_recipient
docker compose --env-file .env -f deploy/docker-compose.yml up -d
docker compose --env-file .env -f deploy/docker-compose.yml run --rm migrate
```

---

## 3. Cosa è verificato e cosa no

| Area | Stato | Evidenza |
|---|---|---|
| Migrazione Alembic | **Verificata** | upgrade/downgrade su SQLite e PostgreSQL 16 (pgserver e container) |
| Auth, CSRF, crypto, settings, credentials | **Verificata** | test unit/integration + login live |
| TMDb connector | **Verificato live** | API key v3, discover con `with_genres`, 79 pagine |
| Acquisizione snapshot | **Verificata live** | 3 snapshot validi, 1.548 item totali |
| MDBList client/sync | **Verificato live** | 3 liste, 1.548 ADD, 0 failed/uncertain |
| Frontend build/test | **Verificato** | Vite build, 41 test, ESLint, SPA live |
| Docker Compose | **Verificato** | 7/7 healthy, 0 restart |
| TMDb live | **OK** | API key reale |
| MDBList live | **OK** | API key reale |
| JustWatch | **Disabilitato** | contratto assente |

---

## 3.1 Correzioni post-review

- `X-Forwarded-For`: il backend usa l'ultimo hop e Caddy sovrascrive l'header con `{remote_host}`; il rate limit non è più aggirabile con un header client.
- Reorder in riconciliazione: `reconcile_run` acquisisce il lock per target prima di scrivere; se il lock è occupato restituisce `LOCK_HELD` e `ORDER_NOT_ENFORCED`.
- REMOVE non applicata: se l'elemento è ancora presente dopo il read-back, l'operazione è `FAILED` (`MDBLIST_REMOVE_NOT_APPLIED`), non `SKIPPED`; il run non può più risultare `SUCCEEDED` con l'elemento ancora in lista.
- Cancel: rifiutato con `409 RUN_IN_PROGRESS` durante `APPLYING`/`VERIFYING`; usare `reconcile`.
- Sweep: task beat `sweep_stale_runs` ogni 15 minuti; i run `APPLYING`/`VERIFYING` orfani vengono riaccodati in riconciliazione, gli altri marcati `FAILED`.
- `plan_hash`: preview e run usano la stessa `policy_version` (`planning-v1`); il wizard invia `planning-v1`.
- Retention: `collection_snapshot.job_execution_id` è `ON DELETE SET NULL`; il cleanup azzera `sync_binding.last_run_id` prima di cancellare i run.
- Admin guard su settings/credentials; errori di validazione con `details.fields` per il frontend.

## 4. Limitazioni note

- I mapping provider TMDb sono seed non verificati (`is_verified=False`); il provider Netflix (8) è stato usato live con successo, ma gli altri mapping non sono stati confermati con `/watch/providers`.
- TMDb non espone la data di aggiunta: le collezioni sono "disponibilità corrente", non "aggiunte recenti".
- JustWatch Partner/Data Export è disabilitato: richiede contratto.
- Il reorder MDBList è opzionale, max 1.000 elementi per chiamata e non atomico.
- Il throttle di scrittura MDBList è process-local (240 item/5 min): il primo popolamento di 755 film richiede alcuni minuti; con più worker serve un token bucket Redis.
- Le tre liste sono pubbliche e i binding sono `MANUAL`: non si aggiornano automaticamente. Per aggiornarle usare un run manuale o creare un binding con schedule.
- HTTP LAN senza TLS: cookie non `__Host-` e `COOKIE_SECURE=false`; per esposizione Internet usare HTTPS e i nomi `__Host-`.
- La copertura test frontend è minima (unit/validation/client), non include ancora E2E Playwright.

---

## 5. Prossimi passi

1. Decidere se rendere private le tre liste MDBList o lasciarle pubbliche.
2. Configurare uno schedule (es. giornaliero) per i binding se si vuole l'aggiornamento automatico.
3. Verificare i mapping TMDb degli altri provider con `/watch/providers`.
4. Aggiungere E2E Playwright e un test di carico per preview/sync su liste grandi.
5. Solo dopo: valutare JustWatch Partner e le collezioni "aggiunte recenti" con `date_basis=AGGREGATOR_FIRST_SEEN`.
