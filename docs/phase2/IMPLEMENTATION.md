# Fase 2 — Contratto di implementazione

**Obiettivo:** rendere il progetto eseguibile con Docker Compose, database, migrazioni, autenticazione, API e frontend shell. Includere il codice dei connettori TMDb/MDBList e del motore di sync, ma **non dichiararli verificati live** senza API key reali.

**Riferimenti obbligatori:** `docs/phase1/00-executive-summary.md`, `03-architecture.md`, `04-data-model.md`, `05-sync-engine.md`, `06-security.md`, `07-frontend-api.md`, `08-ops-tests-risks.md`, `schema.sql`.

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
- `scripts/backup.sh`, `restore.sh`
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
- `scripts/backup.sh` con `pg_dump -Fc` + `age`; `restore.sh`.
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
