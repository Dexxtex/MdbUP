# Fase 1 — Operazioni, test e rischi

**Stato:** progettazione. Nessun servizio implementato, nessun connettore reale, nessun dato simulato in produzione.
**Riferimenti:** [`03-architecture.md`](03-architecture.md), [`04-data-model.md`](04-data-model.md), [`05-sync-engine.md`](05-sync-engine.md), [`06-security.md`](06-security.md).

**Regola trasversale:** ogni dato ha origine dichiarata (`OFFICIAL`/`AGGREGATOR`/`CUSTOM`) e, se ha una data, un `date_basis`. Un test che non distingue la provenienza è incompleto. Un connettore mock non è avviabile con `APP_ENV=production` (guardia all'avvio, non solo in CI).

---

## 1. Docker Compose

### 1.1 Servizi

| Servizio | Immagine | Comando | Ruolo |
|---|---|---|---|
| `proxy` | `caddy:2.8-alpine` | `caddy run --config /etc/caddy/Caddyfile` | TLS, `/api/*` → `api:8000`, resto → `frontend:8080`, header di sicurezza |
| `frontend` | `nginx:1.27-alpine` (build da `node:20-alpine`) | `nginx -g "daemon off;"` | `dist/` con SPA fallback, nessun segreto |
| `api` | `mdbup-api:local` (python:3.12-slim) | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers` | HTTP, auth, orchestrazione, nessun job lungo |
| `worker` | stessa immagine | `celery -A app.jobs.celery_app worker -Q acquisitions,sync,maintenance -c 2 --max-tasks-per-child=200` | Acquisizione, sync, manutenzione |
| `scheduler` | stessa immagine | `celery -A app.jobs.celery_app beat -s /tmp/celerybeat-schedule` | Tick periodici: binding dovuti, healthcheck, retention |
| `migrate` | stessa immagine | `alembic upgrade head` | One-shot |
| `postgres` | `postgres:16-alpine` | default | Dati |
| `redis` | `redis:7-alpine` | `redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy noeviction` | Broker, cache, rate limit |

`api`, `worker`, `scheduler`, `migrate` condividono **una sola immagine**, diversa solo per comando: una superficie di supply chain, nessuna deriva di versione.

### 1.2 Compose (estratto normativo)

```yaml
x-app: &app
  image: mdbup-api:local
  build: { context: ., dockerfile: deploy/Dockerfile.api }
  env_file: [.env]
  user: "10001:10001"
  read_only: true
  tmpfs: ["/tmp:size=64m,mode=1777"]
  cap_drop: ["ALL"]
  security_opt: ["no-new-privileges:true"]
  restart: unless-stopped
  depends_on:
    postgres: { condition: service_healthy }
    redis: { condition: service_healthy }
  networks: [internal]
  logging: { driver: json-file, options: { max-size: "10m", max-file: "5" } }

services:
  proxy:
    image: caddy:2.8-alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./deploy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks: [edge]
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:2019/config/"]
      interval: 30s
      timeout: 5s
      retries: 3

  frontend:
    image: mdbup-frontend:local
    build: { context: ./frontend, dockerfile: Dockerfile }
    read_only: true
    tmpfs: ["/var/cache/nginx", "/var/run"]
    networks: [edge]
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:8080/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3

  api:
    <<: *app
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
    networks: [edge, internal]
    depends_on:
      migrate: { condition: service_completed_successfully }
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "python", "-m", "app.ops.healthcheck", "http://127.0.0.1:8000/api/health"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 20s

  worker:
    <<: *app
    command: ["celery", "-A", "app.jobs.celery_app", "worker",
              "-Q", "acquisitions,sync,maintenance", "-c", "2",
              "--max-tasks-per-child=200"]
    healthcheck:
      test: ["CMD-SHELL", "celery -A app.jobs.celery_app inspect ping -d celery@$$HOSTNAME"]
      interval: 30s
      timeout: 10s
      retries: 3

  scheduler:
    <<: *app
    command: ["celery", "-A", "app.jobs.celery_app", "beat",
              "-s", "/tmp/celerybeat-schedule"]
    healthcheck:
      test: ["CMD-SHELL", "pgrep -f 'celery.*beat' >/dev/null"]
      interval: 30s
      timeout: 5s
      retries: 3

  migrate:
    <<: *app
    command: ["alembic", "upgrade", "head"]
    restart: "no"

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: mdbup
      POSTGRES_USER: mdbup
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    secrets: [postgres_password]
    volumes: ["pgdata:/var/lib/postgresql/data"]
    networks: [internal]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mdbup -d mdbup"]
      interval: 10s
      timeout: 5s
      retries: 10
    command: ["postgres", "-c", "shared_buffers=256MB", "-c", "max_connections=60"]

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes", "--maxmemory", "256mb",
              "--maxmemory-policy", "noeviction"]
    volumes: ["redisdata:/data"]
    networks: [internal]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

