# JustWatch pubblico — verifica generi e catalogo IT

**Data:** 2026-11-18
**Endpoint:** `POST https://apis.justwatch.com/graphql`
**Paese:** `IT` — **Lingua:** `it` — **Throttle:** 1,2 s
**Modalità:** sola lettura, nessuna scrittura MDBList, nessun volume toccato.

## Esito

| Endpoint | Film | Serie | Esito |
|---|---|---|---|
| `genres(language: it)` | 19 generi | 19 generi | **OK** |
| `popularTitles` per ogni genere | 19/19 non vuoti | 19/19 non vuoti | **OK** |
| `popularTitles` con genere + anni | OK | OK | **OK** |
| Paginazione catalogo | 100/pagina, cap #1999 | 100/pagina, cap #1999 | **OK** |
| Partizionamento per anno | split automatico oltre 1999 | split automatico oltre 1999 | **OK** |

## Generi restituiti (19)

`thriller-e-mistero` (`trl`), `fantascienza` (`scf`), `animazione` (`ani`),
`commedia` (`cmy`), `documentario` (`doc`), `famiglia` (`fml`),
`storia` (`hst`), `sport-e-fitness` (`spt`), `di-produzione-europea` (`eur`),
`romantico` (`rma`), `drammatico` (`drm`), `fantasy` (`fnt`), `orrore` (`hrr`),
`musica` (`msc`), `guerra` (`war`), `reality-tv` (`rly`),
`azione-e-avventura` (`act`), `giallo` (`crm`), `western` (`wsn`).

Per ogni genere sono state verificate entrambe le tipologie:

- Film: 19 generi, **19/19** con risultati, tutti `MOVIE`, ID TMDb/IMDb presenti;
- Serie: 19 generi, **19/19** con risultati, tutti `SHOW`, ID TMDb/IMDb presenti.

Esempi di totali con Netflix flatrate (range 1900–2026):

| Genere | Film | Serie |
|---|---:|---:|
| Drammatico (`drm`) | 2.774 | 1.595 |
| Commedia (`cmy`) | 2.291 | 982 |
| Thriller (`trl`) | 1.300 | 693 |
| Animazione (`ani`) | 333 | 494 |
| Western (`wsn`) | 35 | 17 |

## Bug trovato e corretto

L’endpoint `genres` restituisce tre forme:

```text
shortName       ani
technicalName   animation
slug            animazione
```

`TitleFilter.genres` di `popularTitles` accetta **solo lo shortName** (`ani`).
Prima del fix, un filtro costruito con lo `slug` localizzato (`animazione`) o
con il `technicalName` (`animation`) falliva con:

```text
JustWatch: animazione genre not found (popularTitles)
```

Il connector ora normalizza i filtri tramite la risposta `genres` e accetta
`shortName`, `technicalName` e slug localizzato. Il test
`test_catalog_passes_genre_and_quality_filters` usa lo slug `azione-e-avventura`
e verifica che al server arrivi `act`.

## Paginazione catalogo

Con Netflix, senza filtro genere:

| Media | Totale | offset 0 | offset 100 | offset 1900 | offset 1999 |
|---|---:|---:|---:|---:|---:|
| Film | 5.534 | 100 | 100 | 99 | 0 |
| Serie | 2.981 | 100 | 100 | 99 | 0 |

`first: 101` viene limitato a **100**, coerente con il limite del server.
Oltre il titolo **#1999** il server non restituisce più edge: il connector
partiziona `releaseYear` e prosegue con il proprio cursore
(`1900-1963|1964-2026:…`).

## Note

- Nessun endpoint `subgenres` separato: i subgeneri sono un filtro opzionale
  passato al connector, non una lista pubblica IT verificata.
- I conteggi per genere possono cambiare nel tempo: sono osservazioni, non
  totali garantiti.
- Le classifiche restano rank JustWatch, non Top 10 ufficiali.
