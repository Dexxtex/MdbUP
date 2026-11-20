# MdbUP

Applicazione **self-hosted** per acquisire cataloghi e raccolte dei provider streaming in **Italia** e mantenere aggiornate liste statiche **MDBList** tramite API.

> **Stato: Fase 11 completata lato repository.** Struttura riordinata in monolite modulare, file residui del vecchio stack rimossi, dipendenze e codice morto ripuliti, documentazione consolidata in `docs/phases/`. Lo stack resta a **4 servizi** (`api`, `worker`, `postgres`, `redis`) con API/SPA su **28080**, volumi `mdbup_v2_*` e seed automatico. Restano invariati i vincoli: nessuna cancellazione/ricreazione delle **6 liste MDBList** e nessuna modifica ai volumi persistenti. La verifica live di scheduler e dry-run delle 6 liste richiede accesso allo stack di produzione ed è rimandata all'operatore.

---

## 1. Cosa fa

- Acquisisce cataloghi/raccolte dei provider italiani da fonti autorizzate.
- Separa **film** e **serie**.
- Salva snapshot immutabili con provenienza e qualità esplicite.
- Associa una collezione a una lista statica MDBList.
- Calcola un piano `to_add`/`to_remove`, esegue dry-run, applica MIRROR/APPEND_ONLY.
- Protegge le rimozioni con soglie, lock, idempotenza e riconciliazione.
- Modifica i binding senza ricrearli: modalità, schedule interval/cron, soglie, pausa, visibilità lista.
- Accoda i binding schedulati sulla coda `sync` con lock Redis per target.
- Applica retention configurabile e backup PostgreSQL cifrati con `age`.
- Mostra dashboard, provider, collezioni, binding, run e impostazioni.

### Risultato live (17 novembre 2026)

> Conteggi storici della verifica precedente al reset del database per il nuovo stack Dockhand. Le liste MDBList esterne restano intatte; i binding vanno ricreati sul nuovo database.

