# Piano di esecuzione per fasi

**Principio:** ogni fase produce qualcosa di verificabile. Non si passa alla fase successiva se i criteri di uscita non sono soddisfatti. Le fasi che richiedono credenziali o contratti si fermano al gate, non vengono simulate.

---

## Fase 1 — Verifica e progettazione (completata)

### Obiettivo
Stabilire cosa è realmente possibile fare con le fonti disponibili, prima di scrivere connettori.

### Deliverable
- `docs/phase1/00-executive-summary.md`
- `docs/phase1/01-source-matrix.md`
- `docs/phase1/02-mdblist-api.md`
- `docs/phase1/03-architecture.md`
- `docs/phase1/04-data-model.md`
- `docs/phase1/05-sync-engine.md`
- `docs/phase1/06-security.md`
- `docs/phase1/07-frontend-api.md`
- `docs/phase1/08-ops-tests-risks.md`
- `docs/phase1/09-phase-plan.md`
- `docs/phase1/10-open-questions.md`
- `docs/phase1/schema.sql`
- `README.md`
- `.env.example`
- `.gitignore`

### Criteri di uscita
- Matrice fonti con etichette VERIFICATO/OSSERVATO/NON VERIFICATO/BLOCCATO.
- MDBList verificato con endpoint, payload, limiti e rischi.
- Architettura, schema dati, sync, sicurezza, frontend, ops e test documentati.
- Blocchi e credenziali necessarie elencati.
- Nessun connettore dichiarato funzionante senza accesso reale.

### Cosa non è incluso
- Codice di produzione.
- Docker Compose eseguibile.
- Migrazioni Alembic reali.
- Connettori reali.
- Acquisizione o sync reali.

---

## Fase 2 — Fondamenta eseguibili

### Obiettivo
Avere un'app che si avvia, autentica, migra il database, espone healthcheck e mostra la shell frontend. Nessun connettore reale.

### Deliverable
- `deploy/docker-compose.yml` con `proxy`, `frontend`, `api`, `worker`, `scheduler`, `migrate`, `postgres`, `redis`.
- `deploy/Caddyfile` con stessa origine per SPA e `/api`.
- `backend/pyproject.toml`, `uv.lock`, `Dockerfile`.
- `backend/app/main.py`, configurazione, logging, error envelope.
- Modelli SQLAlchemy e migrazione `0001_initial` (tutte le tabelle di Fase 1).
- Auth: bootstrap admin, login, logout, sessione HttpOnly, CSRF, rate limit.
- Cifratura credenziali con AES-256-GCM e chiave da file.
- API minime: `/health`, `/ready`, `/auth/*`, `/dashboard`, `/settings`, `/providers`, `/collections`, `/bindings`, `/runs` (lettura).
- Frontend shell: login, dashboard vuota, impostazioni, credenziali mascherate.
- CI: lint, typecheck, test unit/integration, migrazioni up/down, build Docker.
- `scripts/backup.sh`, `scripts/restore.sh`.
- README con comandi di avvio.

### Criteri di uscita
- `docker compose up` porta tutti i servizi a `healthy`.
- `alembic upgrade head` su DB vuoto e `downgrade base` funzionano.
- Login con admin creato da bootstrap; cookie HttpOnly/Secure/SameSite; CSRF attivo.
- Credenziale TMDb/MDBList salvata cifrata e riletta mascherata; nessun segreto nei log.
- `/ready` restituisce 503 se DB/Redis non sono pronti.
- CI verde.
- Nessun connettore reale, nessun mock in produzione.

### Test minimi
- Migrazioni su DB vuoto.
- Bootstrap: token monouso, nessuna credenziale predefinita.
- Login: password errata, rate limit, lockout, sessione scaduta.
- CSRF: richiesta senza token → 403.
- Cifratura: round-trip, chiave errata, `key_version`.
- Redazione log: token/apikey/cookie assenti.
- Healthcheck: liveness senza DB, readiness con DB/Redis.

### Gate
Nessuno esterno. Può iniziare subito dopo l'approvazione della Fase 1.

---

## Fase 3 — Prima integrazione verticale reale

### Obiettivo
Acquisire una collezione reale autorizzata, salvarla in uno snapshot, mostrarne l'anteprima, fare un dry-run e aggiornare una lista statica MDBList di test.

### Percorso consigliato (unico disponibile senza contratto JustWatch)
- Provider: **Netflix Italia**.
- Fonte: **TMDb** (`AGGREGATOR`, dati watch provider powered by JustWatch).
- Collezione: "Netflix IT — Disponibilità corrente — Fonte TMDb/JustWatch", tipo `CATALOG`, origine `AGGREGATOR`, `date_basis=UNKNOWN`.
- Media type: film (prima verticale), poi serie.
- Target: lista MDBList statica di test, creata dall'app o importata.
- Modalità: `MIRROR` con soglie conservative; dry-run prima dell'applicazione.

### Deliverable
- `backend/app/connectors/tmdb/` completo: client, mapper, connector, capability flags.
- `backend/app/integrations/mdblist/` completo: client, modelli, mapper.
- `backend/app/services/acquisition.py`, `sync_planner.py`, `sync_executor.py`, `reconciliation.py`.
- Task Celery `acquire_collection`, `run_sync`.
- API: preview, dry-run, start sync, run detail, operations.
- Frontend: collezioni, anteprima, wizard binding, dettaglio sync.
- Test: contract TMDb/MDBList con fixture sintetiche; e2e con mock MDBList; test live opzionale gated.
- Documentazione: `docs/phase3/` con esito reale, limiti e screenshot/testo.

