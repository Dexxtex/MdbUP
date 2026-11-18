# Fase 01 — Fondamenta, fonti e architettura

> Report consolidato della fase. Le fonti originali sono state unite in questo documento.


---

## Fonte: `phase-01.md`

# Fase 1 — Sintesi esecutiva

**Data:** 2026-11-17
**Esito:** Fase 1 completata (verifica fonti + progettazione). **Nessun connettore reale è stato implementato o dichiarato funzionante.** Il progetto non è ancora eseguibile end-to-end: la Fase 2 (fondamenta) e la Fase 3 (prima integrazione reale) sono da avviare.

---

## 1. Cosa abbiamo verificato davvero

| Fonte | Esito | Conseguenza |
|---|---|---|
| **MDBList** | API documentata e utilizzabile con API key. Creazione liste, lettura a cursore, add/remove, reorder (max 1.000 per chiamata), rate limit 1.000 read/300 write per 5 min. | È la **destinazione** del progetto. Serve una API key e una lista di test. |
| **TMDb** | API ufficiale, disponibilità corrente per l'Italia, cinque tipi di offerta. **Nessuna data di aggiunta**, discover limitato a 500 pagine. Dati watch provider forniti da JustWatch. | È la **prima fonte reale** per la Fase 3, etichettata `AGGREGATOR`. Non può alimentare "Aggiunte recenti" con date dichiarate. |
| **JustWatch Partner API / Data Export** | Documentazione pubblica completa; accesso solo con contratto, token e credenziali S3. `date_created` = prima osservazione JustWatch. | **BLOCCATO.** È la fonte corretta per date di aggiunta reali e catalogo completo, ma serve un contratto. |
| **JustWatch sito pubblico / GraphQL** | GraphQL non documentato; ToS §7.1 vieta scraping/data mining. | **ESCLUSO.** Nessun connettore, nessun fallback. |
| **Movieplayer / ComingSoon** | Editoriali, senza API pubblica; robots/ToS contrari; cataloghi parziali. | **NON IDONEI** come connettori. Solo link-out manuale. |
| **PlayPilot** | 403 anti-bot, nessuna API pubblica documentata. | **ESCLUSO.** |
| **Top 10 ufficiale provider** | Nessuna API ufficiale verificata. | **NON IMPLEMENTARE** finché non esiste una fonte ufficiale verificata e un uso consentito. |

---

## 2. Le tre etichette che non si possono confondere

| Origine | Significato | Esempio |
|---|---|---|
| `OFFICIAL` | Categoria pubblicata ufficialmente dal provider. | "Netflix IT — Top 10 ufficiale" **solo** con fonte ufficiale verificata. |
| `AGGREGATOR` | Raccolta costruita da un aggregatore (JustWatch, TMDb). | "Netflix IT — Disponibilità corrente — Fonte TMDb/JustWatch". |
| `CUSTOM` | Filtro o derivazione dell'app. | "Netflix IT — Thriller — Filtro personalizzato"; "Aggiunte recenti rilevate dall'app". |

A queste si aggiunge `date_basis`:

| `date_basis` | Significato | Disponibilità |
|---|---|---|
| `PROVIDER_OFFICIAL` | Data dichiarata ufficialmente dal provider. | Nessuna fonte verificata. |
| `AGGREGATOR_FIRST_SEEN` | Prima osservazione dell'aggregatore (JustWatch `date_created`). | Solo con contratto JustWatch. |
| `APP_FIRST_SEEN` | Prima osservazione della nostra app (`first_seen_at`). | Disponibile con TMDb, ma è una derivazione `CUSTOM`. |
| `UNKNOWN` | Nessuna data. | TMDb current availability. |

**Regola:** l'UI mostra sempre origine e `date_basis`. Non si sostituisce silenziosamente una fonte con un'altra.

---

## 3. Decisioni architetturali chiave

1. **Monolite modulare** con processi separati `web`, `api`, `worker`, `scheduler`, più `postgres`, `redis`, `migrate`.
2. **PostgreSQL fonte di verità**; Redis solo broker/cache.
3. **Snapshot immutabili** con flag di completezza; solo snapshot validi alimentano le sync.
4. **Connettori con capability flags**: ogni fonte dichiara cosa supporta davvero.
5. **Operation ledger** per MDBList: nessuna transazione distribuita; riconciliazione dopo timeout.
6. **Lock per target** (advisory lock PostgreSQL + unique partial index) per impedire sync concorrenti.
7. **Soglie di sicurezza** assolute e percentuali; blocco su snapshot incompleto o vuoto; revisione manuale.
8. **Segreti cifrati a riposo** con AES-256-GCM e chiave esterna al DB.
9. **Frontend SPA** con client generato da OpenAPI; nessun segreto nel browser.
10. **MDBList ID numerico** come chiave stabile; slug/URL solo display.

---

## 4. Cosa è pronto e cosa manca

| Area | Stato |
|---|---|
| Matrice fonti e capacità | ✅ Documentata con evidenze |
| Verifica MDBList | ✅ Endpoint, limiti, payload, rischi |
| Architettura e struttura repo | ✅ Documentata |
| Modello dati e schema | ✅ Documentato (DDL in `schema.sql`) |
| Motore di sync e sicurezza | ✅ Progettato |
| Frontend e contratto API | ✅ Progettato |
| Docker Compose, migrazioni, auth | ⏳ Fase 2 |
| Connettore TMDb reale | ⏳ Fase 3 (serve API key) |
| Connettore MDBList reale | ⏳ Fase 3 (serve API key) |
| Connettore JustWatch | ⛔ Bloccato da contratto |
| "Aggiunte recenti" con data JustWatch | ⛔ Bloccato da contratto |
| "Top 10 ufficiale" | ⛔ Nessuna fonte ufficiale verificata |

---

## 5. Cosa serve per proseguire

### Per la Fase 2 (fondamenta eseguibili)
Nessuna credenziale esterna. Servono solo:
- decisione sul dominio/TLS e sull'email del primo admin;
- conferma della policy di backup e custodia di `APP_ENCRYPTION_KEY`.

### Per la Fase 3 (prima integrazione reale)
1. **TMDb API key** (read access token).
2. **MDBList API key** e piano (free/supporter).
3. **Lista MDBList di test** dedicata (non una lista personale).
4. **Decisione su JustWatch:** contratto Partner + credenziali S3, oppure accettare che la Fase 3 mostri "disponibilità corrente" e non "aggiunte recenti".
5. **Conferma legale** su uso non commerciale TMDb e attribuzione JustWatch.

### Per la Fase 4-5
- Contratto JustWatch (se si vogliono date reali e catalogo completo).
- Eventuale fonte ufficiale per Top 10 (solo se verificata e consentita).
- Più provider/collezioni e feedback sull'UI.

---

## 6. Rischi principali

| Rischio | Impatto | Mitigazione |
|---|---|---|
| JustWatch non ottenibile | Nessuna data di aggiunta reale | TMDb current availability + etichetta `CUSTOM`/`APP_FIRST_SEEN`; connettore disabilitato |
| TMDb discover limitato a 500 pagine | Catalogo parziale | Partizionamento per anno/genere; snapshot incompleto = nessuna rimozione |
| MDBList 300 scritture/5 min | Sync lente o bloccate | Batch, token bucket, ripresa, `Retry-After` |
| Timeout MDBList con esito incerto | Doppie aggiunte/rimozioni | `UNCERTAIN` + rilettura remota prima del retry |
| Snapshot anomalo | Rimozioni massive | Soglie, revisione manuale, blocco su snapshot invalido/vuoto |
| Perdita chiave di cifratura | Credenziali irrecuperabili | Backup separato della chiave, procedura documentata |
| Violazione ToS | Blocco/legale | Solo endpoint documentati; niente scraping; attribuzione |

---

## 7. Prossimo passo consigliato

1. Approvare la matrice fonti e le decisioni di Fase 1.
2. Fornire TMDb API key e MDBList API key (e la lista di test).
3. Avviare la **Fase 2**: Docker Compose, PostgreSQL, Alembic, auth, healthcheck, frontend shell, CI.
4. Solo dopo, avviare la **Fase 3** con TMDb + MDBList su una lista di test, senza dichiarare "aggiunte recenti" finché non c'è JustWatch.

**Nota:** la Fase 1 non contiene codice di produzione né connettori reali. Questo è intenzionale: il vincolo del progetto è non dichiarare funzionante ciò che non è stato verificato con accessi reali.


---

## Fonte: `phase-01.md`

# Fase 1 — Matrice delle fonti e capacità effettive

**Data di riferimento delle verifiche:** 2026-11-17
**Stato:** Fase 1 completata — nessun connettore reale implementato in questa fase.

Questo documento risponde a una domanda sola: **quali dati possiamo acquisire davvero, con quale accesso, con quali limiti e con quale etichetta di provenienza**. Non è una lista di desiderata. Ogni affermazione importante è etichettata:

| Etichetta | Significato |
|---|---|
| **VERIFICATO** | Letto su documentazione ufficiale o su specifica OpenAPI pubblica. |
| **OSSERVATO** | Osservato su sito pubblico, senza scraping massivo e senza aggirare blocchi. |
| **NON VERIFICATO** | Nessuna fonte sufficiente; non usare come base implementativa. |
| **BLOCCATO** | Richiede contratto, credenziali o autorizzazione non disponibili. |

---

## 1. Sintesi esecutiva

1. **MDBList è l'unica destinazione verificata e utilizzabile subito**, una volta fornita una API key. L'API consente di creare una lista statica, leggerne gli elementi con paginazione a cursore, aggiungere e rimuovere film/serie (e, se serve, stagioni/episodi) tramite ID TMDb/IMDb, e riordinare gli elementi con `POST /lists/{listid}/items/reorder` (max 1.000 elementi per chiamata, ordine custom `usort`).
2. **TMDb è la fonte di metadati e disponibilità corrente**, con una API key gratuita per uso non commerciale. I dati watch provider sono **forniti da JustWatch** e richiedono attribuzione a JustWatch. TMDb espone la **disponibilità corrente**, non la data di aggiunta al provider.
3. **JustWatch Partner API e data export sono la fonte corretta per date di aggiunta e cataloghi completi**, ma sono **BLOCCATI da un contratto commerciale** e da token/S3 credentials. La documentazione è pubblica; l'accesso no.
4. **L'endpoint GraphQL pubblico di JustWatch è implementato come fonte `AGGREGATOR`** (Fase 8): catalogo per provider, novità, in arrivo, classifiche con rank, stagioni ed episodi, con ID TMDb/IMDb. Non è documentato e non fornisce date di aggiunta; il client applica un throttle locale obbligatorio. La Partner API resta l'unica via per `date_created` ed è bloccata da contratto.
5. **Movieplayer, ComingSoon e PlayPilot non sono fonti di catalogo integrabili**: sono editoriali/aggregatori, senza API pubblica documentata, con robots/ToS contrari o accesso bloccato (403).
6. **Nessuna fonte pubblica verificata fornisce una categoria ufficiale "Top 10" dei provider** (es. Netflix) tramite API. Una lista "Top 10 ufficiale" non va creata finché non esiste una fonte ufficiale verificata e un uso consentito.
7. **"Aggiunte recenti" ha tre significati diversi** e il database/UI devono tenerli separati:
   - data ufficiale dichiarata dal provider: **nessuna fonte verificata**;
   - prima osservazione di un aggregatore: JustWatch `date_created` (**BLOCCATO** senza contratto);
   - prima osservazione della nostra app: `first_seen_at` (**disponibile**, ma è una derivazione `CUSTOM`, non una categoria ufficiale).

---

## 2. Matrice comparativa

| Fonte | Tipo | Dati realmente disponibili | Copertura IT | Accesso | Credenziali | Data di aggiunta | Stagioni / episodi | Paginazione | ToS / attribuzione | Stato | Uso previsto |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **MDBList** | Destinazione (liste statiche) | Liste, elementi, aggiunta/rimozione per TMDb/IMDb, stagioni/episodi, riordino, modifiche | Globale | REST `https://api.mdblist.com` | API key (free) o OAuth | n/a | Film e serie come entità separate; stagioni/episodi supportati dal payload | `cursor`/`next_cursor` (preferito), `limit` max 1000; `offset` deprecato; header `X-Has-More` | Documentazione API; nessun obbligo di attribuzione paragonabile a JustWatch | **VERIFICATO** | Destinazione delle sync |
| **TMDb** | Aggregatore (watch provider powered by JustWatch) | Disponibilità corrente per paese/provider, tipi offerta, metadati, ID esterni | `IT` | REST `https://api.themoviedb.org/3` | API key / Bearer (free non commerciale) | **No** | Metadati serie/stagioni; disponibilità a livello di serie, non di episodio | 20 per pagina; discover max 500 pagine | Attribuzione TMDb + **JustWatch** per i watch provider | **VERIFICATO** | Metadati, ID, disponibilità corrente |
| **JustWatch Partner API** | Aggregatore commerciale | Offerte, provider, `date_created`, `available_to`, upcoming, top X, streaming charts, stagioni/episodi | `it_IT` | REST `https://apis.justwatch.com/contentpartner/v2/content` | Contratto + partner token | **Sì, `date_created` = prima osservazione JustWatch** | Sì, route stagioni con offerte per episodio | `page`/`page_size`; top X max 20; upcoming max 25 | Branded link JustWatch obbligatori; contratto e riservatezza | **BLOCCATO** | Fonte primaria solo con contratto |
| **MDBList JustWatch charts** | Aggregatore (via MDBList) | Streaming chart JustWatch per film/serie, rank 1d/7d/30d | **IT non elencata** negli alias documentati (US, GB/UK, CA, AU, DE) | REST MDBList `/justwatch/streaming-charts/{media_type}` | API key MDBList | n/a | n/a | `x` max 20 | Dati JustWatch via MDBList; verificare attribuzione | **NON UTILIZZABILE PER IT** | Non usare per l'Italia finché non verificato |
| **JustWatch Data Export** | Aggregatore commerciale | NDJSON con tutti i titoli e le offerte, tutti i paesi | `it_IT` incluso | S3 `jw-data-partner-out` | Contratto + AWS Access Key/Secret/directory | Da verificare nello schema del dump; l'API offers espone `date_created` | Da verificare nel dump | File completo (non paginato) | Branded link; contratto | **BLOCCATO** | Refresh giornaliero completo, se contratto |
| **JustWatch sito pubblico / GraphQL** | Aggregatore | Catalogo per provider, novità, in arrivo, in partenza, classifiche con rank/trend, stagioni ed episodi, ID TMDb/IMDb | IT | `POST https://apis.justwatch.com/graphql` | Nessuna | **No** (etichette relative) | Sì, con offerte per episodio | 100/pagina, paginazione completa via partizioni `releaseYear` (tetto 1999 per query) | Attribuzione JustWatch; throttle locale obbligatorio | **IMPLEMENTATO** | Novità, classifiche, disponibilità per provider |
| **Movieplayer** | Editoriale | Cataloghi per piattaforma, offerte, prossime uscite | IT | HTML/RSS; `/api/` disallowed | Nessuna | Solo uscite future | Non esposti | n/d | ToS non reperito; robots restrittivo | **NON IDONEO** | Solo link-out editoriale, mai catalogo |
| **ComingSoon** | Editoriale | Cataloghi parziali per piattaforma | IT | HTML; `/rss/` disallowed | Nessuna | No | Non esposti | n/d | Art. 2.4 vieta diffusione materiali | **NON IDONEO** | Solo link-out editoriale |
| **PlayPilot** | Aggregatore commerciale | Guida where-to-watch, prodotti B2B | IT (sito localizzato) | Sito/portale partner; 403 anti-bot | Presumibilmente contratto | Non verificabile | Non verificabile | n/d | ToS non leggibili (403) | **BLOCCATO / ESCLUSO** | Non usare |
| **Top 10 ufficiale provider** | Ufficiale provider | Classifiche settimanali pubblicate editorialmente | IT | Pagine pubbliche, nessuna API verificata | Nessuna | n/a | n/a | n/d | Da verificare caso per caso | **NON VERIFICATO** | Non implementare finché non verificato |

---

## 3. MDBList — destinazione verificata

### 3.1 Accesso e autenticazione

- Base URL: `https://api.mdblist.com`.
- Autenticazione: API key come parametro `apikey`, oppure OAuth 2.0 Bearer per app di terze parti. La API key si genera dalle preferenze MDBList. **VERIFICATO** (`https://docs.mdblist.com/docs/api`, OpenAPI MDBList).
- Limiti dichiarati: 1.000 richieste/giorno sul piano free; su tutti i piani 1.000 letture e 300 scritture ogni 5 minuti. I limiti sono per account e condivisi tra tutte le API key. Header `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`; su `429` è presente `Retry-After`. **VERIFICATO** (`https://docs.mdblist.com/docs/api`).
- Limite liste statiche: la documentazione Supporter indica 4 liste statiche + 4 dinamiche per il piano free; il vecchio schema OpenAPI mostrava un `403` con `limit: 4`. **VERIFICATO sulla documentazione; da confermare sul proprio account.**

### 3.2 Operazioni verificate

| Operazione | Metodo ed endpoint | Note |
|---|---|---|
| Elenco delle mie liste | `GET /lists/user` | Restituisce `id`, `name`, `slug`, `items`, `likes`, `ranked` (e altri campi secondo il piano). |
| Dettaglio lista | `GET /lists/{listid}` | Include `id`, `name`, `slug`, `mediatype`, `items`, `private`, `user_id`, `user_name`. **Non** espone in modo affidabile `type`/`dynamic`. |
| Elementi della lista | `GET /lists/{listid}/items?cursor=&limit=&sort=rank&order=asc` | Paginazione a cursore: passare `next_cursor` fino ad assenza. `limit` default 100, max 1000; `offset` deprecato. Header `X-Has-More`. `sort` supporta `rank`, `usort`, `added`, `title`, `released`, ecc. |
| Creazione lista statica | `POST /lists/user/add` | Body `{"name": "...", "private": false}` → `200 {"id", "name", "slug"}`; la descrizione promette anche l'URL pubblico, ma lo schema non lo elenca. Costruire l'URL dallo slug e rileggerlo dopo una rinomina. |
| Aggiornamento lista | `PUT /lists/{listid}` | Solo `name` e `private`. **Nessun campo ordine.** |
| Aggiunta/rimozione elementi | `POST /lists/{listid}/items/{action}` con `action=add|remove` | Body `{"movies":[{"tmdb": 630, "imdb": "tt..."}], "shows":[{"tmdb": 1396}], "seasons":[...], "episodes":[...]}`. Risposta con contatori `added`, `removed`, `existing`, `not_found` per tipo. |
| Riordino elementi | `POST /lists/{listid}/items/reorder` | Body `{"items":[{"mediatype":"movie","ids":{"tmdb":603}}], "after"|"before"|"position":"top|bottom"}`. Max 1.000 elementi per chiamata; imposta l'ordine custom (`sort=usort`). Solo liste statiche possedute. |
| Appartenenza a liste statiche | `GET /lists/user/membership?mediatype=movie&tmdb=...` | Restituisce `{"contains":[list_id,...]}`; controlla solo liste statiche. Utile per preflight, non per sincronizzare. |
| Modifiche lista | `GET /lists/{listid}/changes` | La descrizione parla di `added_ids`/`removed_ids`, ma lo schema 200 documenta `{id, movie, updated}`: incongruenza. Usare solo come indizio, non come fonte di verità. |
| Eliminazione lista | `DELETE /lists/{listid}` | **Non usare per aggiornare**: distrugge ID e URL. |

**Identificativi supportati:** `tmdb`, `imdb`, `trakt`, `tvdb`, `mal`, `mdblist`. Per l'aggiunta/rimozione, il body distingue `movies`, `shows`, `seasons`, `episodes`; per i film `tmdb` è richiesto, per le serie è accettato almeno un ID tra `tmdb` e `imdb`; stagioni/episodi usano `tmdb`. **VERIFICATO** (schema live MDBList, `https://api.mdblist.com/schema/?format=json`).

### 3.3 JustWatch streaming charts via MDBList

Il nuovo schema MDBList espone `GET /justwatch/streaming-charts/{media_type}` con rank 1d/7d/30d, provider e genere. È un dato **JustWatch via MDBList**, quindi `AGGREGATOR`. Tuttavia gli alias documentati per `country` sono solo `US`, `GB/UK`, `CA`, `AU`, `DE` e gli esempi di `locale` sono `en_US`, `en_GB`, `en_CA`, `en_AU`, `de_DE`: **l'Italia non è elencata**. Non usare questo endpoint per collezioni italiane finché non viene verificato un locale `it_IT` o un alias `IT`. **NON VERIFICATO per IT.**

### 3.4 Limiti e rischi MDBList

- **Ordine:** il riordino è supportato da `POST /lists/{listid}/items/reorder`, con `sort=usort`. Il limite è **1.000 elementi per chiamata**; per liste più lunghe servono più chiamate con `after`/`before`, e l'operazione **non è atomica**. Non si deve cancellare e ricreare la lista per simulare l'ordine: si perderebbero ID, URL e cronologia. L'ordine è quindi un'operazione opzionale, best-effort e tracciata separatamente.
- **Atomicità:** add, remove e reorder sono chiamate separate; non esiste una transazione unica. Un `200` non prova che ogni elemento sia stato aggiunto: `not_found` e `existing` vanno riconciliati con una lettura successiva.
- **Idempotenza:** non è documentato un header di idempotenza. L'app deve usare una tabella `sync_operations` con chiave locale e riconciliare lo stato remoto dopo timeout.
- **Rate limit:** 1.000 letture e 300 scritture per finestra fissa di 5 minuti (finestre che iniziano a :00, :05, :10…), su ogni piano; limite giornaliero per piano (1.000 free). Una lista grande richiede batch, throttle e ripresa.
- **Liste statiche:** una lista ha un solo `mediatype` (movie/show/season/episode). Film e serie devono andare su due liste distinte, oppure su due binding distinti. Il limite free è di 4 liste statiche; max 10.000 elementi per lista free.
- **Tipo lista:** `GET /lists/{listid}` non espone in modo affidabile `type`/`dynamic`; il preflight deve verificare proprietà (`user_id`/`user_name`) e leggere la lista, e l'UI deve chiedere conferma esplicita che sia una lista statica. Un `403` su add/remove/reorder è un blocco, non un retry.
- **Piano:** il limite di 4 liste statiche free può essere insufficiente; valutare un piano supporter.

---

## 4. TMDb — fonte di disponibilità corrente

### 4.1 Accesso

- Base URL: `https://api.themoviedb.org/3`.
- Autenticazione: Bearer token (v4 read access token) o `api_key` (v3). **VERIFICATO** (schema OpenAPI TMDb).
- Rate limit: i vecchi 40 richieste/10 secondi sono disabilitati; restano limiti nell'ordine di **40 richieste/secondo**, con obbligo di rispettare `429`. **VERIFICATO** (`https://developer.themoviedb.org/docs/rate-limiting`).
- Uso: gratuito per uso non commerciale; uso commerciale richiede accordo scritto. **VERIFICATO** dalla FAQ TMDb (fonte secondaria ufficiale).

### 4.2 Endpoint utili

| Operazione | Endpoint |
|---|---|
| Provider disponibili per film in Italia | `GET /watch/providers/movie?watch_region=IT&language=it-IT` |
| Provider disponibili per serie in Italia | `GET /watch/providers/tv?watch_region=IT&language=it-IT` |
| Disponibilità di un film | `GET /movie/{movie_id}/watch/providers` |
| Disponibilità di una serie | `GET /tv/{series_id}/watch/providers` |
| Scoperta film per provider/offerta | `GET /discover/movie?watch_region=IT&with_watch_providers=8&with_watch_monetization_types=flatrate&page=1` |
| Scoperta serie per provider/offerta | `GET /discover/tv?watch_region=IT&with_watch_providers=8&with_watch_monetization_types=flatrate&page=1` |
| ID esterni | `GET /movie/{id}/external_ids`, `GET /tv/{id}/external_ids` |

**Tipi di offerta:** `flatrate`, `rent`, `buy`, `ads`, `free`. **VERIFICATO** (schema watch providers e parametro `with_watch_monetization_types`).

### 4.3 Limiti critici TMDb

- **Nessuna data di aggiunta al provider.** La risposta watch providers contiene solo lo stato corrente e il link TMDB. Non esiste un campo `date_created`/`added_at`. Quindi TMDb **non può** alimentare una collezione "Aggiunte recenti" con date dichiarate dalla fonte.
- **Discover è limitato a 500 pagine** (20 elementi per pagina, massimo 10.000 risultati). Per cataloghi più grandi bisogna partizionare le query (anno, genere, provider) e verificare che ogni partizione sia completa. **VERIFICATO** (TMDb Talk).
- **Disponibilità a livello di serie, non di episodio.** Le stagioni/episodi sono metadati, non offerte per episodio.
- **Attribuzione JustWatch obbligatoria** per i dati watch provider: "In order to use this data you must attribute the source of the data as JustWatch." **VERIFICATO** (`https://developer.themoviedb.org/reference/movie-watch-providers`).
- **Dati aggregati, non ufficiali del provider.** Una lista costruita da TMDb è `AGGREGATOR`, mai `OFFICIAL`.

---

## 5. JustWatch — fonte corretta per le date, ma bloccata

### 5.1 Cosa è verificato

- **Partner API:** root `https://apis.justwatch.com/contentpartner/v2/content`, token come query parameter, assegnato dopo contratto. **VERIFICATO** (`https://apis.justwatch.com/docs/api`).
- **Locale Italia:** `it_IT` è elencata ufficialmente. **VERIFICATO**.
- **Offerte:** `monetization_type` (`flatrate`, `rent`, `buy`, `ads`, `free`, `none`), `presentation_type` (`sd`, `hd`, `4k`, ...), `provider_id`, `retail_price`, `currency`, `urls.standard_web`. **VERIFICATO**.
- **Date:** il campo `offers[].date_created` è documentato come **"The date this offer was first seen by JustWatch"**. È quindi una **prima osservazione dell'aggregatore**, non una data ufficiale del provider. Esiste anche `available_to` (data di fine disponibilità, se nota). **VERIFICATO** (OpenAPI `jw-partner-api.yaml`, schema `offers.Offer`).
- **Stagioni/episodi:** le route `/v2/content/offers/object_type/show/.../season_number/{season_number}/...` popolano `episodes` con `episode_offers`. **VERIFICATO** (OpenAPI).
- **Prossime uscite:** route `/v2/content/titles/upcoming/...`, max 25 titoli per richiesta, con `start_timestamp`/`end_timestamp`. **VERIFICATO** (OpenAPI).
- **Classifiche:** `/v2/content/titles/top_x/...` con `x` massimo 20, finestra `rank=1|7|30`; streaming chart per singolo titolo. **VERIFICATO** (OpenAPI).
- **Data export:** NDJSON su S3 `jw-data-partner-out`, una riga per titolo con le offerte in tutti i paesi; credenziali fornite da JustWatch; aggiornamento giornaliero. **VERIFICATO** (`https://apis.justwatch.com/docs/data_export`).
- **Attribuzione:** link brandizzati JustWatch accanto a ogni widget/"where to watch"; per le classifiche, link su ogni rank. **VERIFICATO**.

### 5.2 Cosa non è verificato

