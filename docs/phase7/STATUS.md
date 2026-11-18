# Fase 7 — UI/UX, retry notifiche, metriche, backup ed E2E

**Data:** 2026-11-17
**Stato:** completata e verificata live su Ubuntu (`/home/mdbup/mdbup`, Docker Compose 7 servizi).

## 1. UI/UX e design system

La UI è stata rifatta con un design system a token CSS e tema **dark-first**:

- `frontend/src/index.css` definisce superfici, bordi, testo, accenti, stati e spaziature; il tema chiaro è un override completo, non una serie di classi `dark:` sparse.
- `ThemeProvider` + `useTheme` con persistenza `localStorage`; script inline in `index.html` per evitare il flash del tema.
- `tailwind.config.ts` usa `darkMode: "class"` e i token del design system.
- Tipografia e conteggi con `tabular-nums`; timestamp visualizzati in `Europe/Rome` con tooltip UTC/relativo (`Timestamp`).
- Badge semantici uniformi per run (`SUCCEEDED`, `AWAITING_APPROVAL`, `FAILED`, `PARTIAL`, `RUNNING`), snapshot (`COMPLETE`, `WARNINGS`, `INCOMPLETE`) e origine (`Ufficiale`, `Aggregatore TMDb/JustWatch`, `Filtro locale / Multi-provider`).
- Skeleton loader coerenti, empty state con CTA, toast non invasivi, conferme per azioni distruttive e per `APPEND_ONLY` → `MIRROR`.
- Navigazione da tastiera, focus visibile, `aria-*`, drawer mobile con Escape/focus management.

### App shell

- Sidebar desktop collassabile e drawer mobile.
- Topbar con health cluster API/Worker/TMDb/MDBList, contatore esatto `AWAITING_APPROVAL` con link rapido, theme switch, utente/logout.
- `HealthCluster` usa `GET /api/system/status`; se l'endpoint non c'è, ricade sullo stato delle fonti della dashboard.

### Viste

- **Dashboard**: KPI (titoli, binding attivi/in pausa, richieste API, ultimo backup), coda “Richiede attenzione” con Approva/Scarta/Riprova, timeline prossime sync, alert e attività recenti.
- **Provider**: card/tabella filtrabile, copertura Film/Serie, mapping TMDb, freschezza snapshot, chip provider noti (Netflix, Prime Video, Disney+, Apple TV+, NOW, Mediaset Infinity, RaiPlay).
- **Collezioni**: builder guidato con provider, tipo media, generi inclusi/esclusi, voto/voti minimi, anni, lingua, flatrate, finestra Appena rilevati, unione multi-provider e anteprima criteri.
- **Binding**: pipeline `Snapshot → Diff → MDBList`, soglie, modalità, schedule, pausa/riattivazione, conferme.
- **Run detail**: pipeline, barra soglia rimozioni (`to_remove` vs limite), tabella campioni add/remove ricercabile, approvazione/scarto/riconciliazione.
- **Impostazioni**: schede Credenziali & Sicurezza, Notifiche & Retry, Backup & Manutenzione, Portabilità JSON.

## 2. Espansione cataloghi IT

Provider già presenti nel seed e verificati live in Fase 5: Netflix, Prime Video, Disney+, NOW, Timvision, Infinity+, Rakuten TV, MUBI, Apple TV+, Paramount+, RaiPlay, Mediaset Infinity.

Live Fase 7:

| Passo | Esito |
|---|---|
| Collezione `disney-plus-movie-animazione` (CATALOG, genere 16, flatrate) | snapshot `COMPLETE`, **532** titoli, 27 pagine, valido |
| Collezione `disney-plus-movie-animazione-top` (`CUSTOM_FILTER` locale) | snapshot `COMPLETE`, **114** titoli, 1 pagina, **0 chiamate TMDb** |
| Target MDBList | **243601** — https://mdblist.com/lists/disney-it-animazione-top |
| Sync reale | `SUCCEEDED`, 114 ADD, 0 failed/uncertain |
| Dry-run successivo | `SUCCEEDED`, `to_add=0`, `to_remove=0`, remote 114 |
| Lista pubblica | HTTP 200 |

La collezione locale usa lo snapshot della collezione Disney+ Animazione, quindi riusa i dati già acquisiti e non moltiplica le chiamate TMDb. Filtri: genere 16, voto ≥ 7.0, voti ≥ 200, anni 1990–2026, ordinamento voto decrescente.