networks:
  edge: {}
  internal: { internal: true }

volumes:
  pgdata: {}
  redisdata: {}
  caddy_data: {}
  caddy_config: {}
  backups: {}
  jw_export_cache: {}

secrets:
  postgres_password:
    file: ./secrets/postgres_password
  app_encryption_key:
    file: ./secrets/app_encryption_key
  bootstrap_token:
    file: ./secrets/bootstrap_token
```

`api`, `worker` e `scheduler` montano `app_encryption_key` e `bootstrap_token`; `postgres` monta `postgres_password`. I file in `./secrets/` non vanno committati (vedi `.gitignore`).

**Limiti** (`deploy.resources.limits`): proxy 0.5 CPU/128M, frontend 0.25/96M, api 1.0/512M, worker 1.0/768M, scheduler 0.25/256M, postgres 1.0/1G, redis 0.5/320M.

**Regole non negoziabili**
1. `internal: true`: PostgreSQL e Redis non sono raggiungibili da `proxy` né dall'host. Solo `proxy` pubblica porte.
2. Processi applicativi come UID/GID `10001`, rootfs `read_only`, `cap_drop: ALL`.
3. `api` non esegue `alembic upgrade` all'avvio: migrazione one-shot con `service_completed_successfully`.
4. `scheduler` ha una sola istanza: scalarlo duplica i tick.
5. `worker` non supera 2 processi finché il budget MDBList (300 scritture/5 min) non è distribuito da un token bucket su Redis.
6. `noeviction` su Redis: un job perso per eviction non viene riconciliato da nessuno.
7. Un solo `scheduler` (Celery beat) con task periodico `enqueue_due_bindings`: la pianificazione è DB-driven, non una entry di beat per binding.

---

## 2. Variabili d'ambiente e segreti

**Regola:** i segreti di infrastruttura (`APP_ENCRYPTION_KEY`, `BOOTSTRAP_TOKEN`, password PostgreSQL) stanno in Docker secrets/file, non in `.env`. Le credenziali delle integrazioni (TMDb, MDBList, JustWatch) **non stanno in env**: si inseriscono dall'interfaccia Impostazioni e vengono cifrate nel database. In alternativa, un comando CLI le importa nel DB cifrate.

```dotenv
# --- core ---
APP_ENV=production
APP_BASE_URL=https://mdblist-sync.example.com
APP_TIMEZONE=Europe/Rome
LOG_LEVEL=INFO
LOG_FORMAT=json

# --- database / cache ---
DATABASE_URL=postgresql+psycopg://mdbup:CHANGE_ME@postgres:5432/mdbup
# oppure: DATABASE_URL_FILE=/run/secrets/database_url
DB_POOL_SIZE=10
DB_STATEMENT_TIMEOUT_MS=15000
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# --- sicurezza ---
APP_ENCRYPTION_KEY_FILE=/run/secrets/app_encryption_key
APP_ENCRYPTION_KEY_VERSION=1
BOOTSTRAP_TOKEN_FILE=/run/secrets/bootstrap_token
SESSION_COOKIE_NAME=__Host-mdbsync-session
CSRF_COOKIE_NAME=__Host-mdbsync-csrf
SESSION_TTL_DAYS=7
SESSION_IDLE_HOURS=12
LOGIN_MAX_ATTEMPTS=5
LOGIN_WINDOW_MINUTES=15
LOGIN_LOCKOUT_MINUTES=30