- Rate limit, SLA, prezzi e condizioni contrattuali dettagliate: **BLOCCATI**.
- Schema esatto del file NDJSON: la documentazione dice "titoli con offerte", ma non mostra un sample. Il campo `date_created` è verificato nell'API offers; la sua presenza nel dump va verificata sul file reale. **NON VERIFICATO**.
- Paginazione completa delle route di ricerca titoli: l'OpenAPI espone `page`/`page_size`, ma non è documentato un limite massimo. **NON VERIFICATO**.
- Presenza di un endpoint "tutte le aggiunte recenti per provider": **non verificato**. La route `titles` è una ricerca per query/anno, non un catalogo completo; il dump è il canale raccomandato per il refresh completo.

### 5.3 Perché il sito pubblico non è una fonte ammissibile

- Il frontend usa `https://apis.justwatch.com/graphql`, **non documentato**. **OSSERVATO** (progetti terzi).
- I Termini di servizio (§7.1) vietano scraping, data mining, robot e aggiramento dei blocchi IP. **VERIFICATO** (`https://support.justwatch.com/article/just-watchs-terms-of-use`).
- Il `robots.txt` è permissivo, ma non autorizza violazioni contrattuali. **VERIFICATO**.
- Conseguenza: **nessun connettore basato su GraphQL o scraping**. Il connettore JustWatch resta `DISABLED`/`UNCONFIGURED` finché non arriva un contratto.

---

## 6. Fonti alternative — esito

### Movieplayer
- Cataloghi per piattaforma, offerte (abbonamento/noleggio/acquisto), deep link, prossime uscite con data. **OSSERVATO**.
- Nessuna API pubblica; `robots.txt` disalloca `/api/` e i parametri di filtro. RSS solo news editoriali. **VERIFICATO**.
- ToS generale non reperito; privacy senza clausole di riuso. **NON VERIFICATO**.
- **Verdetto:** non integrare come connettore. Solo link-out editoriale.

### ComingSoon
- Cataloghi parziali per piattaforma (es. Netflix: 1.597 film, 394 serie). **OSSERVATO**.
- Nessuna API; `robots.txt` disalloca `/rss/`. **VERIFICATO**.
- ToS art. 2.4 vieta distribuzione/diffusione dei materiali. **VERIFICATO**.
- **Verdetto:** non integrare.

### PlayPilot
- Sito italiano localizzato, ma pagine e ToS restituiscono 403 al fetcher; portale partner con login. **BLOCCATO**.
- Nessuna API pubblica documentata. **NON VERIFICATO**.
- **Verdetto:** escludere.

### Top 10 ufficiale dei provider
- Netflix pubblica classifiche ufficiali tramite Tudum, ma non è stata verificata una API pubblica né un'autorizzazione all'estrazione automatica. **NON VERIFICATO**.
- **Verdetto:** non creare una collezione `OFFICIAL` "Top 10" finché non esiste una fonte ufficiale verificata e un uso consentito. In alternativa, supportare un import manuale CSV dichiarato `OFFICIAL` con URL della fonte, in Fase 5.

---

## 7. Decisioni di Fase 1

| Decisione | Motivazione |
|---|---|
| **MDBList è la destinazione unica** | API verificata, supporta liste statiche e ID TMDb/IMDb, consente add/remove in place. |
| **TMDb è la prima fonte reale (Fase 3)** | Unica fonte con accesso self-service, copertura IT e disponibilità corrente. Etichetta `AGGREGATOR`. |
| **JustWatch resta disabilitato** | Partner API/export richiedono contratto; il sito pubblico è vietato dai ToS. |
| **Nessun connettore mock in produzione** | I test useranno fixture sintetiche e mock HTTP, ma il codice di produzione avrà solo connettori reali o `DISABLED`. |
| **"Aggiunte recenti" solo con date basis esplicita** | `AGGREGATOR_FIRST_SEEN` (JustWatch, bloccato) oppure `APP_FIRST_SEEN` (derivato, `CUSTOM`). Mai spacciato per data ufficiale. |
| **Nessuna lista "Top 10 ufficiale" senza fonte verificata** | Rispetta il vincolo di non inventare categorie ufficiali. |
| **Film e serie separati** | MDBList ha liste a mediatype singolo; TMDb usa endpoint e ID distinti. |
| **Solo flatrate per le liste di abbonamento** | Evita di mescolare noleggio/acquisto/canali; configurabile per collezione. |

---

## 8. Blocchi da sbloccare prima della Fase 3

1. **TMDb API key** (read access token) — necessaria per la prima acquisizione reale.
2. **MDBList API key** — necessaria per creare/leggere/aggiornare la lista di test. Indicare il piano (free/supporter) per verificare limite liste e rate.
3. **Lista MDBList di test** — meglio una lista dedicata, non una lista personale già usata.
4. **Decisione su JustWatch:** se servono date di aggiunta reali e catalogo completo, serve un contratto Partner + credenziali S3. Senza contratto, la Fase 3 userà TMDb e dichiarerà "disponibilità corrente", non "aggiunte recenti".
5. **Dominio/TLS** per il deploy e **email** del primo admin.
6. **Chiave di cifratura** (`APP_ENCRYPTION_KEY`) e politica di backup: se si perde, le credenziali salvate non sono recuperabili.
7. **Conferma legale** sull'uso personale/non commerciale di TMDb e sull'attribuzione JustWatch.

---

## 9. Attribuzione e condizioni d'uso

- **TMDb:** mostrare "This product uses the TMDB API but is not endorsed or certified by TMDB" e attribuire **JustWatch** per i dati watch provider, con link alla pagina TMDB/JustWatch del titolo. Non ridistribuire i dati come se fossero ufficiali del provider.
- **JustWatch (se contrattualizzato):** link brandizzati a `full_path` su ogni titolo/offerta; per le classifiche, link sul rank; rispettare la riservatezza dei dati Partner.
- **MDBList:** usare l'API secondo i limiti del piano; non aggirare rate limit; non creare liste duplicate per simulare l'ordine.
- **Movieplayer/ComingSoon/PlayPilot:** nessun uso automatizzato; solo link-out manuale, se consentito.

---

## 10. Fonti consultate

### JustWatch
- Intro: https://apis.justwatch.com/docs
- Content Partner: https://apis.justwatch.com/docs/content_partner
- API: https://apis.justwatch.com/docs/api
- Data export: https://apis.justwatch.com/docs/data_export
- OpenAPI: https://apis.justwatch.com/docs/static/jw-partner-api.yaml
- API Reference: https://apis.justwatch.com/docs/api/reference
- Termini di servizio: https://support.justwatch.com/article/just-watchs-terms-of-use
- Portale partner: https://partners.justwatch.com/
- robots.txt: https://www.justwatch.com/robots.txt

### MDBList
- Documentazione API: https://docs.mdblist.com/docs/api
- API docs: https://api.mdblist.com/docs
- Schema OpenAPI live: https://api.mdblist.com/schema/?format=json
- Autenticazione: https://api.mdblist.com/docs/authentication/
- Tipi di lista: https://docs.mdblist.com/docs/list_types
- Limiti e piani: https://docs.mdblist.com/docs/api, https://docs.mdblist.com/docs/supporter

### TMDb
- Watch providers film: https://developer.themoviedb.org/reference/movie-watch-providers
- Watch provider list film: https://developer.themoviedb.org/reference/watch-providers-movie-list
- Watch provider list serie: https://developer.themoviedb.org/reference/watch-provider-tv-list
- Discover film: https://developer.themoviedb.org/reference/discover-movie
- Discover serie: https://developer.themoviedb.org/reference/discover-tv
- Rate limit: https://developer.themoviedb.org/docs/rate-limiting
- Limite 500 pagine: https://www.themoviedb.org/talk/655749887f054018d6f30816

### Fonti alternative
- Movieplayer streaming: https://movieplayer.it/streaming/
- Movieplayer robots: https://movieplayer.it/robots.txt
- ComingSoon streaming: https://www.comingsoon.it/streaming/
- ComingSoon ToS: https://www.comingsoon.it/policy/terminiduso.html
- ComingSoon robots: https://www.comingsoon.it/robots.txt
- PlayPilot: https://www.playpilot.com/it/ (403 al fetcher)
- PlayPilot partner: https://partner.playpilot.net/login

---

## 11. Cosa non fare

- Non usare il GraphQL JustWatch come fallback "temporaneo".
- Non dedurre "audio italiano" dalla disponibilità in Italia.
- Non dedurre "data di aggiunta" dalla data di uscita del titolo o dalla prima osservazione dell'app senza etichettarla.
- Non includere rent/buy/ads in una lista di abbonamento senza dichiararlo.
- Non cancellare e ricreare una lista MDBList per aggiornarla o riordinarla.
- Non dichiarare completo uno snapshot solo perché l'HTTP status è 200.
- Non dichiarare "Top 10 ufficiale" senza fonte ufficiale verificata.


---

## Fonte: `phase-01.md`

# Fase 1 — Verifica API MDBList

**Data di accesso:** 2026-11-17
**Fonte primaria:** schema OpenAPI live `https://api.mdblist.com/schema/?format=json` (OpenAPI 3.0.3, `info.title: "MDBList API"`, `info.version: "1.0.0"`).
**Fonti di supporto:** `https://docs.mdblist.com/docs/api`, `https://docs.mdblist.com/docs/supporter`, `https://api.mdblist.com/docs/authentication/`, `https://docs.mdblist.com/docs/list_types`.

> **Nota di verifica.** Un vecchio snapshot OpenAPI pubblico (repository GitHub `linaspurinis/api.mdblist.com`) non conteneva l'endpoint di riordino e documentava `offset` come paginazione principale. Lo schema live è più recente e include `POST /lists/{listid}/items/reorder` e la paginazione a cursore. In caso di conflitto, **prevale lo schema live**. Il progetto deve congelare uno snapshot datato dello schema con hash SHA-256 e usarlo nei contract test.

---

## 1. Sintesi operativa

MDBList è una **destinazione** adatta al progetto:

- crea una lista statica e restituisce un **ID numerico stabile**;
- legge gli elementi con **paginazione a cursore**;
- aggiunge e rimuove film, serie, stagioni ed episodi tramite ID TMDb/IMDb/Trakt/TVDb/MDBList;
- supporta il **riordino** tramite `POST /lists/{listid}/items/reorder` (max 1.000 elementi per chiamata, ordine custom `usort`);
- non espone un header di idempotenza, non offre transazioni atomiche e non garantisce la stabilità dello slug/URL dopo una rinomina.

Il progetto deve quindi usare l'ID numerico come chiave, tracciare ogni operazione in locale e riconciliare lo stato remoto dopo ogni timeout.

---

## 2. Autenticazione

| Metodo | Uso | Note |
|---|---|---|
| API key | `?apikey=<key>` su ogni richiesta | Generata da `https://mdblist.com/preferences/#api`. Semplice, adatta a un'app self-hosted. |
| OAuth 2.0 Bearer | `Authorization: Bearer <token>` | Flusso PKCE/Device Code; token con scadenza 30 giorni e refresh token. Utile solo se si vuole un'app multi-utente. |

- Esiste **un solo scope, `write`**, che dà accesso completo a profilo, liste, watchlist, rating, collection e playback. **Non esiste uno scope read-only.**
- La API key è quindi necessariamente read-write: va trattata come un segreto critico.
- Gli endpoint OAuth richiedono lo slash finale (es. `/oauth/token/`).

**Implicazione di sicurezza:** la API key MDBList non va mai esposta al browser, né inclusa in export, log o messaggi di errore. Va cifrata a riposo con la stessa chiave delle altre credenziali.

---

## 3. Limiti

### 3.1 Rate limit

- **1.000 letture** e **300 scritture** per finestra fissa di **5 minuti**, su ogni piano. Le finestre iniziano a `:00`, `:05`, `:10`, … e non sono rolling.
- I `GET` contano come letture; gli altri metodi contano come scritture, salvo alcuni POST batch-lookup che contano come letture.
- Limite giornaliero per piano, reset alle **00:00 UTC**:

| Piano | Richieste/giorno |
|---|---|
| Free | 1.000 |
| 1 € | 10.000 |
| 2 € | 25.000 |
| 3 € | 100.000 |
| 5 € VIP | 250.000 |

- Header su ogni risposta: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (Unix timestamp).
- Su `429`: header `Retry-After` in secondi; il campo `error` distingue `"Daily API limit exceeded!"` da `"API rate limit exceeded!"`.
- **Non aggirare** il limite con loop o più API key: i limiti sono per account e condivisi tra tutte le chiavi.

### 3.2 Capacità

- Piano free: **4 liste statiche** (+4 dinamiche), **max 10.000 elementi per lista**.
- Piani a pagamento: più liste e più elementi (fino a 600 liste e 150.000 elementi nei piani alti).
- Inattività di 120 giorni senza login: le liste smettono di aggiornarsi; gli account Supporter ne sono esenti.
- Il numero esatto di liste/elementi va verificato sul proprio account; non hardcodare i valori nel codice, leggere la risposta `403` e mostrare un messaggio chiaro.

---

## 4. Endpoint verificati

### 4.1 Liste

| Operazione | Metodo | Endpoint | Note |
|---|---|---|---|
| Elenco liste utente | GET | `/lists/user` | Array non paginato; `sort=created|name|ranked`; `unified`, `include_shared`. |
| Dettaglio lista | GET | `/lists/{listid}` | `id`, `name`, `slug`, `private`, `mediatype`, `user_id`, `user_name`, `items`, `likes`, `liked`. |
| Dettaglio per nome | GET | `/lists/{username}/{listname}` | Utile per import da URL; restituisce un array (può contenere movie+show). |
| Creazione lista statica | POST | `/lists/user/add` | Body `{name, private?}`; risposta `{id, name, slug}`. |
| Aggiornamento metadati | PUT | `/lists/{listid}` | Solo `name` e/o `private`. **Non** imposta l'ordine. |
| Eliminazione | DELETE | `/lists/{listid}` | Solo liste statiche possedute. **Mai usare per aggiornare.** |
| Appartenenza | GET | `/lists/user/membership` | `mediatype` + `tmdb|imdb|trakt|tvdb`; restituisce `{contains:[list_id]}`. Solo liste statiche. |

**Nota:** `GET /lists/{listid}` non espone in modo affidabile `type`/`dynamic`. Non è possibile determinare con certezza dal solo metadata se una lista è statica. Il preflight deve:
1. leggere la lista e verificare che `user_id`/`user_name` corrispondano all'account autenticato;
2. chiedere all'utente conferma esplicita che la lista è statica e che può essere modificata;
3. trattare un `403` su add/remove/reorder come blocco definitivo, non come retry.

### 4.2 Elementi

| Operazione | Metodo | Endpoint | Note |
|---|---|---|---|
| Lettura elementi | GET | `/lists/{listid}/items` | `cursor` preferito; `limit` default 100, max 1000; `offset` deprecato. Header `X-Has-More`. |
| Aggiunta/rimozione | POST | `/lists/{listid}/items/{action}` | `action=add|remove`; body `{movies, shows, seasons, episodes}`; risposta `{added, removed, existing, not_found}`. |
| Riordino | POST | `/lists/{listid}/items/reorder` | Body `{items:[{mediatype, ids}], after|before|position}`; max 1.000 elementi; risposta `{updated, not_found}`. |
| Modifiche | GET | `/lists/{listid}/changes` | La descrizione parla di `added_ids`/`removed_ids`, ma lo schema 200 documenta `{id, movie, updated}`. Usare solo come indizio. |

#### Lettura con cursore

```http
GET /lists/{listid}/items?limit=100&sort=rank&order=asc
```

Risposta (forma semplificata):

```json
{
  "movies": [
    {
      "id": 917496,
      "rank": 1,
      "rank_change": null,
      "title": "Beetlejuice Beetlejuice",
      "imdb_id": "tt2049403",
      "ids": {"mdblist": "m917496", "imdb": "tt2049403", "tmdb": 917496, "tvdb": null},
      "mediatype": "movie",
      "release_year": 2024
    }
  ],
  "shows": [],
  "seasons": [],
  "episodes": [],
  "pagination": {
    "next_cursor": "..."
  }
}
```

- Passare `next_cursor` come `cursor` fino a quando non è assente.
- `X-Has-More: true/false` è un secondo segnale.
- `extended=ids_only` restituisce solo gli ID TMDb conservando paginazione e ordinamento: utile per il diff MIRROR, perché riduce il payload.
- `unified=true` fonde movie+show in una lista unica; **non usarlo per la sincronizzazione**, perché il target MDBList è a mediatype singolo.
- `sort=usort` legge l'ordine custom; `sort=rank` legge l'ordine della lista.

#### Aggiunta/rimozione

```http
POST /lists/{listid}/items/add
Content-Type: application/json

{
  "movies": [{"tmdb": 630, "imdb": "tt0032138"}, {"tmdb": 238}],
  "shows": [{"tmdb": 1396}, {"imdb": "tt0417299"}],
  "seasons": [],
  "episodes": []
}
```

Risposta:

```json
{
  "added": {"movies": 2, "shows": 2},
  "removed": {"movies": 0, "shows": 0},
  "existing": {"movies": 0, "shows": 0},
  "not_found": {"movies": 0, "shows": 0}
}
```

- Il body accetta `movies`, `shows`, `seasons`, `episodes`.
- Per i film, `tmdb` è la chiave primaria; `imdb` è opzionale.
- Per le serie, almeno un ID tra `tmdb` e `imdb`.
- Per stagioni/episodi, usare `tmdb`.
- La risposta è aggregata: `not_found` non identifica quali elementi sono falliti. Dopo un batch, rileggere la lista e riconciliare.
- Non è documentato un limite di elementi per singola richiesta add/remove. Usare batch conservativi (es. 100) e misurare con l'API reale.

#### Riordino

```http
POST /lists/{listid}/items/reorder
Content-Type: application/json

{
  "items": [
    {"mediatype": "movie", "ids": {"tmdb": 603}},
    {"mediatype": "movie", "ids": {"tmdb": 238}}
  ],
  "position": "top"
}
```

- `items`: 1–1.000 elementi, nell'ordine desiderato.
- `after` / `before`: collocano gli elementi dopo/prima di un elemento esistente.
- `position`: `top` (default) o `bottom`, se non si usa `after`/`before`.
- "Sending the whole list replaces the order"; per liste >1.000 elementi servono più chiamate con `after`/`before`.
- L'operazione **non è atomica**: un'interruzione lascia un ordine parziale. Va tracciata come operazione separata e riconciliata con `sort=usort`.
- Solo il proprietario della lista statica può riordinare.

---

## 5. Algoritmo di sincronizzazione MDBList

### 5.1 Preflight

1. Verificare che la credenziale MDBList esista e sia decifrabile.
2. `GET /lists/{listid}`: verificare `user_id`/`user_name`, `private`, `mediatype`.
3. Chiedere conferma esplicita che la lista è statica e che MIRROR può rimuovere elementi aggiunti manualmente.
4. Leggere tutti gli elementi con `cursor` e `extended=ids_only`; se la lettura è incompleta, **non applicare**.
5. Verificare che lo snapshot sorgente sia valido e non vuoto.
6. Acquisire un lock per `target_id` (PostgreSQL advisory lock) e verificare che non ci sia un altro run attivo.
7. Calcolare il piano e le soglie; se superate, fermarsi in `AWAITING_APPROVAL`.

### 5.2 Diff

Normalizzare ogni elemento in una chiave `(media_type, tmdb_id)`:

- se manca `tmdb` ma c'è `imdb`, risolvere con TMDb `find` o `/movie/{id}/external_ids` / `/tv/{id}/external_ids`;
- se non è risolvibile, registrare `UNRESOLVED` e non includerlo nel diff;
- se lo snapshot ha elementi non risolti, MIRROR non può rimuovere (rischio di falsi negativi); richiedere revisione manuale.

```
source_keys = { (media_type, tmdb_id) | snapshot item resolved }
remote_keys = { (media_type, tmdb_id) | remote item resolved }

MIRROR:
  to_add    = source_keys - remote_keys
  to_remove = remote_keys - source_keys

APPEND_ONLY:
  to_add    = source_keys - remote_keys
  to_remove = {}
```

### 5.3 Applicazione

1. Creare in DB un `SyncOperation` per ogni elemento, con `idempotency_key = sha256(run_id|action|media_type|tmdb_id|target_id)`.
2. Applicare `add` prima di `remove` (evita una finestra in cui mancano elementi desiderati; il costo è un temporaneo sovrainsieme). Se la lista è vicina al limite massimo, il client può ridurre il batch o pianificare prima le rimozioni, ma solo dopo aver verificato che gli `ADD` siano andati a buon fine.
3. Batch di add/remove: massimo 100 elementi per richiesta (configurabile), throttle per rispettare 300 scritture/5 minuti.
4. Dopo ogni batch, aggiornare i contatori; in caso di timeout/5xx, segnare le operazioni `UNCERTAIN` e rileggere la lista prima di ritentare.
5. Al termine, rileggere la lista completa e riconciliare: ogni operazione `SUCCEEDED` deve essere presente/assente come atteso.
6. Se `preserve_order=true`, eseguire il reorder dopo la riconciliazione dei contenuti:
   - lista ≤1.000: una chiamata con tutti gli elementi nell'ordine della sorgente;
   - lista >1.000: chunk da 1.000 con `after` = ultimo elemento del chunk precedente;
   - se il reorder fallisce, il contenuto è corretto ma l'ordine è parziale: il run resta `SUCCEEDED` con warning `ORDER_NOT_ENFORCED` e `order_enforced=false`; non è un `PARTIAL`, perché non mancano elementi.
7. Aggiornare lo stato finale: `SUCCEEDED`, `PARTIAL`, `FAILED`, `BLOCKED`.

### 5.4 Idempotenza e ripresa

- Non esiste un header `Idempotency-Key` lato MDBList.
- La chiave locale `idempotency_key` evita di creare due operazioni per lo stesso elemento nello stesso run.
- Dopo un crash, riprendere solo le operazioni `PENDING`/`FAILED`; per le `IN_FLIGHT`/`UNCERTAIN`, **rileggere lo stato remoto** prima di ritentare.
- Non riapplicare un batch se non si è certi del suo esito: la lettura remota è la fonte di verità.

### 5.5 Ordine e limiti

- `preserve_order` è **opt-in** e default `false` per MIRROR.
- Per APPEND_ONLY, l'ordine è quello di inserimento; non serve reorder.
- Per liste >1.000, il reorder è multi-chiamata e non atomico: l'UI deve mostrare "ordine parziale" se il run viene interrotto; il run resta `SUCCEEDED` con warning `ORDER_NOT_ENFORCED`.
- Non cancellare e ricreare la lista per ottenere l'ordine: perderebbe ID, URL, like e cronologia.

---

## 6. Errori e gestione

| HTTP | Significato | Azione |
|---|---|---|
| 400 | Parametro/body mancante o malformato | Errore permanente; correggere il payload, non ritentare. |
| 401 | API key/token mancante o invalido | Disabilitare il target, chiedere credenziale valida. |
| 403 | Account bloccato, lista non propria, funzione supporter | Bloccare il binding; messaggio chiaro; non ritentare. |
| 404 | Lista non trovata | Verificare ID; non ricreare automaticamente. |
| 429 | Rate limit giornaliero o 5 minuti | Rispettare `Retry-After`; backoff con jitter; riprendere. |
| 5xx | Errore temporaneo | Retry limitato; dopo timeout, riconciliare lo stato remoto. |

**Tassonomia interna:** `MDBLIST_AUTH_FAILED`, `MDBLIST_PERMISSION_DENIED`, `MDBLIST_RATE_LIMITED`, `MDBLIST_LIST_NOT_FOUND`, `MDBLIST_UNCERTAIN`, `MDBLIST_SCHEMA_CHANGED`, `MDBLIST_INTERNAL`.

---

## 7. Test di contratto

Congelare uno snapshot dello schema live e creare fixture sintetiche per:

- `GET /lists/{listid}` (lista statica, privata, di un altro utente);
- `GET /lists/{listid}/items` con due pagine e `next_cursor`;
- `POST /lists/{listid}/items/add` con `added`, `existing`, `not_found`;
- `POST /lists/{listid}/items/remove`;
- `POST /lists/{listid}/items/reorder` con `updated` e `not_found`;
- `429` con `Retry-After`;
- `403` su lista non propria;
- timeout simulato dopo una scrittura, seguito da lettura che mostra l'elemento presente.

I test non devono mai chiamare liste reali. Le fixture devono avere header `SYNTHETIC_FIXTURE` e non contenere dati personali.

---

## 8. Blocchi e verifiche residue

1. **API key reale** per verificare:
   - se il piano free può scrivere su liste statiche o se serve Supporter;
   - il limite effettivo di elementi per richiesta add/remove;
   - la posizione di inserimento (testa/coda) e il comportamento sui duplicati;
   - la stabilità dello slug dopo `PUT {name}`.
2. **Lista di test dedicata** per la Fase 3, non una lista personale.
3. **Piano MDBList** (free/supporter) per dimensionare liste e rate.
4. **Conferma** che l'endpoint `reorder` sia disponibile sul proprio account e che il limite di 1.000 elementi sia applicato come documentato.
5. **Attribuzione:** MDBList non impone un'attribuzione paragonabile a JustWatch, ma i dati di disponibilità provengono da TMDb/JustWatch: l'attribuzione JustWatch resta obbligatoria a monte.

---

## 9. Fonti

- Schema OpenAPI live: https://api.mdblist.com/schema/?format=json
- Documentazione API: https://docs.mdblist.com/docs/api
- Autenticazione: https://api.mdblist.com/docs/authentication/
- Tipi di lista: https://docs.mdblist.com/docs/list_types
- Piani e limiti: https://docs.mdblist.com/docs/supporter
- API docs UI: https://api.mdblist.com/docs


---

## Fonte: `phase-01.md`

# Fase 1 — Architettura

**Stato:** progetto di Fase 1, nessun servizio applicativo implementato.
**Vincoli di riferimento:** monolite modulare, processi separati per web/worker/scheduler, PostgreSQL come fonte di verità, Redis solo come broker/cache, nessun job lungo nel processo HTTP.

---

## 1. Decisioni in breve

| Decisione | Scelta | Alternativa scartata |
|---|---|---|
| Forma del sistema | Monolite modulare con 4 processi (web, api, worker, scheduler) | Microservizi indipendenti, Kubernetes |
| Fonte di verità | PostgreSQL | Redis, file JSON, stato in memoria |
| Coda e pianificazione | Celery + Redis; beat nel processo `scheduler` | `BackgroundTasks` FastAPI, cron di sistema |
| Acquisizione | Snapshot immutabili con flag di completezza | Aggiornamento in place della collezione |
| Provenienza | Enum `OFFICIAL` / `AGGREGATOR` / `CUSTOM` + `date_basis` | Un unico campo "fonte" generico |
| Connettori | Interfaccia con capability flags dichiarate | Interfaccia unica che presume tutte le capacità |
| Sync | Operation ledger + riconciliazione remota | Transazione distribuita DB/API |
| Ordine | Reorder MDBList opzionale, best-effort, max 1.000 per chiamata | Cancellare e ricreare la lista |
| Concorrenza | Advisory lock per target + unique partial index | Lock in memoria o "speranza" |
| Segreti | AES-256-GCM con chiave esterna al DB | Segreti in `.env` o in chiaro nel DB |
| Frontend | SPA React + client generato da OpenAPI | SSR, client scritto a mano |
| Target MDBList | ID numerico stabile; slug/URL solo display | Usare lo slug come chiave |

