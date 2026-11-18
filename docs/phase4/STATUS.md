# Fase 4 — Automazione e robustezza

**Data:** 2026-11-17
**Stato:** completata e verificata live sul server Ubuntu (`http://192.0.2.10:8088`).

---

## 1. Obiettivi raggiunti

### 1.1 Modifica binding senza ricrearlo

- Nuovo endpoint `PATCH /api/bindings/{id}` con CSRF e audit `binding_updated`.
- Campi modificabili: `mode` (MIRROR/APPEND_ONLY), pianificazione (`MANUAL`, `INTERVAL`, `CRON`, `DAILY`, `WEEKLY`), soglie `max_remove_count`/`max_remove_percent`, `enabled`, `policy_version`, `target_private`, policy e opzioni di review.
- Nuova pagina frontend `/app/bindings/:bindingId/edit` con pulsante **Modifica** nella tabella Binding.
- La lista MDBList non viene mai ricreata: `remote_list_id` resta la chiave stabile.

### 1.2 Visibilità lista MDBList

Verificato live l'endpoint `PUT /lists/{id}` (solo `name`/`private`, nessun effetto sugli elementi).
Il client ora espone `MdbListClient.update_list`; il backend aggiorna `mdblist_target.is_private` e l'audit.
La UI espone il checkbox **Lista MDBList privata**.

### 1.3 Scheduling e lock

- `sync_binding.schedule_interval_hours` (migrazione `0002_binding_schedule_interval`) per pianificazioni a intervallo; `schedule_cron` resta per cron/DAILY/WEEKLY.
- `next_run_at` calcolato per intervallo o cron; il scheduler include entrambi i tipi.
- Celery Beat accoda i binding scaduti sulla coda `sync`; i task periodici restano sulla coda `maintenance`.
- Nuovo `DispatchLock` Redis (`SET NX EX` + rilascio Lua) con fallback in-process: serializza la creazione del run per target tra scheduler e richieste manuali. Il lock del worker (`TargetLock` PostgreSQL advisory) resta la protezione delle scritture remote.
- Live test: lock Redis impostato manualmente → `POST /bindings/{id}/runs` risponde `409 RUN_IN_PROGRESS`; nessun run creato.

### 1.4 Guardrail anti-svuotamento

