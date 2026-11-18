# Fase 7 — note backend (workstream backend/ops)

Documento di contratto per il frontend e per l'esercizio. Nessuna modifica live:
solo codice, migrazione `0004_notification_retry` e script.

## 1. Retry delle notifiche

- Colonne nuove su `notification_channel` (migrazione `0004_notification_retry`,
  idempotente come `0003`): `retry_count` (int, default 0), `next_retry_at`
  (timestamptz, null), `last_event` (string 32), `last_payload` (JSON).
  Indice `notification_retry_idx` su `(last_status, next_retry_at)`.
- `last_payload` contiene `{"message": str, "payload": dict}`: è la copia durevole
  dell'ultimo invio, così il retry non ricostruisce il messaggio dallo stato del run.
- Backoff dopo un invio fallito: 1 min, 5 min, 15 min. Dopo il terzo retry fallito
  `next_retry_at` torna `NULL` e la consegna si ferma (`retry_count` resta a 4 come
  contatore dei tentativi falliti). Un invio riuscito azzera `retry_count` e
  `next_retry_at`.
- Task Celery `app.jobs.tasks.retry_failed_notifications` sulla coda `maintenance`,
  ogni 60 s (`retry-failed-notifications` in `celery_app.conf.beat_schedule`).
  Rinvia solo i canali abilitati con `last_status='FAILED'` e
  `next_retry_at <= now`. Non blocca mai un run di sync: gli errori restano sul
  canale e nei log (`notification_retry_exhausted`, `notification_retry_run`).
- `NotificationChannelOut` espone `retry_count: int` e `next_retry_at: datetime|null`.
  Nessun altro campo cambia: la UI può mostrare "in retry" quando
  `last_status == "FAILED"` e `next_retry_at != null`.

## 2. Metriche e stato di sistema

Variabili nuove:

| Variabile | Default | Note |
|---|---|---|
| `METRICS_ENABLED` | `true` | `false` ⇒ `GET /api/metrics` risponde `404 METRICS_DISABLED` |
| `METRICS_TOKEN` | vuoto | accetta anche `METRICS_TOKEN_FILE` (Docker secret) |
| `BACKUP_DIR` | `/backups` | directory montata in sola lettura in `api`/`worker` |
| `BACKUP_STATUS_FILE` | `<BACKUP_DIR>/last_backup.json` | |
| `BACKUP_AGE_IDENTITY_FILE` | vuoto | solo host/CLI, mai nei container |

`GET /api/metrics` (`text/plain; version=0.0.4; charset=utf-8`):

- autenticazione con `Authorization: Bearer <token>` **o** `X-Metrics-Token: <token>`;
- `METRICS_TOKEN` assente ⇒ `503 METRICS_TOKEN_MISSING`; header assente ⇒
  `401 METRICS_TOKEN_REQUIRED`; token errato ⇒ `403 METRICS_TOKEN_INVALID`;
- famiglie esposte: `mdbup_up`, `mdbup_info{version}`,
  `mdbup_database_up`, `mdbup_redis_up`, `mdbup_encryption_key_ready`,
  `mdbup_worker_up`, `mdbup_service_up{service="tmdb|mdblist"}`,
  `mdbup_celery_queue_depth{queue="celery|maintenance|sync|acquisitions"}`,
  `mdbup_sync_runs{status}` (tutti gli stati presenti, con `SUCCEEDED`, `FAILED`,
  `AWAITING_APPROVAL`, `PARTIAL` sempre presenti), `mdbup_pending_approvals`,
  `mdbup_api_calls{provider,window="hour|day"}`,
  `mdbup_last_backup_valid_timestamp_seconds` (0 se il file manca o lo stato non è
  `OK`), `mdbup_backup_age_hours` (-1 se sconosciuto), `mdbup_backup_status_ok`.

`GET /api/system/status` (sessione admin, `401` senza cookie):

