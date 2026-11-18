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