# --- policy di sincronizzazione ---
SYNC_BATCH_SIZE=100
SYNC_MAX_REMOVAL_ABSOLUTE=50
SYNC_MAX_REMOVAL_PERCENT=10
SYNC_MAX_ADDITION_PERCENT=50
SNAPSHOT_RETENTION_DAYS=90
SCHEDULER_POLL_SECONDS=60
HTTP_TIMEOUT_SECONDS=20
HTTP_MAX_RETRIES=4
HTTP_BACKOFF_BASE_MS=500
HTTP_BACKOFF_MAX_MS=30000
HTTP_JITTER_RATIO=0.30

# --- proxy / osservabilità ---
PROXY_DOMAIN=mdblist-sync.example.com
ACME_EMAIL=admin@example.com
METRICS_ENABLED=true

# --- backup ---
BACKUP_DIR=/backups
BACKUP_RETENTION_DAILY=7
BACKUP_RETENTION_WEEKLY=4
BACKUP_RETENTION_MONTHLY=6
BACKUP_AGE_RECIPIENT_FILE=/run/secrets/backup_age_recipient
```

**Nota:** il file `.env.example` nel repository è una bozza coerente; i valori `CHANGE_ME` non sono segreti reali. Le credenziali TMDb/MDBList/JustWatch non vanno in `.env`: si inseriscono dalla UI o con un comando CLI che le cifra nel DB.

---

## 3. Migrazioni Alembic

**Comando di startup:** `alembic upgrade head` nel servizio `migrate`, con `api` dipendente da `service_completed_successfully`. Deploy: `pull` → `up -d postgres redis` → `run --rm migrate` → `up -d api worker scheduler proxy frontend`.

**Ordine (un solo head, nessun branch):**

| Rev | Contenuto |
|---|---|
| `0001_extensions` | `pgcrypto`, `citext`. |
| `0002_identity` | `app_user`, `session`, `app_setting`. |
| `0003_sources` | `source`, `credential`, `provider`, `provider_mapping`. |
| `0004_media` | `media`, `availability`. |
| `0005_collections` | `collection`, `job_execution`. |
| `0006_snapshots` | `collection_snapshot`, `snapshot_item`, FK differita `collection.last_valid_snapshot_id`. |
| `0007_mdblist` | `mdblist_target`, `sync_binding`. |
| `0008_sync` | `sync_run`, `sync_operation`, `sync_run_event`, FK differita `sync_binding.last_run_id`. |
| `0009_episodes` | `episode_event`. |
| `0010_audit` | `audit_log`, `source_healthcheck`. |
| `0011_indexes` | Indici e unique partial. |

**Regole:** ogni revisione ha `downgrade()` testato; nessuna modifica a revisioni rilasciate; `alembic check` in CI senza diff; `alembic heads` con una sola riga.

**Rollback:** `downgrade -1` solo su DB non produttivo o per revisioni senza perdita dati. Per una revisione distruttiva il rollback è **ripristino da backup**. Procedura: `alembic current` → snapshot di sicurezza → `downgrade` al target → `alembic current` → smoke test `/api/ready`.

**Seed:** `python -m app.cli seed` idempotente (`ON CONFLICT DO NOTHING`) dopo `migrate`: anagrafica provider canonica con `origin` esplicito, `app_setting` di default, nessun utente, nessuna credenziale, nessuna lista. L'admin nasce solo da `app.cli bootstrap-admin --token-file`, token monouso con scadenza, consumato in transazione e registrato in `audit_log`.

---

## 4. Backup e ripristino

**Cosa si salva:** solo PostgreSQL. Redis non è un asset: i job persi vengono riportati a `VERIFYING` dai `SyncRun` non terminali.

**Procedura giornaliera** (`scripts/backup.sh`, servizio `backup` o cron host):

```bash
set -euo pipefail
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
pg_dump --format=custom --compress=9 --no-owner --no-privileges \
        --file="/backups/mdbup-${STAMP}.dump" "$DATABASE_URL"