---

## 2. Topologia dei processi

```mermaid
flowchart LR
    U[Utente] -->|HTTPS 443| W[web / Caddy]
    W -->|static SPA| F[frontend build]
    W -->|/api/*| A[api FastAPI]
    A --> P[(PostgreSQL)]
    A --> R[(Redis)]
    A -->|enqueue| R
    R -->|tasks| K[worker Celery]
    K --> P
    K -->|HTTP| X[TMDb / JustWatch / MDBList]
    S[scheduler Celery beat] -->|enqueue due bindings| R
    S --> P
    M[migrate one-shot] --> P
```

| Processo | Responsabilità | Non deve fare |
|---|---|---|
| `web` | TLS, serving SPA, reverse proxy `/api`, header di sicurezza | Logica applicativa, accesso al DB |
| `api` | Autenticazione, validazione, query, enqueue job, OpenAPI | Scraping, sync, job lunghi, `BackgroundTasks` |
| `worker` | Acquisizione, normalizzazione, sync, riconciliazione, retry | Servire HTTP all'utente |
| `scheduler` | Celery beat: calcola i binding dovuti, enqueue manutenzione | Eseguire sync nel proprio processo |
| `migrate` | `alembic upgrade head` e seed | Restare in esecuzione |
| `postgres` | Stato persistente, lock, storico | Esposizione pubblica |
| `redis` | Broker Celery, cache, rate limit | Fonte di verità |

**Regola:** l'API non esegue mai un'acquisizione o una sync. Risponde `202 Accepted` con un `job_id`/`run_id` e il frontend fa polling.

---

## 3. Struttura del repository

```text
MdbUP/
├── backend/
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   ├── errors.py
│   │   │   └── routers/
│   │   │       ├── auth.py
│   │   │       ├── dashboard.py
│   │   │       ├── providers.py
│   │   │       ├── sources.py
│   │   │       ├── collections.py
│   │   │       ├── mdblist.py
│   │   │       ├── bindings.py
│   │   │       ├── sync_runs.py
│   │   │       ├── settings.py
│   │   │       └── health.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   ├── crypto.py
│   │   │   ├── security.py
│   │   │   └── time.py
│   │   ├── domain/
│   │   │   ├── enums.py
│   │   │   ├── models.py
│   │   │   ├── errors.py
│   │   │   └── policies.py
│   │   ├── services/
│   │   │   ├── acquisition.py
│   │   │   ├── normalization.py
│   │   │   ├── sync_planner.py
│   │   │   ├── sync_executor.py
│   │   │   ├── reconciliation.py
│   │   │   ├── dashboard.py
│   │   │   └── credentials.py
│   │   ├── connectors/
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   ├── tmdb/
│   │   │   │   ├── connector.py
│   │   │   │   ├── client.py
│   │   │   │   └── mapper.py
│   │   │   ├── justwatch/
│   │   │   │   ├── connector.py
│   │   │   │   ├── client.py
│   │   │   │   ├── export.py
│   │   │   │   └── mapper.py
│   │   │   └── manual_csv/
│   │   │       └── connector.py
│   │   ├── repositories/
│   │   │   ├── providers.py
│   │   │   ├── collections.py
│   │   │   ├── snapshots.py
│   │   │   ├── bindings.py
│   │   │   ├── sync_runs.py
│   │   │   └── settings.py
│   │   ├── jobs/
│   │   │   ├── celery_app.py
│   │   │   ├── scheduler.py
│   │   │   └── tasks/
│   │   │       ├── acquisition.py
│   │   │       ├── sync.py
│   │   │       └── maintenance.py
│   │   ├── integrations/
│   │   │   ├── mdblist/
│   │   │   │   ├── client.py
│   │   │   │   ├── models.py
│   │   │   │   └── mapper.py
│   │   │   └── tmdb/
│   │   │       ├── client.py
│   │   │       └── models.py
│   │   └── db/
│   │       ├── base.py
│   │       ├── session.py
│   │       └── models/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── contract/
│   │   ├── e2e/
│   │   └── fixtures/
│   └── scripts/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/
│   │   │   ├── client.ts
│   │   │   └── schema.d.ts
│   │   ├── components/
│   │   ├── features/
│   │   │   ├── auth/
│   │   │   ├── dashboard/
│   │   │   ├── providers/
│   │   │   ├── collections/
│   │   │   ├── bindings/
│   │   │   ├── sync/
│   │   │   └── settings/
│   │   ├── lib/
│   │   ├── routes/
│   │   └── styles/
│   └── e2e/
├── deploy/
│   ├── docker-compose.yml
│   ├── Caddyfile
│   ├── Dockerfile.api
│   ├── Dockerfile.web
│   └── backup/
├── docs/
│   └── phase1/
├── scripts/
│   ├── backup.sh
│   └── restore.sh
├── .env.example
└── README.md
```

### Regola di dipendenza

```text
api ──────────────► services ──────────────► domain
                         │
                         ├──► repositories ───► db
                         ├──► connectors ─────► integrations
                         └──► jobs? (no: jobs chiamano services)
```

- `domain` non importa FastAPI, SQLAlchemy, HTTPX o Celery.
- `api` non contiene query SQL complesse né logica di sync.
- `services` orchestra casi d'uso e non conosce FastAPI.
- `connectors` conosce solo la fonte esterna e restituisce modelli normalizzati.
- `repositories` è l'unico layer che parla con SQLAlchemy.
- `jobs` è un adapter sottile: deserializza l'input, chiama un servizio, registra lo stato.
- `integrations` contiene client HTTP e traduzione payload, senza regole di business.

---

## 4. Interfaccia `SourceConnector`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any, Protocol, Sequence


class MediaType(StrEnum):
    MOVIE = "MOVIE"
    SHOW = "SHOW"


class CollectionKind(StrEnum):
    CATALOG = "CATALOG"
    RECENTLY_ADDED = "RECENTLY_ADDED"
    UPCOMING = "UPCOMING"
    CHART = "CHART"
    CUSTOM_FILTER = "CUSTOM_FILTER"


class CollectionOrigin(StrEnum):
    OFFICIAL = "OFFICIAL"
    AGGREGATOR = "AGGREGATOR"
    CUSTOM = "CUSTOM"


class DateBasis(StrEnum):
    PROVIDER_OFFICIAL = "PROVIDER_OFFICIAL"
    AGGREGATOR_FIRST_SEEN = "AGGREGATOR_FIRST_SEEN"
    APP_FIRST_SEEN = "APP_FIRST_SEEN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ConnectorCapabilities:
    catalog: bool = False
    recently_added: bool = False
    upcoming: bool = False
    charts: bool = False
    ordering: bool = False
    added_dates: bool = False
    seasons_episodes: bool = False
    full_pagination: bool = False
    data_export: bool = False
    requires_credentials: bool = True
    requires_contract: bool = False
    max_page_size: int = 100
    notes: str = ""


@dataclass(frozen=True)
class SourceProvider:
    external_id: str
    name: str
    country_code: str = "IT"


@dataclass(frozen=True)
class SourceCollection:
    key: str
    name: str
    provider_external_id: str
    media_type: MediaType
    kind: CollectionKind
    origin: CollectionOrigin
    date_basis: DateBasis
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawItem:
    source_item_id: str
    media_type: MediaType
    title: str
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    tvdb_id: int | None = None
    source_date_created: date | None = None
    source_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Page:
    items: Sequence[RawItem]
    next_cursor: str | None
    total_pages: int | None = None
    total_items: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedItem:
    media_type: MediaType
    tmdb_id: int | None
    imdb_id: str | None
    title: str
    year: int | None
    offer_types: frozenset[str]
    source_date_created: date | None
    date_basis: DateBasis
    raw: dict[str, Any]


class NotSupportedError(RuntimeError):
    """La fonte non supporta questa capacità."""


class SourceConnector(Protocol):
    key: str
    capabilities: ConnectorCapabilities

    async def healthcheck(self) -> bool: ...

    async def list_providers(self, country_code: str) -> Sequence[SourceProvider]: ...

    async def list_collections(self, country_code: str) -> Sequence[SourceCollection]: ...

    async def fetch_collection_page(
        self,
        collection: SourceCollection,
        cursor: str | None,
        page_size: int,
    ) -> Page: ...

    def normalize_item(self, raw: RawItem) -> NormalizedItem: ...

    async def aclose(self) -> None: ...
```

### Regole

1. Ogni connettore dichiara le capacità **reali**. Se una capacità è `False`, il metodo corrispondente può sollevare `NotSupportedError`.
2. L'UI usa le capacità per disabilitare le collezioni non disponibili e mostra il motivo.
3. `normalize_item` non inventa ID: se manca `tmdb_id`, il resolver TMDb prova a risolvere da IMDb; se fallisce, l'item resta `UNRESOLVED`.
4. `source_date_created` è la data dichiarata dalla fonte, non `first_seen_at`.
5. `Page.next_cursor` è l'unico modo per proseguire; `total_pages`/`total_items` sono segnali di completezza, non garanzie.

### Matrice capacità connettori

| Connettore | catalogo | aggiunte recenti | prossime uscite | classifiche | ordinamento | date aggiunta | stagioni/episodi | paginazione completa | data export | Stato |
|---|---|---|---|---|---|---|---|---|---|---|
| `tmdb` | ✅ disponibilità corrente | ❌ | ❌ (solo uscite cinema) | ❌ | limitato | ❌ | ✅ metadati | ❌ (cap 500 pagine) | ❌ | **Con API key** |
| `justwatch_partner` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `date_created` | ✅ | ✅ | ✅ | **BLOCCATO contratto** |
| `justwatch_export` | ✅ | ✅ (da verificare nel dump) | ❌ | ❌ | ordine sorgente | ✅ (da verificare) | ❌ (da verificare) | ✅ | ✅ | **BLOCCATO contratto** |
| `manual_csv` | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ | **Disponibile** |

**Nota MDBList:** il target supporta `POST /lists/{listid}/items/reorder` (max 1.000 elementi per chiamata, ordine custom `usort`). Il reorder è un'operazione opzionale del sync executor, non una capacità della fonte. Non è atomico per liste >1.000 e non va usato per simulare un ordine non disponibile nella sorgente.

**Nota:** `tmdb` non è una fonte ufficiale del provider. È un aggregatore (dati watch provider powered by JustWatch). Le collezioni TMDb sono sempre `AGGREGATOR`.

---

## 5. Flusso di acquisizione

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant API as API FastAPI
    participant Q as Redis/Celery
    participant W as Worker
    participant DB as PostgreSQL
    participant S as Fonte esterna

    UI->>API: POST /collections/{id}/acquire
    API->>DB: JobExecution(QUEUED)
    API->>Q: enqueue acquire_collection
    API-->>UI: 202 {job_id}
    Q->>W: acquire_collection(collection_id)
    W->>DB: advisory lock collection
    W->>DB: CollectionSnapshot(RUNNING)
    loop pagine
        W->>S: fetch_collection_page(cursor)
        S-->>W: Page
        W->>W: valida schema, normalizza, risolve ID, dedup
        W->>DB: SnapshotItem
    end
    W->>DB: calcola checksum/completezza
    alt completa e valida
        W->>DB: snapshot COMPLETE + is_valid=true
        W->>DB: collection.last_valid_snapshot_id
    else incompleta/errore
        W->>DB: snapshot INCOMPLETE/FAILED, is_valid=false
    end
    W->>DB: JobExecution(SUCCEEDED/FAILED)
```

### Completezza

Uno snapshot è `COMPLETE` solo se:

- tutte le pagine attese sono state lette (`pages_fetched == pages_expected`, quando la fonte espone un totale);
- non ci sono errori di schema o di rete non recuperati;
- il cursore non è entrato in loop;
- il numero di item letti è coerente con `total_items`, se disponibile;
- il checksum è stato calcolato.

`is_valid` richiede `COMPLETE`, `items_count > 0` e `unresolved_count == 0` (per MIRROR). Per APPEND_ONLY, `COMPLETE` con warning può bastare, ma le aggiunte non risolte vengono saltate.

### Snapshot immutabile

- Ogni acquisizione crea un nuovo `CollectionSnapshot`.
- Non si aggiorna mai uno snapshot esistente, salvo il passaggio `RUNNING -> COMPLETE/INCOMPLETE/FAILED`.
- `collection.last_valid_snapshot_id` punta all'ultimo snapshot valido.
- La sync usa solo `last_valid_snapshot_id`; se non esiste, la sync è `BLOCKED`.

### Deduplicazione

- Chiave: `(media_type, tmdb_id)`.
- Se `tmdb_id` manca, `(media_type, imdb_id)`.
- Mai il titolo.
- Lo stesso ID numerico TMDb può esistere per un film e per una serie: `media_type` è sempre nella chiave.
- Duplicati nella stessa pagina: tiene la prima occorrenza, incrementa `duplicate_count`.

---

## 6. Orchestrazione job

### Code

| Coda | Task | Concorrenza | Note |
|---|---|---|---|
| `acquisitions` | `acquire_collection` | 2 | Una acquisizione per collezione alla volta (advisory lock). |
| `sync` | `run_sync` | 2 | Un run per target alla volta (advisory lock). |
| `maintenance` | `enqueue_due_bindings`, `cleanup_old_data`, `healthcheck_sources` | 1 | Task brevi e idempotenti. |

### Scheduler

- `scheduler` esegue `celery beat`.
- Ogni 60 secondi: `enqueue_due_bindings`.
- Il task:
  1. `SELECT ... FROM sync_bindings WHERE is_enabled AND next_run_at <= now() FOR UPDATE SKIP LOCKED`;
  2. per ogni binding, verifica che non ci sia un run attivo;
  3. enqueue `run_sync(binding_id, trigger="SCHEDULED")`;
  4. calcola `next_run_at` con `croniter` nel fuso `Europe/Rome`, salva in UTC.
- La pianificazione è **DB-driven**, non una entry di beat per binding: aggiungere/rimuovere binding non richiede reload del beat.
- `cleanup_old_data` giornaliero: snapshot/run/operation oltre la retention; audit log oltre 180 giorni (configurabile).
- `healthcheck_sources` orario: aggiorna `Source.status` e `last_healthcheck_at`.

### Idempotenza

- `JobExecution` ha `task_id` unico.
- `SyncRun` ha un unique partial index su `binding_id` per gli stati attivi.
- `SyncBinding` ha un unique partial index su `target_id` dove `is_enabled = true`.
- Le task rileggono lo stato dal DB prima di agire; un doppio enqueue non crea un secondo run.

### Retry

- Retry automatico solo per errori transitori (`429`, `5xx`, timeout di rete).
- Backoff esponenziale con jitter, max 5 tentativi.
- `Retry-After` ha precedenza sul backoff.
- Errori `400`, `401`, `403`, `404`, schema cambiato: **no retry**, stato `FAILED`/`BLOCKED`.
- Dopo un timeout di scrittura: `UNCERTAIN`, riconciliazione remota prima di ritentare.

---

## 7. Flusso di sincronizzazione

```mermaid
sequenceDiagram
    participant SCH as Scheduler
    participant Q as Redis/Celery
    participant W as Worker
    participant DB as PostgreSQL
    participant M as MDBList

    SCH->>DB: binding dovuti
    SCH->>Q: enqueue run_sync
    Q->>W: run_sync(binding_id)
    W->>DB: advisory lock target
    W->>DB: SyncRun(PREFLIGHT)
    W->>M: GET /lists/{id}
    W->>M: GET items (cursor)
    W->>DB: SyncRun(PLANNING)
    W->>DB: calcola to_add/to_remove
    alt soglie superate o snapshot invalido
        W->>DB: SyncRun(BLOCKED/AWAITING_APPROVAL)
    else piano ok
        W->>DB: SyncRun(APPLYING)
        W->>M: POST items/remove (batch)
        W->>M: POST items/add (batch)
        W->>M: GET items (riconciliazione)
        opt preserve_order
            W->>M: POST items/reorder
        end
        W->>DB: SyncRun(SUCCEEDED/PARTIAL/FAILED)
    end
```

### Punti di fallimento

| Punto | Gestione |
|---|---|
| Lettura lista remota incompleta | `BLOCKED`, nessuna scrittura |
| Snapshot non valido | `BLOCKED`, nessuna scrittura |
| Snapshot vuoto | `BLOCKED`, nessuna rimozione |
| Soglia rimozioni superata | `AWAITING_APPROVAL`, nessuna scrittura |
| Timeout su add/remove | `UNCERTAIN`, rileggi lista, poi decidi |
| Parziale | `PARTIAL`, operazioni fallite riprovabili |
| Reorder fallito | `SUCCEEDED` con warning `ORDER_NOT_ENFORCED`; contenuto corretto, ordine parziale |
| 401/403 | `FAILED`/`BLOCKED`, credenziale o permesso da correggere |

### Perché non una transazione distribuita

Non esiste atomicità tra PostgreSQL e MDBList. Il sistema usa:

- un **operation ledger** persistente;
- una **riconciliazione** finale con lettura remota;
- stati espliciti `UNCERTAIN` e `PARTIAL`;
- una UI che mostra chiaramente cosa è stato applicato.

---

## 8. Tassonomia errori

```python
class AppError(Exception):
    category: str          # AUTH | VALIDATION | SOURCE | TARGET | POLICY | CONFLICT | INTERNAL
    code: str              # es. SOURCE_RATE_LIMITED
    message: str           # messaggio utente in italiano
    retryable: bool
    details: dict
```

| Categoria | Esempi | UI |
|---|---|---|
| `AUTH` | `AUTH_INVALID_CREDENTIALS`, `AUTH_SESSION_EXPIRED` | Login / re-login |
| `VALIDATION` | `VALIDATION_INVALID_CRON`, `VALIDATION_BAD_TARGET` | Errore di form |
| `SOURCE` | `SOURCE_UNAVAILABLE`, `SOURCE_AUTH_FAILED`, `SOURCE_RATE_LIMITED`, `SOURCE_SCHEMA_CHANGED` | "Errore della fonte X" |
| `TARGET` | `MDBLIST_AUTH_FAILED`, `MDBLIST_PERMISSION_DENIED`, `MDBLIST_RATE_LIMITED`, `MDBLIST_UNCERTAIN` | "Errore MDBList" |
| `POLICY` | `SNAPSHOT_INCOMPLETE`, `SNAPSHOT_EMPTY`, `THRESHOLD_EXCEEDED`, `MANUAL_REVIEW_REQUIRED` | "Operazione bloccata per sicurezza" |
| `CONFLICT` | `SYNC_ALREADY_RUNNING`, `BINDING_DISABLED` | "Operazione già in corso" |
| `INTERNAL` | `INTERNAL_ERROR` | "Errore interno, riprova" |

**Regola UI:** un errore `SOURCE` non deve mai essere mostrato come errore MDBList, e viceversa. Il campo `category` determina il badge e il suggerimento.

---

## 9. ADR

### ADR-001 — Monolite modulare, non microservizi
**Contesto:** app single-user, team ridotto, deploy Docker Compose.
**Decisione:** un'unica codebase con layer espliciti e processi separati.
**Conseguenze:** semplicità operativa; nessun contratto di rete interno; disciplina sui confini dei moduli.

### ADR-002 — Processi separati per API, worker e scheduler
**Contesto:** job lunghi e sincronizzazioni non devono bloccare le richieste HTTP.
**Decisione:** `api`, `worker`, `scheduler` con la stessa immagine ma comandi diversi.
**Conseguenze:** più container; healthcheck distinti; nessun `BackgroundTasks`.

### ADR-003 — PostgreSQL fonte di verità
**Contesto:** stato di job, snapshot, run e operazioni deve sopravvivere ai restart.
**Decisione:** tutto lo stato persistente in PostgreSQL; Redis solo broker/cache.
**Conseguenze:** backup del DB obbligatorio; Redis può essere svuotato senza perdere dati.

### ADR-004 — Snapshot immutabili
**Contesto:** una sync non deve mai partire da dati parziali o mutati durante la lettura.
**Decisione:** ogni acquisizione crea uno snapshot; solo gli snapshot validi alimentano le sync.
**Conseguenze:** più spazio su disco; retention necessaria; storia completa.

### ADR-005 — Capability flags nei connettori
**Contesto:** fonti diverse hanno capacità diverse; non tutte hanno date, stagioni, paginazione completa.
**Decisione:** ogni connettore dichiara `ConnectorCapabilities`; l'UI disabilita ciò che non è supportato.
**Conseguenze:** niente fallimenti a runtime per capacità inventate; test di contratto per ogni flag.

### ADR-006 — Provenienza e `date_basis` espliciti
**Contesto:** categoria ufficiale, aggregatore e filtro personalizzato non sono la stessa cosa; la data di aggiunta può essere ufficiale, di aggregatore o di prima osservazione dell'app.
**Decisione:** enum `CollectionOrigin` e `DateBasis`; etichette distinte in DB e UI.
**Conseguenze:** nessuna sostituzione silenziosa; l'utente vede sempre la provenienza.

### ADR-007 — Operation ledger e riconciliazione
**Contesto:** MDBList non offre transazioni atomiche né idempotency key.
**Decisione:** ogni modifica remota è un `SyncOperation` persistito; dopo timeout si rilegge lo stato remoto.
**Conseguenze:** stato parziale visibile; ripresa affidabile; più codice di riconciliazione.

### ADR-008 — Lock per target e unique partial index
**Contesto:** due run concorrenti sulla stessa lista possono corrompere l'ordine o duplicare elementi.
**Decisione:** advisory lock PostgreSQL su `target_id` + unique partial index su `sync_bindings(target_id)` e `sync_runs(binding_id)` attivi.
**Conseguenze:** un solo writer per target; doppio avvio respinto con `CONFLICT`.

### ADR-009 — Segreti con AES-256-GCM e chiave esterna
**Contesto:** API key MDBList/TMDb e token JustWatch sono credenziali potenti.
**Decisione:** cifratura a riposo con chiave in env/secret manager, `key_version`, masking e redazione log.
**Conseguenze:** perdita della chiave = credenziali irrecuperabili; backup della chiave separato.

### ADR-010 — SPA + client OpenAPI generato
**Contesto:** frontend e backend devono restare allineati.
**Decisione:** FastAPI genera OpenAPI; `openapi-typescript` + `openapi-fetch` generano il client.
**Conseguenze:** type safety end-to-end; rigenerazione in CI; nessun client manuale duplicato.

### ADR-011 — Celery beat + query DB dei binding dovuti
**Contesto:** le pianificazioni sono per binding e cambiano dall'UI.
**Decisione:** beat esegue un task periodico che interroga i binding dovuti; non una entry di beat per binding.
**Conseguenze:** modifiche alla pianificazione immediate; un solo punto di verità (DB).

### ADR-012 — ID numerico MDBList come chiave, slug solo display
**Contesto:** lo slug/URL può cambiare con una rinomina; l'ID è stabile.
**Decisione:** `mdblist_targets.remote_list_id` è la chiave; slug/URL sono campi di display riletti.
**Conseguenze:** rinomine sicure; nessun binding rotto.

### ADR-013 — Reorder MDBList opzionale, non atomico
**Contesto:** lo schema live MDBList documenta `POST /lists/{listid}/items/reorder` con un limite di 1.000 elementi per chiamata; per liste più lunghe servono più chiamate e l'operazione non è atomica.
**Decisione:** `preserve_order` è opt-in, default `false`; il reorder è una `SyncOperation` separata, eseguita dopo la riconciliazione dei contenuti; un fallimento produce `SUCCEEDED` con warning `ORDER_NOT_ENFORCED`, non un rollback e non un `PARTIAL` (gli elementi ci sono tutti).
**Conseguenze:** l'ordine è best-effort; nessuna cancellazione/ricreazione della lista; l'UI dichiara il limite.

---

## 10. Cosa è implementabile ora e cosa è bloccato

| Area | Stato | Dipendenza |
|---|---|---|
| Docker Compose, DB, migrazioni, auth | **Implementabile subito** | Nessuna credenziale esterna |
| Frontend shell, dashboard, impostazioni | **Implementabile subito** | Backend Fase 2 |
| Connettore TMDb | **Implementabile con API key** | TMDb key |
| Connettore MDBList | **Implementabile con API key** | MDBList key |
| Sync MIRROR/APPEND_ONLY, soglie, lock, retry | **Implementabile subito** | Test con mock |
| Connettore JustWatch Partner API | **BLOCCATO** | Contratto + token |
| Connettore JustWatch Data Export | **BLOCCATO** | Contratto + credenziali S3 |
| Collezioni "Top 10 ufficiale" | **BLOCCATO/NON VERIFICATO** | Fonte ufficiale verificata |
| Collezioni "Aggiunte recenti" con data JustWatch | **BLOCCATO** | Contratto JustWatch |
| Collezioni "Aggiunte recenti" derivate | **Implementabile** | `first_seen_at` + etichetta `CUSTOM` |
| Reorder MDBList | **Implementabile con API key** | MDBList key; max 1.000 per chiamata |

---

## 11. File da creare in Fase 2

### Backend
- `backend/pyproject.toml`, `backend/uv.lock`
- `backend/app/main.py`
- `backend/app/core/config.py`, `logging.py`, `crypto.py`, `security.py`, `time.py`
- `backend/app/db/base.py`, `session.py`
- `backend/app/db/models/user.py`, `session.py`, `provider.py`, `source.py`, `collection.py`, `media.py`, `availability.py`, `snapshot.py`, `mdblist.py`, `sync.py`, `settings.py`, `audit.py`
- `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/0001_initial.py`
- `backend/app/api/deps.py`, `errors.py`
- `backend/app/api/routers/auth.py`, `health.py`, `dashboard.py`, `providers.py`, `sources.py`, `collections.py`, `mdblist.py`, `bindings.py`, `sync_runs.py`, `settings.py`
- `backend/app/jobs/celery_app.py`, `scheduler.py`, `tasks/acquisition.py`, `tasks/sync.py`, `tasks/maintenance.py`
- `backend/app/connectors/base.py`, `registry.py`
- `backend/app/integrations/mdblist/client.py`, `models.py`, `mapper.py`
- `backend/app/integrations/tmdb/client.py`, `models.py`
- `backend/tests/conftest.py`, `unit/`, `integration/`, `contract/`, `e2e/`, `fixtures/`

### Frontend
- `frontend/package.json`, `package-lock.json`, `vite.config.ts`, `tsconfig.json`, `tailwind.config.ts`
- `frontend/src/main.tsx`, `App.tsx`, `routes/`
- `frontend/src/api/client.ts`, `schema.d.ts`
- `frontend/src/features/auth/`, `dashboard/`, `providers/`, `collections/`, `bindings/`, `sync/`, `settings/`
- `frontend/src/components/` (Badge, DataTable, Wizard, StatusPill, ErrorBanner, EmptyState, Skeleton)
- `frontend/e2e/`

### Deploy
- `deploy/docker-compose.yml`
- `deploy/Caddyfile`
- `deploy/Dockerfile.api`
- `deploy/Dockerfile.web`
- `deploy/backup/`
- `deploy/scripts/backup.sh`, `deploy/scripts/restore.sh`
- `.env.example` (già creato in Fase 1)
- `README.md` (già creato in Fase 1, da aggiornare con i comandi di Fase 2)

---

## 12. Non-obiettivi

