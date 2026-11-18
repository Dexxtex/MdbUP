# Fase 09 — Multi-fonte, Cambi Catalogo IT e scheduling

> Report consolidato della fase. Le fonti originali sono state unite in questo documento.


---

## Fonte: `phase-09.md`

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


---

## Fonte: `phase-09.md`

# Fase 9 — multi-fonte, Cambi Catalogo IT e scheduling

**Data:** 2026-11-18
**Stato:** completata e verificata live su server Ubuntu (stack 4 servizi).

---

## 1. Risultato

La Fase 9 rende **JustWatch la fonte predefinita** e aggiunge:

- selettore esplicito **JustWatch / TMDb / Combinata locale (JustWatch + TMDb)**
  nel builder, con default configurabile da *Impostazioni → Connettori*;
- feed **Cambi Catalogo IT** con eventi `ADDED`/`REMOVED` calcolati solo tra
  snapshot consecutivi `COMPLETE`/`CLEAN`, con baseline iniziale ignorata;
- collezioni combinate locali per **unione** o **intersezione** deduplicate per
  `media_id`, senza chiamate esterne;
- scheduling scaglionato JustWatch: 96 slot da 15 minuti, **massimo una
  acquisizione per tick**, lock Redis e throttle globale 1 req/s;
- matrice comparativa provider JustWatch/TMDb, widget dashboard, ricerca
  istantanea nello snapshot e avvisi per le raccolte In arrivo;
- default source e scheduling configurabili a runtime.

Nessuna modifica automatica ai binding esistenti e nessuna sync MDBList per le
nuove collezioni.

---

## 2. Live produzione

| Controllo | Esito |
|---|---|
| Stack | `api`, `worker`, `postgres`, `redis` **4/4 healthy** |
| Migrazione | `0005_snapshot_item_availability` |
| Immagine | `ghcr.io/dexxtex/mdbup:latest` |
| Digest | `sha256:6d84cb4a96dc99184b2e70a2e47b642ead6c28a39b3d9248f8b79bc6971dfdef` |
| Fonte predefinita | `justwatch` |
| Scheduling | `catalog_schedule_enabled=true`; 88 prossime acquisizioni nelle 24h; primo job scaglionato accodato (Paramount Plus — Serie — Catalogo) |
| Porte | API `28080`; PostgreSQL/Redis solo `127.0.0.1` |

### Acquisizioni JustWatch live

| Provider / collezione | Esito |
|---|---|
| Prime Video — Film catalogo | **8.240** titoli, 87 pagine, `COMPLETE/CLEAN`, valido |
| NOW — Film catalogo | **1.145** titoli, 12 pagine, `COMPLETE/CLEAN`, valido |
| Disney+ — Film in arrivo | **3** titoli, `COMPLETE/CLEAN`, `UPCOMING`, valido |
| Apple TV+ — Film catalogo | **116** titoli, valido |
| Apple TV+ — Film classifica | **105** titoli, valido |
| Apple TV+ — Film in arrivo | **3** titoli, `UPCOMING`, valido |
| Netflix — Film catalogo | **5.525** titoli, snapshot storico invariato |

Preview source-only: **READY** per Prime (`to_add=8240`), NOW (`to_add=1145`),
Disney in arrivo (`to_add=3`) e Apple (`to_add=116`), sempre `to_remove=0`.

### Cambi Catalogo IT

`GET /api/catalog-changes?window=24h` risponde **200** con contatori e feed
vuoto: nel database di produzione non esistono ancora due snapshot consecutivi
validi con titoli diversi. Il calcolo è coperto da test con fixture
`ADDED`/`REMOVED`, snapshot `INCOMPLETE` ignorati e baseline saltata.

### Liste MDBList

Le **6 liste** sono invariate. Dry-run/preview su tutti i 6 binding:
`to_add=0`, `to_remove=0`.

| Lista | Elementi |
|---|---:|
| Netflix IT — Film Azione | 755 |
| Netflix IT — Film Avventura | 428 |
| Netflix IT — Film Horror | 365 |
| Apple TV+ IT — Serie TV | 226 |
| Mediaset Infinity IT — Film | 146 |
| Disney+ IT — Animazione Top | 114 |

Backup pre-deploy: `mdbup-20261118T110636Z.dump.age` (7.0 MB).

---

## 3. Test

| Suite | Esito |
|---|---|
| Backend `pytest` | **357 passed** |
| Backend `ruff check` / `format --check` | puliti |
| Frontend `typecheck` / `build` / `lint` | verdi |
| Frontend Vitest | **115 passed** |
| Playwright E2E | **12 passed** |

E2E aggiunto per il feed Cambi Catalogo IT e per la matrice provider; restano
coperti builder JustWatch, switch fonte, preview source-only, eventi
stagione/episodio e badge di origine.

---

## 4. Limiti noti

- JustWatch non pubblica date di aggiunta: `date_basis=UNKNOWN`; il feed mostra
  il timestamp di rilevazione dello snapshot, non una data ufficiale.
- `newTitles` ignora `objectTypes` e in Italia restituisce solo film: una
  collezione **serie TV — Novità** può restare vuota e invalida.
- La classifica è la classifica streaming JustWatch (rank globali), mai Top 10
  ufficiale del provider.
- Lo scheduling assegna uno slot per collezione e accoda al massimo una
  acquisizione per tick; dopo un fermo macchina il recupero avviene nei tick
  successivi, non con un burst.
- Le collezioni combinate usano solo snapshot validi già presenti: se una
  sorgente non ha snapshot valido, la collezione non è valida.
