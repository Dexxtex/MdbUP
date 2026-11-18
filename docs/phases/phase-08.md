# Fase 08 — JustWatch pubblico e guardrail

> Report consolidato della fase. Le fonti originali sono state unite in questo documento.


---

## Fonte: `phase-08.md`

# JustWatch — fonte `justwatch` (endpoint GraphQL pubblico)

**Data:** 2026-11-17
**Stato:** implementata e attiva (`SourceStatus.OK`)
**Chiave fonte:** `justwatch`
**Credenziali:** nessuna

---

## 1. Cosa aggiunge

La fonte `justwatch` copre ciò che TMDb non espone:

| Capacità | TMDb | JustWatch |
|---|---|---|
| Catalogo per provider | ✅ (cap 500 pagine) | ✅ (paginazione completa) |
| Novità | ❌ | ✅ `pageType: NEW` |
| In arrivo | ❌ | ✅ `pageType: UPCOMING` |
| In partenza | ❌ | ✅ `pageType: LEAVING_SOON` |
| Classifiche con rank | ❌ | ✅ rank, trend, giorni in top 10 |
| Stagioni / episodi con offerte | parziale | ✅ |
| ID TMDb e IMDb nel nodo | — | ✅ `content.externalIds` |
| Data di aggiunta | ❌ | ❌ (nessun timestamp) |

La fonte resta **`AGGREGATOR`**, mai `OFFICIAL`: l'endpoint non pubblica date
dichiarate dal provider, quindi `date_basis=UNKNOWN` e `source_date_created=None`.
Per `date_created` l'unica via resta la Partner API, che è contrattuale.

---

## 2. Implementazione

```
backend/app/integrations/justwatch/
    queries.py     # documenti GraphQL verificati a mano (introspection disabilitata)
    models.py      # Title, Offer, Package, ChartEntry, Season, Episode, Page
    client.py      # httpx, retry+backoff+jitter, throttle, errori tipizzati
backend/app/connectors/justwatch/
    connector.py   # SourceConnector: providers, collections, paging, hierarchy
backend/app/services/justwatch_collections.py
                   # mapping provider + upsert collezioni
```

Convenzioni riprese da TMDb: `record_api_call("justwatch")`, `backoff_delay`,
`follow_redirects=False`, nessun payload nei log, `SourceConnector` completo.

### Paginazione completa

L'endpoint si ferma all'elemento **#1999** per query. Il connettore non tronca:
partiziona `releaseYear` (`IntFilter {min,max}`) e spezza in due ogni intervallo che
supera il tetto, fino a foglie che ci stanno dentro. Il cursore trasporta gli
intervalli ancora da percorrere:

```
"1900-2030|1966-2030:300"   →  intervalli pendenti + offset nel primo
```

È stateless: un run può riprendere dal solo cursore. Se un **singolo anno** supera
1999 titoli non c'è modo di scendere oltre; in quel caso la pagina porta
`raw["_truncated"] = true` invece di far finta di aver finito.

### Collezioni

Ogni collezione è legata a un provider (lo schema lo richiede) e a un tipo di media:

| Tipo | Chiave sorgente | Slug |
|---|---|---|
| `CATALOG` | `<pkg>:<MOVIE\|SHOW>` | `<provider>-<media>-justwatch` |
| `CHART` | `chart:<pkg>:<MOVIE\|SHOW>` | `<provider>-<media>-justwatch-chart` |
| `RECENTLY_ADDED` | `recently-added:<pkg>:<MOVIE\|SHOW>` | `<provider>-<media>-justwatch-new` |
| `UPCOMING` | `upcoming:<pkg>:<MOVIE\|SHOW>` | `<provider>-<media>-justwatch-upcoming` |

Creazione/aggiornamento:

```bash
cd backend
uv run python -m app.cli justwatch-collections              # tutti i provider mappati
uv run python -m app.cli justwatch-collections --provider netflix
```