- Kubernetes, service mesh, microservizi indipendenti.
- SSR o Next.js.
- Multi-tenant o registrazione pubblica.
- Scraping di siti non autorizzati.
- Uso di dati simulati in produzione.
- Creazione automatica di categorie "ufficiali" senza fonte verificata.
- Cancellazione e ricreazione delle liste MDBList per simulare l'ordine.


---

## Fonte: `phase-01.md`

# Fase 1 — Modello dati

**Stato:** progettazione. Il DDL di riferimento è in [`schema.sql`](schema.sql); la migrazione Alembic `0001_initial` di Fase 2 dovrà produrre uno schema equivalente.

---

## 1. Principi

1. **Nessun titolo come chiave.** L'identità di un media è `(media_type, tmdb_id)`; in mancanza, `(media_type, imdb_id)`. Lo stesso ID numerico TMDb può identificare un film e una serie: `media_type` è sempre nella chiave.
2. **Film e serie separati.** `media.media_type ∈ {MOVIE, SHOW}`. Le stagioni/gli episodi non sono `Media`: sono eventi (`episode_event`) collegati alla serie.
3. **Provenienza esplicita.** Ogni collezione ha `origin ∈ {OFFICIAL, AGGREGATOR, CUSTOM}` e `date_basis ∈ {PROVIDER_OFFICIAL, AGGREGATOR_FIRST_SEEN, APP_FIRST_SEEN, UNKNOWN}`.
4. **Snapshot immutabili.** Ogni acquisizione crea un nuovo `collection_snapshot`; solo gli snapshot validi alimentano le sync.
5. **Osservazione vs dichiarazione.** `first_seen_at`/`last_seen_at` sono tempi di osservazione dell'app; `source_date_created` è la data dichiarata dalla fonte (JustWatch `date_created`), se disponibile.
6. **UTC nel database, Europe/Rome nella UI.** Tutti i timestamp sono `TIMESTAMPTZ`; le date `DATE` sono date di calendario della fonte.
7. **Segreti mai in chiaro.** `credential` contiene solo ciphertext, nonce, `key_version` e un hint mascherato.
8. **Concorrenza nel database.** Advisory lock applicativo + unique partial index; nessun lock in memoria.

---

## 2. Diagramma ER

```mermaid
erDiagram
    app_user ||--o{ session : has
    app_user ||--o{ audit_log : writes
    source ||--o{ credential : has
    source ||--o{ provider_mapping : maps
    provider ||--o{ provider_mapping : mapped
    source ||--o{ collection : provides
    provider ||--o{ collection : belongs
    collection ||--o{ collection_snapshot : snapshots
    collection_snapshot ||--o{ snapshot_item : contains
    media ||--o{ snapshot_item : resolved
    media ||--o{ availability : available
    provider ||--o{ availability : offers
    source ||--o{ availability : observed
    collection ||--o{ sync_binding : binds
    mdblist_target ||--o{ sync_binding : target
    sync_binding ||--o{ sync_run : runs
    collection_snapshot ||--o{ sync_run : source
    sync_run ||--o{ sync_operation : operations
    media ||--o{ sync_operation : item
    media ||--o{ episode_event : show
    provider ||--o{ episode_event : provider
    source ||--o{ episode_event : source
    collection_snapshot ||--o{ episode_event : snapshot
    source ||--o{ source_healthcheck : checks
    job_execution ||--o{ collection_snapshot : job
    sync_run ||--o{ sync_run_event : events
```

---

## 3. Tabelle

### 3.1 Identità e sicurezza

#### `app_user`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `email` | CITEXT UNIQUE NOT NULL | Login. |
| `password_hash` | TEXT NOT NULL | Argon2id. |
| `is_admin` | BOOLEAN | Single-user: true. |
| `is_active` | BOOLEAN | Disattivazione senza cancellazione. |
| `created_at`, `updated_at`, `last_login_at` | TIMESTAMPTZ | UTC. |

#### `session`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID FK `app_user` | `ON DELETE CASCADE`. |
| `token_hash` | BYTEA UNIQUE | SHA-256 del token opaco; il token in chiaro sta solo nel cookie. |
| `csrf_hash` | BYTEA | Hash del token CSRF. |
| `expires_at`, `last_seen_at`, `revoked_at` | TIMESTAMPTZ | Scadenza, idle, revoca. |
| `ip`, `user_agent` | INET/TEXT | Audit. |

#### `credential`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `scope` | TEXT | `SOURCE`, `TARGET`, `SYSTEM`. |
| `source_id` | UUID FK `source` NULL | Solo per `SOURCE`. |
| `key` | TEXT | Es. `api_key`, `partner_token`, `s3_secret_key`. |
| `ciphertext`, `nonce` | BYTEA | AES-256-GCM. |
| `key_version` | SMALLINT | Rotazione. |
| `masked_hint` | TEXT | Es. `••••1234`. |
| `last_used_at`, `last_verified_at` | TIMESTAMPTZ | |

Vincolo: `UNIQUE NULLS NOT DISTINCT (scope, source_id, key)`.

### 3.2 Fonti e provider

#### `source`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `key` | TEXT UNIQUE | `tmdb`, `justwatch_partner`, `justwatch_export`, `manual_csv`. |
| `name` | TEXT | Nome UI. |
| `type` | TEXT | `API`, `DATA_EXPORT`, `MANUAL_CSV`. |
| `base_url` | TEXT | Solo host allowlist. |
| `config` | JSONB | Non segreto: locale, page size, ecc. |
| `capabilities` | JSONB | Capability flags dichiarate. |
| `status` | TEXT | `UNCONFIGURED`, `OK`, `DEGRADED`, `ERROR`, `DISABLED`. |
| `status_message` | TEXT | Messaggio UI. |
| `last_healthcheck_at`, `last_success_at` | TIMESTAMPTZ | |

#### `provider`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `slug` | TEXT UNIQUE | `netflix`, `prime-video`, ecc. |
| `name` | TEXT | Nome canonico. |
| `logo_url`, `website_url` | TEXT | Display. |

#### `provider_mapping`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `provider_id` | UUID FK `provider` | |
| `source_id` | UUID FK `source` | |
| `country_code` | CHAR(2) | `IT`. |
| `external_provider_id` | TEXT | ID TMDb/JustWatch. |
| `external_name` | TEXT | Nome nella fonte. |
| `metadata` | JSONB | Display priority, varianti. |

Vincolo: `UNIQUE (source_id, country_code, external_provider_id)`.
**Nota:** i provider ID non vanno hardcodati; si risolvono a ogni sync e si mappano sull'anagrafica canonica. Le varianti "Amazon Channel", "with Ads", "basic" sono mapping separati, non lo stesso provider.

### 3.3 Collezioni

#### `collection`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `slug` | TEXT UNIQUE | Stabile, leggibile. |
| `source_id` | UUID FK `source` | |
| `provider_id` | UUID FK `provider` | |
| `country_code` | CHAR(2) | Default `IT`. |
| `media_type` | TEXT | `MOVIE`, `SHOW`. |
| `kind` | TEXT | `CATALOG`, `RECENTLY_ADDED`, `UPCOMING`, `CHART`, `CUSTOM_FILTER`. |
| `origin` | TEXT | `OFFICIAL`, `AGGREGATOR`, `CUSTOM`. |
| `date_basis` | TEXT | `PROVIDER_OFFICIAL`, `AGGREGATOR_FIRST_SEEN`, `APP_FIRST_SEEN`, `UNKNOWN`. |
| `name` | TEXT | Etichetta UI. |
| `source_collection_key` | TEXT | Chiave nella fonte (provider slug, genere, chart id). |
| `source_url` | TEXT | URL sorgente, se disponibile. |
| `offer_types` | TEXT[] | Default `{FLATRATE}`. |
| `filters` | JSONB | Genere, anno, ecc. |
| `quality_flags` | JSONB | `partial_pages`, `unverified_provider_mapping`, `added_date_missing`, ecc. |
| `sort_mode` | TEXT | `SOURCE_ORDER`, `POPULARITY`, `TITLE`, `RELEASE_DATE`, `ADDED_DATE`, `CUSTOM`. |
| `is_active` | BOOLEAN | |
| `last_valid_snapshot_id` | UUID FK `collection_snapshot` | Deferrable; punta all'ultimo snapshot valido. |

Vincolo: `UNIQUE (source_id, provider_id, country_code, media_type, kind, source_collection_key)` dove la chiave non è null.

**Regola di etichettatura:**
- `OFFICIAL` richiede una fonte ufficiale verificata e un URL.
- `AGGREGATOR` richiede `source_id` di un aggregatore e un `date_basis` coerente.
- `CUSTOM` è una derivazione dell'app o un filtro utente; non può essere presentata come categoria del provider.

### 3.4 Media e disponibilità

#### `media`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `media_type` | TEXT | `MOVIE`, `SHOW`. |
| `tmdb_id` | BIGINT | Chiave principale. |
| `imdb_id` | TEXT | Fallback. |
| `tvdb_id`, `trakt_id` | BIGINT | Altri ID. |
| `title`, `original_title` | TEXT | Display, non chiave. |
| `release_year` | SMALLINT | |
| `metadata` | JSONB | Overview, poster, generi, runtime. |
| `resolution_status` | TEXT | `RESOLVED`, `UNRESOLVED`, `AMBIGUOUS`. |
| `not_found_count` | INTEGER | Rifiuti consecutivi di MDBList; dopo 3 il media è soppresso. |
| `sync_suppressed_until` | TIMESTAMPTZ | Riattivabile manualmente. |

Vincoli:
- `UNIQUE (tmdb_id, media_type) WHERE tmdb_id IS NOT NULL`
- `UNIQUE (imdb_id, media_type) WHERE imdb_id IS NOT NULL`
- `CHECK (tmdb_id IS NOT NULL OR imdb_id IS NOT NULL OR tvdb_id IS NOT NULL OR trakt_id IS NOT NULL)`

**Non si crea un `media` senza almeno un ID esterno.** Gli item non risolti restano in `snapshot_item` con `media_id NULL` e `resolution_status='UNRESOLVED'`.

#### `availability`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `media_id` | UUID FK `media` | |
| `provider_id` | UUID FK `provider` | |
| `country_code` | CHAR(2) | |
| `offer_type` | TEXT | `FLATRATE`, `RENT`, `BUY`, `ADS`, `FREE`. |
| `presentation_type` | TEXT | SD/HD/4K. |
| `channel`, `plan` | TEXT | Canale/piattaforma. |
| `source_id` | UUID FK `source` | |
| `source_offer_id` | TEXT | ID offerta nella fonte. |
| `source_date_created` | DATE | JustWatch `date_created`, se disponibile. |
| `first_seen_at`, `last_seen_at`, `last_checked_at` | TIMESTAMPTZ | Osservazione. |
| `is_active` | BOOLEAN | |
| `metadata` | JSONB | Prezzo, valuta, URL. |

Vincolo: `UNIQUE NULLS NOT DISTINCT (media_id, provider_id, country_code, offer_type, presentation_type, channel, plan, source_id)`.

**Nota:** `first_seen_at` non è la data di aggiunta del provider. È la prima osservazione dell'app. La data dichiarata dalla fonte va in `source_date_created` e va etichettata con `date_basis`.

### 3.5 Snapshot

#### `collection_snapshot`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `collection_id` | UUID FK `collection` | |
| `status` | TEXT | `RUNNING`, `COMPLETE`, `INCOMPLETE`, `FAILED`, `CANCELLED`. |
| `quality` | TEXT | `CLEAN`, `WARNINGS`, `ANOMALY`. |
| `is_valid` | BOOLEAN | Solo `COMPLETE` + `CLEAN` + item > 0 + 0 errori + 0 unresolved. |
| `started_at`, `finished_at` | TIMESTAMPTZ | |
| `pages_expected`, `pages_fetched` | INTEGER | Completezza. |
| `items_count`, `resolved_count`, `unresolved_count`, `duplicate_count`, `error_count` | INTEGER | Contatori. |
| `errors`, `warnings` | JSONB | Dettagli. |
| `source_revision` | TEXT | ETag/last-modified/dump date. |
| `checksum` | TEXT | SHA-256 degli ID normalizzati. |
| `job_execution_id` | UUID FK `job_execution` | |

Vincoli:
- `CHECK (NOT is_valid OR (status='COMPLETE' AND quality='CLEAN' AND items_count > 0 AND error_count = 0 AND unresolved_count = 0))`
- `UNIQUE (collection_id) WHERE status='RUNNING'` — un solo snapshot in corso per collezione.

**Regola:** uno snapshot `COMPLETE` con `quality='WARNINGS'` può essere usato per APPEND_ONLY, ma non per MIRROR. `is_valid=false` non significa "dati inutili": significa "non autorizza rimozioni".

#### `snapshot_item`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `snapshot_id` | UUID FK `collection_snapshot` | `ON DELETE CASCADE`. |
| `media_id` | UUID FK `media` NULL | NULL se non risolto. |
| `position` | INTEGER | Ordine nella fonte. |
| `source_item_id` | TEXT | ID nella fonte. |
| `source_payload` | JSONB | Payload normalizzato/anonimizzato. |
| `source_date_created` | DATE | |
| `date_basis` | TEXT | |
| `resolution_status` | TEXT | `RESOLVED`, `UNRESOLVED`, `AMBIGUOUS`. |
| `resolution_error` | TEXT | |

Vincoli:
- `UNIQUE (snapshot_id, position)`
- `UNIQUE (snapshot_id, media_id) WHERE media_id IS NOT NULL` — dedup.

### 3.6 Target MDBList e sync

#### `mdblist_target`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `remote_list_id` | BIGINT UNIQUE | **Chiave stabile.** |
| `remote_slug` | TEXT | Display; può cambiare. |
| `remote_url` | TEXT | Display. |
| `name` | TEXT | |
| `mediatype` | TEXT | `MOVIE`, `SHOW`, `SEASON`, `EPISODE`. |
| `is_private` | BOOLEAN | |
| `item_count` | INTEGER | Letto dalla lista. |
| `last_verified_at`, `last_remote_read_at` | TIMESTAMPTZ | |
| `capabilities` | JSONB | `supports_reorder`, `max_reorder_batch`, ecc. |

#### `sync_binding`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `collection_id` | UUID FK `collection` | |
| `target_id` | UUID FK `mdblist_target` | |
| `mode` | TEXT | `MIRROR`, `APPEND_ONLY`. |
| `schedule_cron` | TEXT | Es. `0 6 * * *`. |
| `timezone` | TEXT | Default `Europe/Rome`. |
| `is_enabled` | BOOLEAN | |
| `policy_version`, `policy_accepted_at`, `policy_accepted_by` | TEXT/TIMESTAMPTZ/UUID | Conferma esplicita. |
| `max_removal_absolute` | INTEGER | Default 50. |
| `max_removal_percent` | NUMERIC(5,2) | Default 10.00. |
| `max_addition_percent` | NUMERIC(5,2) | Default 50.00. |
| `preserve_order` | BOOLEAN | Default false. |
| `reorder_enabled` | BOOLEAN | Default true; disattivabile per liste grandi/fragili. |
| `require_manual_review` | BOOLEAN | Default true. |
| `schedule_policy` | TEXT | `AUTO_APPLY_IF_SAFE`, `ALWAYS_APPROVE`, `DRY_RUN_ONLY`. |
| `auto_apply_max_removals` | INTEGER | Default 5. |
| `auto_apply_max_removal_ratio` | NUMERIC(5,2) | Default 2.00%. |
| `max_plan_age_minutes` | INTEGER | Default 60; oltre, la conferma scade. |
| `last_run_id` | UUID FK `sync_run` | Deferrable. |
| `next_run_at` | TIMESTAMPTZ | Calcolato dallo scheduler. |

Vincoli:
- `UNIQUE (collection_id, target_id)`
- `UNIQUE (target_id) WHERE is_enabled = true` — un solo writer attivo per target.
- `CHECK (NOT is_enabled OR (policy_accepted_at IS NOT NULL AND policy_version IS NOT NULL))`
- `media_type` + FK composita `(collection_id, media_type) → collection(id, media_type)` e `(target_id, media_type) → mdblist_target(id, mediatype)`: un binding non può collegare una collezione film a una lista serie.

**Separazione film/serie a livello DB:** `collection` e `mdblist_target` hanno `UNIQUE (id, media_type)`; `sync_binding` e `sync_run` portano `media_type` e FK composite. `episode_event` ha `media_type='SHOW'` e FK composita a `media(id, media_type)`. Questo impedisce di mescolare film e serie anche con una scrittura manuale.

#### `sync_run`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `binding_id` | UUID FK `sync_binding` | |
| `target_id` | UUID FK `mdblist_target` | Denormalizzato per il lock/unique per target. |
| `media_type` | TEXT | Coerente con binding e target. |
| `snapshot_id` | UUID FK `collection_snapshot` | |
| `mode` | TEXT | |
| `status` | TEXT | `PENDING`, `PREFLIGHT`, `PLANNING`, `AWAITING_APPROVAL`, `APPLYING`, `VERIFYING`, `SUCCEEDED`, `PARTIAL`, `FAILED`, `BLOCKED`, `CANCELLED`. |
| `is_dry_run` | BOOLEAN | |
| `trigger` | TEXT | `MANUAL`, `SCHEDULED`, `RETRY`. |
| `plan_hash`, `snapshot_hash` | TEXT | Conferma legata al piano visto. |
| `order_enforced` | BOOLEAN | False se reorder disabilitato/fallito. |
| `warnings` | JSONB | Es. `ORDER_NOT_ENFORCED`. |
| `parent_run_id` | UUID FK `sync_run` | Ripresa da un run precedente. |
| `not_before` | TIMESTAMPTZ | Attesa per rate limit/finestra. |
| `abort_reason` | TEXT | `LOCK_HELD`, `NO_ACCESS`, `SNAPSHOT_EMPTY`, ecc. |
| `threshold_breached`, `requires_approval`, `approved_at`, `approved_by` | BOOL/TIMESTAMPTZ/UUID | Revisione manuale. |
| `started_at`, `finished_at` | TIMESTAMPTZ | |
| `source_item_count`, `remote_item_count` | INTEGER | |
| `to_add_count`, `to_remove_count` | INTEGER | Piano. |
| `added_count`, `removed_count`, `failed_count`, `uncertain_count` | INTEGER | Esecuzione. |
| `error_code`, `error_message` | TEXT | |
| `summary` | JSONB | Dettagli UI. |
| `lock_key` | TEXT | Audit del lock. |
| `requested_by` | UUID FK `app_user` | |

Vincolo: `UNIQUE (binding_id) WHERE status IN ('PENDING','PREFLIGHT','PLANNING','AWAITING_APPROVAL','APPLYING','VERIFYING')` — un solo run attivo per binding.

#### `sync_operation`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `run_id` | UUID FK `sync_run` | `ON DELETE CASCADE`. |
| `batch_id` | UUID | Raggruppa le operazioni inviate insieme. |
| `action` | TEXT | `ADD`, `REMOVE`, `REORDER`. |
| `media_id` | UUID FK `media` NULL | NULL per REORDER di chunk. |
| `remote_id` | TEXT | ID usato verso MDBList. |
| `idempotency_key` | TEXT UNIQUE | `sha256(run_id|action|media_type|tmdb_id|target_id)`. |
| `status` | TEXT | `PENDING`, `IN_FLIGHT`, `SUCCEEDED`, `FAILED`, `UNCERTAIN`, `SKIPPED`. |
| `attempt`, `max_attempts` | INTEGER | Default max 5. |
| `next_retry_at`, `reconciled_at` | TIMESTAMPTZ | Retry e riconciliazione. |
| `http_status`, `duration_ms` | INTEGER | Audit. |
| `request_hash` | TEXT | |
| `response` | JSONB | Risposta remota redatta. |
| `error_code`, `error_message` | TEXT | |
| `started_at`, `finished_at` | TIMESTAMPTZ | |

Vincoli:
- `UNIQUE (run_id, action, media_id)` — evita duplicati nello stesso run. Per REORDER, `media_id` è NULL e più righe sono ammesse (NULL distinct).
- `idempotency_key` unico globalmente.

#### `sync_run_event`
Audit leggero delle transizioni di stato: `run_id`, `from_status`, `to_status`, `message`, `created_at`. Alimenta la timeline UI.

### 3.7 Eventi stagioni/episodi

#### `episode_event`
| Colonna | Tipo | Note |
|---|---|---|
| `id` | UUID PK | |
| `show_media_id` | UUID FK `media` | La serie, non l'episodio. |
| `provider_id` | UUID FK `provider` | |
| `country_code` | CHAR(2) | |
| `source_id` | UUID FK `source` | |
| `snapshot_id` | UUID FK `collection_snapshot` NULL | |
| `event_type` | TEXT | `SEASON_ADDED`, `SEASON_REMOVED`, `EPISODE_ADDED`, `EPISODE_REMOVED`. |
| `season_number` | INTEGER | |
| `episode_number` | INTEGER NULL | |
| `occurred_at` | TIMESTAMPTZ | |
| `source_payload` | JSONB | |

Vincolo: `UNIQUE NULLS NOT DISTINCT (show_media_id, provider_id, country_code, source_id, event_type, season_number, episode_number)`.

**Regola:** un nuovo episodio non crea un nuovo `media`; crea un `episode_event` e, se il target lo supporta, può essere aggiunto come `episode` a MDBList. Di default le liste restano a livello serie.

### 3.8 Job, audit, healthcheck

#### `job_execution`
Stato persistente dei task Celery: `task_id` unico, `task_name`, `queue`, `status`, `payload`, `result`, `error_code`, `error_message`, timestamp. Serve alla dashboard e al debug; non sostituisce `sync_run`.

#### `audit_log`
`actor_user_id`, `actor_type`, `action`, `entity_type`, `entity_id`, `before`, `after`, `ip`, `user_agent`, `request_id`, `created_at`. I campi `before`/`after` sono redatti: mai segreti.

#### `source_healthcheck`
`source_id`, `status`, `latency_ms`, `message`, `details`, `checked_at`. Storico per la dashboard.

---

## 4. Enum e valori

| Dominio | Valori |
|---|---|
| `media_type` | `MOVIE`, `SHOW` |
| `collection.kind` | `CATALOG`, `RECENTLY_ADDED`, `UPCOMING`, `CHART`, `CUSTOM_FILTER` |
| `collection.origin` | `OFFICIAL`, `AGGREGATOR`, `CUSTOM` |
| `date_basis` | `PROVIDER_OFFICIAL`, `AGGREGATOR_FIRST_SEEN`, `APP_FIRST_SEEN`, `UNKNOWN` |
| `offer_type` | `FLATRATE`, `RENT`, `BUY`, `ADS`, `FREE` |
| `snapshot.status` | `RUNNING`, `COMPLETE`, `INCOMPLETE`, `FAILED`, `CANCELLED` |
| `snapshot.quality` | `CLEAN`, `WARNINGS`, `ANOMALY` |
| `sync_binding.mode` | `MIRROR`, `APPEND_ONLY` |
| `sync_run.status` | `PENDING`, `PREFLIGHT`, `PLANNING`, `AWAITING_APPROVAL`, `APPLYING`, `VERIFYING`, `SUCCEEDED`, `PARTIAL`, `FAILED`, `BLOCKED`, `CANCELLED` |
| `sync_operation.action` | `ADD`, `REMOVE`, `REORDER` |
| `sync_operation.status` | `PENDING`, `IN_FLIGHT`, `SUCCEEDED`, `FAILED`, `UNCERTAIN`, `SKIPPED` |
| `source.status` | `UNCONFIGURED`, `OK`, `DEGRADED`, `ERROR`, `DISABLED` |
| `source.type` | `API`, `DATA_EXPORT`, `MANUAL_CSV` |
| `credential.scope` | `SOURCE`, `TARGET`, `SYSTEM` |
| `episode_event.event_type` | `SEASON_ADDED`, `SEASON_REMOVED`, `EPISODE_ADDED`, `EPISODE_REMOVED` |

---

## 5. Trigger e guardie di integrità

Il DDL include trigger che rendono impossibili alcuni errori a livello di database:

| Trigger | Regola |
|---|---|
| `collection_origin_guard` | `OFFICIAL` richiede `source.is_official = true`; `AGGREGATOR` richiede `source.origin_default = 'AGGREGATOR'`. |
| `sync_run_snapshot_guard` | Lo snapshot deve appartenere alla stessa collezione, il target e il `media_type` devono coincidere con il binding, `mode` deve coincidere, lo snapshot non può essere `RUNNING`; MIRROR richiede `is_valid`, APPEND_ONLY richiede `COMPLETE` e `items_count > 0`. |
| `sync_operation_media_type_guard` | Un'operazione ADD/REMOVE deve riferirsi a un media dello stesso `media_type` del run. |
| `audit_log_append_only` | `UPDATE`/`DELETE` su `audit_log` falliscono. |
| `*_touch` | Aggiorna `updated_at` su ogni `UPDATE`. |

Queste guardie non sostituiscono la validazione applicativa: sono la seconda barriera contro bug e scritture manuali.

## 6. Indici e concorrenza

| Indice | Scopo |
|---|---|
| `media_tmdb_uq`, `media_imdb_uq` | Identità e dedup. |
| `snapshot_one_running_uq` | Un solo snapshot RUNNING per collezione. |
| `snapshot_item_media_uq` | Dedup nello snapshot. |
| `binding_one_active_target_uq` | Un solo binding attivo per target. |
| `binding_due_idx` | Query dello scheduler. |
| `run_one_active_binding_uq` | Un solo run attivo per binding. |
| `sync_operation.idempotency_key` | Idempotenza locale. |
| `availability` unique nulls not distinct | Evita duplicati di disponibilità. |
| `episode_event` unique nulls not distinct | Evita duplicati di eventi. |
| `credential` unique nulls not distinct | Una credenziale per scope/source/key. |

**Advisory lock:** `pg_try_advisory_lock(hashtext('target:' || target_id))` nel worker. L'indice unique è la seconda barriera; il lock è la prima.

---

## 7. Ordine delle migrazioni Alembic

| Revisione | Contenuto |
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
| `0011_indexes` | Indici e unique partial non creati inline. |

Regole: una sola head; `downgrade()` testato; `alembic check` in CI; nessuna modifica a revisioni rilasciate.

---

## 8. Retention

| Dato | Retention default | Note |
|---|---|---|
| `collection_snapshot` + `snapshot_item` | 90 giorni | Mantieni l'ultimo valido per collezione anche se più vecchio. |
| `sync_run` + `sync_operation` | 180 giorni | I run `PARTIAL`/`FAILED` recenti non vanno cancellati. |
| `sync_run_event` | 180 giorni | |
| `audit_log` | 180 giorni | Non cancellare eventi di sicurezza recenti. |
| `source_healthcheck` | 30 giorni | |
| `job_execution` | 30 giorni | |
| `session` scadute | 7 giorni dopo `expires_at` | |
| `credential` | Fino a revoca | Mai cancellare senza audit. |

La retention è un task `maintenance` idempotente; non deve mai cancellare l'ultimo snapshot valido o un run non terminale.

---

## 9. Regole di qualità dei dati

