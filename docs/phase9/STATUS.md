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