pg_restore --list "/backups/mdbup-${STAMP}.dump" > "/backups/mdbup-${STAMP}.toc"
age --encrypt --recipients-file "$BACKUP_AGE_RECIPIENT_FILE" \
    --output "/backups/mdbup-${STAMP}.dump.age" "/backups/mdbup-${STAMP}.dump"
sha256sum "/backups/mdbup-${STAMP}.dump.age" > "/backups/mdbup-${STAMP}.sha256"
rm -f "/backups/mdbup-${STAMP}.dump"
```

**Cifratura:** `age` con chiave pubblica nel container, privata **fuori** da host e DB. `APP_ENCRYPTION_KEY` è un asset separato: senza di essa il dump si ripristina ma le credenziali restano illeggibili.

**Retention:** 7 giornalieri, 4 settimanali, 6 mensili (`BACKUP_RETENTION_*`) da `app.cli retention`; un backup recente non verificato blocca la cancellazione dei vecchi.

**Verifica (mensile, automatica):** `age -d` → `pg_restore --clean --if-exists` su PostgreSQL scratch → `alembic current` uguale al sorgente → conteggi di `media`, `availability`, `sync_binding`, `sync_operation` → `/api/ready` sull'istanza scratch.

**Disaster recovery:** RPO 24 h, RTO 2 h. Ordine:
1. secrets (`app_encryption_key`, `backup_age_recipient`, chiavi integrazioni);
2. `postgres` vuoto;
3. `age -d` + `pg_restore`;
4. `alembic current` atteso, altrimenti `upgrade head`;
5. `redis` vuoto;
6. `api/worker/scheduler`;
7. `/api/ready` verde;
8. riconciliazione dei `SyncRun` non terminali **prima** di riabilitare lo scheduler (`SCHEDULER_ENABLED=false` fino a fine riconciliazione).

---

## 5. Healthcheck e osservabilità

| Endpoint | Semantica | Contenuto |
|---|---|---|
| `GET /api/health` | Liveness. Nessuna dipendenza esterna. | `{"status":"ok","version":"..."}` — 200 anche con DB irraggiungibile |
| `GET /api/ready` | Readiness. | `{"status":"ok\|degraded","checks":{"db":"ok","redis":"ok","migrations":"ok","encryption_key":"ok"}}`; 503 se un check critico fallisce, senza host/utenti |
| `GET /api/metrics` | Prometheus, solo rete `internal` | metriche sotto |

`/api/health` non tocca il DB: un healthcheck dipendente amplifica i failover.

**Log:** JSON con `timestamp` UTC, `level`, `logger`, `message`, `request_id`, `job_id`, `run_id`, `binding_id`, `source_id`, `duration_ms`, `outcome`. Redazione obbligatoria su `Authorization`, `apikey`, `token`, `password`, `cookie`, `set-cookie` e su ogni URL con `apikey`/`token` in query. Corpi HTTP non loggati: solo metodo, host, path normalizzato, status, latenza. Test dedicato.

**Metriche minime:** `http_requests_total{route,status}`, `http_request_duration_seconds`, `sync_runs_total{status}`, `sync_operations_total{action,status}`, `sync_run_duration_seconds`, `source_fetch_duration_seconds{source}`, `source_http_errors_total{source,status}`, `snapshot_items_total{valid}`, `snapshot_completeness_ratio`, `mdblist_write_requests_total`, `rate_limit_sleep_seconds`, `queue_depth{queue}`, `worker_heartbeat_age_seconds`, `db_pool_in_use`.

**Alert minimi:** heartbeat più vecchio di 3× l'intervallo; `/api/ready` 503 per 5 minuti; `snapshot_completeness_ratio < 0.98`; `rate_limit_sleep_seconds` crescente; operazioni `UNCERTAIN` non riconciliate da 30 minuti.

---

## 6. Matrice di test

Legenda: **U** unit (senza I/O), **I** integration (PostgreSQL/Redis reali), **C** contract (HTTP registrato/anonimizzato), **E** e2e (compose completo). Ogni cella è un file di test; il nome deriva dal requisito, non dal modulo.

| Requisito non negoziabile | U | I | C | E |
|---|---|---|---|---|
| Dedup per identità `(tmdb_id, media_type)`, mai per titolo | `test_dedup.py` | `test_dedup_repo.py` | — | `e2e_dedup.spec.ts` |
| Film e serie separati (liste, endpoint, ID) | `test_media_type.py` | `test_binding_mediatype.py` | `test_mdblist_mediatype.py` | `e2e_split_mediatype.spec.ts` |
| MIRROR: calcolo `to_add`/`to_remove` | `test_mirror_plan.py` | `test_mirror_apply.py` | — | `e2e_mirror.spec.ts` |
| APPEND_ONLY: nessuna rimozione, mai | `test_append_only.py` | `test_append_only_repo.py` | — | `e2e_append_only.spec.ts` |
| Snapshot incompleto ⇒ nessuna rimozione | `test_snapshot_validity.py` | `test_sync_blocks_invalid.py` | — | `e2e_invalid_snapshot.spec.ts` |
| Catalogo vuoto ⇒ run `BLOCKED`, zero scritture | `test_empty_catalog.py` | `test_sync_blocks_empty.py` | — | `e2e_empty_catalog.spec.ts` |
| Paginazione parziale (pagine attese ≠ ottenute) | `test_pagination_completeness.py` | `test_partial_pages.py` | `test_tmdb_pagination.py` | `e2e_partial_pages.spec.ts` |
| TMDb discover limitato a 500 pagine | `test_tmdb_cap.py` | `test_tmdb_partition.py` | `test_tmdb_500.py` | `e2e_tmdb_cap.spec.ts` |
| Rate limit 429 + `Retry-After` | `test_backoff_jitter.py` | `test_rate_limiter.py` | `test_mdblist_429.py` | `e2e_rate_limit.spec.ts` |
| Timeout con esito incerto ⇒ riconciliazione, no retry cieco | `test_uncertain_outcome.py` | `test_reconcile_after_timeout.py` | `test_mdblist_timeout.py` | `e2e_timeout_reconcile.spec.ts` |
| Fallimento a metà batch ⇒ stato parziale e ripresa | `test_partial_batch.py` | `test_resume_after_crash.py` | — | `e2e_partial_batch.spec.ts` |
| Job duplicati ⇒ un solo run attivo per binding | `test_idempotency_key.py` | `test_advisory_lock.py` | — | `e2e_duplicate_job.spec.ts` |
| Soglie assolute e percentuali | `test_thresholds.py` | `test_threshold_review.py` | — | `e2e_threshold_review.spec.ts` |
| Stagioni/episodi senza duplicare la serie | `test_episode_event.py` | `test_episode_upsert.py` | `test_tmdb_season.py` | `e2e_seasons.spec.ts` |
| Auth: sessione HttpOnly, rotazione, revoca | `test_session.py` | `test_session_repo.py` | — | `e2e_auth.spec.ts` |
| CSRF su ogni mutazione | `test_csrf.py` | `test_csrf_middleware.py` | — | `e2e_csrf.spec.ts` |
| Rate limit login e lockout | `test_login_throttle.py` | `test_login_lockout.py` | — | `e2e_login_lockout.spec.ts` |
| Segreti cifrati a riposo, mai in chiaro | `test_crypto.py` | `test_credential_roundtrip.py` | — | `e2e_no_secret_leak.spec.ts` |
| Redazione log (token, apikey, cookie) | `test_log_redaction.py` | `test_log_pipeline.py` | — | `e2e_log_scan.spec.ts` |
| Provenienza OFFICIAL/AGGREGATOR/CUSTOM distinta | `test_origin_labels.py` | `test_origin_constraints.py` | — | `e2e_origin_badges.spec.ts` |
| `date_basis` distinto (ufficiale/aggregatore/app) | `test_date_basis.py` | `test_date_basis_repo.py` | — | `e2e_date_basis_badges.spec.ts` |
| Nessun mock in produzione | `test_prod_guards.py` | `test_startup_refuses_mock.py` | — | `e2e_prod_profile.spec.ts` |
| Attribuzione TMDb + JustWatch presente | `test_attribution.py` | — | — | `e2e_attribution.spec.ts` |
| Reorder MDBList: max 1.000, non atomico, `SUCCEEDED` + warning su errore | `test_reorder_chunking.py` | `test_reorder_readback.py` | `test_mdblist_reorder.py` | `e2e_reorder.spec.ts` |
| Ordine non preservato di default; nessuna ricreazione lista | `test_order_policy.py` | `test_order_readback.py` | `test_mdblist_reorder_capability.py` | `e2e_order_notice.spec.ts` |
| ADD prima di REMOVE (mai lista incompleta) | `test_apply_order.py` | `test_apply_order_repo.py` | — | `e2e_apply_order.spec.ts` |
| `plan_hash`/`snapshot_hash`: conferma legata al piano visto | `test_plan_hash.py` | `test_confirm_stale_plan.py` | — | `e2e_stale_plan.spec.ts` |
| `schedule_policy` AUTO_APPLY_IF_SAFE / ALWAYS_APPROVE / DRY_RUN_ONLY | `test_schedule_policy.py` | `test_schedule_policy_repo.py` | — | `e2e_schedule_policy.spec.ts` |
| Advisory lock di sessione per target | `test_advisory_lock.py` | `test_session_lock.py` | — | `e2e_lock.spec.ts` |
| `not_found` soppresso dopo N rifiuti, riattivabile | `test_not_found_suppression.py` | `test_not_found_repo.py` | `test_mdblist_not_found.py` | `e2e_not_found.spec.ts` |
| Duplicati remoti e `unmapped_remote` mai rimossi | `test_remote_duplicates.py` | `test_unmapped_remote.py` | — | `e2e_remote_duplicates.spec.ts` |

**Copertura:** nessuna riga è soddisfatta dal solo unit test.

---

## 7. Fixture sintetiche

- Percorso `tests/fixtures/synthetic/*.json`; ogni file inizia con `"_fixture": {"synthetic": true, "note": "dati inventati, nessuna relazione con cataloghi reali"}`.
- ID TMDb `900000000–999999999`; IMDb `tt9900000`+; provider `Provider Sintetico Alfa/Beta`; titoli `Titolo Sintetico 001`.
- Nessuna fixture contiene liste MDBList reali, slug, username, token o URL firmati.
- `tests/fixtures/guard_test.py` fallisce se un ID esce dal range sintetico, se compare una stringa da API key (`[A-Za-z0-9]{32,}`), un dominio `mdblist.com`/`themoviedb.org` in un payload, o se manca `_fixture.synthetic`.
- In CI le base URL puntano a mock locali; `test_prod_guards.py` verifica che `APP_ENV=production` rifiuti base URL non ufficiali e connettori `MOCK`.

---

## 8. Contract test dei connettori

- Registrazioni in `tests/contract/fixtures/{tmdb,mdblist}/<operation>__<status>.json`, da risposte reali poi **anonimizzate** (ID rimappati nel range sintetico, titoli sostituiti, header rimossi salvo `content-type`, `x-has-more`, `retry-after`).
- Trasporto: `respx` (unit) e server mock (e2e) con gli stessi fixture: un solo set di dati per entrambi i livelli.
- Asserzioni: campi obbligatori, enum chiusi (`flatrate|rent|buy|ads|free`), forma della paginazione (`next_cursor`/`X-Has-More`), forma degli errori `401/403/404/429`, assenza di campi usati ma non documentati.
- **MDBList:** congelare lo snapshot di `https://api.mdblist.com/schema/?format=json` con hash SHA-256; testare `GET /lists/{id}`, `GET /lists/{id}/items` (cursor), `POST /lists/{id}/items/add|remove`, `POST /lists/{id}/items/reorder`, `429`, `403`.
- **TMDb:** testare `GET /watch/providers/movie|tv`, `GET /movie|tv/{id}/watch/providers`, `GET /discover/movie|tv`, `429`, paginazione 500.
- **JustWatch:** fixture solo se e quando esiste un contratto; altrimenti test `skipped` con motivo esplicito.
- **Drift detection:** job notturno `contract-live` (non bloccante, solo `main` con secret) ripete le asserzioni sull'API reale e apre una issue se lo schema cambia; non salva risposte reali nel repository.
- Nessuna verifica di contenuti editoriali (nomi, prezzi): solo la forma del contratto.

---

## 9. E2E

Scenario unico e deterministico: `docker compose -f compose.yml -f compose.test.yml up --abort-on-container-exit`.

1. **Fonte:** `FixtureSource` (solo con `APP_ENV=test`) espone 3 provider sintetici e 2 collezioni, una con 120 item su 3 pagine.
2. **Snapshot:** `POST /api/v1/collections/{id}/snapshots` → `SUCCEEDED`; `pages_expected == pages_fetched == 3`, `is_valid=true`, `items=120`.
3. **Dry-run:** `POST /api/v1/bindings/{id}/previews` → `to_add=120`, `to_remove=0`, `blocked=false`, zero scritture sul mock MDBList (contatore del mock).
4. **Sync:** `POST /api/v1/bindings/{id}/runs` con conferma esplicita → `SUCCEEDED`; `added=120`, `existing=0`, `not_found=0`, chiamate del mock esattamente quelle attese.
5. **Verifica:** rilettura lista remota dal mock, confronto insiemi di ID, `sync_operation` tutte `SUCCEEDED`, `audit_log` popolato, nessun segreto nei log (`e2e_log_scan`).
6. **Varianti:** snapshot invalido (`BLOCKED`, zero scritture), 429 al primo tentativo (backoff e successo), timeout dopo invio (`UNCERTAIN` → riconciliazione → `SUCCEEDED`), doppio click (un solo run), reorder >1.000 (chunk; su errore `SUCCEEDED` + warning `ORDER_NOT_ENFORCED`).

Guardia: l'e2e rifiuta di partire se `MDBLIST_BASE_URL` è `https://api.mdblist.com`. Nessuna lista reale viene toccata.

---

## 10. CI

| Job | Comando | Bloccante |
|---|---|---|
| `lint` | `ruff check .`, `ruff format --check .`, `eslint .`, `prettier --check` | sì |
| `typecheck` | `mypy --strict app`, `tsc --noEmit` | sì |
| `unit` | `pytest tests/unit -q` | sì |
| `integration` | `pytest tests/integration -q` con service `postgres:16` e `redis:7` | sì |
| `contract` | `pytest tests/contract -q` (replay) | sì |
| `migrations` | `upgrade head` → `downgrade base` → `upgrade head`; `alembic check`; `heads` = 1 | sì |
| `build` | `docker buildx build` api e frontend; `vite build`; `trivy` | sì |
| `e2e` | compose test, `--abort-on-container-exit` | sì |
| `security` | `pip-audit`, `npm audit --omit=dev`, `gitleaks`, `trivy fs` | sì (≥ high) |
| `contract-live` | notturno, solo `main`, secret richiesti | no |

Branch protection: tutti i job bloccanti richiesti; nessun merge con `migrations` o `e2e` rossi. Cache `pip`/`npm` per lockfile. Python 3.12, Node 20.

---

## 11. Rischi e mitigazioni

| # | Rischio | Prob. | Impatto | Mitigazione |
|---|---|---|---|---|
| R1 | Budget MDBList 300 scritture/5 min saturato da liste grandi | Alta | Alto | Token bucket su Redis, batch piccoli, ripresa, budget 240 con margine |
| R2 | Reorder MDBList non atomico, max 1.000 per chiamata | Alta | Medio | `preserve_order` opt-in, chunk, warning `ORDER_NOT_ENFORCED`, nessuna ricreazione della lista |
| R3 | TMDb non espone `added_at` → "aggiunte recenti" ambigue | Certa | Alto | Etichetta `CUSTOM`/`APP_FIRST_SEEN`, `first_seen_at`, conferma su N rilevazioni, testo UI esplicito |
| R4 | `discover` TMDb limitato a 500 pagine → catalogo parziale | Media | Alto | Partizionamento per anno/genere, `is_valid=false` se incompleto, nessuna rimozione |
| R5 | Snapshot parziale letto come calo di catalogo | Media | Critico | Soglie assolute+percentuali, revisione manuale, blocco rimozioni su `is_valid=false` |
| R6 | Doppio avvio job / retry duplicato | Media | Alto | Advisory lock per target, unique parziale su run attivo, chiave di idempotenza |
| R7 | Timeout dopo invio: stato remoto ignoto | Media | Alto | `UNCERTAIN`, rilettura remota prima di ogni retry, riconciliazione obbligatoria |
| R8 | Perdita `APP_ENCRYPTION_KEY` | Bassa | Critico | Custodia esterna, backup separato, rotazione con `key_version` |
| R9 | JustWatch Partner API non ottenibile | Alta | Medio | Connettore `DISABLED`, interfaccia pronta, nessuna dipendenza da date ufficiali |
| R10 | Violazione ToS/attribuzione (TMDb, JustWatch) | Bassa | Alto | Solo endpoint documentati, attribuzione in UI, revisione legale prima della Fase 3 |
| R11 | Perdita Redis → job accodati persi | Media | Medio | Riconciliazione dei run non terminali, scheduler fermo fino a fine recovery |
| R12 | Crescita dischi da snapshot | Alta | Medio | Retention, partizionamento mensile, `app.cli retention` |
| R13 | Drift schema upstream | Media | Medio | Contract replay + `contract-live` notturno, modelli Pydantic strict |
| R14 | Brute force su login single-user | Media | Alto | Rate limit per IP+utente, lockout progressivo, Argon2id, audit |
| R15 | Supply chain immagini | Bassa | Alto | Pin per digest, `trivy`, `no-new-privileges`, non-root, `read_only` |
| R16 | MDBList non espone `type`/`dynamic` in modo affidabile | Media | Alto | Conferma esplicita, preflight, `403` = blocco; non scrivere su liste non verificate |
| R17 | MDBList non ha idempotency key | Alta | Alto | Operation ledger, riconciliazione remota, nessun retry cieco |

---

## 12. Criteri di accettazione per fase

**Fase 1 — Progettazione.** Documenti 00–10; ogni capacità etichettata VERIFICATO/OSSERVATO/NON VERIFICATO/BLOCCATO; matrici fonti e test approvate; nessun connettore; blocchi elencati.

**Fase 2 — Scheletro operativo.** Compose con tutti i servizi `healthy`; `migrate` idempotente e reversibile su DB vuoto; `/api/health` e `/api/ready` corretti; login HttpOnly + CSRF + rate limit; credenziali cifrate con chiave da file; CI verde; nessun connettore reale.

**Fase 3 — Acquisizione TMDb.** Connettore reale con sola API documentata; completezza snapshot misurata; dedup per identità; provenienza `AGGREGATOR`; zero scritture MDBList; verdi paginazione parziale, 429, catalogo vuoto; dry-run e sync su lista di test.

**Fase 4 — Sync MDBList in dry-run.** Lista di test, piano, soglie, lock, idempotenza, riconciliazione post-timeout; scritture solo con conferma manuale; nessuna esecuzione pianificata.

**Fase 5 — Esercizio continuo.** Sync pianificate con approvazione per liste esistenti; alert attivi; drill di restore documentato; runbook; retention attiva; nessun segreto nei log su un ciclo completo.

**Bloccato (serve input esterno):** contratto JustWatch Partner + credenziali S3; API key MDBList e piano (limite liste statiche); TMDb read token; dominio/TLS ed email admin; custodia della chiave di cifratura; conferma legale su uso non commerciale e attribuzione; fonte ufficiale verificata per una "Top 10" `OFFICIAL`.
