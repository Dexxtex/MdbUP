# Architettura MdbUP

MdbUP è un monolite modulare Python/FastAPI con una SPA React servita dalla
stessa API. Lo stack di esecuzione è composto da **quattro servizi** Docker
Compose e non richiede un reverse proxy interno: TLS e proxy sono esterni.

## 1. Stack a 4 servizi

```text
                         ┌──────────────────────────────┐
  browser  ── HTTP :28080 ──►│ api                          │
                         │ FastAPI + SPA + Alembic      │
                         └───────────┬──────────────────┘
                                     │ SQL
                         ┌───────────▼──────────┐
                         │ postgres:16          │
                         │ dati applicativi     │
                         └──────────────────────┘
                                     ▲
                         ┌───────────┴──────────┐
                         │ worker               │
                         │ Celery worker + beat │
                         └───────────┬──────────┘
                                     │ broker/result
                         ┌───────────▼──────────┐
                         │ redis:7              │
                         │ coda, lock, rate     │
                         └──────────────────────┘
```

| Servizio | Responsabilità | Persistenza |
|---|---|---|
| `api` | HTTP, auth/CSRF, SPA, migrazioni, seed iniziale | volumi applicativi tramite PostgreSQL |
| `worker` | acquisizioni, preview, sync, notifiche, manutenzione, beat | nessuna locale |
| `postgres` | dati relazionali, snapshot, run, audit | volume `mdbup_v2_pgdata` |
| `redis` | broker Celery, lock distribuiti, rate limit, cache | volume `mdbup_v2_redisdata` |

`api` e `worker` usano la stessa immagine (`deploy/Dockerfile.api`) e cambiano
solo per il comando. Non esistono container separati per frontend, proxy,
migrazioni o scheduler.

## 2. Direzione delle dipendenze

```text
app/api ──► app/services ──► app/repositories ──► app/db
   │             │                  │
   │             ├──► app/connectors ──► app/integrations
   │             ├──► app/jobs
   │             └──► app/domain
   └────────────────► app/domain (comandi/errori)
```

Regole applicate e verificate in Fase 11:

- `app/api/` contiene router, dipendenze auth/CSRF, schema request/response;
  non esegue SQL diretto e non importa repository, connector o task.
- `app/domain/` contiene enum, comandi Pydantic condivisi, regole pure e la
  gerarchia degli errori applicativi.
- `app/services/` orchestra i casi d'uso e non importa `app.api`.
- `app/connectors/` adatta le sorgenti esterne; `app/integrations/` contiene i
  client HTTP.
- `app/repositories/` e `app/db/` sono l'unico accesso SQLAlchemy.
- `app/jobs/` contiene Celery, task e scheduler; può dipendere da services e
  domain, non da API.
- `app/core/` contiene configurazione, logging, cifratura, lock, metriche e
  utility trasversali.

## 3. Flussi principali

### Acquisizione

1. l'utente accoda una collezione (`POST /api/collections/{id}/acquire`);
2. `collection_admin` verifica fonte e connettore, quindi accoda il task;
3. il worker usa il connector della fonte (TMDb o JustWatch), normalizza gli
   item e risolve gli identificativi esterni;
4. lo snapshot viene validato, deduplicato per checksum e finalizzato;
5. `catalog_changes` confronta snapshot validi consecutivi per il feed
   **Cambi Catalogo IT**.

### Preview e sync MDBList

1. `POST /api/previews` costruisce un piano locale e calcola `plan_hash`;
2. le soglie bloccano piani troppo distruttivi;
3. un run reale richiede approvazione quando previsto;
4. il worker esegue add/remove/reorder in batch, con advisory lock per target;
5. gli esiti incerti restano `UNCERTAIN` e vengono riconciliati, senza mai
   ricreare o svuotare le liste.

Per JustWatch (aggregatore, `date_basis=UNKNOWN`) il binding nasce **disabilitato**:
snapshot e preview sono sempre possibili, mentre una sync MDBList reale richiede
un dry-run completato con successo e non viene mai accodata automaticamente
dallo scheduler. Provider, mapping e collezioni sono creati dall’operatore;
`seed-sources` precarica solo le fonti e `justwatch-collections` può riverificare
i mapping JustWatch live. La pagina **Provider** può leggere il catalogo unificato
TMDb/JustWatch/TVDB; TheTVDB è una fonte di metadati/company ID, non di disponibilità
territoriale.

### Scheduling

- 96 slot deterministici da 15 minuti (`sha256(slug) % 96`, Europe/Rome);
- massimo un'acquisizione JustWatch per tick;
- lock Redis `mdbup:justwatch:catalog-scheduler`;
- task beat `enqueue_scheduled_catalog_acquisitions` ogni 300 secondi;
- throttle globale 1 req/s verso JustWatch.

## 4. Dati e sicurezza

- PostgreSQL è la fonte di verità; Redis non è un asset di backup.
- Credenziali e segreti notifiche sono cifrati AES-256-GCM con keyring
  versionato; l'API espone solo hint mascherati.
- Password con Argon2id; sessioni con cookie HttpOnly e CSRF.
- In HTTPS i cookie usano il prefisso `__Host-`, `Secure`, `Path=/`.
- Rate limit e lockout login sono su Redis.
- Errori API con envelope unico e `request_id`.
- Il compose non contiene segreti nel repository: usa environment variables con
  default di primo avvio, da sostituire in produzione.

## 5. Backup e disaster recovery

`deploy/scripts/backup.sh` esegue `pg_dump` nel container PostgreSQL, cifra con
`age`, calcola SHA-256 e applica retention GFS. `backup-verify.sh` verifica
checksum/header e, con la chiave privata, il magic `PGDMP`. `restore.sh`
ripristina su un database scratch o sul DB live solo con conferma esplicita.

La chiave privata `age` resta fuori dal repository. Dopo un restore i run non
terminali vanno riconciliati prima di riabilitare lo scheduling.

## 6. Struttura del repository

```text
.
├── docker-compose.yml
├── .env.example
├── .dockerignore
├── .gitignore
├── README.md
├── backend/
│   ├── app/{api,domain,services,connectors,integrations,repositories,db,jobs,core}
│   ├── alembic/
│   └── tests/
├── frontend/
│   ├── src/{api,hooks,components,pages,lib,app}
│   └── e2e/
├── deploy/
│   ├── Dockerfile.api
│   └── scripts/{backup,backup-verify,restore}.sh
└── docs/
    ├── ARCHITECTURE.md
    └── phases/phase-01.md … phase-11.md
```
