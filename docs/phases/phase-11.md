# Fase 11 — Pulizia, riorganizzazione e architettura definitiva

**Data:** 2026-11-18
**Stato:** completata lato repository, test, build immagine e smoke test dei 4
servizi in CI. La verifica live su produzione (scheduler e dry-run delle 6 liste)
resta in carico all'operatore.

---

## 1. Audit e rimozione dei residui

### Vecchio stack a 7 servizi

Rimossi:

- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `frontend/.dockerignore`
- `deploy/docker-compose.yml`
- `deploy/dockhand-compose.yml`

L'unico compose è `docker-compose.yml` alla root. L'unica immagine applicativa è
`deploy/Dockerfile.api`, con contesto dalla root e SPA compilata nello stesso
build. Non esistono più container separati per frontend, proxy, migrate o
scheduler.

### Backend

Rimossi moduli/helper non importati:

- `FeatureNotImplementedError`
- `to_timezone`
- `genre_name`
- `JustWatchClient.search_titles` e la query GraphQL `QUERY_SEARCH_TITLES`
- `MdbListClient.get_user_lists`, `membership` e il modello `MdbListMembership`
- `audit.list_recent`, `credentials.mark_used`, `runs.get_operation`,
  `users.get_by_id`
- `bindings.is_always_approve`, `bindings.is_dry_run_only`
- `settings.UnknownSettingError`
- `planning.PlanSamples` / `plan_samples`
- `snapshots.get_snapshot_summary`
- `config_portability._provider_slug_map`

Dipendenze rimosse da `backend/pyproject.toml`:

- `packaging`
- `python-multipart`
- `orjson`
- `python-dateutil` (+ `types-python-dateutil`)
- `pytest-cov`
- `freezegun`
- `pgserver`

`uv.lock` è stato rigenerato. Restano come runtime-only, non rilevabili
staticamente, `psycopg`, `uvicorn` ed `email-validator`; `respx` e gli altri
strumenti di test restano nelle dev dependencies perché usati dalla suite.

### Frontend

- Hook TanStack Query spostati da `src/api/` a `src/hooks/` e import aggiornati.
- Payload delle collezioni spostato in `src/api/types.ts` per evitare che
  `src/lib/` dipenda dagli hook.
- Rimossi componenti/helper non referenziati: `IconCalendar`, `InlineCode`,
  `readBlockedReason`, `isTheme` e le costanti esportate senza uso.
- Export interni declassati (nessuna API pubblica inutile).
- `knip` non segnala più export non usati, esclusi i tipi generati da OpenAPI.
- Verificato `package.json`: nessun pacchetto inutilizzato.

### Contesto build e Git

`.gitignore` e `.dockerignore` escludono:

- `node_modules`, `dist`, `.vite`, `test-results`, `playwright-report`, `.playwright`;
- `.venv`, `__pycache__`, cache pytest/mypy/ruff, coverage;
- `backups/`, `secrets/`, `.env*` (tranne `.env.example`), chiavi e certificati;
- `*.db`, `*.sqlite3`, log e file temporanei;
- test, e2e, OpenAPI e documentazione dal contesto runtime Docker.

---

## 2. Architettura e layer

Sono stati eliminati i due principali scostamenti dal monolite modulare:

1. **Errori di dominio**: le classi `AppError` e derivate sono ora in
   `app/domain/errors.py`; `app/api/errors.py` conserva solo l'adapter FastAPI e
   li ri-esporta per compatibilità. Services, connector e job non importano più
   `app.api`.
2. **Comandi condivisi**: i modelli Pydantic di input (`CollectionCreateIn`,
   `BindingCreateIn`, `PreviewRequest`, `TargetCreateIn`, `StartRunIn`, …) sono
   in `app/domain/commands.py`. Gli schemi API li ri-esportano; i services
   importano il dominio.

Altri interventi:

- nuova `app/services/settings.py` per render, validazione e audit;
- export/import configurazione con audit nel service, non nel router;
- accodamento acquisizione in `collection_admin`, non nel router;
- readiness DB/Redis riusa `system_status`, niente SQL nel router health;
- i router non importano repository, job o connector.
- `seed-sources` installa solo le fonti; provider, mapping e collezioni sono
  creati dall’operatore dalla UI. La pagina **Guida** spiega il flusso.
- I binding JustWatch nascono disabilitati; l'abilitazione richiede un dry-run
  riuscito e lo scheduler non accoda mai una sync MDBList automatica per
  JustWatch. Una sync reale resta manuale.