Il mapping slug canonico → codice JustWatch è **esplicito** in
`app/services/justwatch_collections.py` (verificato sulla lista provider IT): il
match per nome è ambiguo (`Apple TV` vs `Apple TV Store`, `Amazon Prime Video` vs
`... with Ads`). I provider che la fonte riporta ma che non hanno mapping vengono
**saltati e contati**, mai indovinati.

---

## 3. Limiti misurati

| Aspetto | Valore |
|---|---|
| Elementi per pagina | **100** (`first: 101` → `page too large`) |
| Elemento massimo raggiungibile | **#1999** per query (oltre: `edges: []`, nessun errore) |
| Rate limit esposto | **nessuno** (nessun header, nessun `429` su 500 concorrenti e 40 req/s) |
| Avviso prima del blocco | **nessuno**: il blocco, se arriva, è un ban IP silenzioso |
| Introspection | disabilitata (`__schema` e `__type` rifiutati) |
| Mutations | 20, tutte dietro `GUEST`/`LOGGED_IN`: nessuna usabile in anonimo |

Il throttle locale (`JUSTWATCH_MIN_INTERVAL_MS`, default 1000) è quindi l'unica
protezione reale: non esiste un feedback dal servizio.

---

## 4. Superficie API verificata

Campi root (22): `popularTitles`, `searchTitles`, `newTitles`, `newTitleBuckets`,
`popularPeople`, `node`, `nodes`, `packages`, `genres`, `subgenres`, `languages`,
`locales`, `streamingCharts`, `titleList`, `articles`, `textRecommendations`,
`settings`, `profile`, `startPageModules`, `urlV2`, `ageCertifications`, `stats`.

Filtri `TitleFilter` (21): `searchQuery`, `objectTypes`, `genres`, `subgenres`,
`excludeGenres`, `packages`, `excludePackages`, `monetizationTypes`,
`presentationTypes`, `ageCertifications`, `productionCountries`,
`excludeProductionCountries`, `releaseYear`, `runtime`, `price`, `imdbScore`, `tags`,
`excludeIrrelevantTitles`, `includeTitlesWithoutUrl`, `excludeEroticAvodHack`,
`experiment`.

Trappole note:

- `presentationTypes` usa `_4K`, non `4K`;
- JustWatch **non traccia il 4K per Netflix**: in IT risultano 2 titoli, contro 1119
  su Prime Video e 2037 su Apple TV Store;
- `tags` accetta stringhe ma ignora i valori inesistenti, e i tag non sono
  interrogabili: il filtro è di fatto inutilizzabile;
- azione e avventura sono **un solo genere** (`act` = "Azione e Avventura"); la
  separazione avviene sui sottogeneri (`adva`, `acat`, `coac`);
- il rank delle classifiche sta sull'edge (`streamingChartInfo`), non sul nodo.

---

## 5. Attribuzione e comportamento d'uso

- Attribuzione **JustWatch** obbligatoria ovunque compaiano i dati (il footer della
  SPA la riporta già per i watch provider TMDb).
- Throttle locale attivo per default; non va abbassato sotto 1000 ms in uso reale.
- Nessun proxy, nessun User-Agent rotante, nessun retry su 403: se il servizio
  blocca, il connettore si ferma e lo segnala.
- La fonte `justwatch_partner` (Partner API) resta `DISABLED` e
  `requires_contract=True`: è un'altra cosa e non è sostituita da questa.

---

## 6. Test

| File | Copre |
|---|---|
| `tests/unit/test_justwatch_client.py` | parsing, clamp pagina, tetto #1999, cursori, rank sull'edge, 401/403/429/5xx, payload non JSON, healthcheck |
| `tests/unit/test_justwatch_connector.py` | capability, collezioni per provider, split degli intervalli, avanzamento tra anni, troncamento di un anno oltre il tetto, filtri genere/qualità, stagioni/episodi, registry senza flag |
| `tests/integration/test_justwatch_collections.py` | mapping provider, upsert collezioni, idempotenza, filtro per provider |

Smoke live eseguito a mano: 109 provider IT, pagina catalogo `nfx:MOVIE` con 100 item
su 5533 totali, rank e trend corretti, `tmdb`/`imdb` risolti dal nodo.