> Nota: il tentativo di acquisire l'intero catalogo Disney+ Film con `popularity.desc`/`vote_count.desc`/`original_title.asc` ha prodotto duplicati TMDb (367) e snapshot non valido. La collezione per genere (27 pagine) è risultata pulita e valida; è quella usata per la lista.

## 3. Notifiche: retry e UI di modifica

- Migrazione `0004_notification_retry`: `retry_count`, `next_retry_at`, `last_event`, `last_payload`, indice `notification_retry_idx`.
- Backoff: 1 minuto, 5 minuti, 15 minuti; massimo 3 retry. Dopo l'esaurimento `next_retry_at` viene azzerato e l'errore resta su `last_error`.
- Task maintenance `retry_failed_notifications` ogni 60 s; non blocca i run di sync.
- UI Impostazioni → Notifiche: creazione, modifica nome/eventi/stato, sostituzione opzionale di URL/token, test, eliminazione; mostra `retry_count` e `next_retry_at`.
- Live: canale webhook con URL non raggiungibile → test fallito, `retry_count=1`, `next_retry_at` valorizzato; dopo il tick maintenance `retry_count=2` con nuovo backoff; canale eliminato.

## 4. Reverse proxy esterno e cookie `__Host-`

MdbUP **non integra** un reverse proxy: l'API espone HTTP su `28080` e serve
anche la SPA compilata. TLS, HSTS e certificati sono responsabilità del proxy
scelto dall'operatore (Caddy, Nginx, Traefik, Tailscale, ecc.).

Configurazione tipica dietro TLS:

```env
APP_BASE_URL=https://mdbup.example.com
COOKIE_SECURE=true
WEB_PORT=28080
```

- Cookie: `__Host-mdbsync-session`/`__Host-mdbsync-csrf`, `Secure`, `Path=/`,
  senza `Domain`.
- In LAN HTTP: `APP_BASE_URL=http://<ip>:28080`, `COOKIE_SECURE=false`.
- HSTS può essere aggiunto dal proxy; l'API applica comunque CSP,
  X-Frame-Options e Referrer-Policy.
- La porta 443 resta libera; l'app ascolta solo su 28080.

## 5. Metriche e stato sistema

`GET /api/metrics` (Prometheus text, `text/plain; version=0.0.4`):

- `mdbup_up`, `mdbup_info`
- `mdbup_database_up`, `mdbup_redis_up`, `mdbup_encryption_key_ready`, `mdbup_worker_up`
- `mdbup_service_up{service="tmdb"|"mdblist"}`
- `mdbup_celery_queue_depth{queue="celery"|"maintenance"|"sync"|"acquisitions"}`
- `mdbup_sync_runs{status=…}`
- `mdbup_pending_approvals`
- `mdbup_api_calls{provider,window}`
- `mdbup_last_backup_valid_timestamp_seconds`, `mdbup_backup_age_hours`, `mdbup_backup_status_ok`

Protezione: `METRICS_TOKEN` (Bearer o `X-Metrics-Token`). Senza token configurato → 503; senza header → 401; token errato → 403. Live verificato: 401/403/200.

`GET /api/system/status` (admin) restituisce health, code, run, api_usage, backup, pending_approvals e prossime sync; usato da topbar/dashboard.

## 6. Backup automatico e verifica

Cron installato per `mdbup`:

```cron
0 3 * * * cd /home/mdbup/mdbup && PATH=/home/mdbup/bin:$PATH BACKUP_DIR=/home/mdbup/mdbup-backups ./scripts/backup.sh >> /home/mdbup/mdbup-backups/backup.log 2>&1
30 3 * * 0 cd /home/mdbup/mdbup && PATH=/home/mdbup/bin:$PATH BACKUP_DIR=/home/mdbup/mdbup-backups BACKUP_STATUS_FILE=/home/mdbup/mdbup-backups/last_backup.json BACKUP_AGE_IDENTITY_FILE=/home/mdbup/mdbup-age-keys.txt ./scripts/backup-verify.sh >> /home/mdbup/mdbup-backups/backup-verify.log 2>&1
```

