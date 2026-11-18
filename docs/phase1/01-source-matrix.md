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