---

## 7. Verifica live (2026-11-17)

- Fonte `justwatch` creata con `seed-providers`; `SourceStatus.OK`.
- Mapping provider `netflix` → package `nfx`.
- Collezione `netflix-movie-justwatch` (CATALOG, MOVIE, AGGREGATOR, `date_basis=UNKNOWN`).
- Acquisizione: **5.525 titoli**, 60 pagine, `COMPLETE`/`CLEAN`, `is_valid=true`,
  0 unresolved, 0 duplicati, 0 errori.
- I due titoli senza `tmdbId`/`imdbId` (`tm1233174`, `tm2889227`) vengono saltati
  dal connettore: non sono sincronizzabili e renderebbero lo snapshot invalido.
- Preview source-only: `READY`, `to_add=5525`, `to_remove=0`, 0 unresolved.
- Nessuna sync MDBList è stata eseguita per questa fonte.
- Le 6 liste MDBList esistenti non sono state toccate.

---

## 8. Fase 8 — cache, schema drift e snapshot parziali

### Cache locale delle risposte

- Cache in-process con TTL (default **300 s**, `JUSTWATCH_CACHE_TTL_SECONDS`) e
  tetto di **512** voci (`JUSTWATCH_CACHE_MAX_ENTRIES`); chiave = query + variabili.
- I payload sono **deep-copy** in scrittura e in lettura: chi modifica una pagina non
  inquina la cache.
- **Mai** in cache: errori (429/5xx/timeout), healthcheck e risposte con schema drift.
- Hit/miss sono contati con lo stesso contatore Redis di `record_api_call`, quindi
  il processo API vede le statistiche prodotte dal worker:
  `api_usage_snapshot()["justwatch"]` espone `hour`, `today`, `cache_hits`, `cache_misses`.

### Schema drift

`JustWatchGraphQLError` (code `SCHEMA_DRIFT`) viene sollevata quando:

- il campo root atteso manca o non è un oggetto (`popularTitles`, `searchTitles`,
  `newTitles`, `streamingCharts`) o non è una lista (`packages`, `genres`);
- `pageInfo` manca dalla connessione;
- `edges` non è una lista.

La validazione avviene **prima** di scrivere in cache, quindi una risposta driftata non
resta servita per tutto il TTL. Una pagina vuota non viene mai restituita come
`COMPLETE`: l'errore arriva all'acquisizione.

### 429 / 5xx / timeout

Il retry resta limitato e con backoff progressivo; esauriti i tentativi l'errore è
tipizzato (`JustWatchRateLimitError` con `retry_after_seconds`, `JustWatchRequestError`,
`JustWatchAuthError`). Un 429 non viene mai nascosto.

### Snapshot: `partial_on_error`

La capability `partial_on_error=True` è attiva su JustWatch (connettore e seed della
fonte). Qualunque errore — anche alla **prima** pagina — produce:

| Campo | Valore |
|---|---|
| `status` | `INCOMPLETE` (mai `COMPLETE`/`FAILED` silenzioso) |
| `quality` | `ANOMALY` |
| `is_valid` | `false` |
| `last_valid_snapshot_id` | invariato |

Uno snapshot non valido non autorizza mai MIRROR.

---

## 9. Regole di contenuto del connettore

- **Flatrate assoluto per default** su catalogo, novità e in arrivo: `monetizationTypes`
  è passato al server *e* le pagine sono post-filtrate. `RENT`, `BUY`, `ADS`, `FREE`,
  canali e addon sono esclusi salvo `offer_types` espliciti nella collezione o nei filtri.
- **Post-filtro sempre attivo** su `collection.media_type`, package richiesto e offer
  type ammesso. Motivo verificato: `newTitles(pageType: NEW)` **ignora `objectTypes`** e
  in Italia con `objectType: SHOW` restituisce solo film. Una collezione SHOW basata sulle
  novità resta quindi vuota e **invalida** (`empty_catalog`): non viene inventato nessun
  show e non viene sincronizzata.
