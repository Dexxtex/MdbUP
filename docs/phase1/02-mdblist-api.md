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