- Snapshot non `COMPLETE`/`CLEAN`, non valido o con 0 elementi → run bloccato prima di qualsiasi scrittura.
- MIRROR: se `to_remove` supera `max_remove_count` o `max_remove_percent` rispetto agli elementi remoti, il run va in `AWAITING_APPROVAL`; nessuna REMOVE viene inviata.
- UI Run Detail: **Approva piano** e **Scarta piano** (quest'ultimo annulla il run senza scritture).
- Test di integrazione: soglia assoluta di rimozione → `AWAITING_APPROVAL`, `remove_route.called == False`; dopo approvazione → `SUCCEEDED` con `removed_count=2`.

### 1.5 Resilienza HTTP

- TMDb: retry limitati su 429 (`Retry-After`), 5xx, timeout e errori di rete; backoff esponenziale con jitter; `max_retries` configurabile.
- MDBList: le letture ritentano 5xx/timeout/429 con backoff; le scritture **non** vengono ritentate alla cieca. Il sync executor marca `UNCERTAIN` e rilegge la lista prima di ritentare.
- Nuove impostazioni: `HTTP_MAX_RETRIES`, `HTTP_BACKOFF_BASE_MS`, `HTTP_BACKOFF_MAX_MS`, `HTTP_JITTER_RATIO`.
- Test: 5xx→200, timeout→200, 5xx esausto, scrittura 5xx senza retry, `update_list` PUT.

### 1.6 Retention e manutenzione

- `cleanup_old_data` sulla coda `maintenance` (beat giornaliero 03:30) usa:
  - `RUN_RETENTION_DAYS` (default 180) per run `SUCCEEDED`;
  - `FAILED_RUN_RETENTION_DAYS` (default 90) per `FAILED`, `PARTIAL`, `BLOCKED`, `CANCELLED`;
  - `JOB_RETENTION_DAYS`, `SESSION_RETENTION_DAYS`, `SNAPSHOT_RETENTION_DAYS`.
- Gli snapshot referenziati da run o `last_valid_snapshot_id` non vengono cancellati.
- Live test: task `cleanup_old_data` accodato su `maintenance` ed eseguito dal worker (`runs_deleted=0`, dati tutti recenti).

### 1.7 Backup/restore

- Installato `age` 1.3.2 in `/home/mdbup/bin` (l'host non lo aveva).
- Chiave pubblica in `secrets/backup_age_recipient`; chiave privata in `/home/mdbup/mdbup-age-keys.txt` (0600, fuori dal repository).
- Backup reale creato: `mdbup-20261117T182343Z.dump.age` (915 KB) + checksum + TOC.
- Verifica: checksum OK, decrypt OK, `pg_restore --list` 174 righe.
- Restore su database scratch `mdbup_restore_test` (mai sul DB live): conteggi identici per `app_user`, `collection`, `collection_snapshot`, `sync_binding`, `sync_run`, `mdblist_target`; scratch eliminato.
- Crontab consigliato per `mdbup`:

```cron
0 3 * * * cd /home/mdbup/mdbup && PATH=/home/mdbup/bin:$PATH BACKUP_DIR=/home/mdbup/mdbup-backups ./scripts/backup.sh >> /home/mdbup/mdbup-backups/backup.log 2>&1
```

- Drill di restore consigliato: mensile su DB scratch, senza `restore.sh` sul DB live.

---

## 2. Verifica live

| Elemento | Esito |
|---|---|
| Stack Docker | 7/7 healthy, 0 restart |
| Migrazione | `0002_binding_schedule_interval` applicata su PostgreSQL |
| Liste Netflix IT | Azione 755, Avventura 428, Horror 365; invariate |
| Dry-run sui 3 binding | tutti `SUCCEEDED`, `to_add=0`, `to_remove=0` |
| Test PATCH binding | `schedule=CRON`, `target_private=true`, `next_run_at` valorizzato |
| Celery Beat | creato un run `SCHEDULED` reale (dry-run) su un binding di test |
| Run schedulato | `SUCCEEDED`, `to_add=755`, `to_remove=0`, nessuna scrittura |
| Lock Redis | run manuale rifiutato con `409 RUN_IN_PROGRESS` mentre il lock era held |
| Cleanup | task `cleanup_old_data` eseguito sulla coda `maintenance` |
| Backup/restore | backup cifrato + restore su scratch DB con conteggi identici |
| Frontend | build, 42 test, lint; asset con “Modifica binding” e “Scarta piano” |

---

## 3. Test

- Backend: **168 passed**, `ruff check` e `ruff format --check` verdi.
- Frontend: **42 passed**, build Vite e ESLint verdi.
- Nuovi test principali:
  - `PATCH` binding: schedule interval/cron, soglie, visibilità, policy;
  - scheduler interval e `DispatchLock` (anche tra istanze);
  - blocco MIRROR per soglia assoluta di rimozione e assenza di REMOVE prima dell'approvazione;
  - TMDb 5xx/timeout retry; MDBList read 5xx/timeout retry, write 5xx no-retry, `update_list`;
  - cleanup di run `FAILED`/`PARTIAL`/`BLOCKED` vecchi e conservazione dello snapshot valido.

---

## 4. File principali modificati

Backend:
- `app/api/routers/bindings.py`, `app/api/schemas_sync.py`
- `app/services/bindings.py`, `app/services/targets.py`, `app/services/runs.py`
- `app/jobs/scheduler.py`, `app/repositories/bindings.py`
- `app/core/locks.py`, `app/core/retry.py`, `app/core/config.py`
- `app/integrations/tmdb/client.py`, `app/integrations/mdblist/client.py`
- `app/db/models/sync.py`, `alembic/versions/0002_binding_schedule_interval.py`
- test: `tests/unit/test_scheduler.py`, `tests/integration/test_sync_api.py`, `tests/contract/test_tmdb_client.py`, `tests/contract/test_mdblist_client.py`

Frontend:
- `src/pages/BindingEditPage.tsx`, `src/pages/BindingsPage.tsx`, `src/pages/RunDetailPage.tsx`
- `src/api/mutations.ts`, `src/api/queries.ts`, `src/api/types.ts`
- `src/app/App.tsx`, `src/lib/collections.ts`, `src/lib/collections.test.ts`

Documentazione:
- `README.md`, `docs/phase4/STATUS.md`, `.env.example`, `.gitattributes`

---

## 5. Cosa resta per la Fase 5

1. **Altri provider**: verificare i mapping TMDb di Prime Video, Disney+, NOW, Timvision, Infinity+, Rakuten, MUBI con `/watch/providers`.
2. **Serie TV**: creare collezioni per stagioni/episodi e verificare i limiti MDBList.
3. **JustWatch Partner**: solo con contratto; sblocca date di aggiunta reali, upcoming e charts.
4. **Top 10 ufficiale**: solo con fonte ufficiale verificata.
5. **E2E Playwright** per login, bootstrap, modifica binding, approvazione/scarto run.
6. **Osservabilità**: `/metrics` Prometheus, alert su run falliti/incerti, dashboard operativa.
7. **HTTPS/TLS** e cookie `__Host-` per esposizione Internet.
8. **Backup automatico**: installare il crontab e fare un drill di restore mensile.