- **Classifiche**: `streamingCharts` restituisce rank globali (es. 20, 144) e può
  includere più package; il connettore post-filtra package + offer type e conserva il
  rank dell'edge. L'etichetta è sempre **`Classifica JustWatch`**, mai Top 10 ufficiale.
- **`UPCOMING`**: gli item hanno `availability_status="UPCOMING"`; catalogo, novità e
  classifiche `CURRENT`. Le collezioni in arrivo restano separate e non alimentano
  l'historico di disponibilità che genera i "appena rilevati".
- Restano attivi lo split `releaseYear` (tetto 1999 per query) e lo scarto dei titoli
  senza id TMDb/IMDb.

### Timeline serie (`justwatch_tv_events`)

`newTitles` non è utilizzabile per le serie, quindi la timeline si osserva sul catalogo
SHOW JustWatch già acquisito:

- cap per run: **20 show, 5 stagioni, 50 episodi**;
- prima osservazione = baseline in `media.metadata_json["justwatch_tv"]`, **nessun evento**;
- osservazioni successive = righe `episode_event` (`SEASON_ADDED`, `EPISODE_ADDED`)
  collegate alla **serie madre**, mai media episodio;
- errori TV best-effort: warning sullo snapshot, che resta valido; operazione idempotente;
- `occurred_at` è il momento di osservazione (la fonte non pubblica date di aggiunta);
- limite noto: il nodo stagione non espone il numero di stagione, quindi si usa il
  `seasonNumber` del primo episodio e, in assenza di episodi, la posizione 1-based
  nella risposta.

---

## 10. Mapping provider (verifica live 2026-11-18)

Una sola query `packages(country: IT, platform: WEB)` (throttle 1 req/s) ha confermato
109 package. Un mapping è **verificato** solo se `shortName` **e** `technicalName`
coincidono; il sync salva `technical_name`, `clear_name`, `monetization_types` e il
timestamp nel metadata del `ProviderMapping`.

| slug canonico | shortName | technicalName | clearName | monetizationTypes |
|---|---|---|---|---|
| netflix | `nfx` | `netflix` | Netflix | FLATRATE |
| prime-video | `prv` | `amazonprimevideo` | Amazon Prime Video | FLATRATE, FREE |
| disney-plus | `dnp` | `disneyplus` | Disney Plus | FLATRATE |
| apple-tv-plus | `atp` | `appletvplus` | Apple TV | FLATRATE, FREE |
| now | `ntv` | `nowtv` | Now TV | FLATRATE, FREE |
| paramount-plus | `pmp` | `paramountplus` | Paramount Plus | FLATRATE, FREE |
| raiplay | `rai` | `raiplay` | Rai Play | ADS, FLATRATE, FREE |
| mediaset-infinity | `msp` | `mediasetplay` | Mediaset Infinity | ADS, FLATRATE, FREE |
| infinity-plus | `inf` | `infinity` | Infinity+ | FLATRATE |
| timvision | `tvi` | `timvision` | Timvision | BUY, FLATRATE, RENT |
| rakuten-tv | `wki` | `wuaki` | Rakuten TV | ADS, BUY, RENT |
| mubi | `mbi` | `mubi` | MUBI | FLATRATE |

`atp` è **Apple TV+** (`appletvplus`), non Apple TV Store (`itu`).

Conseguenze nel sync (`justwatch-collections`):

- `rakuten-tv` è verificato ma **senza FLATRATE**: viene riportato in
  `skipped_providers` e non riceve collezioni;
- package live senza mapping curato finiscono in `unmapped_packages`; provider il cui
  `technicalName` non coincide finiscono in `unverified_providers` e vengono saltati;
- `offer_types` di default è `["FLATRATE"]`;
- l'upsert aggiorna **solo** metadati e filtri: snapshot e `last_valid_snapshot_id`
  esistenti (per esempio `netflix-movie-justwatch`) non vengono toccati.

Nomi: `— Catalogo JustWatch`, `— Novità JustWatch`, `— In arrivo JustWatch`,
`— Classifica JustWatch`.
Etichette API (`CollectionOut.source_label`): `Classifica JustWatch` per le chart
JustWatch, `Fonte: JustWatch (Aggregatore)` per le altre, `TMDb` per TMDb.

