# Fase 2 — Stato di implementazione

**Data:** 2026-11-17
**Stato:** Fase 2 completa e **Fase 3 verificata live** su server Ubuntu con Docker Compose. Le lane A (fondazione), B (catalogo TMDb), C (sync MDBList), D (frontend) ed E (deploy/CI) sono complete.

> **Verificato live:** stack Docker avviato (PostgreSQL 16, Redis 7, API, worker, scheduler, Caddy, frontend); TMDb e MDBList chiamati con credenziali reali; tre collezioni Netflix Italia per genere (Azione, Avventura, Horror) acquisite in snapshot validi; tre liste statiche MDBList create e popolate con **755 / 428 / 365** film; confronto TMDb ↔ MDBList con **0 mancanti e 0 extra**. I test automatici restano 168 backend + 42 frontend. La Fase 4 (automazione e robustezza) è documentata in [`docs/phase4/STATUS.md`](../phase4/STATUS.md).

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
- `scripts/backup.sh`, `scripts/restore.sh` con `pg_dump`, `age`, checksum, retention, restore.
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