| Collezione | Snapshot TMDb | Lista MDBList | Film |
|---|---|---|---|
| Netflix IT — Film Azione | `4f755dfc…` (38 pagine) | [netflix-it-film-azione](https://mdblist.com/lists/netflix-it-film-azione/) | 755 |
| Netflix IT — Film Avventura | `66089823…` (22 pagine) | [netflix-it-film-avventura](https://mdblist.com/lists/netflix-it-film-avventura/) | 428 |
| Netflix IT — Film Horror | `f27f79a3…` (19 pagine) | [netflix-it-film-horror](https://mdblist.com/lists/netflix-it-film-horror/) | 365 |
| Apple TV+ IT — Serie TV | 12 pagine | [apple-tv-it-serie-tv](https://mdblist.com/lists/apple-tv-it-serie-tv/) | 226 serie |
| Mediaset Infinity IT — Film | 8 pagine | [mediaset-infinity-it-film](https://mdblist.com/lists/mediaset-infinity-it-film/) | 146 |
| Disney+ IT — Animazione Top | 27 pagine (fonte) + filtro locale | [disney-it-animazione-top](https://mdblist.com/lists/disney-it-animazione-top/) | 114 |

Tutte le liste sono pubbliche, in modalità `MIRROR`, con binding manuale e approvazione del piano. Il confronto TMDb ↔ MDBList è stato eseguito leggendo gli ID TMDb da entrambi i lati: nessuna differenza.

### Provider verificati live (TMDb, IT)

| Provider | Film TMDb | Serie TMDb |
|---|---:|---:|
| Netflix | 8 | 8 |
| Amazon Prime Video | 119 | 119 |
| Disney+ | 337 | 337 |
| NOW | 39 | 39 |
| Timvision | 109 | 109 |
| Infinity+ | 110 | — |
| Rakuten TV | 35 | 35 |
| MUBI | 11 | 11 |
| Apple TV+ | 350 | 350 |
| Paramount+ | 531 | 531 |
| RaiPlay | 222 | 222 |
| Mediaset Infinity | 359 | 359 |

Infinity+ non ha copertura TV in Italia: la relativa collezione serie è stata rimossa.

### Fase 7 — UI/UX, retry e metriche

- UI dark-first con tema chiaro persistente, design system a token, sidebar collassabile/drawer mobile, topbar con health API/worker/TMDb/MDBList, badge semantici, skeleton, empty state, toast e conferme per azioni distruttive.
- Dashboard operativa con KPI, coda “Richiede attenzione” (Approva/Scarta/Riprova), timeline prossime sync, consumo API e ultimo backup.
- Builder collezioni guidato con anteprima criteri, generi inclusi/esclusi, voto/voti/anni/lingua, flatrate, Appena rilevati e unione multi-provider.
- Binding/Run detail con pipeline Snapshot → Diff → MDBList, barra soglia rimozioni, tabella campioni ricercabile e controlli inline.
- Impostazioni a schede: Credenziali & Sicurezza, Notifiche & Retry, Backup & Manutenzione, Portabilità JSON.
- Notifiche con retry esponenziale 1m/5m/15m (max 3), `retry_count`/`next_retry_at`/`last_error`, modifica completa del canale e sostituzione opzionale del segreto.
- Stack ridotto a **4 servizi**: SPA compilata dentro l'immagine API, migrazioni all'avvio, worker+beat in un solo processo; nessun reverse proxy integrato.
- `GET /api/metrics` Prometheus protetto da token e `GET /api/system/status` per la UI; backup cron giornaliero + verifica settimanale con `backup-verify`.
- Suite Playwright isolata con API mockate: 7 test E2E, nessuna chiamata a MDBList/TMDb reali.

### Fase 8 — JustWatch pubblico, UI e guardrail

- Fonte `justwatch` con catalogo, novità, in arrivo e classifiche separate; filtro `FLATRATE` di default, post-filter media/package/offerta e mapping provider verificati con `shortName` + `technicalName`.
- Cache GraphQL (300 s, 512 voci) con hit/miss Redis; schema drift, 429 e timeout producono snapshot `INCOMPLETE`/`ANOMALY`, mai validi per MIRROR.
- 12 mapping IT verificati; `justwatch-collections` crea 88 collezioni e salta Rakuten TV (senza flatrate). L'upsert non tocca snapshot esistenti.
- Live: Apple TV+ Film catalogo **116**, classifica **105**, in arrivo **3**; `UPCOMING` distinto da `CURRENT`; preview source-only **READY**.
- UI: card connettore in Provider/Impostazioni→Connettori, builder con fonte e tipologia, badge `Fonte: JustWatch (Aggregatore)`/`Classifica JustWatch`, anteprima e eventi stagioni/episodi.
- Binding JustWatch disabilitato di default, accettazione policy esplicita e dry-run obbligatorio (`DRY_RUN_REQUIRED`).
- Test: **315 backend**, **93 frontend**, **10 E2E**.
- Dettagli: [`docs/phases/phase-08.md`](docs/phases/phase-08.md) e [`docs/phases/phase-08.md`](docs/phases/phase-08.md).

### Fase 9 — multi-fonte, Cambi Catalogo IT e scheduling

- **JustWatch predefinito** (`default_source` configurabile) con selettore esplicito nel builder: JustWatch, TMDb, Combinata locale.
- **Cambi Catalogo IT**: feed ADDED/REMOVED tra snapshot consecutivi `COMPLETE/CLEAN`, baseline saltata, filtri 24h/7g/14g/30g, provider, media, fonte, direzione e ricerca.
- **Combinata locale**: unione o intersezione deduplicata per `media_id` dagli snapshot validi; nessuna chiamata esterna.
- **Scheduling scaglionato**: 96 slot da 15 min, una acquisizione JustWatch per tick, lock Redis, throttle globale 1 req/s, cache condivisa.
- **Matrice provider** JustWatch/TMDb, widget dashboard, ricerca snapshot, eventi stagioni/episodi e avvisi In arrivo.
- Live: Prime Video **8.240**, NOW **1.145**, Disney+ in arrivo **3**, Apple TV+ **116/105/3**; 6 liste MDBList invariate.
- Test: **357 backend**, **115 frontend**, **12 E2E**.
- Dettagli: [`docs/phases/phase-09.md`](docs/phases/phase-09.md) e [`docs/phases/phase-09.md`](docs/phases/phase-09.md).

### Fase 10 — CI verde, snapshot dedup e storage

- **CI bloccante verde**: mypy 0 errori, pip-audit 0 vulnerabilità, npm audit 0, 361 test backend, 115 frontend, 12 E2E.
- **Snapshot invariati deduplicati**: checksum deterministico, `items_from_snapshot_id`, `last_verified_at`; lo storico delle verifiche resta completo e Cambi Catalogo IT continua a funzionare.
- **Retention** protegge lo snapshot che possiede gli item condivisi e l'ultima baseline valida.
- **Storage**: `GET /api/system/status.storage` con byte e righe di snapshot/run; indicatore in Impostazioni.
- **Compose autonomo**: 4 servizi, environment variables, default di primo avvio e `seed-providers` automatico all'avvio dell'API.
- Test: **361 backend**, **115 frontend**, **12 E2E**.
- Dettagli: [`docs/phases/phase-10.md`](docs/phases/phase-10.md).

### Fase 11 — pulizia, riorganizzazione e architettura definitiva

- Rimossi `frontend/Dockerfile`, `frontend/nginx.conf`, `.dockerignore` del vecchio frontend e i compose duplicati in `deploy/`.
- Script operativi spostati in `deploy/scripts/`; compose unico alla root; documentazione consolidata in `docs/phases/phase-01.md` … `phase-11.md` e `docs/ARCHITECTURE.md`.
- Backend: comandi/errori spostati in `app/domain/`, servizi senza dipendenze da `app.api`, API senza SQL diretto; rimossi moduli/helper non usati e dipendenze inutilizzate.
- Frontend: hook spostati in `src/hooks/`, export morti rimossi, payload API separati dai componenti.
- `.gitignore` e `.dockerignore` aggiornati per escludere cache, test, build, backup e segreti.
- Test: **423 backend**, **192 frontend**, **12 E2E**; typecheck, lint, build, mypy, ruff, pip-audit e npm audit verdi. Smoke test CI dei 4 container (`api`, `worker`, `postgres`, `redis`) e health su `28080`: **success**.
- Dettagli: [`docs/phases/phase-11.md`](docs/phases/phase-11.md).

### Fase 6 — hardening e regole avanzate

- Cookie LAN (`mdbsync-session`/`mdbsync-csrf`, `COOKIE_SECURE=false`) e HTTPS (`__Host-…`, `Secure`, HSTS solo su TLS) con switch da `.env`.
- Rate limit login persistente su Redis con lockout configurabile; endpoint `POST /api/auth/change-password` con revoca di tutte le sessioni.
- Rotazione della chiave AES-256-GCM con keyring `APP_ENCRYPTION_KEYS` e CLI `rotate-encryption-key` (credenziali e segreti notifiche, senza reinserire le API key).
- Notifiche webhook/Telegram/Discord configurabili da Impostazioni, con messaggio di prova; eventi `RUN_PENDING_APPROVAL`, `RUN_FAILED`, `RUN_UNCERTAIN`, `AUTH_ERROR`, riepilogo giornaliero opzionale.
- Collezioni `CUSTOM_FILTER`: filtro locale per voto medio, numero voti, anni, lingua, generi inclusi/esclusi e unione multi-provider dagli snapshot validi, senza chiamate API esterne.
- Export/import JSON di provider, mapping, target, collezioni, binding, pianificazioni e impostazioni; nessun segreto o ciphertext.
- Sweep automatico dei lock Redis orfani sulla coda `maintenance`.

### Fase 5 — estensione

- Provider IT verificati live con ID film/serie separati; `flatrate` predefinito.
- Serie TV supportate: Apple TV+ IT Serie TV sincronizzata su MDBList.
- Nuove stagioni/episodi: eventi audit `tv_season_added`/`tv_episode_added` associati alla serie madre; nessuna entità stagione/episodio inviata a MDBList.
- Collezioni **Appena rilevati**: derivate da `availability.first_seen_at`; la prima acquisizione del catalogo sorgente è la baseline e non marca tutto come nuovo.
- **Snapshot condiviso**: più collezioni dello stesso provider/regione/tipo possono riusare un unico snapshot completo, filtrando per genere senza chiamate TMDb.
- Dashboard: contatore reale richieste TMDb/MDBList per ora/giorno + stima da binding attivi.
- Form **Collezioni** per creare/modificare senza CLI; pagina **Run** con filtri provider/stato/tipo media; footer con attribuzioni TMDb/JustWatch.

### Fase 4 — automazione

- Pagina **Binding → Modifica**: `MANUAL`/`INTERVAL`/`CRON`/`DAILY`/`WEEKLY`, `MIRROR`/`APPEND_ONLY`, `max_remove_count`, `max_remove_percent`, attivo/pausa, lista pubblica/privata.
- `PATCH /api/bindings/{id}` con audit; la lista MDBList non viene mai ricreata.
- Visibilità lista tramite `PUT /lists/{id}` (verificato live; non tocca gli elementi).
- Celery Beat accoda i binding scaduti su `sync`; un lock Redis per target impedisce run concorrenti tra scheduler e richieste manuali.
- Run bloccati dalle soglie restano in `AWAITING_APPROVAL`; UI **Approva piano** / **Scarta piano**.
- TMDb/MDBList: retry con backoff+jitter su 429/5xx/timeout; le scritture MDBList non vengono ritentate alla cieca.
- Retention: run riusciti 180 giorni, run falliti/bloccati 90, job 30, sessioni 7, snapshot 90 (configurabili).

---

## 2. Provenienza: tre categorie, mai confuse

| Origine | Significato | Esempio |
|---|---|---|
| `OFFICIAL` | Categoria pubblicata ufficialmente dal provider. | "Netflix IT — Top 10 ufficiale" **solo** con fonte ufficiale verificata. |
| `AGGREGATOR` | Raccolta costruita da un aggregatore. | "Netflix IT — Disponibilità corrente — Fonte TMDb/JustWatch". |
| `CUSTOM` | Filtro o derivazione dell'app. | "Netflix IT — Thriller — Filtro personalizzato". |

`date_basis` distingue:

- `PROVIDER_OFFICIAL`: data dichiarata dal provider — **nessuna fonte verificata**;
- `AGGREGATOR_FIRST_SEEN`: prima osservazione dell'aggregatore (JustWatch `date_created`) — **solo con contratto JustWatch**;
- `APP_FIRST_SEEN`: prima osservazione dell'app (`first_seen_at`) — derivazione `CUSTOM`;
- `UNKNOWN`: nessuna data.

**TMDb non espone la data di aggiunta**: le collezioni TMDb sono "disponibilità corrente", non "aggiunte recenti". La Partner API JustWatch sarebbe l'unica fonte per `date_created`, ma richiede contratto; l'endpoint pubblico è attivo come aggregatore senza date ufficiali.

### JustWatch — fonte `justwatch`

Fonte attiva, senza credenziali, sull'endpoint GraphQL pubblico (distinta dalla
Partner API, che resta bloccata da contratto).

Aggiunge rispetto a TMDb: **novità, in arrivo, in partenza, classifiche con rank e
trend, stagioni ed episodi con offerte**, e gli ID TMDb/IMDb già nel nodo. Non può
dare **date di aggiunta** (nessun timestamp), quindi resta `AGGREGATOR` con
`date_basis=UNKNOWN`.

La paginazione è completa: il tetto di 1999 elementi per query viene aggirato
partizionando `releaseYear`, con un cursore stateless che trasporta gli intervalli
pendenti. Throttle locale obbligatorio: l'endpoint non espone rate limit e non
avvisa prima di un blocco.

```bash
cd backend
uv run python -m app.cli justwatch-collections            # collezioni per i provider mappati
uv run python -m app.cli justwatch-collections --provider netflix
```

Live: collezione `netflix-movie-justwatch` acquisita con **5.525 titoli**, snapshot `COMPLETE`/`CLEAN`/valido, 0 unresolved, 60 pagine; preview source-only `READY` con `to_add=5525`. Nessuna sync MDBList è stata eseguita per questa fonte.

Dettagli, limiti misurati e superficie API verificata:
[`docs/phases/phase-08.md`](docs/phases/phase-08.md).

---

## 3. Stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (sincrono), Alembic, PostgreSQL 16, HTTPX.
- **Job:** Celery + Redis; `worker` con beat embedded (`-B`) in un unico processo.
- **Frontend:** React 18, TypeScript, Vite, TanStack Query, React Hook Form, Zod, Tailwind.
- **Deploy:** Docker Compose a 4 servizi; SPA statica servita da FastAPI; TLS/reverse proxy esterni.
- **Test:** pytest, respx, Vitest, ESLint, ruff.

---

## 4. Struttura

```text
.
├── docker-compose.yml          # stack autonomo a 4 servizi
├── .env.example                # variabili e default documentati
├── .dockerignore / .gitignore
├── README.md
├── backend/
│   ├── app/
│   │   ├── api/                # router HTTP, deps auth/CSRF, schemi request/response
│   │   ├── domain/             # enum, comandi, errori e regole pure
│   │   ├── services/           # casi d'uso: acquisizione, diff, sync, notifiche
│   │   ├── connectors/         # adattatori TMDb, JustWatch, CSV e interfaccia
│   │   ├── integrations/       # client HTTP MDBList/TMDb/JustWatch
│   │   ├── repositories/       # query SQLAlchemy
│   │   ├── db/                 # session, base e modelli ORM
│   │   ├── jobs/               # Celery app, task, beat e scheduler
│   │   └── core/               # config, logging, crypto, lock, metriche
│   ├── alembic/                # migrazioni 0001 … 0006
│   └── tests/                  # unit, integration, contract
├── frontend/
│   ├── src/api/                # client HTTP, tipi, query keys
│   ├── src/hooks/              # hook TanStack Query
│   ├── src/components/         # UI base e componenti dominio
│   ├── src/pages/              # pagine React
│   ├── src/lib/                # funzioni pure, formato, validazione, tema
│   └── e2e/                    # Playwright
├── deploy/
│   ├── Dockerfile.api          # immagine unica API + worker + SPA
│   └── scripts/                # backup, verify e restore host
└── docs/
    ├── ARCHITECTURE.md         # architettura definitiva, flussi, sicurezza
    └── phases/                 # report consolidati phase-01 … phase-11
```

Non esistono più `frontend/Dockerfile`, `frontend/nginx.conf`, compose
duplicati in `deploy/` o pacchetti frontend legacy: l'unica superficie di build
è `deploy/Dockerfile.api` con contesto dalla root.

---

## 5. Avvio in sviluppo

### Backend

```bash
cd backend
uv sync --extra dev

export APP_ENV=dev
export DATABASE_URL="sqlite:///./mdbup.db"
export APP_ENCRYPTION_KEY="$(python -c 'import base64,os; print(base64.b64encode(os.urandom(32)).decode())')"
export BOOTSTRAP_TOKEN="dev-bootstrap-token"
export REDIS_URL=""

uv run alembic upgrade head
uv run python -m app.cli seed-providers
uv run python -m app.cli bootstrap-admin --email admin@example.com
# Collezioni TMDb per genere (ID TMDb: 28 azione, 12 avventura, 27 horror)
uv run python -m app.cli create-collection --provider netflix --media-type movie   --slug netflix-movie-azione --name "Netflix — Film Azione" --genre-ids 28
uv run uvicorn app.main:app --reload --port 8000
```

API: `http://localhost:8000/api/docs` (OpenAPI).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Aprire `http://localhost:5173`. Il dev server Vite inoltra `/api` a `http://localhost:8000` (vedi `vite.config.ts`).

### Primo accesso

1. Aprire `/bootstrap` e usare il token `BOOTSTRAP_TOKEN`.
2. Creare l'admin con una password di almeno 12 caratteri.
3. In **Impostazioni → Credenziali** inserire TMDb API key e MDBList API key.
4. Eseguire `seed-providers` se non già fatto.
5. Acquisire una collezione e creare un binding.
6. Dalla pagina **Binding** usare `Dry-run` per il piano o `Esegui` per una sync reale; il piano reale richiede approvazione.

Per cambiare la password dell'admin (revoca anche le sessioni attive):

```bash
docker compose exec -T api python -m app.cli reset-password --email admin@example.com
```

---

## 6. Avvio con Docker Compose

Il compose della root è **autonomo**: non serve `.env`, non serve `secrets/` e
non esiste un servizio `init` o `migrate`. I valori sono environment variables
con default semplici per il primo avvio; in Dockhand basta incollare
`docker-compose.yml` e avviare lo stack.

```bash
docker compose pull
docker compose up -d
# API + SPA: http://<host>:28080
```

Variabili principali:

| Variabile | Default | Note |
|---|---|---|
| `MDBUP_IMAGE` | `ghcr.io/dexxtex/mdbup:latest` | immagine unica |
| `WEB_PORT` | `28080` | porta HTTP pubblicata dall'API |
| `POSTGRES_PASSWORD` | `mdbup` | **non cambiarla dopo il primo avvio** |
| `APP_ENCRYPTION_KEY` | Base64 di 32 byte | **non cambiarla dopo il primo avvio** |
| `BOOTSTRAP_TOKEN` | `bootstrap` | usato una sola volta su `/bootstrap` |
| `METRICS_TOKEN` | `metrics` | token Prometheus |
| `APP_BASE_URL` | `http://<host>:28080` | origine esatta per CSRF/cookie |
| `DEFAULT_SOURCE` | `justwatch` | fonte predefinita del builder |
| `CATALOG_SCHEDULE_ENABLED` | `true` | scheduling scaglionato |

I default sono volutamente semplici e **da sostituire** prima di esporre il
servizio. Dopo il primo avvio cambiare `POSTGRES_PASSWORD` o
`APP_ENCRYPTION_KEY` rende il database/credenziali illeggibili: per farlo
servirebbe ricreare i volumi `mdbup_v2_*`.

All'avvio l'API esegue:

```text
alembic upgrade head
python -m app.cli seed-providers
uvicorn app.main:app ...
```

Il seed è idempotente e garantisce fonti, provider e mapping anche su un
database vuoto. Il worker esegue Celery Beat embedded (`-B`).

### Immagine precompilata (GHCR)

Il workflow `Build image` pubblica l'immagine unica su GitHub Container Registry
a ogni push su `main`, per i tag `v*` e manualmente da **Actions → Build image →
Run workflow**.

```bash
# default: immagine GHCR
docker compose pull
docker compose up -d

# build locale, se serve
docker build -f deploy/Dockerfile.api -t mdbup-api:local .
MDBUP_IMAGE=mdbup-api:local docker compose up -d
```

L'immagine è `ghcr.io/dexxtex/mdbup`; i tag includono `latest`, `sha-<commit>`
e il nome del branch/tag. Se il package GHCR non è pubblico, renderlo visibile
da **GitHub → Packages → mdbup → Settings**.

Servizi: **`api`, `worker`, `postgres`, `redis`**. `api` pubblica
`${WEB_PORT:-28080}`; PostgreSQL e Redis restano sulla rete interna e non sono
esposti sull'host. `worker` esegue anche Celery Beat (`-B`) e raggiunge
TMDb/MDBList tramite la rete predefinita. Non ci sono container `proxy`,
`frontend`, `migrate` o `scheduler` separati.

Per HTTP su LAN (senza TLS):

```env
APP_BASE_URL=http://<host>:28080
COOKIE_SECURE=false
WEB_PORT=28080
```

Con un reverse proxy TLS usare `APP_BASE_URL=https://<dominio>` e
`COOKIE_SECURE=true`: i cookie diventano `__Host-mdbsync-session` /
`__Host-mdbsync-csrf`, `Secure`, `Path=/`, senza `Domain`.

### Reverse proxy esterno

MdbUP **non integra** Caddy/Nginx/Traefik: l'app ascolta HTTP sulla porta
`28080` e la SPA è servita dalla stessa API. Ognuno può metterci davanti il
proxy che preferisce.

```env
APP_BASE_URL=https://mdbup.example.com
COOKIE_SECURE=true
WEB_PORT=28080
```

- Con TLS terminato dal proxy: `APP_BASE_URL=https://...`, `COOKIE_SECURE=true`;
  i cookie diventano `__Host-mdbsync-session`/`__Host-mdbsync-csrf`, `Secure`,
  `Path=/`, senza `Domain`.
- In LAN HTTP: `APP_BASE_URL=http://<ip>:28080`, `COOKIE_SECURE=false`.
- HSTS, CSP e gli altri header di sicurezza possono essere aggiunti dal proxy;
  l'API applica comunque CSP/X-Frame-Options/Referrer-Policy alle proprie
  risposte.
- Il proxy deve inoltrare `/` e `/api/*` allo stesso upstream `api:8000`
  (host: `28080`).

> **Nota:** il compose è stato avviato e verificato su Ubuntu con Docker 29.9 / Compose v5.7.1. I secret file devono essere leggibili dall'UID 10001: Docker Compose li monta con i permessi dell'host, non con `0444` automatico.

### Backup e restore

Prerequisiti: `age` sull'host, chiave pubblica in `secrets/backup_age_recipient`, chiave privata fuori dal repository.

```bash
# backup manuale
PATH=/home/mdbup/bin:$PATH BACKUP_DIR=/home/mdbup/mdbup-backups ./deploy/scripts/backup.sh

# crontab consigliato per mdbup
0 3 * * * cd /home/mdbup/mdbup && PATH=/home/mdbup/bin:$PATH BACKUP_DIR=/home/mdbup/mdbup-backups ./deploy/scripts/backup.sh >> /home/mdbup/mdbup-backups/backup.log 2>&1
```

Il restore è documentato in `deploy/scripts/restore.sh`; per un drill usare un database scratch, non il DB live. La Fase 7 ha verificato il backup `mdbup-20261117T201311Z.dump.age` (4.0 MB, checksum OK) e il comando `python -m app.cli backup-verify` (checksum/header; la decifratura completa richiede la chiave age sull'host). Il cronjob giornaliero è installato su `mdbup`:

```cron
0 3 * * * cd /home/mdbup/mdbup && PATH=/home/mdbup/bin:$PATH BACKUP_DIR=/home/mdbup/mdbup-backups ./deploy/scripts/backup.sh >> /home/mdbup/mdbup-backups/backup.log 2>&1
30 3 * * 0 cd /home/mdbup/mdbup && PATH=/home/mdbup/bin:$PATH BACKUP_DIR=/home/mdbup/mdbup-backups BACKUP_STATUS_FILE=/home/mdbup/mdbup-backups/last_backup.json BACKUP_AGE_IDENTITY_FILE=/home/mdbup/mdbup-age-keys.txt ./deploy/scripts/backup-verify.sh >> /home/mdbup/mdbup-backups/backup-verify.log 2>&1
```

`deploy/scripts/backup.sh` scrive `last_backup.json` (timestamp, file, size, sha256, status) letto da `/api/metrics` e `/api/system/status`; la retention GFS non tocca il file di stato. In aggiunta, `BACKUP_RETENTION_DAYS=180` rimuove gli archivi più vecchi di 180 giorni (0 disabilita il limite); l'archivio più recente non viene mai eliminato.

---

## 7. Test

```bash
# Backend (gate: 90% statement coverage)
cd backend
REDIS_URL="" APP_ENV=test uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=90
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run --with pip-audit pip-audit

# Frontend (gate: 90% line/branch/function coverage sui moduli logici)
cd ../frontend
npm run test:coverage
npm run typecheck
npm run lint
npm run build
npm run test:e2e
npm audit --omit=dev
```

Stato attuale: **423 test backend**, **192 test frontend** e **12 test E2E
Playwright** verdi; `ruff check`, `ruff format --check`, `mypy`, build Vite,
lint e audit senza vulnerabilità. I test unitari usano `respx`/fixture; la
verifica live è stata eseguita separatamente su TMDb e MDBList reali.

Coverage gate: backend **90.25%** statement, frontend **96.94%** linee / **90.33%** branch / **96.39%** funzioni sui moduli logici (`src/lib`, `src/api`, `src/hooks`). Le pagine e i componenti presentazionali sono coperti dagli E2E Playwright, non dal denominatore Vitest.

---

## 8. API principali

| Metodo | Endpoint | Note |
|---|---|---|
| `GET` | `/api/health` | Liveness |
| `GET` | `/api/ready` | DB/Redis/encryption key |
| `GET` | `/api/system/status` | Health, code, run, API usage, backup, prossime sync (admin) |
| `GET` | `/api/metrics` | Prometheus text; richiede `METRICS_TOKEN` (Bearer/X-Metrics-Token) |
| `POST` | `/api/auth/bootstrap` | Primo admin, token monouso |
| `POST` | `/api/auth/login` | Cookie HttpOnly + CSRF; rate limit Redis con lockout |
| `POST` | `/api/auth/change-password` | Verifica password attuale, revoca tutte le sessioni |
| `GET` | `/api/dashboard` | Contatori, alert, run recenti |
| `GET` | `/api/providers` | Provider IT + mapping TMDb |
| `GET` | `/api/collections` | Collezioni con origine/date_basis e filtri |
| `POST` | `/api/collections` | Crea una collezione (catalogo o Appena rilevati) |
| `PATCH` | `/api/collections/{id}` | Modifica una collezione |
| `GET` | `/api/genres` | Generi TMDb ufficiali per tipo media |
| `POST` | `/api/collections/{id}/acquire` | Accoda acquisizione |
| `GET` | `/api/snapshots/{id}/items` | Anteprima titoli |
| `GET/POST` | `/api/targets` | Liste MDBList |
| `GET/POST` | `/api/bindings` | Binding collezione → lista |
| `POST` | `/api/previews` | Piano/dry-run |
| `GET` | `/api/previews/{id}` | Esito preview |
| `POST` | `/api/bindings/{id}/runs` | Avvia sync |
| `GET` | `/api/runs` | Cronologia con filtri provider/stato/tipo media |
| `GET` | `/api/runs/{id}` | Stato sync |
| `POST` | `/api/runs/{id}/approve` | Approva piano bloccato |
| `POST` | `/api/runs/{id}/cancel` | Annulla |
| `POST` | `/api/runs/{id}/reconcile` | Riconcilia |
| `GET/PUT/DELETE` | `/api/credentials` | Credenziali mascherate/cifrate |
| `GET` | `/api/notifications/channels` | Canali di notifica (segreti mascherati) |
| `POST` | `/api/notifications/channels` | Crea un canale webhook/Telegram/Discord |
| `PATCH/DELETE` | `/api/notifications/channels/{id}` | Modifica/elimina un canale |
| `POST` | `/api/notifications/channels/{id}/test` | Messaggio di prova |
| `GET` | `/api/config/export` | Configurazione JSON senza segreti |
| `POST` | `/api/config/import` | Import upsert di provider/mapping/collezioni/binding |

Tutte le mutazioni richiedono `X-CSRF-Token`; gli errori usano l'envelope `{error:{code,category,message,retryable,request_id,details}}`.

---

## 9. Sicurezza

- Bootstrap con token monouso, nessuna credenziale predefinita.
- Password Argon2id; sessioni con cookie `HttpOnly`, `Secure` in produzione, `SameSite=Lax`; CSRF double-submit.
- Rate limit login persistente su Redis (fixed window + lockout); `Origin`/`Referer` confrontati per schema, host e porta effettiva.
- Cookie LAN senza prefisso; in HTTPS i nomi diventano automaticamente `__Host-…` e `Secure`; HSTS è inviato solo su TLS.
- Reverse proxy esterno: l'app espone solo HTTP 28080; TLS/HSTS sono responsabilità del proxy scelto dall'operatore.
- `/api/metrics` non è mai pubblico: richiede `METRICS_TOKEN` (Bearer o `X-Metrics-Token`); senza token risponde 503.
- Rotazione chiavi: `APP_ENCRYPTION_KEYS` è un keyring JSON; `rotate-encryption-key` re-cifra credenziali e segreti notifiche con la nuova versione.
- Credenziali delle integrazioni e segreti delle notifiche solo backend, cifrati AES-256-GCM con chiave esterna al DB, mascherati, esclusi da log ed export.
- SSRF: nessun URL arbitrario; host allowlist nei connettori; redirect disabilitati.
- Log JSON con redazione; audit log append-only a livello applicativo.
- Docker: non-root, read-only, `cap_drop: ALL`, `no-new-privileges`; PostgreSQL/Redis non pubblicati.
- Backup PostgreSQL cifrati con `age`; chiave di cifratura custodita separatamente.

Dettagli: [`docs/phases/phase-01.md`](docs/phases/phase-01.md).

---

## 10. Attribuzione

- **TMDb:** "This product uses the TMDB API but is not endorsed or certified by TMDB."
- **JustWatch:** attribuzione obbligatoria per i dati watch provider (TMDb è "powered by JustWatch"); link alla pagina del titolo. Se in futuro si usa la Partner API, rispettare i link brandizzati e la riservatezza contrattuale.
- **MDBList:** usare l'API secondo i limiti del piano; non aggirare rate limit; non creare liste duplicate per simulare l'ordine.
- **Movieplayer / ComingSoon / PlayPilot:** nessun uso automatizzato; solo link-out manuale, se consentito.

---

## 11. Limitazioni note

1. **TMDb non ha la data di aggiunta**: le collezioni sono "disponibilità corrente", non "aggiunte recenti".
2. **JustWatch Partner è disabilitato**: richiede contratto. L'endpoint pubblico è attivo in modo opt-in con throttle 1 req/s, nessuna data di aggiunta e rischio ToS/ban IP.
3. **Top 10 ufficiale** non è implementabile senza una fonte ufficiale verificata.
4. **MDBList**: reorder max 1.000 elementi per chiamata, non atomico; niente idempotency key lato API.
5. **TMDb discover** è limitato a 500 pagine; cataloghi grandi richiedono partizionamento. Per Apple TV+ Serie TV è stato usato `sort_by=vote_count.desc` per evitare duplicati da paginazione.
6. **Preview** è calcolata in modo sincrono nell'API (può essere lenta su liste grandi).
7. **Rate limit di scrittura MDBList** è process-local (240 item/5 min); con più worker serve un token bucket Redis.
8. **Binding manuali per default**: le 5 liste sono in `MIRROR` con schedule `MANUAL`; la pagina **Modifica** permette `INTERVAL`/`CRON`/`DAILY`/`WEEKLY`.
9. **Liste pubbliche**: le 5 liste MDBList sono pubbliche. La pagina **Modifica** può renderle private via `PUT /lists/{id}`.
10. **HTTP LAN senza TLS**: cookie non `__Host-` e `COOKIE_SECURE=false`; per esposizione Internet usare HTTPS e `COOKIE_SECURE=true` (prefisso automatico). HSTS è inviato solo su TLS.
11. **Admin**: l'email è `admin@example.com`; la password è stata generata al bootstrap e non è nel repository. Conservarla in un password manager.
12. **Backup**: chiave privata `age` sull'host in `/home/mdbup/mdbup-age-keys.txt`; senza di essa il backup non è ripristinabile. Il crontab non è installato automaticamente.
13. **Appena rilevati**: la prima acquisizione è una baseline vuota; la lista si popola solo con titoli osservati dopo la baseline. Non è una data ufficiale del provider.
14. **Stagioni/episodi**: sono eventi audit sulla serie madre, non entità separate inviate a MDBList.
15. **Fonti editoriali secondarie**: ComingSoon/Movieplayer non sono stati integrati per vincoli robots/ToS e assenza di API pubblica stabile.
16. **Notifiche**: l'invio è best-effort con timeout; un webhook irraggiungibile viene registrato su `last_error` ma non blocca il run. Non c'è una coda di retry dedicata.
17. **Collezioni locali**: richiedono snapshot validi delle sorgenti; se una sorgente manca, lo snapshot combinato è `WARNINGS`/non valido e non autorizza MIRROR.
18. **Export/import**: i segreti non sono esportati; i canali di notifica sono inclusi solo come metadati e non vengono riattivati senza segreto.
19. **Rotazione chiavi**: la nuova versione deve essere già presente in `APP_ENCRYPTION_KEYS`; dopo la rotazione va aggiornata `APP_ENCRYPTION_KEY_VERSION` e riavviato lo stack.
20. **E2E**: la suite Playwright usa API mockate e non avvia un backend reale; copre la UI e i payload, non l'integrazione completa con PostgreSQL/Celery.
21. **Reverse proxy esterno**: l'app non include Caddy/Nginx; esporre `28080` con il proxy scelto e impostare `APP_BASE_URL`/`COOKIE_SECURE` di conseguenza.
22. **Metrics token**: `METRICS_TOKEN` va ruotato manualmente e non è gestito dal keyring; senza token l'endpoint risponde 503.
23. **backup-verify nel container**: verifica checksum/header; la decifratura PGDMP completa richiede la chiave age sull'host (script `backup-verify.sh`).
24. **UI**: redesign verificato con typecheck/build/test/lint e smoke live, senza screenshot regression automatici.

---

## 12. Documentazione

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architettura definitiva a 4 servizi, flussi dati, sicurezza e mappa directory.
- [`docs/phases/phase-01.md`](docs/phases/phase-01.md) — fonti, architettura, modello dati e piano.
- [`docs/phases/phase-02.md`](docs/phases/phase-02.md) — contratto di implementazione e stato.
- [`docs/phases/phase-03.md`](docs/phases/phase-03.md) — implementazione core.
- [`docs/phases/phase-04.md`](docs/phases/phase-04.md) — automazione.
- [`docs/phases/phase-05.md`](docs/phases/phase-05.md) — estensione multi-fonte.
- [`docs/phases/phase-06.md`](docs/phases/phase-06.md) — hardening.
- [`docs/phases/phase-07.md`](docs/phases/phase-07.md) — backup, notifiche, metriche e UI/UX.
- [`docs/phases/phase-08.md`](docs/phases/phase-08.md) — JustWatch pubblico e guardrail.
- [`docs/phases/phase-09.md`](docs/phases/phase-09.md) — multi-fonte, Cambi Catalogo IT e scheduling.
- [`docs/phases/phase-10.md`](docs/phases/phase-10.md) — CI, snapshot dedup e storage.
- [`docs/phases/phase-11.md`](docs/phases/phase-11.md) — pulizia, riorganizzazione e verifica finale.
- [`docs/justwatch-it-verification.md`](docs/justwatch-it-verification.md) — verifica live degli endpoint JustWatch per film e serie in Italia.

---

## 13. Prossimi passi

1. Acquisire, su richiesta, tutte le collezioni JustWatch già create (Prime Video, NOW, RaiPlay, Paramount+, Disney+, Mediaset, Infinity+, Timvision, MUBI) e osservare i cambi catalogo reali.
2. E2E full-stack su stack isolato (backend reale + MDBList stub), oltre alla suite UI mockata.
3. Alert esterni Prometheus/Alertmanager e dashboard Grafana.
4. Drill di restore mensile automatizzato e verifica periodica della chiave age.
5. Valutare JustWatch Partner per date ufficiali e una fonte ufficiale Top 10 solo con contratti/credenziali.
6. Valutare una coda retry notifiche con dead-letter e UI di storico consegne.