---

## 11. Superficie API Fase 8

| Endpoint / modello | Novità |
|---|---|
| `GET /api/sources` | blocco `justwatch`: `throttle_ms`, TTL/max cache, `cache_hits`, `cache_misses`, `requests_hour`, `requests_today`, `mappings[]` verificati (slug, nome, external id, technical/clear name, monetization, `collections_count`), `supported_kinds`, `supported_offer_types` |
| `GET /api/providers` | `justwatch_provider_id`, `justwatch_verified`, `justwatch_monetization_types` |
| `GET /api/collections/{id}` | `source_label` |
| `GET /api/snapshots/{id}/items` | `availability_status`, `source_offer_types` |
| `GET /api/collections/{id}/episode-events?limit=` | eventi stagione/episodio delle serie madri (titolo, tipo, stagione, episodio, `occurred_at`, `source_key`); 422 `COLLECTION_NOT_SHOW` su collezioni film |
| `POST /api/collections` | `source_key` (`tmdb` default, `justwatch`), kind `CHART` e `UPCOMING`, `offer_types`; per JustWatch serve un mapping verificato e i filtri diventano `packages`/`watch_region`/`media_type`/anni/`offer_types`, `origin=AGGREGATOR`, `date_basis=UNKNOWN`; nessuna derivazione `RECENTLY_DETECTED` |
| `PATCH /api/collections/{id}` | stessi campi; `source_key` immutabile (`SOURCE_KEY_IMMUTABLE`), kind TMDb-only rifiutati (`KIND_NOT_SUPPORTED`) |
| `POST /api/bindings` | `justwatch_policy_accepted` (default `false`): senza accettazione esplicita → 422 `JUSTWATCH_POLICY_NOT_ACCEPTED`; i binding JustWatch nascono **sempre** `enabled=false` |
| `POST /api/bindings/{id}/runs` | un run reale su collezione JustWatch richiede un dry-run `SUCCEEDED` per quel binding, altrimenti 409 `DRY_RUN_REQUIRED`; il dry-run resta sempre possibile |

Migrazione: `0005_snapshot_item_availability` aggiunge
`snapshot_item.availability_status` **nullable** (`CURRENT`/`UPCOMING`/`LEAVING`),
idempotente, compatibile SQLite e PostgreSQL (su PostgreSQL aggiunge anche il CHECK).

Nessun binding viene creato automaticamente e nessuna sync MDBList è stata eseguita:
le 6 liste di produzione non sono state lette né scritte.

---

## 12. Test Fase 8

| File | Copre |
|---|---|
| `tests/unit/test_justwatch_client_cache.py` | cache hit + deep copy, cache disabilitabile, errori/healthcheck mai in cache, drift per root/`pageInfo`/`edges`, payload driftato non cachato, hit/miss in `api_usage_snapshot` |
| `tests/unit/test_justwatch_connector_rules.py` | film in collezione SHOW scartati, package obbligatorio, flatrate vs rent/buy/ads/free, `offer_types` espliciti, chart con rank globale, etichette, `UPCOMING`/`CURRENT`, capability `partial_on_error` |
| `tests/unit/test_justwatch_partial_snapshot.py` | 429 e schema drift ⇒ `INCOMPLETE`/`ANOMALY` non valido, nessun MIRROR, collezione SHOW novità vuota invalida, `availability_status` e nessuna osservazione per UPCOMING |
| `tests/unit/test_justwatch_tv_events.py` | baseline senza eventi, nuovi episodi/stagioni come eventi sulla serie madre, idempotenza, errori TV = warning, cap episodi |
| `tests/unit/test_migration_0005.py` | revisione/chain e aggiunta idempotente della colonna |
| `tests/integration/test_justwatch_api.py` | blocco `justwatch` in `/sources`, campi provider, creazione collezione JustWatch (chart/catalogo, mapping non verificato, kind TMDb-only), policy binding + binding disabilitato, `DRY_RUN_REQUIRED` poi dry-run e run reale, episode-events e 422 su film, `availability_status`/`source_offer_types` negli item |
| `tests/integration/test_justwatch_collections.py` | mapping verificato short+technical, Rakuten saltato, package non verificati, snapshot esistenti intatti |

