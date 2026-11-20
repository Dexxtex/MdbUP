# JustWatch pubblico — verifica endpoint IT (film e serie)

**Data verifica:** 2026-11-18
**Endpoint:** `POST https://apis.justwatch.com/graphql` (pubblico, senza credenziali)
**Paese:** `IT` — **Lingua:** `it` — **Throttle:** 1,2 s tra le chiamate
**Modalità:** sola lettura; nessuna scrittura su MDBList, nessuna modifica a DB o volumi.

## Esito sintetico

| Endpoint / operazione | Film | Serie TV | Esito |
|---|---|---|---|
| healthcheck (`__typename`) | — | — | **OK** (187 ms) |
| `packages(country: IT, platform: WEB)` | — | — | **OK**, 109 package |
| `genres(language: it)` | — | — | **OK**, 19 generi localizzati |
| `popularTitles` (nfx, 2020–2025, FLATRATE) | 2.592 totali | 1.858 totali | **OK** |
| `newTitles(pageType: NEW, nfx, FLATRATE)` | 600 totali, 5/5 film | 600 totali, 5/5 serie | **OK dopo fix** |
| `newTitles(pageType: UPCOMING, nfx)` | 27 totali, 5/5 film | 86 totali; primo sample 4 serie + 1 film, il connector filtra il film | **OK dopo fix** |
| `streamingCharts` (nfx) | 5.127 totali | 2.923 totali | **OK**, rank globali |
| `node(id).seasons` | n/a | Lupin: 4 stagioni | **OK** |
| `node(id).episodes` | n/a | Lupin S1: 5 episodi con offerte | **OK** |
| `newTitles(pageType: LEAVING_SOON)` | 0 con nfx | 0 con nfx | non usato dal connector |

## Dettaglio

### Package e mapping provider

`packages` ha restituito **109 package** per l’Italia. I 12 mapping di riferimento
sono stati confrontati su `shortName` **e** `technicalName`:

| Provider | shortName | technicalName | FLATRATE |
|---|---|---|---|
| Netflix | `nfx` | `netflix` | sì |
| Prime Video | `prv` | `amazonprimevideo` | sì |
| Disney+ | `dnp` | `disneyplus` | sì |
| Apple TV+ | `atp` | `appletvplus` | sì |
| NOW | `ntv` | `nowtv` | sì |
| Paramount+ | `pmp` | `paramountplus` | sì |
| RaiPlay | `rai` | `raiplay` | sì |
| Mediaset Infinity | `msp` | `mediasetplay` | sì |
| Infinity+ | `inf` | `infinity` | sì |
| Timvision | `tvi` | `timvision` | sì |
| Rakuten TV | `wki` | `wuaki` | **no** (correttamente saltato) |
| MUBI | `mbi` | `mubi` | sì |

### Film

- `popularTitles` con Netflix, FLATRATE, 2020–2025: **2.592** risultati;
  primi titoli: *Godzilla Minus One* (TMDb 940721), *Drop: Accetta o rifiuta*
  (1249213), *Black Bag - Doppio gioco* (1233575).
- `newTitles NEW`: **600** risultati, tutti `MOVIE` e con ID TMDb/IMDb.
- `newTitles UPCOMING`: **27** risultati, tutti `MOVIE`.
- `streamingCharts`: **5.127** risultati; rank JustWatch globali
  (es. *Fight Club* rank 3, *Godzilla Minus One* rank 9).

### Serie TV

- `popularTitles` con Netflix, FLATRATE, 2020–2025: **1.858** risultati;
  *Lupin* (TMDb 96677), *Black Doves* (225385), *The Diplomat* (203857).
- `newTitles NEW`: **600** risultati dopo il fix, tutti `SHOW` (prima il
  parser riceveva nodi `SHOW_SEASON` e la collezione restava vuota).
- `newTitles UPCOMING`: **86** risultati; il primo sample contiene 4 serie e 1
  film. Il server mescola i tipi, quindi il connector applica il post-filter
  sul tipo media.
- `streamingCharts`: **2.923** risultati; *Chiaroscuro* rank 3, *The Body*
  rank 4, *Lupin* rank 6.
- Stagioni/episodi di *Lupin*: 4 stagioni (`Part 1`, `Stagione 2`, `Stagione 3`,
  `Stagione 4`); prima stagione 5 episodi, tutti con offerta Netflix
  `FLATRATE` SD/HD.

## Problema trovato e corretto

`newTitles` non restituisce `Show` per le serie: restituisce nodi
**`SHOW_SEASON`** (`Season`). Il vecchio fragment `TitleDetails on MovieOrShow`
non si applicava a `Season`, quindi il server rispondeva `node: {}` e il
connector scartava tutti i nodi. Le collezioni `RECENTLY_ADDED` e `UPCOMING`
per le serie restavano vuote/`ANOMALY`.

Correzione:

```graphql
edges {
  node {
    ... on Movie { ...TitleDetails }
    ... on Season { show { ...TitleDetails } }
  }
}
```

Il client usa il `Show` annidato come titolo della serie. Il post-filter
`media_type` continua a scartare eventuali film mescolati dal server.

Test aggiunto: `test_new_titles_maps_show_season_to_parent_show`.

## Nota di prodotto

I mapping IT qui verificati sono disponibili come riferimento per la creazione
dei provider dalla UI; MdbUP non li installa automaticamente. `justwatch-collections`
può eseguire la riverifica live e creare le collezioni su richiesta. I binding
JustWatch restano disabilitati fino a un dry-run riuscito e lo scheduler non
accoda mai una sync MDBList automatica per questa fonte.

## Limiti

- JustWatch pubblico non fornisce date di aggiunta: `date_basis=UNKNOWN`.
- Le classifiche sono rank dell’aggregatore, **non** una Top 10 ufficiale.
- Il totale `newTitles` per le serie conta stagioni/episodi, non serie uniche:
  possibili duplicati tra pagine, gestiti dalla deduplicazione a valle.
- `LEAVING_SOON` non è esposto come tipo di collezione; con Netflix IT il
  campione era vuoto.
- La verifica è stata eseguita in locale, non sullo stack di produzione.
