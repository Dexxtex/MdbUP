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