1. **Snapshot valido** = `COMPLETE` + `CLEAN` + `items_count > 0` + `error_count = 0` + `unresolved_count = 0`.
2. **Snapshot con warning** = `COMPLETE` + `WARNINGS`; può alimentare APPEND_ONLY, non MIRROR.
3. **Snapshot anomalo** = `COMPLETE` ma con variazione oltre soglia o catalogo vuoto; `is_valid=false`, `ANOMALY`.
4. **Elemento non risolto** = nessun `tmdb_id`/`imdb_id`; resta in `snapshot_item` con `media_id NULL`; non entra nel piano MIRROR.
5. **Duplicato** = stessa chiave `(media_type, tmdb_id)` nella stessa pagina; tiene la prima occorrenza e incrementa `duplicate_count`.
6. **Conflitto** = stesso `tmdb_id` con titoli/anni incompatibili; `AMBIGUOUS`, richiede revisione.
7. **Data** = `source_date_created` solo se la fonte la dichiara; `first_seen_at` è sempre dell'app; `date_basis` dice quale delle due stai guardando.

---

## 10. Cosa non viene memorizzato

- Nessun titolo come chiave di deduplicazione.
- Nessun episodio come `media` separato: solo `episode_event`.
- Nessun segreto in chiaro.
- Nessun payload di fonte non necessario: si conserva il minimo per audit e debug, redatto.
- Nessuna lista MDBList duplicata per simulare l'ordine.
- Nessuna categoria "ufficiale" senza fonte verificata.


---

## Fonte: `phase-01.md`

# Fase 1 — Motore di sincronizzazione

**Stato:** progettazione. Nessuna sync reale eseguita.
**Riferimenti:** [`02-mdblist-api.md`](02-mdblist-api.md), [`04-data-model.md`](04-data-model.md), [`schema.sql`](schema.sql).

---

## 1. Principi

1. **Nessuna scrittura senza piano.** Ogni run produce un piano `to_add`/`to_remove`/`to_keep`; il dry-run è sempre disponibile.
2. **Nessuna rimozione da dati incompleti.** Snapshot non valido, vuoto o anomalo → `BLOCKED`.
3. **Nessuna transazione distribuita.** Ogni modifica remota è una `SyncOperation` persistita; lo stato incerto si riconcilia leggendo il remoto.
4. **Un solo writer per target.** Advisory lock PostgreSQL + unique partial index.
5. **Nessun retry cieco.** Dopo un timeout, si legge lo stato remoto prima di ritentare.
6. **Ordine best-effort.** Il reorder MDBList è opzionale, max 1.000 elementi per chiamata, non atomico; non si ricrea la lista.
7. **Tutto tracciato.** Run, operazioni, transizioni di stato, errori e contatori sono nel DB e visibili in UI.

---

## 2. Stati

### 2.1 `SyncRun`

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PREFLIGHT
    PREFLIGHT --> PLANNING
    PREFLIGHT --> BLOCKED
    PLANNING --> AWAITING_APPROVAL
    PLANNING --> APPLYING
    PLANNING --> SUCCEEDED: dry-run
    PLANNING --> BLOCKED
    AWAITING_APPROVAL --> APPLYING: approvato
    AWAITING_APPROVAL --> CANCELLED
    APPLYING --> VERIFYING
    APPLYING --> PARTIAL
    APPLYING --> FAILED
    VERIFYING --> SUCCEEDED
    VERIFYING --> PARTIAL
    VERIFYING --> FAILED
    PARTIAL --> APPLYING: riprendi operazioni fallite
    FAILED --> APPLYING: retry manuale
    SUCCEEDED --> [*]
    PARTIAL --> [*]
    FAILED --> [*]
    BLOCKED --> [*]
    CANCELLED --> [*]
```

| Stato | Significato | Scritture remote |
|---|---|---|
| `PENDING` | Run creato, in coda. | No |
| `PREFLIGHT` | Verifica credenziali, target, snapshot, lock. | No |
| `PLANNING` | Lettura remota e calcolo del piano. | No |
| `AWAITING_APPROVAL` | Soglie superate o revisione richiesta. | No |
| `APPLYING` | Add/remove in batch. | Sì |
| `VERIFYING` | Rilettura e riconciliazione. | No (solo letture) |
| `SUCCEEDED` | Contenuto e ordine (se richiesto) allineati. | — |
| `PARTIAL` | Alcune operazioni fallite/incerte; contenuto parziale. | — |
| `FAILED` | Errore fatale, nessuna operazione riuscita o auth/permessi. | — |
| `BLOCKED` | Policy: snapshot invalido/vuoto, soglie, target non scrivibile. | No |
| `CANCELLED` | Annullato prima dell'applicazione. | No |

### 2.2 `SyncOperation`

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> IN_FLIGHT
    IN_FLIGHT --> SUCCEEDED
    IN_FLIGHT --> FAILED
    IN_FLIGHT --> UNCERTAIN: timeout/5xx
    UNCERTAIN --> SUCCEEDED: riconciliato presente/assente
    UNCERTAIN --> FAILED: riconciliato non applicato e tentativi esauriti
    UNCERTAIN --> PENDING: retry dopo riconciliazione
    PENDING --> SKIPPED: già presente/assente
    FAILED --> PENDING: retry manuale
    SUCCEEDED --> [*]
    SKIPPED --> [*]
    FAILED --> [*]
```

| Stato | Significato |
|---|---|
| `PENDING` | Operazione pianificata, non inviata. |
| `IN_FLIGHT` | Richiesta inviata, risposta non ancora registrata. |
| `SUCCEEDED` | Verificata sul remoto. |
| `FAILED` | Errore definitivo o tentativi esauriti. |
| `UNCERTAIN` | Timeout/5xx dopo l'invio: esito remoto ignoto. |
| `SKIPPED` | Già presente (ADD) o già assente (REMOVE). |

---

## 3. Preflight

```python
async def preflight(run_id: UUID) -> PreflightResult:
    run = await runs.get(run_id)
    binding = await bindings.get(run.binding_id)
    target = await targets.get(binding.target_id)
    snapshot = await snapshots.get(run.snapshot_id)

    # 1. Credenziale MDBList
    credential = await credentials.get_target("MDBLIST")
    if not credential:
        return block("MDBLIST_AUTH_MISSING")

    # 2. Target leggibile e proprietario
    remote = await mdblist.get_list(target.remote_list_id)
    if remote.user_id != credential.user_id:
        return block("MDBLIST_PERMISSION_DENIED")

    # 3. Snapshot utilizzabile
    if snapshot.status != "COMPLETE":
        return block("SNAPSHOT_INCOMPLETE")
    if snapshot.items_count == 0:
        return block("SNAPSHOT_EMPTY")
    if run.mode == "MIRROR" and not snapshot.is_valid:
        return block("SNAPSHOT_NOT_VALID_FOR_MIRROR")
    if run.mode == "MIRROR" and snapshot.unresolved_count > 0:
        return block("SNAPSHOT_UNRESOLVED_ITEMS")

    # 4. Lock per target
    if not await locks.try_target(target.id):
        return block("SYNC_ALREADY_RUNNING")

    # 5. Policy
    if binding.is_enabled and binding.policy_accepted_at is None:
        return block("POLICY_NOT_ACCEPTED")

    return PreflightResult(ok=True, remote=remote)
```

**Regole:**
- Il preflight non scrive nulla sul remoto.
- Se la lista remota non è leggibile completamente, il run è `BLOCKED`.
- Se il target è una lista dinamica o non posseduta, add/remove/reorder possono restituire `403`: trattare come blocco definitivo.
- Il lock va rilasciato in `finally`, anche in caso di eccezione.

---

## 4. Piano

### 4.1 Normalizzazione delle chiavi

```python
def media_key(media_type: str, tmdb_id: int | None, imdb_id: str | None) -> tuple[str, str] | None:
    if tmdb_id is not None:
        return (media_type, f"tmdb:{tmdb_id}")
    if imdb_id is not None:
        return (media_type, f"imdb:{imdb_id}")
    return None
```

- `media_type` sempre presente: un film e una serie con lo stesso ID numerico sono entità diverse.
- Gli item non risolti non entrano nel piano; vengono contati e mostrati.
- I duplicati nella sorgente vengono collassati prima del diff.

### 4.2 MIRROR

```python
source_keys = {media_key(i) for i in snapshot.resolved_items}
remote_keys = {media_key(i) for i in remote_items}

to_add = source_keys - remote_keys
to_remove = remote_keys - source_keys
to_keep = source_keys & remote_keys
```

- `to_remove` è calcolato **solo** se lo snapshot è valido e non vuoto.
- Se `to_remove` supera le soglie, il run va in `AWAITING_APPROVAL`.
- Se la lista remota contiene elementi non risolvibili (senza TMDB/IMDb), non rimuoverli automaticamente: vanno in `unmapped_remote` e richiedono revisione.
- Se la lista remota contiene duplicati dello stesso `MediaKey`, non rimuoverli: `remove` potrebbe cancellare tutte le occorrenze. Vanno in `remote_duplicates` e sono mostrati in UI.
- Gli elementi locali non risolti (`unresolved`) non entrano in `to_remove`: non esistono remotamente, quindi non devono causare rimozioni.

### 4.3 APPEND_ONLY

```python
to_add = source_keys - remote_keys
to_remove = set()
```

- Nessuna rimozione, mai.
- Se un elemento è già presente, `SKIPPED`.
- Se lo snapshot è `COMPLETE` con `WARNINGS`, le aggiunte risolte sono ammesse; gli unresolved vengono saltati.

### 4.4 Dry-run e `plan_hash`

- Crea un `SyncRun` con `is_dry_run=true`.
- Esegue preflight, lettura remota e piano.
- Non crea `SyncOperation` con stato `IN_FLIGHT`; può crearle in `PENDING` per mostrare il dettaglio, ma non le invia.
- Stato finale `SUCCEEDED` (piano pronto) o `BLOCKED` (policy).
- Il dry-run è sempre disponibile, anche per binding disabilitati.
- Il piano produce un `plan_hash = sha256(mode | snapshot_hash | sorted(to_add) | sorted(to_remove) | rank_target_digest | policy_version)`. La conferma manuale è legata a `plan_hash` + `snapshot_hash`: se il piano cambia o scade (`max_plan_age_minutes`, default 60), la conferma restituisce `409` e va rifatta.
- Il `snapshot_hash` è lo SHA-256 degli ID normalizzati dello snapshot usato.

---

## 5. Soglie di sicurezza

Configurazione per binding:

| Soglia | Default | Significato |
|---|---|---|
| `max_removal_absolute` | 50 | Numero massimo di rimozioni in un run. |
| `max_removal_percent` | 10% | Percentuale massima di rimozioni rispetto al remoto. |
| `max_addition_percent` | 50% | Percentuale massima di aggiunte rispetto al remoto. |
| `require_manual_review` | true | Se una soglia è superata, richiede approvazione. |

Calcolo:

```python
def evaluate_thresholds(plan, remote_count, binding) -> ThresholdResult:
    if remote_count == 0:
        # Lista vuota: aggiunte illimitate? No, applica la soglia sulle aggiunte
        # rispetto allo snapshot, non al remoto.
        addition_ratio = 1.0 if plan.to_add else 0.0
    else:
        addition_ratio = len(plan.to_add) / remote_count

    removal_ratio = len(plan.to_remove) / max(remote_count, 1)

    blocked = (
        len(plan.to_remove) > binding.max_removal_absolute
        or removal_ratio > binding.max_removal_percent / 100
        or addition_ratio > binding.max_addition_percent / 100
    )
    return ThresholdResult(blocked=blocked, ...)
```

**Regole:**
- Snapshot vuoto → `BLOCKED`, non "rimuovi tutto".
- Snapshot incompleto → `BLOCKED`, nessuna rimozione.
- Snapshot con unresolved > 0 → MIRROR `BLOCKED`; APPEND_ONLY può procedere con warning.
- Variazione anomala (es. rimozioni > 50% o aggiunte > 100%) → `AWAITING_APPROVAL`.
- Le soglie non si applicano al dry-run: il dry-run mostra il piano e segnala il blocco.

---

## 6. Esecuzione

### 6.1 Ordine di applicazione

L'ordine è **ADD → REMOVE → REORDER**:

1. aggiungere gli elementi mancanti;
2. rimuovere quelli in eccesso;
3. applicare il reorder, se richiesto.

Un fallimento a metà non deve mai lasciare la lista priva di elementi desiderati: il costo è una finestra temporanea di sovrainsieme, non distruttiva. L'ordine inverso (remove prima) potrebbe lasciare la lista incompleta se il processo si interrompe.

### 6.2 Creazione delle operazioni

```python
for key in plan.to_remove:
    operations.add(SyncOperation(
        run_id=run.id,
        action="REMOVE",
        media_id=media_id(key),
        idempotency_key=sha256(f"{run.id}|REMOVE|{key}|{target.id}"),
        status="PENDING",
    ))

for key in plan.to_add:
    operations.add(SyncOperation(
        run_id=run.id,
        action="ADD",
        media_id=media_id(key),
        idempotency_key=sha256(f"{run.id}|ADD|{key}|{target.id}"),
        status="PENDING",
    ))
```

- Le operazioni vengono create **prima** dell'invio, in una transazione DB.
- `idempotency_key` unico evita duplicati nello stesso run.
- `batch_id` raggruppa le operazioni inviate nella stessa richiesta.

### 6.3 Batch

- Dimensione batch configurabile (default 100).
- Budget scritture: 300/5 min; il client usa un token bucket Redis con margine (es. 240/5 min).
- Ordine: **ADD → REMOVE → REORDER**. Aggiungere prima evita una finestra in cui mancano elementi desiderati; il costo è un temporaneo sovrainsieme. Se la lista è vicina al limite massimo, ridurre il batch o concordare una strategia specifica, ma non rimuovere prima di aver verificato gli `ADD`.
- Dopo ogni batch:
  - `200` con contatori → marca le operazioni `SUCCEEDED`/`SKIPPED` in base a `added`/`existing`/`not_found`; per `not_found` marca `FAILED` con `MDBLIST_NOT_FOUND`.
  - `429` → rispetta `Retry-After`, non marcare nulla, riprova il batch.
  - `5xx`/timeout → marca le operazioni del batch `UNCERTAIN`, non ritentare subito.
  - `401`/`403`/`404` → `FAILED`/`BLOCKED`, stop.

### 6.4 Riconciliazione

Dopo l'applicazione (e dopo ogni batch incerto):

```python
async def reconcile(run_id: UUID):
    remote = await read_all_remote_items(target)
    remote_keys = {media_key(i) for i in remote}

    for op in operations.pending_or_uncertain(run_id):
        present = op.media_key in remote_keys
        if op.action == "ADD" and present:
            op.mark_succeeded()
        elif op.action == "REMOVE" and not present:
            op.mark_succeeded()
        elif op.attempt < max_attempts:
            op.mark_pending_for_retry()
        else:
            op.mark_failed("MDBLIST_UNCERTAIN")
```

- La lettura remota usa `cursor` + `X-Has-More`; se è incompleta, non si conclude nulla.
- La riconciliazione è la fonte di verità, non i contatori aggregati.
- Se la lista cambia durante la lettura (modifica manuale), il run va in `PARTIAL` e richiede revisione.

### 6.5 Retry

```python
def next_delay(attempt: int, retry_after: int | None) -> float:
    if retry_after is not None:
        return retry_after
    base = 0.5 * (2 ** attempt)
    cap = 30.0
    jitter = random.uniform(0.8, 1.2)
    return min(base, cap) * jitter
```

- Max 5 tentativi per operazione.
- `Retry-After` ha precedenza.
- Non retryable: `400`, `401`, `403`, `404`, schema cambiato, policy.
- Dopo un timeout: `UNCERTAIN` → riconciliazione → retry solo se l'operazione non è stata applicata.

### 6.6 Ordine (reorder)

- `preserve_order` default `false`.
- Se `true` e il target è una lista statica:
  1. attendere che add/remove siano riconciliati;
  2. leggere l'ordine corrente (`sort=usort`);
  3. costruire la sequenza desiderata dallo snapshot;
  4. se la lista ≤ 1.000 elementi: una chiamata `POST /lists/{id}/items/reorder` con tutti gli elementi nell'ordine;
  5. se > 1.000: chunk da 1.000; il primo chunk con `position=top`, i successivi con `after` = ultimo elemento del chunk precedente;
  6. rileggere `sort=usort` e verificare l'ordine;
  7. se il reorder fallisce: il run resta `SUCCEEDED` con warning `ORDER_NOT_ENFORCED` e `order_enforced=false`; il contenuto è corretto, l'ordine no. Non è un `PARTIAL`, perché non mancano elementi.
- Non cancellare e ricreare la lista.
- L'UI mostra "ordine best-effort; liste >1.000 elementi possono richiedere più passaggi e un'interruzione lascia l'ordine parziale".
- Se `reorder_enabled=false`, il run dichiara `order_enforced=false` fin dall'inizio.

### 6.7 Successi parziali

- `PARTIAL` se almeno un'operazione è `SUCCEEDED` e almeno una è `FAILED`/`UNCERTAIN`.
- Il run espone i contatori e l'elenco operazioni.
- "Riprendi" crea un nuovo run con `parent_run_id`, rilegge lo snapshot e ricalcola il piano: non riusa il piano vecchio, perché la lista può essere cambiata a mano.
- Non si nasconde un fallimento parziale come successo.
- `not_found` (ID non riconosciuto da MDBList) viene registrato per media; dopo N rifiuti consecutivi (default 3) il media è soppresso dai piani successivi, con possibilità di riattivarlo manualmente.

---

## 7. Concorrenza e idempotenza

### 7.1 Lock

```python
async def try_target_lock(conn, target_id: UUID) -> bool:
    key = f"mdblist_target:{target_id}"
    return await conn.scalar(
        "SELECT pg_try_advisory_lock(hashtextextended(:key, 0))", {"key": key}
    )
```

- Il lock è **di sessione**, non transazionale: il run attraversa più transazioni (piano, batch, riconciliazione). `pg_advisory_xact_lock` non basta.
- Il lock è per `target_id`, non per binding: due binding sullo stesso target non possono scrivere insieme.
- La connessione che tiene il lock resta aperta per tutto il run; il lock va rilasciato in `finally`.
- In caso di contesa, il run non attende: `FAILED(LOCK_HELD)` o riaccodato al tick successivo.

### 7.2 Unique partial index

- `sync_binding (target_id) WHERE is_enabled = true` → un solo binding attivo per target.
- `sync_run (binding_id) WHERE status IN (...)` → un solo run attivo per binding.
- `collection_snapshot (collection_id) WHERE status = 'RUNNING'` → una sola acquisizione per collezione.

### 7.3 Idempotenza

- `idempotency_key` unico per operazione.
- `task_id` deterministico per il task Celery.
- La creazione del run è idempotente rispetto a `binding_id` + slot temporale: lo scheduler usa `last_enqueued_slot`/`next_run_at` per non duplicare.
- Dopo un crash, il run resta `RUNNING`/`APPLYING`; uno sweep lo porta a `VERIFYING` e riconcilia.

---

## 8. Conferma e policy

- Alla creazione di un binding su una lista **esistente**, l'UI mostra:
  - numero di elementi remoti;
  - elementi che MIRROR rimuoverebbe;
  - avviso che anche gli elementi aggiunti manualmente saranno rimossi;
  - checkbox di conferma esplicita.
- `policy_accepted_at` e `policy_version` vengono salvati sul binding.
- Le sync pianificate non chiedono conferma a ogni run: l'utente ha autorizzato la policy abilitando il binding.
- `schedule_policy`:
  - `AUTO_APPLY_IF_SAFE` (default): applica solo se non ci sono blocker, nessuna soglia superata e `to_remove == 0` oppure rimozioni entro i tetti di auto-apply;
  - `ALWAYS_APPROVE`: ogni run pianificato richiede approvazione;
  - `DRY_RUN_ONLY`: il run pianificato produce solo il piano.
- Se una soglia viene superata, il run si ferma in `AWAITING_APPROVAL` e richiede una conferma manuale legata a `plan_hash`.
- Un binding disabilitato non esegue sync pianificate; il dry-run manuale resta disponibile.

---

## 9. Cosa dipende da capacità MDBList non verificate

| Capacità | Stato | Impatto |
|---|---|---|
| `POST /lists/{listid}/items/reorder` | **VERIFICATO** nello schema live; max 1.000 per chiamata | Reorder opzionale, non atomico. |
| Limite elementi per add/remove | **NON VERIFICATO** | Batch conservativi (100), misurare con API key. |
| Posizione di inserimento di `add` | **NON VERIFICATO** | Non assumere testa/coda; leggere `rank`/`usort`. |
| Semantica di `existing`/`not_found` | **PARZIALMENTE VERIFICATO** | Riconciliare con lettura completa. |
| Stabilità dello slug dopo rinomina | **NON VERIFICATO** | Usare `remote_list_id`; rileggere slug/URL. |
| Tipo statico vs dinamico | **NON VERIFICATO** | Conferma esplicita + preflight; `403` = blocco. |
| Idempotency key lato API | **NON DOCUMENTATO** | Solo idempotenza locale + riconciliazione. |
| Atomicità add/remove/reorder | **NON DOCUMENTATA** | Operation ledger + `PARTIAL` per add/remove; warning `ORDER_NOT_ENFORCED` per il reorder. |

---

## 10. Test da implementare

### Unit
- `test_mirror_plan.py`: `to_add`/`to_remove` con duplicati, unresolved, lista vuota.
- `test_append_only.py`: nessuna rimozione, anche con differenze.
- `test_thresholds.py`: soglie assolute/percentuali, lista vuota, variazione anomala.
- `test_media_key.py`: film vs serie con lo stesso ID; IMDb fallback; unresolved.
- `test_retry_policy.py`: 429/Retry-After, 5xx, 4xx non retryable, jitter.
- `test_uncertain_outcome.py`: timeout → `UNCERTAIN` → riconciliazione.
- `test_reorder_chunking.py`: ≤1.000, >1.000, fallimento a metà.
- `test_state_machine.py`: transizioni valide/invalide.

### Integration (PostgreSQL/Redis)
- `test_advisory_lock.py`: due run sullo stesso target, uno solo procede.
- `test_one_active_run.py`: unique partial index.
- `test_snapshot_validity.py`: snapshot incompleto/vuoto non autorizza rimozioni.
- `test_resume_after_crash.py`: operazioni `IN_FLIGHT`/`UNCERTAIN` riprese.
- `test_partial_batch.py`: fallimento a metà, stato `PARTIAL`.
- `test_reorder_readback.py`: ordine letto con `sort=usort`.

### Contract (MDBList)
- `test_mdblist_add_remove.py`: payload, contatori, `not_found`.
- `test_mdblist_reorder.py`: payload, `updated`, `not_found`, limite 1.000.
- `test_mdblist_429.py`: `Retry-After`.
- `test_mdblist_timeout.py`: timeout dopo invio, riconciliazione.
- `test_mdblist_forbidden.py`: lista non propria → `403`.

### E2E
- Fonte fixture → snapshot → preview → dry-run → sync → verifica.
- Snapshot invalido → `BLOCKED`, zero scritture.
- Doppio click → un solo run.
- Timeout → `UNCERTAIN` → riconciliazione → `SUCCEEDED`.
- Soglia superata → `AWAITING_APPROVAL`, zero scritture.

**Regola:** i test non devono mai modificare liste MDBList reali. Usare `respx`/mock server e fixture sintetiche etichettate.


---

## Fonte: `phase-01.md`

# Fase 1 — Sicurezza

**Stato:** progettazione. Nessun codice di produzione implementato.
**Modello:** app privata, single-user, esposta su Internet solo dopo security review.

---

## 1. Threat model

### Asset

| Asset | Perché è critico |
|---|---|
| API key MDBList | Può leggere/scrivere tutte le liste dell'account. |
| API key TMDb | Accesso all'API, quota e attribuzione. |
| Token/credenziali JustWatch | Accesso a dati commerciali e S3. |
| `APP_ENCRYPTION_KEY` | Decifra tutte le credenziali salvate. |
| Sessioni admin | Accesso completo all'app. |
| Database PostgreSQL | Snapshot, cronologia, configurazioni. |
| Backup | Copia completa del database. |
| Log | Possono contenere segreti se non redatti. |

### Attori e superfici

| Attore | Superficie | Minaccia |
|---|---|---|
| Internet anonimo | Login, bootstrap, API | Brute force, credential stuffing, scansione. |
| Utente malintenzionato con sessione | API | CSRF, privilege escalation, accesso a segreti. |
| Dipendenza compromessa | Build/container | Supply chain, esfiltrazione. |
| Errore operativo | Log/export/backup | Leak di segreti. |
| SSRF | URL forniti dall'utente | Accesso a metadata cloud/rete interna. |

### Minacce principali e mitigazioni

| Minaccia | Mitigazione |
|---|---|
| Credenziali predefinite | Nessuna; bootstrap con token monouso. |
| Brute force login | Argon2id + rate limit per IP+email + lockout progressivo + audit. |
| Sessione rubata | Cookie HttpOnly/Secure/SameSite, rotazione, revoca, scadenza. |
| CSRF | Double-submit + Origin/Referer check. |
| XSS | CSP strict, React escaping, nessun `dangerouslySetInnerHTML`. |
| Segreti nei log | Redazione centralizzata, test automatici. |
| Segreti nel browser | Nessun endpoint restituisce segreti; solo `masked_hint`. |
| SSRF | Host allowlist, nessun URL utente, redirect disabilitati. |
| Perdita chiave di cifratura | Custodia separata, backup offline, procedura di rotazione. |
| Backup rubato | Cifratura `age` con chiave pubblica; privata offline. |
| Supply chain | Lockfile, pin digest, `pip-audit`, `npm audit`, `trivy`. |

---

## 2. Bootstrap del primo admin

**Requisiti:**
- Nessuna credenziale predefinita.
- Il primo admin si crea una sola volta, con un token monouso.
- Dopo la creazione, il bootstrap è disabilitato.