- `scripts/backup.sh` scrive `last_backup.json` con timestamp/file/size/sha256/status; la retention GFS non lo tocca.
- `scripts/backup-verify.sh` verifica checksum, header age e, con identità, decifra e controlla il magic `PGDMP`.
- CLI `python -m app.cli backup-verify` funziona anche con `/backups` montato read-only: verifica checksum/header e salta l'aggiornamento dello status; la decifratura completa richiede la chiave age sull'host.
- Live: backup `mdbup-20261117T201311Z.dump.age` (4.0 MB, checksum OK), status `OK`, metriche backup valorizzate.

## 7. E2E Playwright

Suite in `frontend/e2e/` con API mockate (`page.route` su pathname `/api/`), quindi nessuna richiesta può raggiungere un backend o MDBList reale.

Copertura (7 test):

1. Login e dashboard.
2. `X-CSRF-Token` su mutazione.
3. Sesto login → 429 → UI “Troppi tentativi / Riprova tra 60 secondi”.
4. Creazione `CUSTOM_FILTER` multi-provider con payload verificato.
5. Creazione/modifica/sostituzione segreto/test canale notifica.
6. Dry-run con diff `+3`/`−2`, barre soglia e tab campioni.
7. Export configurazione con scansione ricorsiva anti-segreti.

Comando: `cd frontend && npm run test:e2e` → **7 passed**.

## 8. Test e verifica live

| Verifica | Esito |
|---|---|
| Backend `pytest` | **272 passed** (include 30 test JustWatch) |
| Backend `ruff check` / `format --check` | puliti |
| Frontend `typecheck` | OK |
| Frontend `build` | OK |
| Frontend `npm test` | **75 passed** |
| Frontend `lint` | pulito |
| Playwright E2E | **7 passed** |
| Migrazione SQLite up/down/up | OK |
| Migrazione PostgreSQL live | `0004_notification_retry` |
| Stack live | 4/4 healthy (`api`, `worker`, `postgres`, `redis`) |
| Code Celery | 0/0/0/0 |
| SPA servita dall'API | HTTP 28080, asset e deep link OK |
| Cookie HTTPS | `__Host-…`, `Secure`, `Path=/`, no Domain |
| Metrics | 401 senza auth, 403 token errato, 200 token valido |
| Backup status | `OK`, timestamp valorizzato |
| Dry-run 6 binding | tutti `SUCCEEDED`, `to_add=0`, `to_remove=0` |
| Liste MDBList | 755 / 428 / 365 / 226 / 146 / **114** invariate/attive |

## 9. File principali

**Backend/ops**
- `backend/alembic/versions/0004_notification_retry.py`
- `backend/app/services/backup.py`, `system_status.py`, `notifications.py`
- `backend/app/api/routers/health.py`, `notifications.py`
- `backend/app/api/schemas.py`, `schemas_notifications.py`
- `backend/app/cli.py`, `core/config.py`, `db/models/notification.py`, `jobs/tasks.py`, `jobs/celery_app.py`
- `scripts/backup.sh`, `scripts/backup-verify.sh`
- `deploy/Dockerfile.api`, `deploy/docker-compose.yml`, `docker-compose.yml`

**Frontend**
- `frontend/src/index.css`, `tailwind.config.ts`, `index.html`
- `frontend/src/app/theme-provider.tsx`, `app-layout.tsx`
- `frontend/src/components/ui/*`, `components/dashboard/*`
- `frontend/src/pages/*`
- `frontend/src/lib/health.ts`, `status.ts`, `theme.ts`, `run-summary.ts`, `format.ts`, `errors.ts`
- `frontend/src/api/*`
- `frontend/e2e/*`, `playwright.config.ts`, `tsconfig.e2e.json`

**Docs**
- `README.md`
- `docs/phase7/STATUS.md`
- `docs/phase7/BACKEND_NOTES.md`

## 10. Limiti residui

- E2E con API mockate: non esercita PostgreSQL/Celery reali; la suite full-stack è il prossimo passo.
- Reverse proxy esterno: l'app non include Caddy/Nginx; esporre `28080` con il proxy scelto.
- `METRICS_TOKEN` è gestito a mano, non dal keyring.
- `backup-verify` nel container non ha la chiave age; la verifica completa è sull'host.
- Il catalogo completo Disney+ Film resta non valido per duplicati TMDb; la collezione per genere è valida.
- Nessuna regressione visuale automatica (screenshot) nella suite E2E.
