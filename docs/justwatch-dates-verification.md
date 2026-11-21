# JustWatch IT — verifica campi data

**Data verifica:** 2026-11-20
**Endpoint:** `POST https://apis.justwatch.com/graphql` (pubblico, senza credenziali)
**Paese:** `IT` — **Lingua:** `it` — **Throttle:** 1,2 s
**Modalità:** sola lettura; nessuna scrittura su MDBList, DB o volumi.

## Esito sintetico

Non esiste un endpoint dedicato alle “date”. Le date pubblicate sono campi
GraphQL dentro `content` e `offers`; le ho verificate con richieste reali su
`popularTitles` e `newTitles`.

| Campo GraphQL | Esito | Significato verificato |
|---|---|---|
| `content.originalReleaseDate` | **esiste** | Data di uscita originale del film/serie (es. Lupin `2021-01-08`) |
| `Offer.dateCreated` | **esiste** | Data di creazione del record offerta JustWatch, non data ufficiale del provider |
| `Offer.availableFromTime` | **esiste** | Inizio disponibilità dell’offerta, quando JustWatch lo pubblica |
| `Offer.availableToTime` | **esiste** | Fine disponibilità dell’offerta, spesso `null` |
| `Offer.availableTo` | **esiste** | Data di fine disponibilità, quando pubblicata |
| `Offer.updatedAt` | **esiste** | Timestamp dell’ultimo aggiornamento dell’offerta |
| `content.dateCreated` | **non esiste** | Errore GraphQL |
| `content.releaseDate` | **non esiste** | Errore GraphQL |
| `MovieOrShow.dateCreated` | **non esiste** | Errore GraphQL |
| `MovieOrShow.updatedAt` | **non esiste** | Errore GraphQL |
| `Offer.availableFrom` | **non esiste** | Esistono solo `availableFromTime`/`availableToTime` |
| `NewTitlesEdge.dateCreated` | **non esiste** | La data non è sull’edge di `newTitles` |

## Esempi reali osservati

- **Lupin** (`popularTitles`): `originalReleaseDate = 2021-01-08`; offerta Netflix
  `dateCreated = 2026-10-23`, `availableFromTime = null`.
- **Il Signore degli Anelli: Gli Anelli del Potere** (`newTitles`, Prime Video):
  `originalReleaseDate = 2022-09-01`, `dateCreated = 2026-11-18`,
  `availableFromTime = 2022-09-02T00:50:00Z`.
- **Cunk on Cinema** (`newTitles`, Netflix): `dateCreated = 2026-11-15`,
  `availableFromTime = null`.
- **Odissea** (`newTitles`): `dateCreated = 2000-07-14`, `availableFromTime = null`.

I valori mostrano che `dateCreated` **non è** la data di aggiunta ufficiale del
provider: per LoTR è il 2026-11-18 mentre `availableFromTime` è il 2022-09-02;
per Odissea è il 2000-07-14. È la data del record offerta/aggregatore.

## Conseguenze per MdbUP

- `content.originalReleaseDate` è una data di **uscita**, non di disponibilità.
- `Offer.dateCreated` può essere conservata come metadato JustWatch, ma non va
  presentata come “data ufficiale di aggiunta del provider”.
- `Offer.availableFromTime` / `availableToTime` / `availableTo` sono le uniche
  date di disponibilità pubblicate, e non sono sempre valorizzate.
- `newTitles(pageType: NEW|UPCOMING)` resta il modo pubblico per osservare
  novità/in arrivo, ma non espone una data sull’edge.
- La policy attuale `date_basis=UNKNOWN` per JustWatch pubblico resta corretta:
  non c’è una data ufficiale del provider. Se si vuole usare `dateCreated`,
  va introdotta un’etichetta esplicita di **data record JustWatch**, non
  `PROVIDER_OFFICIAL`.

## Riproduzione

```bash
# Campo release date
curl -sS https://apis.justwatch.com/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"query { popularTitles(country: IT, first: 1) { edges { node { id ... on Movie { content(country: IT, language: it) { title originalReleaseDate } } } } } }"}'

# Campi offerta
curl -sS https://apis.justwatch.com/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"query { popularTitles(country: IT, first: 1) { edges { node { id offers(country: IT, platform: WEB) { dateCreated availableFromTime availableToTime availableTo updatedAt } } } } }"}'
```