```json
{
  "health": {"api": true, "database": true, "redis": true, "worker": true,
             "tmdb": "OK", "mdblist": "MISSING_CREDENTIAL"},
  "queues": {"celery": 0, "maintenance": 0, "sync": 0, "acquisitions": 0},
  "runs": {"SUCCEEDED": 5, "FAILED": 0, "AWAITING_APPROVAL": 1, "PARTIAL": 0},
  "api_usage": {"tmdb": {"hour": 0, "today": 12}, "mdblist": {"hour": 0, "today": 4}},
  "backup": {"last_valid_at": "2026-11-18T02:00:00Z", "file": "mdbup-....dump.age",
             "status": "OK", "age_hours": 9.5},
  "pending_approvals": 1,
  "upcoming": [{"binding_id": "...", "collection_name": "...",
                "target_name": "...", "next_run_at": "2026-11-18T12:00:00Z"}]
}
```

`health.tmdb`/`health.mdblist` sono stringhe: `OK`, `MISSING_CREDENTIAL`,
`DEGRADED`, `ERROR`, `DISABLED`. Il worker usa un ping Celery con timeout 1 s e
non solleva mai eccezioni se il broker è irraggiungibile (in quel caso
`worker=false` e le code valgono 0).

## 3. Backup

Schema di `BACKUP_STATUS_FILE` (scritto da `scripts/backup.sh` e
`scripts/backup-verify.sh` / `python -m app.cli backup-verify`):

```json
{"timestamp": "2026-11-18T02:00:00Z", "file": "mdbup-....dump.age", "size": 1234567,
 "sha256": "…", "status": "OK", "error": null}
```

`backup-verify` aggiunge `decrypted` e `age_available`. Stati possibili:
`OK`, `MISSING`, `EMPTY`, `CHECKSUM_MISSING`, `CHECKSUM_MISMATCH`,
`INVALID_HEADER`, `DECRYPT_FAILED`, `PGDMP_INVALID`, `FAILED` (backup.sh).
Solo `OK` produce un timestamp valido per le metriche.

- `scripts/backup-verify.sh` (host): bash + coreutils + `age` opzionale; decifra in
  una directory temporanea e verifica il magic `PGDMP` se
  `BACKUP_AGE_IDENTITY_FILE` è impostata. Exit 0 solo con stato `OK`.
- `python -m app.cli backup-verify [--backup-dir] [--status-file] [--identity-file]`:
  stessa verifica in Python (solo stdlib + binario `age`). Se la directory è in sola
  lettura la verifica riesce comunque e l'aggiornamento dello stato viene saltato
  con un warning nei log.
- `scripts/backup.sh` scrive `status=OK` dopo cifratura e checksum e `status=FAILED`
  nel trap di errore. La retention pota solo `mdbup-*`, quindi il file di stato non
  viene mai rimosso.
- `deploy/Dockerfile.api` installa `age` se disponibile nella base image; se manca
  il build non fallisce e la CLI riporta "age non disponibile".
- `deploy/docker-compose.yml`: `api` e `worker` montano
  `${BACKUP_HOST_DIR:-../backups}:/backups:ro` con `BACKUP_DIR=/backups` e
  `BACKUP_STATUS_FILE=/backups/last_backup.json`. Nessun container riceve la chiave
  privata age; i 7 servizi restano invariati.

## 4. Provider

Il seed conteneva già Prime Video (`119`), Disney+ (`337`), NOW (`39`),
Paramount+ (`531`) e RaiPlay (`222`), con id film e serie verificati; nessun id è
stato inventato. `tests/unit/test_provider_seed.py` verifica che ogni provider del
seed abbia il mapping film e, dove esiste la copertura TV, anche il mapping serie
(`infinity-plus` è l'unica eccezione documentata). Non è stato aggiunto un comando
`ensure-it-providers`: `seed-providers` è già un upsert idempotente e un secondo
comando duplicherebbe la stessa logica.

## 5. Verifica

- `uv run ruff format .` / `uv run ruff check .`: puliti.
- `REDIS_URL="" APP_ENV=test uv run pytest`: **240 passed** (204 esistenti + 36 nuovi).
- `alembic upgrade head` → `downgrade 0003_notifications` → `upgrade head` su SQLite: OK.
- `docker compose config` e build dell'immagine **non eseguiti** in questo worktree
  (nessun demone Docker disponibile): da verificare in fase di deploy.