Regola verificata da `backend/tests/unit/test_architecture.py`:

```text
api ──► services ──► repositories ──► db
 │          ├──► connectors / integrations
 │          ├──► jobs
 │          └──► domain
 └────────────► domain
```

---

## 3. Documentazione

I report sono stati consolidati in:

```text
docs/
├── ARCHITECTURE.md
└── phases/
    ├── phase-01.md … phase-10.md
    └── phase-11.md
```

Le vecchie directory `docs/phase1/`, `docs/phase2/`, `docs/phase4/` … `docs/phase10/`
sono state rimosse. Tutti i riferimenti nei commenti, nel README, nei workflow e
negli script puntano ai nuovi path.

---

## 4. Allineamento path

- `docker-compose.yml` resta l'unico compose; API su `${WEB_PORT:-28080}`.
- `deploy/Dockerfile.api` usa ancora il contesto root e copia `backend/` e
  `frontend/`; rimosso il pacchetto `procps` non più necessario.
- `deploy/scripts/*.sh` usano `REPO_ROOT` corretto (`deploy/scripts/../..`) e
  `COMPOSE_FILE=${REPO_ROOT}/docker-compose.yml`.
- Workflow CI e build-image non referenziano file rimossi.
- README aggiornato con mappa directory, stack, comandi e documentazione.

---

## 5. Verifica eseguita

| Controllo | Esito |
|---|---|
| `pytest` backend | **441 passed** |
| `mypy app` | **0 errori**, 134 file |
| `ruff check` | pulito |
| `ruff format --check` | **205 file** formattati |
| `pip-audit` | **0 vulnerabilità** |
| Vitest | **198 passed** |
| Playwright E2E | **14 passed** |
| `npm run typecheck` | verde |
| `npm run lint` | verde |
| `npm run build` | verde |
| Coverage backend (statement) | **90.12%** (gate 90%) |
| Coverage frontend logica (line/branch/function) | **96.03% / 90.30% / 95.15%** |
| `npm audit --omit=dev` | **0 vulnerabilità** |
| `knip` | nessun export/file non usato (solo tipi generati OpenAPI) |

### Verifica Docker in CI

Il daemon Docker non è disponibile nell'ambiente locale (`docker: command not
found`), quindi la verifica dei container è stata eseguita dal workflow
**Compose smoke** su GitHub Actions:

- build pulita di `deploy/Dockerfile.api`;
- `docker compose up -d` con i 4 servizi;
- attesa di `api`, `worker`, `postgres`, `redis` in stato `healthy`;
- `GET http://127.0.0.1:28080/api/health` con `status=ok`;
- cleanup con `docker compose down -v`.

Esito: **success** (run `44310429762`, commit `ed0c40c`). Il workflow Build image
ha inoltre pubblicato l'immagine GHCR con esito **success**.

### Limiti della verifica

- **Coverage frontend**: il gate misura i moduli logici (`src/lib`, `src/api`,
  `src/hooks`); le pagine e i componenti presentazionali sono esercitati dagli
  E2E Playwright e non sono inclusi nel denominatore, per evitare un gate
  artificiale su JSX non testabile senza browser.
- **Verifica live di produzione non eseguita da questo agente**: l'accesso al
  server è riservato all'operatore. Non sono stati quindi verificati dal vivo gli
  88 slot dello scheduler né il dry-run `to_add=0,to_remove=0` sulle 6 liste
  MDBList; la verifica va eseguita dall'operatore dopo il deploy.
- Nessuna lista MDBList è stata modificata, svuotata o ricreata durante la
  Fase 11. I volumi persistenti non sono stati toccati.

---

## 6. Comandi operativi

```bash
# Qualità backend
cd backend
REDIS_URL="" APP_ENV=test uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run --with pip-audit pip-audit

# Qualità frontend
cd ../frontend
npm run typecheck
npm run lint
npm test
npm run build
npm run test:e2e
npm audit --omit=dev

# Immagine e stack
docker build -f deploy/Dockerfile.api -t mdbup-api:local .
docker compose up -d
```

Per il deploy: aggiornare il compose in Dockhand, redeploy senza rimuovere i
volumi `mdbup_v2_*`, quindi verificare `/api/health`, migrazione `0008`, scheduler
e dry-run delle 6 liste dal pannello dell'app.