### Criteri di uscita
- Acquisizione reale TMDb completa (pagine attese = ottenute) o snapshot `INCOMPLETE` dichiarato.
- Dedup per `(media_type, tmdb_id)`; film e serie separati.
- Anteprima con conteggi e provenienza.
- Dry-run senza scritture remote.
- Sync su lista di test: `to_add`/`to_remove` calcolati, soglie rispettate, operazioni tracciate.
- Riconciliazione finale: lista remota coerente con lo snapshot.
- Nessuna dichiarazione di "aggiunte recenti" o "Top 10 ufficiale".
- Attribuzione TMDb + JustWatch visibile.

### Gate
- TMDb API key.
- MDBList API key.
- Lista MDBList di test.
- Conferma che la lista è statica e modificabile.
- Decisione: accettare "disponibilità corrente" senza date, oppure attendere il contratto JustWatch.

### Cosa non è incluso
- Date di aggiunta reali (serve JustWatch).
- Catalogo completo di tutti i provider.
- Sync pianificate automatiche (Fase 4).
- Top 10 ufficiale.

---

## Fase 4 — Automazione e robustezza

### Obiettivo
Rendere le sync pianificate, sicure e ripristinabili.

### Deliverable
- Scheduler DB-driven: binding dovuti, `next_run_at`, lock, un run attivo per target.
- Soglie assolute/percentuali configurabili; stato `AWAITING_APPROVAL`; UI di revisione.
- Retry con backoff/jitter, `Retry-After`, riconciliazione post-timeout.
- Cronologia run/operazioni, filtri, dettaglio errori.
- Protezioni: snapshot incompleto/vuoto, catalogo anomalo, unresolved, target non scrivibile.
- Manutenzione: retention snapshot/run/audit, healthcheck fonti.
- Test di concorrenza, timeout incerto, fallimenti a metà, job duplicati, soglie.
- Runbook operativo e procedura di restore testata.

### Criteri di uscita
- Sync pianificata end-to-end su lista di test, con policy accettata.
- Doppio avvio → un solo run.
- Snapshot incompleto → nessuna rimozione.
- Soglia superata → `AWAITING_APPROVAL`, nessuna scrittura.
- Timeout → `UNCERTAIN` → riconciliazione → `SUCCEEDED`/`PARTIAL`.
- Cronologia e contatori corretti.
- Restore da backup verificato su DB scratch.

### Gate
- Fase 3 completata e lista di test stabile.
- Policy di soglie approvata.
- Backup/restore testato.

---

## Fase 5 — Estensione

### Obiettivo
Aggiungere provider, collezioni e fonti senza rompere i vincoli di provenienza.

### Deliverable
- Più provider italiani (Prime Video, Disney+, NOW, Timvision, Infinity+, Rakuten, MUBL, ecc.) tramite TMDb, con mapping provider verificati.
- Collezioni film e serie separate.
- Collezioni `CUSTOM` (genere, anno, filtro) chiaramente etichettate.
- Se disponibile contratto JustWatch:
  - connettore Partner API;
  - connettore Data Export S3;
  - collezioni `RECENTLY_ADDED` con `date_basis=AGGREGATOR_FIRST_SEEN`;
  - upcoming e charts.
- Se disponibile una fonte ufficiale verificata per Top 10:
  - collezione `OFFICIAL` con URL e data della fonte;
  - in alternativa, import manuale CSV dichiarato `OFFICIAL`.
- UI: dashboard avanzata, qualità dati, avvisi, accessibilità.
- Documentazione: attribuzione, limiti, runbook.

### Criteri di uscita
- Ogni nuova collezione ha origine, `date_basis`, fonte e URL.
- Nessuna categoria ufficiale inventata.
- Nessun provider senza mapping verificato.
- Test di contratto per ogni nuovo connettore.
- Revisione legale delle fonti aggiunte.

### Gate
- Contratto JustWatch (per date reali).
- Eventuale accordo per fonti ufficiali.
- Capacità operative (rate limit, storage) verificate.

---

## Riepilogo gate

| Gate | Fase | Stato |
|---|---|---|
| Approvazione Fase 1 | 2 | ⏳ |
| TMDb API key | 3 | ⏳ |
| MDBList API key + lista test | 3 | ⏳ |
| Contratto JustWatch | 5 (o 3 se si vogliono date reali) | ⛔ |
| Fonte ufficiale Top 10 | 5 | ⛔ |
| Dominio/TLS + email admin | 2 | ⏳ |
| Chiave di cifratura + backup | 2 | ⏳ |

---

## Definition of done per il progetto

Il progetto è "pronto" solo quando:

1. l'acquisizione reale da almeno una fonte autorizzata funziona e produce snapshot completi;
2. una lista MDBList di test viene aggiornata in modo riconciliato, con soglie e lock;
3. le sync pianificate funzionano e sono osservabili;
4. backup/restore è testato;
5. nessun segreto è esposto;
6. ogni collezione dichiara origine e `date_basis`;
7. le fonti non disponibili sono disabilitate, non simulate.
