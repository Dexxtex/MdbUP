# Fase 06 — Hardening e regole avanzate

> Report consolidato della fase. Le fonti originali sono state unite in questo documento.


---

## Fonte: `phase-06.md`

# Fase 6 — Hardening, alerting e regole avanzate

**Data:** 2026-11-17
**Stato:** completata e verificata live su Ubuntu (`/home/mdbup/mdbup`, Docker Compose 7 servizi).

## 1. Sicurezza e preparazione HTTPS

### Cookie LAN / HTTPS

Il backend deriva il nome effettivo dei cookie da `COOKIE_SECURE`:

| Modalità | `COOKIE_SECURE` | Cookie sessione | Cookie CSRF | Attributi |
|---|---:|---|---|---|
| LAN HTTP | `false` | `mdbsync-session` | `mdbsync-csrf` | `HttpOnly` solo sessione, `SameSite=Lax` |
| HTTPS | `true` | `__Host-mdbsync-session` | `__Host-mdbsync-csrf` | `Secure`, `Path=/`, nessun `Domain` |

Il prefisso `__Host-` viene aggiunto/rimosso automaticamente: il `.env` può contenere
`SESSION_COOKIE_NAME=mdbsync-session` in entrambe le modalità. La cancellazione dei
cookie usa gli stessi nomi effettivi e `Secure` in HTTPS.