Suite backend: **315 test verdi** (`cd backend && REDIS_URL="" APP_ENV=test uv run pytest`),
`ruff check` e `ruff format --check` puliti. Frontend: **93 test Vitest** e **10 E2E
Playwright** verdi; typecheck, build e lint puliti. Stato completo in
[`STATUS.md`](STATUS.md).


---

## Fonte: `phase-08.md`

# Fase 8 — JustWatch pubblico: stato

**Data:** 2026-11-18
**Stato:** completata e verificata live su server Ubuntu; immagine GHCR e compose a 4 servizi.

---

## 1. Risultato

La Fase 8 estende la fonte `justwatch` già attiva con:

- catalogo, novità, in arrivo e classifiche separate;
- filtro `FLATRATE` di default e post-filter su media type, package e offerta;
- mapping provider verificati con `shortName` + `technicalName`;
- cache GraphQL con TTL e statistiche hit/miss;
- snapshot `INCOMPLETE` su 429, timeout, errori parziali o schema drift;
- stato `UPCOMING` distinto dal catalogo corrente;
- timeline stagioni/episodi sulla serie madre;
- collezioni JustWatch creabili da UI e API;
- binding JustWatch disabilitato di default, con policy esplicita e dry-run obbligatorio;
- UI dedicata in Provider, Impostazioni → Connettori, Collezioni, Builder e Dettaglio.

Nessuna sync MDBList è stata eseguita per le nuove collezioni JustWatch.

---

## 2. Provider verificati

Verifica live: `packages(country: IT, platform: WEB)` → **109 package**.
Mapping confermati solo con `shortName` **e** `technicalName`:

| Canonico | shortName | technicalName | Offerte |
|---|---|---|---|
| Netflix | `nfx` | `netflix` | FLATRATE |
| Prime Video | `prv` | `amazonprimevideo` | FLATRATE, FREE |
| Disney+ | `dnp` | `disneyplus` | FLATRATE |
| Apple TV+ | `atp` | `appletvplus` | FLATRATE, FREE |
| NOW | `ntv` | `nowtv` | FLATRATE, FREE |
| Paramount+ | `pmp` | `paramountplus` | FLATRATE, FREE |
| RaiPlay | `rai` | `raiplay` | ADS, FLATRATE, FREE |
| Mediaset Infinity | `msp` | `mediasetplay` | ADS, FLATRATE, FREE |
| Infinity+ | `inf` | `infinity` | FLATRATE |
| Timvision | `tvi` | `timvision` | BUY, FLATRATE, RENT |
| Rakuten TV | `wki` | `wuaki` | ADS, BUY, RENT |
| MUBI | `mbi` | `mubi` | FLATRATE |

Rakuten TV è mappato ma **senza FLATRATE**: viene saltato nella creazione
collezioni e riportato esplicitamente.

Il comando `justwatch-collections` crea **88 collezioni** (11 provider flatrate ×
4 tipologie × 2 media type). L'upsert non tocca snapshot né
`last_valid_snapshot_id`.

---

## 3. Verifica live su DB temporaneo

Eseguita su SQLite temporaneo, senza dati o liste di produzione:

| Controllo | Esito |
|---|---|
| `seed-providers` | 12 provider, 4 fonti, 12 mapping TMDb |
| `justwatch-collections` | 12 mapping verificati, 88 collezioni, `wki` saltato |
| Apple TV+ Film catalogo | `COMPLETE` / `CLEAN`, **116** titoli, 0 unresolved, 2 pagine |
| Preview source-only Apple TV+ | **READY**, `to_add=116`, `to_remove=0` |
| Apple TV+ Film in arrivo | `COMPLETE` / `CLEAN`, **3** titoli, `availability_status=UPCOMING` |

