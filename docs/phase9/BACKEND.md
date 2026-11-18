# Fase 9 — note backend (parte A)

Solo codice backend: nessuna modifica a frontend, server o liste MDBList reali.
Nessuna migrazione: i nuovi dati vivono in colonne JSON/righe `app_setting`
già esistenti, quindi la collezione `netflix-movie-justwatch` (5.525 titoli) e
le 6 liste MDBList restano intatte.

## 1. Fonte predefinita e scheduler

| Variabile | Default | Impostazione runtime |
|---|---|---|
| `DEFAULT_SOURCE` | `justwatch` | `default_source`, valori ammessi `justwatch`/`tmdb` |
| `CATALOG_SCHEDULE_ENABLED` | `true` | `catalog_schedule_enabled` |

`SettingSpec` ha un campo `choices`: `PATCH /api/settings` rifiuta con
`VALIDATION_INVALID_SETTING` qualunque valore fuori elenco. Entrambe le chiavi
compaiono in `GET /api/settings` e viaggiano in `GET /api/config/export` /
`POST /api/config/import` come tutte le altre impostazioni.

`catalog_schedule_enabled` è `true` di default perché il tick non è un burst:
enqueue al massimo una acquisizione per volta, solo per collezioni più vecchie
di 20 ore e solo nel proprio slot. Il costo in richieste JustWatch resta quello
già imposto dal throttle (1 req/s).

## 2. Mapping provider JustWatch movie/tv

`ProviderMapping` resta una riga per `(source, country, external_provider_id)`
con il vincolo unico esistente. `services/justwatch_collections.py` aggiunge in
`metadata_json`:

- `movie_external_id` / `tv_external_id` (lo stesso `shortName` verificato, ma
  separato per tipo come per i mapping TMDb);
- `movie_verified` / `tv_verified`;
- `technical_name`, `clear_name`, `monetization_types`, `verified_at`,
  `verified_on`.

`ProviderOut` espone `justwatch_movie_verified` e `justwatch_tv_verified` accanto
ai campi già presenti (`justwatch_provider_id`, `justwatch_verified`,
`justwatch_monetization_types`).

## 3. Acquisizioni scaglionate del catalogo JustWatch

`app/services/catalog_schedule.py`:

- slot deterministico `sha256(slug) % 96` → 96 bucket da 15 minuti nella giornata
  `Europe/Rome`; `next_acquire_at(slug, now)` calcola la prossima occorrenza;
- una collezione è dovuta se: attiva, fonte `justwatch`, nessuno snapshot
  `RUNNING`, ultimo snapshot `COMPLETE` assente o più vecchio di 20 h, ultimo
  tentativo (qualunque stato) più vecchio di 60 min, nessun job di acquisizione
  `QUEUED`/`RUNNING`, slot odierno già iniziato;
- il tick ordina per slot e accoda **una sola** collezione, sotto il lock Redis
  `mdbup:justwatch:catalog-scheduler` (namespace `DispatchLock`
  `mdbup:justwatch`, TTL 900 s) più un controllo `RUNNING` ripetuto dentro il lock.

Task Celery `app.jobs.tasks.enqueue_scheduled_catalog_acquisitions`, coda
`maintenance`, beat ogni 300 s (`enqueue-scheduled-catalog-acquisitions`).
Accetta `now` ISO per i test; in produzione legge l'orologio. L'enqueue passa da
`tasks.enqueue_acquire_collection`, quindi il job row resta la fonte di verità.

`GET /api/system/status` aggiunge `catalog_acquisitions`: le prossime
acquisizioni nelle 24 h, ordinate, con `collection_id`, `collection_name`,
`provider_name`, `next_acquire_at` (UTC).

## 4. Throttle globale

`JustWatchClient` usa `RequestPacer`: un solo pacer di processo
(`_PROCESS_PACER`) con lock `threading`, quindi due client costruiti da due task
del worker (concorrenza 2) condividono lo stesso budget di 1 req/s. L'intervallo
è misurato inizio-inizio. Un clock o una sleep iniettati (test) creano un pacer
privato: nessun test esistente cambia comportamento.

## 5. Ricerca negli snapshot

`GET /api/snapshots/{snapshot_id}/items` accetta `search` (max 200 caratteri):
match case-insensitive su `media.title` con escape dei metacaratteri LIKE. Il
`total` è quello filtrato, la paginazione resta `page`/`page_size`. Provider e
metadati delle offerte non sono cercati; gli item non risolti non matchano.

## 6. Guardrail binding per target

Tre livelli, invariati nei dati esistenti:

1. indice unico parziale `binding_one_active_target_uq` (`target_id` dove
   `is_enabled`);
2. `create_binding` / `update_binding` rispondono `409 TARGET_LOCKED`;
3. `enqueue_due_bindings` considera solo il binding abilitato più vecchio di ogni
   target (`scheduler.target_binding_owner`), avanzando `next_run_at` degli altri
   e loggando `scheduler_target_binding_conflict`.

## 7. Test

`pytest` backend completo, `ruff check`, `ruff format --check`. Nuovi test:
impostazioni `default_source`/`catalog_schedule_enabled` (default, patch,
export/import), mapping movie/tv JustWatch, slot deterministico e un solo
enqueue per tick, backoff e job in coda, throttle condiviso, `system/status` con
`catalog_acquisitions`, ricerca snapshot, target lock (DB, service, scheduler).

## 8. Da fare nella parte B

- Rigenerare `frontend/src/api/schema.d.ts` per i due campi nuovi di
  `ProviderOut` e per `catalog_acquisitions`.
- UI: selettore della fonte predefinita, elenco delle prossime acquisizioni,
  campo di ricerca nello snapshot.