Caddy applica CSP, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`,
`Permissions-Policy`, `X-Content-Type-Options: nosniff`, COOP/CORP. HSTS è
condizionato al matcher `protocol https`, quindi non viene inviato in LAN HTTP.

### Rate limiting Redis

`RateLimiter` usa Redis con contatore a finestra fissa e lockout separato:

- login: `LOGIN_MAX_ATTEMPTS` in `LOGIN_WINDOW_MINUTES`, poi lockout
  `LOGIN_LOCKOUT_MINUTES`;
- cambio password: 3 tentativi / 15 minuti + lockout;
- bootstrap: limite dedicato;
- fallback in-memory solo se Redis non è raggiungibile (fail closed, non fail open).

Live: 5 login errati → `401`, sesto → `429 AUTH_RATE_LIMITED`; chiave Redis
`mdbup:ratelimit:login:<ip>:<email>` con TTL; chiave di test rimossa.

### Origin / Referer

`verify_origin` confronta schema, hostname e porta effettiva (default 80/443) di
`Origin` e `Referer`. Un header valido non maschera l'altro; in produzione un
header assente viene rifiutato. Sono rifiutati URL con credenziali incorporate e
look-alike host.

### Rotazione chiave di cifratura

- `APP_ENCRYPTION_KEYS` è un keyring JSON: `{"1":"<base64>","2":"<base64>"}`.
- `APP_ENCRYPTION_KEY`/`APP_ENCRYPTION_KEY_VERSION` indicano la chiave attiva.
- CLI:
  ```bash
  # la nuova versione deve essere già nel keyring, con la vecchia chiave ancora presente
  docker compose --env-file .env -f deploy/docker-compose.yml exec api \
    python -m app.cli rotate-encryption-key --new-version 2 --dry-run
  docker compose --env-file .env -f deploy/docker-compose.yml exec api \
    python -m app.cli rotate-encryption-key --new-version 2
  ```
- Re-cifra sia `credential` sia i segreti dei canali di notifica, senza reinserire
  le API key. Dopo la rotazione impostare `APP_ENCRYPTION_KEY_VERSION=2` (e la
  chiave corrispondente) e riavviare `api`, `worker`, `scheduler`.
- Test unitario: credenziale TMDb cifrata con v1, rotazione a v2, lettura con la
  nuova configurazione.

## 2. Notifiche

Tabella `notification_channel` (migrazione `0003_notifications`):

- `kind`: `WEBHOOK`, `TELEGRAM`, `DISCORD`;
- `events`: lista di eventi;
- `config`: `chat_id` per Telegram (nessun segreto);
- segreto cifrato AES-256-GCM con AAD `NOTIFICATION|<channel_id>|<kind>|<version>`;
- `last_sent_at`, `last_status`, `last_error`.

Eventi:

| Evento | Quando |
|---|---|
| `RUN_PENDING_APPROVAL` | run in `AWAITING_APPROVAL` per soglie/policy |
| `RUN_FAILED` | run `FAILED` |
| `RUN_UNCERTAIN` | run `PARTIAL` con operazioni incerte |
| `AUTH_ERROR` | 401/403 TMDb o MDBList (dedupe 6h) |
| `SUMMARY` | riepilogo giornaliero opzionale |

Task Celery sulla coda `maintenance`:

- `send_run_notifications` ogni 60 s;
- `send_periodic_summary` ogni ora (invia solo nell'ora configurata, una volta al giorno);
- `sweep_orphan_locks` ogni 5 min.

Il primo canale creato marca `sync_run.notified_at` per i run storici, evitando
di riprodurre tutta la cronologia. La migrazione fa lo stesso backfill.

API:

- `GET /api/notifications/channels`
- `POST /api/notifications/channels`
- `PATCH /api/notifications/channels/{id}`
- `DELETE /api/notifications/channels/{id}`
- `POST /api/notifications/channels/{id}/test`

Live: canale webhook temporaneo su rete `mdbup_edge`, messaggio di prova
ricevuto con `event=TEST`, `200`; canale eliminato e container di test rimosso.

## 3. Collezioni avanzate

`CollectionKind.CUSTOM_FILTER` + `filters.derivation=LOCAL_FILTER`:

- `source_collection_ids`: una o più collezioni, anche di provider diversi;
- `with_genres`, `exclude_genres`;
- `min_vote_average`, `min_vote_count`;
- `year_from`, `year_to`;
- `original_language`;
- `sort_by` locale (`vote_average.desc`, `vote_count.desc`, `release_date.desc`,
  `title.asc`, `popularity.desc`).

L'acquisizione usa solo gli snapshot validi già in PostgreSQL: nessuna chiamata
TMDb/MDBList. Deduplica per `media_id`, quindi lo stesso titolo presente su più
provider compare una volta. Se una sorgente non ha uno snapshot valido, lo
snapshot combinato è `WARNINGS`/non valido e non autorizza MIRROR.

UI:

- form Collezioni con tipo “Raccolta combinata / filtrata localmente”;
- selezione multipla delle sorgenti, filtri e generi esclusi;
- badge “Combinata multi-provider (locale)” / “Filtrata localmente”;
- nota esplicita che non è una lista ufficiale dei provider.

Live: creata “Film Azione IT — combinata live” da Netflix Azione + Mediaset
Infinity Film, `genre=28`, voto ≥ 6.5, voti ≥ 100, anni 1990–2026:
snapshot `COMPLETE`, **232 item**, `is_valid=true`, `is_multi_provider=true`.
La collezione di test è stata eliminata dopo la verifica.

## 4. Portabilità configurazione

`GET /api/config/export` produce:

```json
{
  "version": 1,
  "app_version": "0.2.0",
  "exported_at": "...",
  "providers": [{"slug": "...", "mappings": [...]}],
  "targets": [{"remote_list_id": 243532, "...": "..."}],
  "collections": [{"slug": "...", "filters": {...}}],
  "bindings": [{"collection_slug": "...", "target_remote_list_id": 243532, "...": "..."}],
  "settings": {"...": "..."},
  "notification_channels": [{"name": "...", "kind": "...", "events": [...]}]
}
```

Non contiene credenziali, ciphertext, utenti, sessioni, run o snapshot.
`POST /api/config/import` è un upsert per slug/remote id; non cancella righe.
Le collezioni sono importate in due passaggi per risolvere i riferimenti
`source_collection_slugs`/`shared_snapshot_collection_slug`. I binding abilitati
importati ricevono `policy_accepted_at` (azione admin esplicita).

Live: export 12 provider / 27 collezioni / 5 target / 5 binding / 10 impostazioni;
import idempotente con gli stessi conteggi; nessuna occorrenza di
`ciphertext`, `api_key`, `app_encryption`, `password` o `bearer `.

## 5. Self-healing lock

`DispatchLock` ha TTL 120 s, ma un container ucciso tra `acquire` e `release`
può lasciare un lock per due minuti. `sweep_orphan_locks` scansiona
`mdbup:dispatch:target:*`, verifica se esiste un run attivo per il target e
cancella il lock se non c'è. Live: lock fittizio creato, task eseguito,
`{"removed": 1}`, chiave assente.

## 6. Test e verifica

| Verifica | Esito |
|---|---|
| Backend `pytest` | **204 passed** |
| Backend `ruff check` / `format --check` | puliti |
| Frontend `npm run typecheck` | OK |
| Frontend `npm run build` | OK |
| Frontend `npm test` | **42 passed** |
| Frontend `npm run lint` | pulito |
| Migrazione SQLite up/down/up | OK |
| Migrazione PostgreSQL live | `0003_notifications` |
| Stack live | 7/7 healthy |
| Code Celery | 0/0/0/0 |
| Dry-run 5 binding | `SUCCEEDED`, `to_add=0`, `to_remove=0` |
| Liste MDBList | 755 / 428 / 365 / 226 / 146 invariate |

Nuovi test:

- `test_cookie_mode.py` — switch LAN/HTTPS e `__Host-`;
- `test_rate_limit_redis.py` — persistenza e lockout;
- `test_notifications.py` — webhook/Telegram/Discord, pending/failed, dedupe auth;
- `test_notifications_api.py` — CRUD e test;
- `test_local_filters.py` — multi-criterio, multi-provider, dedupe, nessuna chiamata esterna;
- `test_config_api.py` — export senza segreti, import idempotente;
- `test_encryption_rotation.py` — rotazione keyring;
- `test_scheduler.py` — sweep lock orfani.

## 7. Limiti residui

- Notifiche best-effort, senza coda di retry dedicata.
- I canali di notifica non vengono riattivati da un import senza segreto.
- La rotazione richiede che la nuova chiave sia già nel keyring e un riavvio
  dopo l'aggiornamento di `APP_ENCRYPTION_KEY_VERSION`.
- Le collezioni locali richiedono snapshot validi delle sorgenti.
- HSTS è assente in HTTP LAN per scelta; in HTTPS è inviato da Caddy.
- E2E Playwright, metriche Prometheus e TLS pubblico non sono parte di questa fase.

## 8. Backup/restore verificato

- Backup pre-deploy: `mdbup-20261117T191855Z.dump.age` (1.4 MB, checksum OK).
- Restore su `mdbup_restore_phase6`: 1 utente, 27 collezioni, 9 snapshot,
  5 binding, 32 run, 5 target, 1705 availability.
- `alembic upgrade head` sul DB ripristinato: `0002_binding_schedule_interval`
  → `0003_notifications`; tabella `notification_channel` e colonna
  `sync_run.notified_at` presenti.
- DB scratch eliminato; il DB live non è stato toccato.

## 9. Verifica live Fase 6

| Controllo | Esito |
|---|---|
| Stack | 7/7 healthy |
| Migrazione | `0003_notifications` |
| Code Celery | 0/0/0/0 |
| Notifica di prova | webhook ricevuto, `200`, `event=TEST` |
| Rate limit login | 5×401, sesto 429; chiave Redis rimossa |
| Cookie LAN | `mdbsync-session`/`mdbsync-csrf`, senza `Secure`/`__Host-` |
| Header Caddy HTTP | CSP, X-Frame-Options, Referrer-Policy, Permissions-Policy; **nessun HSTS** |
| Header Caddy HTTPS (test locale) | HSTS presente su TLS; redirect HTTP→HTTPS |
| Export/import | 12 provider, 27 collezioni, 5 target, 5 binding, 10 impostazioni; nessun segreto |
| Collezione combinata | 232 item, `COMPLETE`, valida, multi-provider; poi eliminata |
| Lock orfano | creato, `sweep_orphan_locks` → `{"removed": 1}`, chiave assente |
| Dry-run 5 binding | `SUCCEEDED`, `to_add=0`, `to_remove=0` |
| Liste MDBList | 755 / 428 / 365 / 226 / 146 invariate |