Nessuna scrittura MDBList.

---

## 3-bis. Verifica live di produzione (2026-11-18)

- Immagine: `ghcr.io/dexxtex/mdbup:latest`, digest
  `sha256:14e44d3289b26e92554645fa11a95a830bd4feca92716a8b5d63d1efff651e69`.
- Stack: `api`, `worker`, `postgres`, `redis` tutti **healthy**; migrazione
  `0005_snapshot_item_availability`.
- Porte: API `0.0.0.0:28080`; PostgreSQL `127.0.0.1:5432`; Redis `127.0.0.1:6379`.
- `justwatch-collections`: **87 create + 1 aggiornata = 88**; Rakuten TV saltato.
- `netflix-movie-justwatch`: snapshot valido **5.525** titoli, nome aggiornato a
  “Netflix — Film — Catalogo JustWatch”; nessuno snapshot modificato.
- Apple TV+ Film catalogo: **116** titoli, 2 pagine, `COMPLETE/CLEAN`, valido.
- Apple TV+ Film classifica: **105** titoli, 2 pagine, `COMPLETE/CLEAN`, valido.
- Apple TV+ Film in arrivo: **3** titoli, `COMPLETE/CLEAN`, valido, tutti
  `availability_status=UPCOMING`.
- Preview source-only Apple TV+ catalogo: **READY**, `to_add=116`, `to_remove=0`.
- `source_label`: `Fonte: JustWatch (Aggregatore)` per il catalogo,
  `Classifica JustWatch` per la chart.
- `/api/collections/{id}/episode-events` su una collezione film risponde 422
  `COLLECTION_NOT_SHOW`.
- Backup pre-deploy: `mdbup-20261118T102720Z.dump.age` (6.9 MB), checksum e
  decifratura verificati.
- **6 liste MDBList invariate**: 755, 428, 365, 226, 146, 114.
- Nessun binding JustWatch creato; nessuna sync MDBList.

---

## 4. Test

| Suite | Esito |
|---|---|
| Backend `pytest` | **315 passed** |
| Backend `ruff check` / `format --check` | puliti |
| Frontend `npm run typecheck` / `build` / `lint` | verdi |
| Frontend Vitest | **93 passed** |
| Playwright E2E | **10 passed** |

Copertura E2E JustWatch: creazione collezione CATALOG, filtro provider verificato,
payload `source_key=justwatch`/`offer_types=[FLATRATE]`, badge di origine,
preview source-only READY, classifica JustWatch, eventi stagione/episodio e
stato di disponibilità.

---

## 5. Limiti noti

- `newTitles(pageType: NEW)` ignora `objectTypes` e in Italia restituisce solo
  film: una collezione **serie TV — Novità** può essere vuota e quindi invalida.
  Non viene inventato alcun show.
- Le date di aggiunta non sono pubblicate: `date_basis=UNKNOWN`; la UI mostra
  “Date non disponibili dalla fonte”.
- La classifica è la classifica streaming JustWatch (rank globali), mai una
  “Top 10 ufficiale” del provider.
- La timeline TV usa il catalogo SHOW già acquisito, con cap per run; la fonte
  non espone il numero di stagione sul nodo stagione.
- L'endpoint pubblico ha ToS che vietano lo scraping: throttle 1 req/s, nessun
  proxy rotante, stop su 401/403.

---

## 6. Liste MDBList di produzione

Le **6 liste** non vengono lette né scritte dalle nuove collezioni JustWatch:

| Lista | Elementi |
|---|---:|
| Netflix IT — Film Azione | 755 |
| Netflix IT — Film Avventura | 428 |
| Netflix IT — Film Horror | 365 |
| Apple TV+ IT — Serie TV | 226 |
| Mediaset Infinity IT — Film | 146 |
| Disney+ IT — Animazione Top | 114 |

Backup pre-deploy: `mdbup-20261118T102720Z.dump.age` (6.9 MB), checksum e
decifratura verificati. Le porte PostgreSQL/Redis sono pubblicate solo su
`127.0.0.1`; l’API su `28080`.