**Flusso:**
1. Al primo avvio, l'app genera/richiede `BOOTSTRAP_TOKEN` (32 byte random, da Docker secret o file).
2. `GET /api/auth/setup` mostra la pagina di bootstrap solo se `users` è vuoto.
3. `POST /api/auth/setup` con `{token, email, password}`:
   - confronto del token in tempo costante;
   - verifica che non esistano utenti;
   - password policy (min 12 caratteri, non compromessa, non uguale all'email);
   - crea l'utente con Argon2id;
   - invalida il token (flag `bootstrap_completed=true`);
   - scrive `audit_log`.
4. Ogni tentativo con token errato è rate-limited e loggato.
5. Se `users` non è vuoto, l'endpoint risponde `409 already_bootstrapped` senza rivelare dettagli.

**Codice di esempio:**

```python
async def setup_admin(token: str, email: str, password: str) -> User:
    if await users.count() > 0:
        raise Conflict("already_bootstrapped")
    if not secrets.compare_digest(token, settings.bootstrap_token):
        await audit.record("bootstrap_failed", ip=request.ip)
        raise AuthError("invalid_token")
    validate_password(password, email)
    user = await users.create(
        email=email,
        password_hash=hash_password(password),
        is_admin=True,
    )
    await settings.set("bootstrap_completed", True)
    await audit.record("bootstrap_completed", actor=user)
    return user
```

---

## 3. Password

- **Algoritmo:** Argon2id (`argon2-cffi`).
- **Parametri:** `time_cost=3`, `memory_cost=65536` (64 MiB), `parallelism=4`, `hash_len=32`, `salt_len=16`.
- **Policy:** minimo 12 caratteri; massimo 128; consigliato generatore; nessun limite di caratteri speciali.
- **Rehash:** al login, se i parametri sono cambiati, rifare l'hash e aggiornare.
- **Reset:** non c'è reset via email in Fase 1; procedura CLI con accesso al server.
- **Audit:** login riuscito/fallito, cambio password, revoca sessioni.

```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(hash_: str, password: str) -> bool:
    try:
        return ph.verify(hash_, password)
    except VerifyMismatchError:
        return False
```

---

## 4. Sessioni

- Token opaco: `secrets.token_urlsafe(32)`.
- Nel DB si salva solo `sha256(token)`.
- Cookie: `__Host-mdbsync-session` in produzione (`Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, nessun `Domain`).
- In sviluppo HTTP: `mdbsync-session` con `Secure=false`, mai in produzione.
- Scadenza assoluta: 7 giorni; idle: 12 ore; rotazione al login e dopo privilege change.
- Logout: revoca della sessione corrente; "logout globale" revoca tutte.
- `last_seen_at` aggiornato al massimo una volta ogni 5 minuti per ridurre le scritture.

```python
def issue_session(user_id: UUID, ip: str, user_agent: str) -> tuple[str, Session]:
    token = secrets.token_urlsafe(32)
    session = sessions.create(
        user_id=user_id,
        token_hash=sha256(token.encode()),
        csrf_hash=sha256(secrets.token_bytes(32)),
        expires_at=now_utc() + timedelta(days=7),
        ip=ip,
        user_agent=user_agent,
    )
    return token, session
```

---

## 5. CSRF

- **Double-submit:** cookie `__Host-mdbsync-csrf` (non HttpOnly) con token random; header `X-CSRF-Token` obbligatorio per `POST/PUT/PATCH/DELETE`.
- Il server conserva `csrf_hash` nella sessione e confronta in tempo costante.
- **Origin/Referer check:** l'origine deve corrispondere a `APP_BASE_URL`; se assente, rifiutare per i metodi non sicuri.
- **SameSite=Lax** come difesa aggiuntiva.
- **Esclusioni:** nessuna per le mutazioni; il login è protetto da Origin check + rate limit (non ha sessione).
- **Errori:** `403 CSRF_INVALID`, senza dettagli sul token.

```python
def verify_csrf(request: Request, session: Session) -> None:
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != settings.base_url.rstrip("/"):
        raise Forbidden("csrf_origin")
    header = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get(settings.csrf_cookie_name, "")
    if not header or not cookie or not secrets.compare_digest(header, cookie):
        raise Forbidden("csrf_token")
    if not secrets.compare_digest(sha256(header.encode()), session.csrf_hash):
        raise Forbidden("csrf_token")
```

---

## 6. Rate limit e lockout

| Endpoint | Limite | Finestra | Chiave |
|---|---|---|---|
| `POST /auth/login` | 5 tentativi | 15 min | IP + email |
| `POST /auth/setup` | 3 tentativi | 15 min | IP |
| `POST /auth/change-password` | 3 | 15 min | utente |
| `POST /bindings/{id}/runs` | 5 | 1 min | utente |
| API globale | 300 richieste | 1 min | sessione/IP |

- Redis `INCR` + `EXPIRE`; se Redis non è disponibile, fallback in memoria con limite più severo (fail-closed per login).
- Lockout progressivo: dopo 5 fallimenti, 15 min; dopo 10, 60 min; dopo 20, blocco manuale.
- Messaggi generici: "Credenziali non valide" (non rivelare se l'email esiste).
- Audit di ogni lockout.

---

## 7. Credenziali delle integrazioni

### 7.1 Cifratura

- **Algoritmo:** AES-256-GCM (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`).
- **Chiave:** 32 byte, da `APP_ENCRYPTION_KEY` (base64) o Docker secret; mai nel DB.
- **Nonce:** 12 byte random per ogni cifratura.
- **AAD:** `scope|source_id|key|key_version` per legare il ciphertext al contesto.
- **key_version:** permette la rotazione; il decrypt usa la versione salvata.
- **Storage:** `ciphertext`, `nonce`, `key_version`, `masked_hint`.
- **Masking:** mostra solo gli ultimi 4 caratteri, es. `••••a1b2`.
- **Mai in risposta:** gli endpoint restituiscono solo `configured`, `masked_hint`, `key_version`, `last_verified_at`.

```python
import os, base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def encrypt_secret(plaintext: str, key: bytes, aad: bytes) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode(), aad)
    return ct, nonce

def decrypt_secret(ct: bytes, nonce: bytes, key: bytes, aad: bytes) -> str:
    return AESGCM(key).decrypt(nonce, ct, aad).decode()
```

### 7.2 Rotazione

1. Aggiungere la nuova chiave a `APP_ENCRYPTION_KEYS` con un nuovo `key_version`.
2. Impostare `APP_ENCRYPTION_ACTIVE_VERSION` alla nuova versione.
3. Eseguire `python -m app.cli rotate-credentials`: decifra con la vecchia, cifra con la nuova, aggiorna `key_version`.
4. Verificare che tutti i record siano alla nuova versione.
5. Rimuovere la vecchia chiave solo dopo il backup e la verifica.

### 7.3 Redazione

- Redigere: `Authorization`, `apikey`, `token`, `password`, `secret`, `access_key`, `secret_key`, `cookie`, `set-cookie`.
- Redigere le query string che contengono `apikey`/`token`.
- Non loggare i body delle richieste di credenziali.
- Test automatico: cercare pattern di API key nei log.

---

## 8. SSRF

- **Nessun URL arbitrario** fornito dall'utente viene fetchato.
- I connettori usano base URL fisse e allowlist di host:
  - `api.themoviedb.org`
  - `api.mdblist.com`
  - `apis.justwatch.com` (solo se contratto)
  - `jw-data-partner-out.s3.amazonaws.com` (solo se contratto)
- L'import di una lista MDBList accetta solo ID o URL `mdblist.com/lists/...`; il backend estrae l'ID e chiama l'API, non fetcha l'URL.
- HTTPX: `follow_redirects=False`, timeout 20 s, limite dimensione risposta.
- Risoluzione DNS: se un host allowlist risolve a IP privato/link-local, rifiutare (protezione DNS rebinding).
- Nessun proxy utente.

---

## 9. Logging e audit

- **Formato:** JSON strutturato, timestamp UTC, `level`, `logger`, `message`, `request_id`, `user_id`, `source_id`, `target_id`, `run_id`, `job_id`, `duration_ms`, `outcome`.
- **Redazione:** centralizzata nel processor di logging; nessuna eccezione.
- **Audit:** login, logout, bootstrap, cambio password, creazione/modifica/eliminazione binding, cambio credenziali, avvio sync, approvazione soglie, export.
- **Retention:** log 30 giorni; audit 180 giorni.
- **Accesso:** i log non sono esposti via API; solo l'admin via filesystem/console.

---

## 10. Header, CORS, TLS

### Header (Caddy/API)

```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https://image.tmdb.org; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
X-Frame-Options: DENY
```

- **CORS:** nessuna origine cross-site in produzione; stessa origine. In sviluppo, `http://localhost:5173` esplicitamente.
- **TLS:** Caddy con Let's Encrypt; HSTS solo dopo aver verificato HTTPS.
- **Cookie:** `__Host-` richiede `Secure`, `Path=/`, nessun `Domain`.

---

## 11. Backup e ripristino

- **Cosa:** solo PostgreSQL (`pg_dump -Fc`); Redis non è un asset.
- **Cifratura:** `age` con chiave pubblica; la privata è offline.
- **Retention:** 7 giornalieri, 4 settimanali, 6 mensili.
- **Verifica:** restore mensile su DB scratch; `alembic current` e conteggi.
- **Chiave di cifratura:** backup separato, mai nello stesso bucket del DB.
- **Disaster recovery:** RPO 24 h, RTO 2 h; scheduler fermo finché i run non terminali non sono riconciliati.

---

## 12. Supply chain

- Lockfile Python (`uv.lock`) e Node (`package-lock.json`).
- Pin delle immagini Docker per digest.
- `pip-audit`, `npm audit --omit=dev`, `trivy fs`, `gitleaks` in CI.
- Container non-root, `read_only`, `cap_drop: ALL`, `no-new-privileges`.
- Nessuna dipendenza non necessaria; rivedere le nuove dipendenze.
- SBOM generato in CI (opzionale ma consigliato).

---

## 13. Test di sicurezza

| Test | Cosa verifica |
|---|---|
| `test_bootstrap_once.py` | Il bootstrap funziona una sola volta; token errato non crea utenti. |
| `test_password_hash.py` | Argon2id, rehash, policy. |
| `test_session_cookie.py` | Flag HttpOnly/Secure/SameSite, scadenza, revoca. |
| `test_csrf.py` | Mutazione senza token → 403; Origin errata → 403. |
| `test_login_rate_limit.py` | Lockout dopo N tentativi; messaggio generico. |
| `test_crypto_roundtrip.py` | Encrypt/decrypt, AAD errata, key_version. |
| `test_log_redaction.py` | Nessun token/apikey/cookie nei log. |
| `test_ssrf_allowlist.py` | Host non allowlist → errore; redirect → errore. |
| `test_secret_not_in_api.py` | Le risposte non contengono segreti. |
| `test_backup_encryption.py` | Il dump è cifrato e ripristinabile. |
| `test_prod_guards.py` | `APP_ENV=production` rifiuta mock/URL non ufficiali. |

---

## 14. Cosa non fare

- Non inserire segreti in `.env` in produzione se è disponibile un secret store.
- Non restituire mai una API key, nemmeno mascherata in parte, se non gli ultimi 4 caratteri.
- Non loggare URL completi con `apikey`/`token`.
- Non accettare URL arbitrari per import/fetch.
- Non usare `SameSite=None` senza necessità.
- Non disabilitare la verifica TLS.
- Non usare `pickle`/`eval` su payload esterni.
- Non fidarsi dei dati della fonte per costruire HTML.


---

## Fonte: `phase-01.md`

# Fase 1 — Frontend e contratto API

**Stato:** progettazione. Nessuna UI implementata.
**Vincoli dalla ricerca:** TMDb è l'unica fonte abilitata (`AGGREGATOR`, disponibilità corrente, nessuna data di aggiunta); JustWatch è `BLOCCATO`; MDBList supporta reorder ma non idempotenza/atomicità. La UI non promette "aggiunte recenti ufficiali" né "ordine garantito".

---

## 1. Pagine e route

| Route | Pagina | Endpoint principali |
|---|---|---|
| `/login` | Login | `POST /api/v1/auth/login` |
| `/bootstrap` | Primo admin | `POST /api/v1/auth/bootstrap` |
| `/app` | Dashboard | `GET /api/v1/dashboard` |
| `/app/providers` | Provider | `GET /api/v1/providers` |
| `/app/providers/:providerId` | Dettaglio provider | `GET /api/v1/providers/{id}` |
| `/app/collections` | Collezioni | `GET /api/v1/collections` |
| `/app/collections/:collectionId` | Dettaglio collezione | `GET /api/v1/collections/{id}`, `/snapshots` |
| `/app/bindings` | Binding | `GET /api/v1/bindings` |
| `/app/bindings/new` | Wizard binding (8 step) | `/previews`, `/targets`, `/bindings` |
| `/app/bindings/:bindingId` | Dettaglio binding | `GET /api/v1/bindings/{id}`, `/runs` |
| `/app/runs` | Run | `GET /api/v1/runs` |
| `/app/runs/:runId` | Dettaglio sync | `GET /api/v1/runs/{id}`, `/operations` |
| `/app/settings` | Impostazioni | `GET/PATCH /api/v1/settings` |
| `/app/settings/credentials` | Credenziali | `GET/PUT/DELETE /api/v1/credentials` |
| `/app/settings/system` | Sistema | `GET /api/v1/health`, `/ready` |

Guardie:
- `RequireSession`: 401 → `/login?next=...`.
- `RequireAdmin`: bootstrap, settings, credenziali.
- `RequireBootstrap`: se non esiste un admin, redirect a `/bootstrap`.

---

## 2. Componenti e stati

### 2.1 Componenti UI

`components/ui`:
- `Button`, `Input`, `Select`, `Checkbox`, `Dialog`, `Stepper`, `Table`, `Pagination`, `Tabs`, `Toast`.
- `StatusPill`: stato run/operazione con testo + icona, mai solo colore.
- `OriginBadge`: `OFFICIAL` / `AGGREGATOR` / `CUSTOM`.
- `DateBasisBadge`: `PROVIDER_OFFICIAL` / `AGGREGATOR_FIRST_SEEN` / `APP_FIRST_SEEN` / `UNKNOWN`.
- `ErrorState`, `EmptyState`, `Skeleton`, `StaleBanner`, `ConfirmDialog`.
- `QualityBanner`: snapshot incompleto, unresolved, catalogo vuoto, ordine parziale.

### 2.2 Etichette di provenienza

| Origine | Etichetta UI | Forma |
|---|---|---|
| `OFFICIAL` | "Categoria ufficiale del provider" | bordo pieno, icona edificio |
| `AGGREGATOR` | "Raccolta di aggregatore: {source}" | bordo tratteggiato, icona nodo |
| `CUSTOM` | "Filtro personalizzato" | sfondo neutro, icona filtro |

| `date_basis` | Etichetta UI |
|---|---|
| `PROVIDER_OFFICIAL` | "Data dichiarata dal provider" |
| `AGGREGATOR_FIRST_SEEN` | "Prima osservazione JustWatch (aggregatore)" |
| `APP_FIRST_SEEN` | "Prima osservazione dell'app (non ufficiale)" |
| `UNKNOWN` | "Data di aggiunta non disponibile" |

**Regola:** se `date_basis=UNKNOWN`, la UI non mostra "Aggiunte recenti" come titolo; mostra "Disponibilità corrente" o "Raccolta".

### 2.3 Stati di caricamento

| Stato | Trigger | Resa |
|---|---|---|
| loading | `isPending` | skeleton con la geometria della tabella |
| empty | `items.length === 0` senza errore | `EmptyState` con azione contestuale |
| error | `isError` | `ErrorState` con categoria, `request_id`, "Riprova" |
| stale | `dataUpdatedAt` oltre soglia | `StaleBanner` non bloccante con ora ultimo aggiornamento |
| blocked | `409 policy_*` o preview `BLOCKED` | motivo, soglia superata, link alla revisione |
| partial | run `PARTIAL` | banner con operazioni fallite/incerte e "Riprendi" |

### 2.4 TanStack Query

- `staleTime: 30_000`.
- `retry`: solo `5xx`, max 2.
- `refetchOnWindowFocus`: solo per run attivi.
- Polling:

| Query | Polling | Note |
|---|---|---|
| `dashboard`, `health` | 30 s | sospeso con `document.hidden` |
| `runs` | 5 s se esiste un run non terminale | `refetchIntervalInBackground: false` |
| `run` | 2 s finché `status ∈ {PENDING, PREFLIGHT, PLANNING, AWAITING_APPROVAL, APPLYING, VERIFYING}` | stop su stato terminale |
| `preview`, `job` | 1,5–2 s finché `RUNNING` | stop su `READY`/`BLOCKED`/`FAILED` |
| collezioni, provider, binding, settings | nessuno | invalidazione esplicita |

Invalidazione:
- snapshot creato → `snapshot*`, `collection`, `collections`, `dashboard`.
- binding creato/aggiornato/eliminato → `bindings`, `binding`, `dashboard`.
- run avviato/terminale → `runs`, `run`, `binding`, `dashboard`, `target`.
- credenziale/settings → `credentials`, `health`, `sources`, `settings`.

---

## 3. Wizard a 8 step

Un solo `useForm<BindingDraft>` con `zodResolver`; ogni step valida il proprio sotto-schema; il submit valida l'intero oggetto. Bozza in `sessionStorage` (`binding-draft:v1`, TTL 24 h, cancellata su submit/annulla), mai `localStorage`, nessun segreto.

| Step | Campo | Validazione | Dati |
|---|---|---|---|
| 1. Provider e paese | `country` (`IT`), `providerId` | provider abilitato | `/providers?country=IT` |
| 2. Fonte | `sourceId` | fonte `OK`/`DEGRADED` con capacità `catalog` | `/sources` |
| 3. Collezione | `collectionId` | coerente con provider e fonte | `/collections` |
| 4. Film o serie | `mediaType` | `MOVIE`/`SHOW`, coerente con la collezione | locale |
| 5. Anteprima | `previewId`, `snapshotId`, `acknowledged` | snapshot `valid`; conferma se `to_remove > 0` | `POST /previews` |
| 6. Lista | `targetMode`, `targetId`/`newListName`, `private` | nome 3–80 caratteri | `/targets/discover`, `POST /previews` |
| 7. Modo e soglie | `mode`, `schedule`, `scheduleTime`, `maxRemovalPct`, `maxRemovalAbs`, `preserveOrder`, `reorderEnabled`, `schedulePolicy`, `requireReview` | soglie > 0; orario `HH:MM` | `/bindings/defaults` |
| 8. Conferma | `policyAccepted`, `confirmName` | spunta; nome collezione digitato | `POST /bindings` |

```ts
const step6Schema = z.object({
  targetMode: z.enum(["existing", "new"]),
  targetId: z.string().uuid().optional(),
  newListName: z.string().trim().min(3).max(80).optional(),
}).superRefine((v, ctx) => {
  if (v.targetMode === "existing" && !v.targetId)
    ctx.addIssue({ code: "custom", path: ["targetId"], message: "Seleziona una lista." });
  if (v.targetMode === "new" && !v.newListName)
    ctx.addIssue({ code: "custom", path: ["newListName"], message: "Inserisci un nome." });
});

const step7Schema = z.object({
  mode: z.enum(["MIRROR", "APPEND_ONLY"]),
  schedule: z.enum(["MANUAL", "DAILY", "WEEKLY"]),
  scheduleTime: z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, "Orario non valido (HH:MM)."),
  maxRemovalPct: z.number().min(0).max(50),
  maxRemovalAbs: z.number().int().min(0).max(5000),
  preserveOrder: z.boolean(),
  reorderEnabled: z.boolean(),
  schedulePolicy: z.enum(["AUTO_APPLY_IF_SAFE", "ALWAYS_APPROVE", "DRY_RUN_ONLY"]),
  requireReview: z.boolean(),
});
```

Navigazione:
- `?step=1..8` nell'URL; `Stepper` con `aria-current="step"`.
- "Indietro" è un link (tasto back); "Avanti" valida e aggiorna la history.
- Aprendo uno step con i precedenti incompleti si torna al primo step invalido.
- Cambiare provider o collezione azzera `snapshotId`, `targetId` e preview, con conferma.

Step 5/6:
- La preview risponde `202`; lo step mostra skeleton e contatori; "Avanti" resta disabilitato finché `state !== "READY"`.
- Con `state === "BLOCKED"` si prosegue solo attivando `requireReview`; lo step 8 mostra l'avviso.
- Step 7 rifiuta `MIRROR` con entrambe le soglie a 0 (anche lato server: `422 thresholds_required`).
- Step 8 riepiloga `to_add`, `to_remove`, `unchanged`, `unresolved`, modo, frequenza, soglie, `preserve_order` e target; invia `policy_version`.

**Testo obbligatorio per liste esistenti:**
> "MIRROR rimuoverà dalla lista gli elementi non presenti nella collezione, inclusi quelli aggiunti manualmente. L'operazione è tracciata e reversibile solo con un nuovo snapshot/sync."

---

## 4. Contratto API REST

Base `/api/v1`, stessa origine, JSON `snake_case`, timestamp ISO 8601 UTC. Envelope errore unico. Paginazione: `page` (1-based), `page_size` (default 25, max 100) → `{items, page, page_size, total, has_more}`.

### 4.1 Auth

| Endpoint | Contratto | Errori |
|---|---|---|
| `POST /auth/bootstrap` | `{token,email,password}` → `201 {user}` | `400 invalid_token`, `409 already_bootstrapped`, `422 weak_password` |
| `POST /auth/login` | `{email,password}` → `204` + cookie sessione + cookie CSRF | `401 invalid_credentials`, `429 rate_limited`, `403 account_locked` |
| `POST /auth/logout` | — → `204` | `401` |
| `GET /auth/session` | → `{user:{id,email,role}, expires_at, csrf_required}` | `401 unauthenticated` |
| `POST /auth/change-password` | `{current_password,new_password}` → `204` | `401`, `422` |

### 4.2 Dashboard e sistema

| Endpoint | Contratto |
|---|---|
| `GET /dashboard` | `{counts:{providers,collections,bindings,active_runs}, last_runs, alerts:[{code,severity,message,resource}], stale_snapshots, sources:[{source_id,status,last_check_at}]}` |
| `GET /health` | `{status:"ok",version}` — liveness, nessuna dipendenza |
| `GET /ready` | `{status:"ok"\|"degraded",checks:{db,redis,migrations,encryption_key}}` — 503 se critico |
| `GET /jobs/{job_id}` | `{id,type,status,progress,result_ref,error}` |

### 4.3 Provider e fonti

| Endpoint | Contratto | Errori |
|---|---|---|
| `GET /providers` | `country&q&enabled&page` → `Page<Provider>` | — |
| `GET /providers/{id}` | → `Provider & {mappings, collections_count}` | `404` |
| `PATCH /providers/{id}` | `{enabled?, display_name?}` → `Provider` | `404`, `422` |
| `GET /sources` | → `[{id,key,name,status,capabilities,last_check_at,last_error}]` | — |
| `POST /sources/{id}/healthcheck` | → `202 {job_id}` | `404`, `409 source_disabled` |

`Provider`: `{id,name,slug,country,enabled,logo_url,source_id,last_seen_at}`.
`capabilities`: `catalog`, `recently_added`, `upcoming`, `charts`, `ordering`, `added_dates`, `seasons_episodes`, `full_pagination`, `data_export`, `requires_contract`.

### 4.4 Collezioni e snapshot

| Endpoint | Contratto | Errori |
|---|---|---|
| `GET /collections` | `provider_id&origin&media_type&q&page` → `Page<Collection>` | — |
| `GET /collections/{id}` | → `Collection & {latest_snapshot, binding_ids}` | `404` |
| `POST /collections` | `{provider_id,name,media_type,filter}` → `201` (`origin:"CUSTOM"`) | `422`, `409 duplicate_name` |
| `PATCH /collections/{id}` | `{name?,filter?,enabled?}` → `Collection` | `409 origin_immutable` |
| `DELETE /collections/{id}` | → `204` | `409 collection_in_use` |
| `POST /collections/{id}/snapshots` | `{reason?}` → `202 {job_id,snapshot_id}` | `409 acquisition_running` |
| `GET /collections/{id}/snapshots` | `page` → `Page<Snapshot>` | `404` |
| `GET /snapshots/{id}` | → `Snapshot` | `404` |
| `GET /snapshots/{id}/items` | `q&media_type&page` → `Page<SnapshotItem>` | `404` |

`Collection`: `{id,slug,name,provider,country,media_type,kind,origin,date_basis,source,source_url,offer_types,sort_mode,last_valid_snapshot,quality_flags}`.
`Snapshot`: `{id,collection_id,status:"RUNNING"|"COMPLETE"|"INCOMPLETE"|"FAILED",quality:"CLEAN"|"WARNINGS"|"ANOMALY",valid,expected_pages,obtained_pages,item_count,unresolved_count,error_count,started_at,finished_at,completeness_reason}`.
`valid` è calcolato dal backend, mai dalla UI.

### 4.5 Target MDBList

| Endpoint | Contratto | Errori |
|---|---|---|
| `GET /targets` | `media_type&page` → `Page<Target>` | — |
| `GET /targets/discover` | `media_type` → `{items:[{remote_list_id,name,item_count,private,already_linked}]}` | `502 mdblist_upstream_error` |
| `POST /targets` | `{mode,remote_list_id?,name?,private?}` → `201 Target` | `409 list_limit_reached`, `409 target_already_linked` |
| `POST /targets/{id}/verify` | → `202 {job_id}` | `502` |

`Target`: `{id,remote_list_id,remote_slug,remote_url,name,mediatype,private,item_count,last_verified_at,capabilities}`.
**Nota:** `remote_list_id` è la chiave; `remote_slug`/`remote_url` sono display e possono cambiare.

### 4.6 Binding, preview, run

| Endpoint | Contratto | Errori |
|---|---|---|
| `GET /bindings` | `collection_id&enabled&page` → `Page<Binding>` | — |
| `GET /bindings/{id}` | → `Binding` | `404` |
| `GET /bindings/defaults` | → `{mode,schedule,schedule_time,max_removal_pct,max_removal_abs,preserve_order,reorder_enabled,schedule_policy,require_review}` | — |
| `POST /bindings` | `{collection_id,target_id,mode,schedule,schedule_time,thresholds,preserve_order,reorder_enabled,schedule_policy,enabled,policy_version}` → `201` | `409 binding_exists`, `409 target_locked`, `422 thresholds_required`, `422 policy_not_accepted` |
| `PATCH /bindings/{id}` | campi modificabili → `Binding` | `409 run_in_progress` |
| `DELETE /bindings/{id}` | → `204` | `409 run_in_progress` |
| `POST /bindings/{id}/policy-accept` | `{policy_version}` → `Binding` | `422 policy_version_mismatch` |
| `POST /previews` | `{collection_id,target_id?,mode?,thresholds?}` → `202 {preview_id}` | `409 target_locked`, `422 snapshot_invalid` |
| `GET /previews/{id}` | → `Preview` | `404` |
| `POST /bindings/{id}/runs` | `{dry_run?,idempotency_key}` → `202 {run_id}` | `409 run_in_progress`, `409 snapshot_invalid`, `409 policy_not_accepted`, `409 thresholds_exceeded` |
| `GET /runs` | `binding_id&status&page` → `Page<RunSummary>` | — |
| `GET /runs/{id}` | → `Run` | `404` |
| `GET /runs/{id}/operations` | `status&action&page` → `Page<Operation>` | `404` |
| `POST /runs/{id}/approve` | `{plan_hash,note?}` → `202 {job_id}` | `409 run_not_awaiting_approval`, `409 stale_plan` |
| `POST /runs/{id}/cancel` | → `202 {job_id}` | `409 run_terminal` |
| `POST /runs/{id}/reconcile` | → `202 {job_id}` | `409 run_not_uncertain` |
| `POST /runs/{id}/resume` | → `202 {job_id}` | `409 run_not_resumable` |

`Preview`: `{id,state:"RUNNING"|"READY"|"BLOCKED"|"FAILED",counts:{to_add?,to_remove?,unchanged,unresolved,unmapped_remote,remote_duplicates},blocked:{reason,threshold,observed}|null,sample,snapshot_id,snapshot_hash,plan_hash,order_enforced,generated_at}`.
`Run`: `{id,binding_id,status,started_at,finished_at,counters:{planned,applied,skipped,not_found,failed,uncertain},snapshot_id,preview_id,plan_hash,snapshot_hash,error,reconcile_required,order_enforced,warnings,idempotency_key}`.
`Operation`: `{id,run_id,action:"ADD"|"REMOVE"|"REORDER",media_id,media,status:"PENDING"|"IN_FLIGHT"|"SUCCEEDED"|"SKIPPED"|"FAILED"|"UNCERTAIN",attempt,error,updated_at}`.

### 4.7 Settings e credenziali

| Endpoint | Contratto | Errori |
|---|---|---|
| `GET /settings` | → `Settings` redatto | — |
| `PATCH /settings` | campi parziali → `Settings` | `422` |
| `GET /credentials` | → `[{kind,configured,masked_hint,key_version,updated_at,last_verified_at,status}]` | — |
| `PUT /credentials/{kind}` | `{secret_fields}` → `204`, nessun segreto in risposta | `400 encryption_key_missing`, `422` |
| `DELETE /credentials/{kind}` | → `204` | `404` |
| `POST /credentials/{kind}/verify` | → `202 {job_id}` | `409 credential_missing` |

`kind ∈ {TMDB, MDBLIST, JUSTWATCH}`. `JUSTWATCH` risponde `409 source_not_available` finché non esiste contratto. Nessun endpoint restituisce segreti.

---

## 5. Tipi TypeScript e generazione client

`openapi-typescript` genera `src/api/generated/schema.d.ts` da `GET /api/openapi.json`; `openapi-fetch` fornisce il client tipizzato. `npm run api:generate` in locale; `npm run api:check` in CI (fallisce sul drift).

```ts
import type { components } from "./generated/schema";

export type MediaType = components["schemas"]["MediaType"];          // "MOVIE" | "SHOW"
export type Origin = components["schemas"]["Origin"];                // "OFFICIAL" | "AGGREGATOR" | "CUSTOM"
export type DateBasis = components["schemas"]["DateBasis"];          // ...
export type SyncMode = components["schemas"]["SyncMode"];            // "MIRROR" | "APPEND_ONLY"
export type RunStatus = components["schemas"]["RunStatus"];
export type OperationStatus = components["schemas"]["OperationStatus"];
export type OfferType = components["schemas"]["OfferType"];          // "FLATRATE" | ...
export type ApiError = components["schemas"]["ErrorEnvelope"];
```

- Un solo spelling: TMDb `tv` → `SHOW`, MDBList `shows` → `SHOW`, `movies` → `MOVIE`; la conversione avviene solo nei connettori backend.
- Client: `baseUrl: "/api/v1"`, `credentials: "same-origin"`, header `X-CSRF-Token` letto dal cookie CSRF per i metodi non sicuri; `401` → login; `request_id` propagato.
- Nessun tipo scritto a mano per i payload API: si usano quelli generati.

---

## 6. Tassonomia errori UI

Il backend restituisce:

```json
{
  "error": {
    "code": "MDBLIST_RATE_LIMITED",
    "category": "TARGET",
    "message": "Limite di scrittura MDBList raggiunto.",
    "retryable": true,
    "retry_after_s": 42,
    "request_id": "req_01H...",
    "details": {"target_id": 3}
  }
}
```

`category ∈ {AUTH, VALIDATION, SOURCE, TARGET, POLICY, CONFLICT, INTERNAL}`; il frontend aggiunge solo `NETWORK`.

| Categoria | Titolo | Messaggio | Azione |
|---|---|---|---|
| `SOURCE` | "Errore della fonte" | "La fonte {name} non ha risposto correttamente. Lo snapshot non è stato considerato valido." | Riprova; nessuna rimozione |
| `TARGET` | "Errore MDBList" | "MDBList ha rifiutato la richiesta. Riprova tra {retry_after} s." | Attesa e ripresa |
| `POLICY` | "Operazione bloccata dalle soglie" | "La rimozione prevista ({observed}) supera la soglia ({threshold}). Serve una revisione manuale." | Vai alla revisione |
| `AUTH` | "Sessione scaduta" | "Accedi di nuovo per continuare." | Login |
| `VALIDATION` | "Dati non validi" | "Controlla i campi evidenziati." | Focus sul campo |
| `CONFLICT` | "Operazione già in corso" | "Un'altra operazione è in corso su questa lista." | Attendi |
| `WARNING` | "Ordine non applicato" | "Gli elementi sono corretti, ma MDBList non ha confermato l'ordine. Nessuna lista è stata ricreata." | Dettagli |
| `NETWORK` | "Connessione assente" | "Impossibile raggiungere il server. Verifica la rete." | Riprova |
| `INTERNAL` | "Errore interno" | "Errore imprevisto. Codice richiesta: {request_id}." | Copia codice |

**Regole:**
- Il testo grezzo del server non viene mai mostrato; si usa `message` solo per categorie mappate.
- `409 thresholds_exceeded` e `409 snapshot_invalid` sono warning con percorso di sblocco, non errori rossi.
- `429` mostra un countdown.
- I `422` sono mappati sui campi via `details.fields`.
- Un errore `SOURCE` non deve mai essere mostrato come errore MDBList, e viceversa.

---

## 7. Accessibilità e responsive

- Skip link, un solo `h1`, focus su `main` al cambio route con annuncio `aria-live="polite"`.
- Wizard: `nav aria-label="Passaggi"`, `aria-current="step"`, `aria-invalid` e `aria-describedby`, focus sul primo campo invalido al submit.
- Tabelle con `<caption>`, `scope="col"`, `aria-sort`; stato run come testo + icona, mai solo colore.
- Polling annunciato in `aria-live` con throttle (max 1/5 s) e `aria-busy` sulla regione.
- Dialog con focus trap, `Esc`, ripristino del focus; `ConfirmDialog` non chiudibile con click fuori.
- Contrasto testo ≥ 4.5:1, UI ≥ 3:1, focus ring 2 px, verificato con axe.
- `prefers-reduced-motion` disattiva transizioni e skeleton pulsanti.
- Breakpoint `sm 640 / md 768 / lg 1024 / xl 1280`; sotto `md` tabelle come card `<dl>`, wizard a step singolo, target touch ≥ 44×44 px, nessuno scroll orizzontale a 320 px.

---

## 8. Sicurezza frontend

- Nessun segreto nel bundle: le API key restano nel backend cifrate.
- Sessione solo in cookie `HttpOnly; Secure; SameSite=Lax; Path=/`; nessun token in `localStorage`/`sessionStorage`, dove sta solo la bozza del wizard.
- CSRF double-submit (`__Host-mdbsync-csrf` + `X-CSRF-Token`) su ogni metodo non sicuro.
- CSP dal reverse proxy: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https://image.tmdb.org; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'`. Nessuno script inline, nessun CDN.
- Altri header: `nosniff`, `Referrer-Policy: same-origin`, `Permissions-Policy` minimale, HSTS.
- Nessun `dangerouslySetInnerHTML`; testi delle fonti resi come testo; link esterni con `rel="noopener noreferrer"`.
- Error boundary senza stack trace; log senza PII; lockfile e `npm audit` in CI.

---

## 9. Albero frontend e wireframe

```text
frontend/
  index.html  vite.config.ts  tailwind.config.ts  tsconfig.json
  src/
    main.tsx
    app/         App.tsx router.tsx providers.tsx error-boundary.tsx
    api/         client.ts generated/schema.d.ts queries/ mutations/
    components/  ui/ (Button Table StatusPill OriginBadge DateBasisBadge Dialog
                 Stepper Pagination Skeleton EmptyState ErrorState StaleBanner
                 ConfirmDialog QualityBanner)
    features/    auth/ dashboard/ providers/ collections/ bindings/wizard/ runs/ settings/
    lib/         errors.ts query-keys.ts format.ts dates.ts validation/
    pages/       Login Bootstrap Dashboard Providers Collections Bindings Wizard Run Settings
    test/        setup.ts mocks/handlers.ts mocks/fixtures/
  e2e/           wizard.spec.ts run.spec.ts auth.spec.ts
```

Dashboard:

```text
┌ Header: logo · stato sistema ● ok · utente ▾ ─────────────┐
│ KPI: Provider 12 · Collezioni 34 · Binding 8 · Run attivi 1│
│ Sync recenti (binding · modo · stato · contatori)          │
│ Snapshot non validi (collezione · motivo · data)           │
│ Avvisi: JustWatch non configurato · TMDb senza date        │
└────────────────────────────────────────────────────────────┘
```

Wizard, step 7:

```text
┌ Passaggi: 1 2 3 4 5 6 [7] 8 ──────────────────────────────┐
│ Modo: (•) MIRROR — rispecchia  ( ) APPEND_ONLY — solo agg. │
│ Frequenza [Giornaliera ▾]  Ora [03:00]                     │
│ Soglie: rimozioni max [10] %  e [50] elementi              │
│ [ ] Preserva l'ordine (best-effort; max 1.000 per blocco)  │
│ [x] Richiedi revisione manuale oltre soglia                │
│ Anteprima: +128 / −3 / =412 / !5 non risolti               │
│                                   [Indietro] [Avanti →]    │
└────────────────────────────────────────────────────────────┘
```

Dettaglio run:

```text
┌ Run #1234 · "Netflix IT → Lista film" · APPLYING ──────────┐
│ Snapshot valido · piano +128 −3 · applicate 96/131         │
│ [Annulla] [Riconcilia]                                     │
│ Operazioni: [Tutte ▾] azione · titolo · stato · tentativi  │
└────────────────────────────────────────────────────────────┘
```

---

## 10. Test frontend e contract test

| Livello | Strumento | Copertura |
|---|---|---|
| Unit | Vitest | schemi Zod (8 step, soglie, nome lista), `lib/errors.ts`, formattazione |
| Component | Testing Library + `jest-axe` | stati loading/empty/error/stale/blocked, `OriginBadge`, `DateBasisBadge`, focus trap, `aria-current`, tastiera |
| Integration | MSW con fixture sintetiche | wizard con preview asincrona, polling che si ferma su stato terminale, invalidazione, `401` → login |
| Contract | `openapi-typescript` + `openapi-msw` | handler MSW validati contro lo schema OpenAPI; `npm run api:check` per il drift |
| Contract backend | Schemathesis sull'app FastAPI | risposte, envelope errori, paginazione, `401/403/409` |
| E2E | Playwright su Compose (profilo `test`) | login → snapshot (connettore fixture) → wizard → dry-run → sync → verifica; axe su ogni pagina |

Fixture sintetiche e marcate (`fixture: true`); nessuna lista MDBList reale modificata; connettore fixture escluso dal build di produzione. I test di errore coprono una risposta per categoria e i `409` di soglia e snapshot invalido.


---

## Fonte: `phase-01.md`

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

**Procedura giornaliera** (`deploy/scripts/backup.sh`, servizio `backup` o cron host):

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


---

## Fonte: `phase-01.md`

# Piano di esecuzione per fasi

**Principio:** ogni fase produce qualcosa di verificabile. Non si passa alla fase successiva se i criteri di uscita non sono soddisfatti. Le fasi che richiedono credenziali o contratti si fermano al gate, non vengono simulate.

---

## Fase 1 — Verifica e progettazione (completata)

### Obiettivo
Stabilire cosa è realmente possibile fare con le fonti disponibili, prima di scrivere connettori.

### Deliverable
- `docs/phases/phase-01.md` — documento consolidato (tutte le sezioni della Fase 1).
- `README.md`
- `.env.example`
- `.gitignore`

### Criteri di uscita
- Matrice fonti con etichette VERIFICATO/OSSERVATO/NON VERIFICATO/BLOCCATO.
- MDBList verificato con endpoint, payload, limiti e rischi.
- Architettura, schema dati, sync, sicurezza, frontend, ops e test documentati.
- Blocchi e credenziali necessarie elencati.
- Nessun connettore dichiarato funzionante senza accesso reale.

### Cosa non è incluso
- Codice di produzione.
- Docker Compose eseguibile.
- Migrazioni Alembic reali.
- Connettori reali.
- Acquisizione o sync reali.

---

## Fase 2 — Fondamenta eseguibili

### Obiettivo
Avere un'app che si avvia, autentica, migra il database, espone healthcheck e mostra la shell frontend. Nessun connettore reale.

### Deliverable
- `deploy/docker-compose.yml` con `proxy`, `frontend`, `api`, `worker`, `scheduler`, `migrate`, `postgres`, `redis`.
- `deploy/Caddyfile` con stessa origine per SPA e `/api`.
- `backend/pyproject.toml`, `uv.lock`, `Dockerfile`.
- `backend/app/main.py`, configurazione, logging, error envelope.
- Modelli SQLAlchemy e migrazione `0001_initial` (tutte le tabelle di Fase 1).
- Auth: bootstrap admin, login, logout, sessione HttpOnly, CSRF, rate limit.
- Cifratura credenziali con AES-256-GCM e chiave da file.
- API minime: `/health`, `/ready`, `/auth/*`, `/dashboard`, `/settings`, `/providers`, `/collections`, `/bindings`, `/runs` (lettura).
- Frontend shell: login, dashboard vuota, impostazioni, credenziali mascherate.
- CI: lint, typecheck, test unit/integration, migrazioni up/down, build Docker.
- `deploy/scripts/backup.sh`, `deploy/scripts/restore.sh`.
- README con comandi di avvio.

### Criteri di uscita
- `docker compose up` porta tutti i servizi a `healthy`.
- `alembic upgrade head` su DB vuoto e `downgrade base` funzionano.
- Login con admin creato da bootstrap; cookie HttpOnly/Secure/SameSite; CSRF attivo.
- Credenziale TMDb/MDBList salvata cifrata e riletta mascherata; nessun segreto nei log.
- `/ready` restituisce 503 se DB/Redis non sono pronti.
- CI verde.
- Nessun connettore reale, nessun mock in produzione.

### Test minimi
- Migrazioni su DB vuoto.
- Bootstrap: token monouso, nessuna credenziale predefinita.
- Login: password errata, rate limit, lockout, sessione scaduta.
- CSRF: richiesta senza token → 403.
- Cifratura: round-trip, chiave errata, `key_version`.
- Redazione log: token/apikey/cookie assenti.
- Healthcheck: liveness senza DB, readiness con DB/Redis.

### Gate
Nessuno esterno. Può iniziare subito dopo l'approvazione della Fase 1.

---

## Fase 3 — Prima integrazione verticale reale

### Obiettivo
Acquisire una collezione reale autorizzata, salvarla in uno snapshot, mostrarne l'anteprima, fare un dry-run e aggiornare una lista statica MDBList di test.

### Percorso consigliato (unico disponibile senza contratto JustWatch)
- Provider: **Netflix Italia**.
- Fonte: **TMDb** (`AGGREGATOR`, dati watch provider powered by JustWatch).
- Collezione: "Netflix IT — Disponibilità corrente — Fonte TMDb/JustWatch", tipo `CATALOG`, origine `AGGREGATOR`, `date_basis=UNKNOWN`.
- Media type: film (prima verticale), poi serie.
- Target: lista MDBList statica di test, creata dall'app o importata.
- Modalità: `MIRROR` con soglie conservative; dry-run prima dell'applicazione.

### Deliverable
- `backend/app/connectors/tmdb/` completo: client, mapper, connector, capability flags.
- `backend/app/integrations/mdblist/` completo: client, modelli, mapper.
- `backend/app/services/acquisition.py`, `sync_planner.py`, `sync_executor.py`, `reconciliation.py`.
- Task Celery `acquire_collection`, `run_sync`.
- API: preview, dry-run, start sync, run detail, operations.
- Frontend: collezioni, anteprima, wizard binding, dettaglio sync.
- Test: contract TMDb/MDBList con fixture sintetiche; e2e con mock MDBList; test live opzionale gated.
- Documentazione: `docs/phases/phase-03.md` con esito reale, limiti e screenshot/testo.

### Criteri di uscita
- Acquisizione reale TMDb completa (pagine attese = ottenute) o snapshot `INCOMPLETE` dichiarato.
- Dedup per `(media_type, tmdb_id)`; film e serie separati.
- Anteprima con conteggi e provenienza.
- Dry-run senza scritture remote.
- Sync su lista di test: `to_add`/`to_remove` calcolati, soglie rispettate, operazioni tracciate.
- Riconciliazione finale: lista remota coerente con lo snapshot.
- Nessuna dichiarazione di "aggiunte recenti" o "Top 10 ufficiale".
- Attribuzione TMDb + JustWatch visibile.

### Gate
- TMDb API key.
- MDBList API key.
- Lista MDBList di test.
- Conferma che la lista è statica e modificabile.
- Decisione: accettare "disponibilità corrente" senza date, oppure attendere il contratto JustWatch.

### Cosa non è incluso
- Date di aggiunta reali (serve JustWatch).
- Catalogo completo di tutti i provider.
- Sync pianificate automatiche (Fase 4).
- Top 10 ufficiale.

---

## Fase 4 — Automazione e robustezza

### Obiettivo
Rendere le sync pianificate, sicure e ripristinabili.

### Deliverable
- Scheduler DB-driven: binding dovuti, `next_run_at`, lock, un run attivo per target.
- Soglie assolute/percentuali configurabili; stato `AWAITING_APPROVAL`; UI di revisione.
- Retry con backoff/jitter, `Retry-After`, riconciliazione post-timeout.
- Cronologia run/operazioni, filtri, dettaglio errori.
- Protezioni: snapshot incompleto/vuoto, catalogo anomalo, unresolved, target non scrivibile.
- Manutenzione: retention snapshot/run/audit, healthcheck fonti.
- Test di concorrenza, timeout incerto, fallimenti a metà, job duplicati, soglie.
- Runbook operativo e procedura di restore testata.

### Criteri di uscita
- Sync pianificata end-to-end su lista di test, con policy accettata.
- Doppio avvio → un solo run.
- Snapshot incompleto → nessuna rimozione.
- Soglia superata → `AWAITING_APPROVAL`, nessuna scrittura.
- Timeout → `UNCERTAIN` → riconciliazione → `SUCCEEDED`/`PARTIAL`.
- Cronologia e contatori corretti.
- Restore da backup verificato su DB scratch.

### Gate
- Fase 3 completata e lista di test stabile.
- Policy di soglie approvata.
- Backup/restore testato.

---

## Fase 5 — Estensione

### Obiettivo
Aggiungere provider, collezioni e fonti senza rompere i vincoli di provenienza.

### Deliverable
- Più provider italiani (Prime Video, Disney+, NOW, Timvision, Infinity+, Rakuten, MUBL, ecc.) tramite TMDb, con mapping provider verificati.
- Collezioni film e serie separate.
- Collezioni `CUSTOM` (genere, anno, filtro) chiaramente etichettate.
- Se disponibile contratto JustWatch:
  - connettore Partner API;
  - connettore Data Export S3;
  - collezioni `RECENTLY_ADDED` con `date_basis=AGGREGATOR_FIRST_SEEN`;
  - upcoming e charts.
- Se disponibile una fonte ufficiale verificata per Top 10:
  - collezione `OFFICIAL` con URL e data della fonte;
  - in alternativa, import manuale CSV dichiarato `OFFICIAL`.
- UI: dashboard avanzata, qualità dati, avvisi, accessibilità.
- Documentazione: attribuzione, limiti, runbook.

### Criteri di uscita
- Ogni nuova collezione ha origine, `date_basis`, fonte e URL.
- Nessuna categoria ufficiale inventata.
- Nessun provider senza mapping verificato.
- Test di contratto per ogni nuovo connettore.
- Revisione legale delle fonti aggiunte.

### Gate
- Contratto JustWatch (per date reali).
- Eventuale accordo per fonti ufficiali.
- Capacità operative (rate limit, storage) verificate.

---

## Riepilogo gate

| Gate | Fase | Stato |
|---|---|---|
| Approvazione Fase 1 | 2 | ⏳ |
| TMDb API key | 3 | ⏳ |
| MDBList API key + lista test | 3 | ⏳ |
| Contratto JustWatch | 5 (o 3 se si vogliono date reali) | ⛔ |
| Fonte ufficiale Top 10 | 5 | ⛔ |
| Dominio/TLS + email admin | 2 | ⏳ |
| Chiave di cifratura + backup | 2 | ⏳ |

---

## Definition of done per il progetto

Il progetto è "pronto" solo quando:

1. l'acquisizione reale da almeno una fonte autorizzata funziona e produce snapshot completi;
2. una lista MDBList di test viene aggiornata in modo riconciliato, con soglie e lock;
3. le sync pianificate funzionano e sono osservabili;
4. backup/restore è testato;
5. nessun segreto è esposto;
6. ogni collezione dichiara origine e `date_basis`;
7. le fonti non disponibili sono disabilitate, non simulate.


---

## Fonte: `phase-01.md`

# Domande aperte e input necessari

**Stato:** Fase 1 completata. Le risposte sotto sbloccano la Fase 2 e la Fase 3.

---

## 1. Credenziali e accessi

| # | Domanda | Perché serve | Default proposto |
|---|---|---|---|
| 1 | Fornisci una **TMDb API key** (read access token). | Prima fonte reale di disponibilità IT. | Nessun default: senza key, la Fase 3 non parte. |
| 2 | Fornisci una **MDBList API key**. | Destinazione delle sync. | Nessun default. |
| 3 | Qual è il **piano MDBList** (free/supporter)? | Limite liste statiche (free: 4) e rate. | Free per il test; supporter se servono più liste. |
| 4 | Quale **lista MDBList di test** usare? | Evitare di toccare liste personali. | Crearne una nuova, privata, dedicata. |
| 5 | Hai un **contratto JustWatch Partner** o accesso al data export S3? | Date di aggiunta reali e catalogo completo. | No: la Fase 3 userà TMDb e dichiarerà "disponibilità corrente". |
| 6 | Se sì, fornisci **partner token** e **credenziali S3** (Access Key, Secret, directory). | Connettore JustWatch. | Nessun default. |

**Nota:** le credenziali non vanno inviate in chat né messe in `.env`. Vanno inserite dall'interfaccia Impostazioni dopo la Fase 2, oppure caricate come Docker secret. In questa fase è sufficiente sapere se sono disponibili.

---

## 2. Deployment

| # | Domanda | Default proposto |
|---|---|---|
| 7 | Quale **dominio** userai? | `mdblist-sync.example.com` (placeholder). |
| 8 | TLS con **Let's Encrypt/Caddy** o certificato esistente? | Caddy + Let's Encrypt. |
| 9 | Quale **email** per il primo admin e per ACME? | `admin@example.com` (placeholder). |
| 10 | Il server ha **Docker Compose** e almeno 2 GB RAM / 10 GB disco? | Sì, ambiente Linux. |
| 11 | Vuoi esporre l'app su Internet o solo su VPN/LAN? | VPN/LAN in Fase 2; Internet solo dopo security review. |

---

## 3. Policy di sincronizzazione

| # | Domanda | Default proposto |
|---|---|---|
| 12 | Quali **tipi di offerta** includere? | Solo `flatrate` (abbonamento). Rent/buy/ads/free disattivati. |
| 13 | Le liste devono includere **film e serie insieme** o separate? | Separate: una lista movie e una show. |
| 14 | **Soglia rimozioni assoluta**? | 50 elementi. |
| 15 | **Soglia rimozioni percentuale**? | 10%. |
| 16 | **Soglia aggiunte percentuale**? | 50%. |
| 17 | Le sync pianificate devono richiedere approvazione a ogni run? | No, se il binding è abilitato con policy accettata; blocco solo se si superano le soglie. |
| 18 | Cosa fare se uno snapshot è incompleto? | Nessuna rimozione; `BLOCKED`; notifica in dashboard. |
| 19 | Cosa fare se uno snapshot è vuoto? | `BLOCKED`; nessuna scrittura. |
| 20 | Cosa fare con elementi non risolti (senza TMDb ID)? | Non includerli; MIRROR bloccato se superano la soglia; mostrare il conteggio. |
| 21 | **Ordine** delle liste: preservarlo? | Default `false`; opzione `preserve_order=true` con reorder best-effort (max 1.000 per chiamata, non atomico). |
| 22 | Retention snapshot/run/operazioni? | 90 giorni snapshot, 180 giorni run/operazioni, audit 180 giorni. |

---

## 4. Provenienza e contenuti

| # | Domanda | Default proposto |
|---|---|---|
| 23 | Vuoi collezioni **"Aggiunte recenti"** derivate dall'app? | Sì, ma etichettate `CUSTOM` / `APP_FIRST_SEEN`, non "ufficiali". |
| 24 | Vuoi collezioni **"Top 10 ufficiale"**? | Non ora: nessuna fonte ufficiale verificata. |
| 25 | Vuoi includere **prossime uscite**? | Solo se JustWatch contract; TMDb non basta per lo streaming. |
| 26 | Vuoi includere **classifiche**? | Solo con JustWatch contract; MDBList JustWatch charts non copre l'Italia. |
| 27 | Quali provider italiani prioritari? | Netflix, Prime Video, Disney+, NOW, Timvision, Infinity+, Rakuten TV, MUBI. |
| 28 | Vuoi l'**audio italiano** come filtro? | No: la disponibilità in Italia non implica audio italiano. Nessun dato verificato. |
| 29 | Vuoi **canali aggiuntivi** (es. Amazon Channels)? | No di default; configurabile per collezione. |

---

## 5. Sicurezza e operazioni

| # | Domanda | Default proposto |
|---|---|---|
| 30 | Come custodisci `APP_ENCRYPTION_KEY`? | Password manager + backup offline; mai nel repo. |
| 31 | Quale **recipient age** per i backup? | Chiave pubblica `age1...`; privata offline. |
| 32 | Backup su volume locale o off-site? | Locale + copia off-site cifrata. |
| 33 | Vuoi **MFA** per l'admin? | Non in Fase 1; valutare in Fase 5. |
| 34 | Vuoi **notifiche** (email/webhook) per sync fallite/soglie? | Dashboard in Fase 2; webhook in Fase 4. |
| 35 | Log retention? | 30 giorni, JSON, senza segreti. |

---

## 6. Legale e attribuzione

| # | Domanda | Default proposto |
|---|---|---|
| 36 | Confermi uso **personale/non commerciale** di TMDb? | Sì. |
| 37 | Accetti l'attribuzione **TMDb + JustWatch** in UI? | Sì, obbligatoria per i dati watch provider. |
| 38 | Hai letto i **Termini TMDb** (pagina 403 al fetcher)? | Da leggere manualmente prima della Fase 3. |
| 39 | Accetti di **non usare** scraping/GraphQL JustWatch? | Sì, vincolo di progetto. |
| 40 | Vuoi una **revisione legale** prima della Fase 3? | Consigliata. |

---

## 7. Decisioni già prese (non serve rispondere)

- Monolite modulare, non microservizi.
- PostgreSQL fonte di verità, Redis broker/cache.
- Snapshot immutabili, solo snapshot validi per le sync.
- MIRROR/APPEND_ONLY, soglie, lock, idempotenza, riconciliazione.
- Segreti cifrati a riposo, sessioni HttpOnly, CSRF, rate limit login.
- UI e documentazione in italiano; identificatori in inglese.
- Nessun connettore mock in produzione.
- Nessuna lista "Top 10 ufficiale" senza fonte verificata.
- Film e serie separati.
- MDBList ID numerico come chiave; slug/URL solo display.

---

## 8. Risposte minime per partire con la Fase 2

La Fase 2 non richiede credenziali esterne. Per partire bastano:

1. conferma di procedere;
2. dominio (anche placeholder) e email admin;
3. decisione su Docker secrets vs `.env` per i segreti;
4. conferma della policy di backup.

Per la Fase 3 servono TMDb key, MDBList key e lista di test. Senza queste, la Fase 3 resta bloccata e non va simulata.


---

## Schema SQL storico di riferimento

```sql
-- ============================================================
-- MdbUP — schema PostgreSQL di riferimento (Fase 1)
-- ============================================================
-- Questo file è un DDL di progettazione, non una migrazione Alembic.
-- La migrazione 0001_initial di Fase 2 sarà generata da SQLAlchemy/Alembic
-- e dovrà produrre uno schema equivalente.
--
-- Convenzioni:
-- - timestamp sempre TIMESTAMPTZ (UTC); la UI mostra Europe/Rome;
-- - enum tramite TEXT + CHECK (più facili da evolvere delle enum PG);
-- - UUID con gen_random_uuid();
-- - nessun titolo usato come chiave;
-- - film e serie separati da media_type.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- ------------------------------------------------------------
-- Utenti, sessioni, impostazioni
-- ------------------------------------------------------------

CREATE TABLE app_user (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           CITEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    is_admin        BOOLEAN NOT NULL DEFAULT TRUE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ
);

CREATE TABLE session (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    token_hash      BYTEA NOT NULL UNIQUE,
    csrf_hash       BYTEA NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ,
    ip              INET,
    user_agent      TEXT
);
CREATE INDEX session_user_idx ON session (user_id);
CREATE INDEX session_expires_idx ON session (expires_at);

CREATE TABLE app_setting (
    key             TEXT PRIMARY KEY,
    value           JSONB NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by      UUID REFERENCES app_user(id)
);

-- ------------------------------------------------------------
-- Fonti, credenziali, provider
-- ------------------------------------------------------------

CREATE TABLE source (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key                 TEXT NOT NULL UNIQUE,
    name                TEXT NOT NULL,
    type                TEXT NOT NULL CHECK (type IN ('API', 'DATA_EXPORT', 'MANUAL_CSV')),
    base_url            TEXT,
    config              JSONB NOT NULL DEFAULT '{}'::jsonb,
    capabilities        JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_official         BOOLEAN NOT NULL DEFAULT FALSE,
    origin_default      TEXT NOT NULL DEFAULT 'AGGREGATOR'
                        CHECK (origin_default IN ('OFFICIAL', 'AGGREGATOR', 'CUSTOM')),
    requires_contract   BOOLEAN NOT NULL DEFAULT FALSE,
    status              TEXT NOT NULL DEFAULT 'UNCONFIGURED'
                        CHECK (status IN ('UNCONFIGURED', 'OK', 'DEGRADED', 'ERROR', 'DISABLED')),
    status_message      TEXT,
    last_healthcheck_at TIMESTAMPTZ,
    last_success_at     TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (NOT is_official OR origin_default = 'OFFICIAL')
);

CREATE TABLE credential (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope           TEXT NOT NULL CHECK (scope IN ('SOURCE', 'TARGET', 'SYSTEM')),
    source_id       UUID REFERENCES source(id) ON DELETE CASCADE,
    key             TEXT NOT NULL,
    ciphertext      BYTEA NOT NULL,
    nonce           BYTEA NOT NULL,
    algorithm       TEXT NOT NULL DEFAULT 'AES-256-GCM',
    key_version     SMALLINT NOT NULL,
    masked_hint     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at    TIMESTAMPTZ,
    last_verified_at TIMESTAMPTZ,
    CHECK (scope <> 'SOURCE' OR source_id IS NOT NULL),
    CHECK (scope = 'SOURCE' OR source_id IS NULL),
    UNIQUE NULLS NOT DISTINCT (scope, source_id, key)
);

CREATE TABLE provider (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL DEFAULT 'SVOD'
                    CHECK (kind IN ('SVOD', 'TVOD', 'AVOD', 'TVE', 'STORE', 'CINEMA', 'CHANNEL')),
    logo_url        TEXT,
    website_url     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE provider_mapping (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id         UUID NOT NULL REFERENCES provider(id) ON DELETE CASCADE,
    source_id           UUID NOT NULL REFERENCES source(id) ON DELETE CASCADE,
    country_code        CHAR(2) NOT NULL,
    external_provider_id TEXT NOT NULL,
    external_name       TEXT,
    is_primary          BOOLEAN NOT NULL DEFAULT FALSE,
    is_verified         BOOLEAN NOT NULL DEFAULT FALSE,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, country_code, external_provider_id)
);
CREATE INDEX provider_mapping_provider_idx ON provider_mapping (provider_id, country_code);
CREATE UNIQUE INDEX provider_mapping_one_primary
    ON provider_mapping (provider_id, source_id, country_code) WHERE is_primary = TRUE;

-- ------------------------------------------------------------
-- Media e disponibilità
-- ------------------------------------------------------------

CREATE TABLE media (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    media_type          TEXT NOT NULL CHECK (media_type IN ('MOVIE', 'SHOW')),
    tmdb_id             BIGINT,
    imdb_id             TEXT,
    tvdb_id             BIGINT,
    trakt_id            BIGINT,
    title               TEXT NOT NULL,
    original_title      TEXT,
    release_year        SMALLINT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    resolution_status   TEXT NOT NULL DEFAULT 'RESOLVED'
                        CHECK (resolution_status IN ('RESOLVED', 'UNRESOLVED', 'AMBIGUOUS')),
    not_found_count     INTEGER NOT NULL DEFAULT 0,
    sync_suppressed_until TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (tmdb_id IS NOT NULL OR imdb_id IS NOT NULL OR tvdb_id IS NOT NULL OR trakt_id IS NOT NULL),
    UNIQUE (id, media_type)
);
CREATE UNIQUE INDEX media_tmdb_uq ON media (tmdb_id, media_type) WHERE tmdb_id IS NOT NULL;
CREATE UNIQUE INDEX media_imdb_uq ON media (imdb_id, media_type) WHERE imdb_id IS NOT NULL;
CREATE INDEX media_title_idx ON media (title);

CREATE TABLE availability (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    media_id            UUID NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    provider_id         UUID NOT NULL REFERENCES provider(id),
    country_code        CHAR(2) NOT NULL,
    offer_type          TEXT NOT NULL CHECK (offer_type IN ('FLATRATE', 'RENT', 'BUY', 'ADS', 'FREE')),
    presentation_type   TEXT,
    channel             TEXT,
    plan                TEXT,
    source_id           UUID NOT NULL REFERENCES source(id),
    source_offer_id     TEXT,
    source_date_created DATE,
    first_seen_at       TIMESTAMPTZ NOT NULL,
    last_seen_at        TIMESTAMPTZ NOT NULL,
    last_checked_at     TIMESTAMPTZ NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE NULLS NOT DISTINCT (
        media_id, provider_id, country_code, offer_type,
        presentation_type, channel, plan, source_id
    )
);
CREATE INDEX availability_lookup_idx
    ON availability (provider_id, country_code, offer_type, is_active);
CREATE INDEX availability_media_idx ON availability (media_id);

-- ------------------------------------------------------------
-- Collezioni e snapshot
-- ------------------------------------------------------------

CREATE TABLE collection (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                    TEXT NOT NULL UNIQUE,
    source_id               UUID NOT NULL REFERENCES source(id),
    provider_id             UUID NOT NULL REFERENCES provider(id),
    country_code            CHAR(2) NOT NULL DEFAULT 'IT',
    media_type              TEXT NOT NULL CHECK (media_type IN ('MOVIE', 'SHOW')),
    kind                    TEXT NOT NULL
                            CHECK (kind IN ('CATALOG', 'RECENTLY_ADDED', 'UPCOMING', 'CHART', 'CUSTOM_FILTER')),
    origin                  TEXT NOT NULL CHECK (origin IN ('OFFICIAL', 'AGGREGATOR', 'CUSTOM')),
    date_basis              TEXT NOT NULL
                            CHECK (date_basis IN ('PROVIDER_OFFICIAL', 'AGGREGATOR_FIRST_SEEN', 'APP_FIRST_SEEN', 'UNKNOWN')),
    name                    TEXT NOT NULL,
    description             TEXT,
    source_collection_key   TEXT,
    source_url              TEXT,
    offer_types             TEXT[] NOT NULL DEFAULT ARRAY['FLATRATE'],
    filters                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_flags           JSONB NOT NULL DEFAULT '{}'::jsonb,
    sort_mode               TEXT NOT NULL DEFAULT 'SOURCE_ORDER'
                            CHECK (sort_mode IN ('SOURCE_ORDER', 'POPULARITY', 'TITLE', 'RELEASE_DATE', 'ADDED_DATE', 'CUSTOM')),
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    last_valid_snapshot_id  UUID,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, media_type)
);
CREATE INDEX collection_provider_idx ON collection (provider_id, country_code, media_type);
CREATE INDEX collection_origin_idx ON collection (origin, kind);
CREATE UNIQUE INDEX collection_source_key_uq
    ON collection (source_id, provider_id, country_code, media_type, kind, source_collection_key)
    WHERE source_collection_key IS NOT NULL;

CREATE TABLE job_execution (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         TEXT UNIQUE,
    task_name       TEXT NOT NULL,
    queue           TEXT NOT NULL,
    status          TEXT NOT NULL
                    CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'RETRY', 'CANCELLED')),
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    result          JSONB,
    error_code      TEXT,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX job_execution_status_idx ON job_execution (status, created_at);

CREATE TABLE collection_snapshot (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id       UUID NOT NULL REFERENCES collection(id) ON DELETE CASCADE,
    status              TEXT NOT NULL
                        CHECK (status IN ('RUNNING', 'COMPLETE', 'INCOMPLETE', 'FAILED', 'CANCELLED')),
    quality             TEXT NOT NULL DEFAULT 'CLEAN'
                        CHECK (quality IN ('CLEAN', 'WARNINGS', 'ANOMALY')),
    is_valid            BOOLEAN NOT NULL DEFAULT FALSE,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,
    pages_expected      INTEGER,
    pages_fetched       INTEGER NOT NULL DEFAULT 0,
    items_count         INTEGER NOT NULL DEFAULT 0,
    resolved_count      INTEGER NOT NULL DEFAULT 0,
    unresolved_count    INTEGER NOT NULL DEFAULT 0,
    duplicate_count     INTEGER NOT NULL DEFAULT 0,
    error_count         INTEGER NOT NULL DEFAULT 0,
    errors              JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings            JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_revision     TEXT,
    checksum            TEXT,
    invalid_reason      TEXT,
    job_execution_id    UUID REFERENCES job_execution(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (quality <> 'CLEAN' OR unresolved_count = 0),
    CHECK (NOT is_valid OR (
        status = 'COMPLETE'
        AND quality = 'CLEAN'
        AND items_count > 0
        AND error_count = 0
        AND unresolved_count = 0
    ))
);
CREATE UNIQUE INDEX snapshot_one_running_uq
    ON collection_snapshot (collection_id) WHERE status = 'RUNNING';
CREATE INDEX snapshot_collection_idx ON collection_snapshot (collection_id, started_at DESC);

ALTER TABLE collection
    ADD CONSTRAINT collection_last_valid_snapshot_fk
    FOREIGN KEY (last_valid_snapshot_id) REFERENCES collection_snapshot(id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE snapshot_item (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id         UUID NOT NULL REFERENCES collection_snapshot(id) ON DELETE CASCADE,
    media_id            UUID REFERENCES media(id),
    position            INTEGER NOT NULL,
    source_item_id      TEXT,
    source_payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_date_created DATE,
    date_basis          TEXT NOT NULL
                        CHECK (date_basis IN ('PROVIDER_OFFICIAL', 'AGGREGATOR_FIRST_SEEN', 'APP_FIRST_SEEN', 'UNKNOWN')),
    resolution_status   TEXT NOT NULL
                        CHECK (resolution_status IN ('RESOLVED', 'UNRESOLVED', 'AMBIGUOUS')),
    resolution_error    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, position)
);
CREATE UNIQUE INDEX snapshot_item_media_uq
    ON snapshot_item (snapshot_id, media_id) WHERE media_id IS NOT NULL;
CREATE INDEX snapshot_item_media_idx ON snapshot_item (media_id);

-- ------------------------------------------------------------
-- Target MDBList e sincronizzazione
-- ------------------------------------------------------------

CREATE TABLE mdblist_target (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    remote_list_id      BIGINT NOT NULL UNIQUE,
    remote_slug         TEXT NOT NULL,
    remote_url          TEXT,
    name                TEXT NOT NULL,
    mediatype           TEXT NOT NULL CHECK (mediatype IN ('MOVIE', 'SHOW', 'SEASON', 'EPISODE')),
    is_private          BOOLEAN NOT NULL DEFAULT FALSE,
    item_count          INTEGER,
    last_verified_at    TIMESTAMPTZ,
    last_remote_read_at TIMESTAMPTZ,
    capabilities        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, mediatype)
);

CREATE TABLE sync_binding (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id           UUID NOT NULL,
    target_id               UUID NOT NULL,
    media_type              TEXT NOT NULL CHECK (media_type IN ('MOVIE', 'SHOW')),
    mode                    TEXT NOT NULL CHECK (mode IN ('MIRROR', 'APPEND_ONLY')),
    schedule_cron           TEXT NOT NULL,
    timezone                TEXT NOT NULL DEFAULT 'Europe/Rome',
    is_enabled              BOOLEAN NOT NULL DEFAULT FALSE,
    policy_version          TEXT,
    policy_accepted_at      TIMESTAMPTZ,
    policy_accepted_by      UUID REFERENCES app_user(id),
    max_removal_absolute    INTEGER NOT NULL DEFAULT 50,
    max_removal_percent     NUMERIC(5,2) NOT NULL DEFAULT 10.00,
    max_addition_percent    NUMERIC(5,2) NOT NULL DEFAULT 50.00,
    preserve_order          BOOLEAN NOT NULL DEFAULT FALSE,
    reorder_enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    require_manual_review   BOOLEAN NOT NULL DEFAULT TRUE,
    schedule_policy         TEXT NOT NULL DEFAULT 'AUTO_APPLY_IF_SAFE'
                            CHECK (schedule_policy IN ('AUTO_APPLY_IF_SAFE', 'ALWAYS_APPROVE', 'DRY_RUN_ONLY')),
    auto_apply_max_removals INTEGER NOT NULL DEFAULT 5,
    auto_apply_max_removal_ratio NUMERIC(5,2) NOT NULL DEFAULT 2.00,
    max_plan_age_minutes    INTEGER NOT NULL DEFAULT 60,
    last_run_id             UUID,
    next_run_at             TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (collection_id, target_id),
    UNIQUE (id, media_type),
    FOREIGN KEY (collection_id, media_type) REFERENCES collection(id, media_type) ON DELETE CASCADE,
    FOREIGN KEY (target_id, media_type) REFERENCES mdblist_target(id, mediatype) ON DELETE CASCADE,
    CHECK (max_removal_absolute >= 0),
    CHECK (max_removal_percent >= 0 AND max_removal_percent <= 100),
    CHECK (max_addition_percent >= 0 AND max_addition_percent <= 100),
    CHECK (NOT is_enabled OR (policy_accepted_at IS NOT NULL AND policy_version IS NOT NULL))
);
CREATE UNIQUE INDEX binding_one_active_target_uq
    ON sync_binding (target_id) WHERE is_enabled = TRUE;
CREATE INDEX binding_due_idx
    ON sync_binding (next_run_at) WHERE is_enabled = TRUE;

CREATE TABLE sync_run (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    binding_id          UUID NOT NULL,
    target_id           UUID NOT NULL,
    media_type          TEXT NOT NULL CHECK (media_type IN ('MOVIE', 'SHOW')),
    snapshot_id         UUID NOT NULL REFERENCES collection_snapshot(id),
    mode                TEXT NOT NULL CHECK (mode IN ('MIRROR', 'APPEND_ONLY')),
    status              TEXT NOT NULL
                        CHECK (status IN ('PENDING', 'PREFLIGHT', 'PLANNING', 'AWAITING_APPROVAL',
                                          'APPLYING', 'VERIFYING', 'SUCCEEDED', 'PARTIAL',
                                          'FAILED', 'BLOCKED', 'CANCELLED')),
    is_dry_run          BOOLEAN NOT NULL DEFAULT FALSE,
    trigger             TEXT NOT NULL CHECK (trigger IN ('MANUAL', 'SCHEDULED', 'RETRY')),
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    source_item_count   INTEGER NOT NULL DEFAULT 0,
    remote_item_count   INTEGER NOT NULL DEFAULT 0,
    to_add_count        INTEGER NOT NULL DEFAULT 0,
    to_remove_count     INTEGER NOT NULL DEFAULT 0,
    added_count         INTEGER NOT NULL DEFAULT 0,
    removed_count       INTEGER NOT NULL DEFAULT 0,
    failed_count        INTEGER NOT NULL DEFAULT 0,
    uncertain_count     INTEGER NOT NULL DEFAULT 0,
    threshold_breached  BOOLEAN NOT NULL DEFAULT FALSE,
    requires_approval   BOOLEAN NOT NULL DEFAULT FALSE,
    approved_at         TIMESTAMPTZ,
    approved_by         UUID REFERENCES app_user(id),
    plan_hash           TEXT,
    snapshot_hash       TEXT,
    order_enforced      BOOLEAN NOT NULL DEFAULT FALSE,
    warnings            JSONB NOT NULL DEFAULT '[]'::jsonb,
    parent_run_id       UUID REFERENCES sync_run(id),
    not_before          TIMESTAMPTZ,
    abort_reason        TEXT,
    correlation_id      UUID NOT NULL DEFAULT gen_random_uuid(),
    error_code          TEXT,
    error_message       TEXT,
    summary             JSONB NOT NULL DEFAULT '{}'::jsonb,
    lock_key            TEXT,
    requested_by        UUID REFERENCES app_user(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (binding_id, media_type) REFERENCES sync_binding(id, media_type) ON DELETE CASCADE,
    FOREIGN KEY (target_id, media_type) REFERENCES mdblist_target(id, mediatype),
    CHECK (NOT is_dry_run OR (added_count = 0 AND removed_count = 0)),
    CHECK (status NOT IN ('SUCCEEDED', 'PARTIAL', 'FAILED', 'BLOCKED', 'CANCELLED') OR finished_at IS NOT NULL)
);
CREATE UNIQUE INDEX run_one_active_binding_uq
    ON sync_run (binding_id)
    WHERE status IN ('PENDING', 'PREFLIGHT', 'PLANNING', 'AWAITING_APPROVAL', 'APPLYING', 'VERIFYING');
CREATE UNIQUE INDEX run_one_active_target_uq
    ON sync_run (target_id)
    WHERE status IN ('PENDING', 'PREFLIGHT', 'PLANNING', 'AWAITING_APPROVAL', 'APPLYING', 'VERIFYING');
CREATE INDEX run_binding_idx ON sync_run (binding_id, created_at DESC);

ALTER TABLE sync_binding
    ADD CONSTRAINT sync_binding_last_run_fk
    FOREIGN KEY (last_run_id) REFERENCES sync_run(id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE sync_operation (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID NOT NULL REFERENCES sync_run(id) ON DELETE CASCADE,
    batch_id            UUID,
    action              TEXT NOT NULL CHECK (action IN ('ADD', 'REMOVE', 'REORDER')),
    media_id            UUID REFERENCES media(id),
    remote_id           TEXT,
    idempotency_key     TEXT NOT NULL UNIQUE,
    status              TEXT NOT NULL
                        CHECK (status IN ('PENDING', 'IN_FLIGHT', 'SUCCEEDED', 'FAILED', 'UNCERTAIN', 'SKIPPED')),
    attempt             INTEGER NOT NULL DEFAULT 0,
    max_attempts        INTEGER NOT NULL DEFAULT 5,
    next_retry_at       TIMESTAMPTZ,
    reconciled_at       TIMESTAMPTZ,
    http_status         INTEGER,
    duration_ms         INTEGER,
    request_hash        TEXT,
    response            JSONB,
    error_code          TEXT,
    error_message       TEXT,
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (action = 'REORDER' OR media_id IS NOT NULL),
    UNIQUE (run_id, action, media_id)
);
CREATE INDEX sync_operation_run_idx ON sync_operation (run_id, status);
CREATE INDEX sync_operation_batch_idx ON sync_operation (batch_id);

CREATE TABLE sync_run_event (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES sync_run(id) ON DELETE CASCADE,
    from_status     TEXT,
    to_status       TEXT NOT NULL,
    message         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX sync_run_event_run_idx ON sync_run_event (run_id, created_at);

-- ------------------------------------------------------------
-- Eventi stagioni/episodi (senza duplicare la serie)
-- ------------------------------------------------------------

CREATE TABLE episode_event (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    show_media_id       UUID NOT NULL,
    media_type          TEXT NOT NULL DEFAULT 'SHOW' CHECK (media_type = 'SHOW'),
    provider_id         UUID NOT NULL REFERENCES provider(id),
    country_code        CHAR(2) NOT NULL,
    source_id           UUID NOT NULL REFERENCES source(id),
    snapshot_id         UUID REFERENCES collection_snapshot(id),
    event_type          TEXT NOT NULL
                        CHECK (event_type IN ('SEASON_ADDED', 'SEASON_REMOVED', 'EPISODE_ADDED', 'EPISODE_REMOVED')),
    season_number       INTEGER NOT NULL,
    episode_number      INTEGER,
    occurred_at         TIMESTAMPTZ,
    source_payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (show_media_id, media_type) REFERENCES media(id, media_type) ON DELETE CASCADE,
    UNIQUE NULLS NOT DISTINCT (
        show_media_id, provider_id, country_code, source_id,
        event_type, season_number, episode_number
    )
);
CREATE INDEX episode_event_show_idx ON episode_event (show_media_id, occurred_at DESC);

-- ------------------------------------------------------------
-- Audit e healthcheck
-- ------------------------------------------------------------

CREATE TABLE audit_log (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_user_id   UUID REFERENCES app_user(id),
    actor_type      TEXT NOT NULL CHECK (actor_type IN ('USER', 'SYSTEM', 'SCHEDULER')),
    action          TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_id       TEXT,
    before          JSONB,
    after           JSONB,
    ip              INET,
    user_agent      TEXT,
    request_id      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audit_entity_idx ON audit_log (entity_type, entity_id, created_at DESC);
CREATE INDEX audit_created_idx ON audit_log (created_at DESC);

CREATE TABLE source_healthcheck (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id       UUID NOT NULL REFERENCES source(id) ON DELETE CASCADE,
    status          TEXT NOT NULL,
    latency_ms      INTEGER,
    message         TEXT,
    details         JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX source_healthcheck_source_idx ON source_healthcheck (source_id, checked_at DESC);

-- ------------------------------------------------------------
-- Trigger e guardie di integrità
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'app_user', 'source', 'credential', 'provider', 'provider_mapping',
        'media', 'collection', 'mdblist_target', 'sync_binding', 'sync_run',
        'sync_operation', 'app_setting', 'job_execution'
    ]
    LOOP
        EXECUTE format(
            'CREATE TRIGGER %I_touch BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at()',
            t, t
        );
    END LOOP;
END;
$$;

-- OFFICIAL solo da una fonte ufficiale; AGGREGATOR solo da una fonte aggregatore.
CREATE OR REPLACE FUNCTION enforce_collection_origin() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    src_official boolean;
    src_origin text;
BEGIN
    SELECT is_official, origin_default INTO src_official, src_origin
    FROM source WHERE id = NEW.source_id;

    IF NEW.origin = 'OFFICIAL' AND NOT COALESCE(src_official, false) THEN
        RAISE EXCEPTION 'collection %: origine OFFICIAL richiede una fonte ufficiale', NEW.slug;
    END IF;

    IF NEW.origin = 'AGGREGATOR' AND src_origin IS DISTINCT FROM 'AGGREGATOR' THEN
        RAISE EXCEPTION 'collection %: origine AGGREGATOR richiede una fonte aggregatore', NEW.slug;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER collection_origin_guard
BEFORE INSERT OR UPDATE OF origin, source_id ON collection
FOR EACH ROW EXECUTE FUNCTION enforce_collection_origin();

-- Un sync_run può usare solo uno snapshot della stessa collezione,
-- dello stesso media type e con completezza sufficiente.
CREATE OR REPLACE FUNCTION enforce_sync_run_snapshot() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    snap_collection uuid;
    snap_status text;
    snap_valid boolean;
    snap_items integer;
    bind_collection uuid;
    bind_target uuid;
    bind_media_type text;
BEGIN
    SELECT collection_id, status, is_valid, items_count
    INTO snap_collection, snap_status, snap_valid, snap_items
    FROM collection_snapshot WHERE id = NEW.snapshot_id;

    SELECT collection_id, target_id, media_type
    INTO bind_collection, bind_target, bind_media_type
    FROM sync_binding WHERE id = NEW.binding_id;

    IF snap_collection IS DISTINCT FROM bind_collection THEN
        RAISE EXCEPTION 'sync_run: snapshot % non appartiene alla collezione del binding', NEW.snapshot_id;
    END IF;

    IF NEW.target_id IS DISTINCT FROM bind_target THEN
        RAISE EXCEPTION 'sync_run: target % diverso dal target del binding', NEW.target_id;
    END IF;

    IF NEW.media_type IS DISTINCT FROM bind_media_type THEN
        RAISE EXCEPTION 'sync_run: media_type % diverso dal binding', NEW.media_type;
    END IF;

    IF NEW.mode IS DISTINCT FROM (SELECT mode FROM sync_binding WHERE id = NEW.binding_id) THEN
        RAISE EXCEPTION 'sync_run: mode % diverso dal binding', NEW.mode;
    END IF;

    IF snap_status = 'RUNNING' THEN
        RAISE EXCEPTION 'sync_run: snapshot % ancora in esecuzione', NEW.snapshot_id;
    END IF;

    IF NEW.mode = 'MIRROR' AND NOT COALESCE(snap_valid, false) THEN
        RAISE EXCEPTION 'sync_run: snapshot % non valido per MIRROR', NEW.snapshot_id;
    END IF;

    IF NEW.mode = 'APPEND_ONLY' AND (snap_status <> 'COMPLETE' OR snap_items = 0) THEN
        RAISE EXCEPTION 'sync_run: snapshot % incompleto o vuoto per APPEND_ONLY', NEW.snapshot_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER sync_run_snapshot_guard
BEFORE INSERT OR UPDATE OF snapshot_id, binding_id, target_id, media_type, mode ON sync_run
FOR EACH ROW EXECUTE FUNCTION enforce_sync_run_snapshot();

-- Un'operazione ADD/REMOVE deve riferirsi a un media dello stesso tipo del run.
CREATE OR REPLACE FUNCTION enforce_sync_operation_media_type() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    run_type text;
    media_type text;
BEGIN
    IF NEW.action = 'REORDER' THEN
        RETURN NEW;
    END IF;

    SELECT media_type INTO run_type FROM sync_run WHERE id = NEW.run_id;
    SELECT media_type INTO media_type FROM media WHERE id = NEW.media_id;

    IF media_type IS DISTINCT FROM run_type THEN
        RAISE EXCEPTION 'sync_operation: media % non coerente con il media_type del run', NEW.media_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER sync_operation_media_type_guard
BEFORE INSERT OR UPDATE OF run_id, media_id, action ON sync_operation
FOR EACH ROW EXECUTE FUNCTION enforce_sync_operation_media_type();

-- audit_log append-only.
CREATE OR REPLACE FUNCTION reject_audit_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log è append-only';
END;
$$;

CREATE TRIGGER audit_log_append_only
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();
```
