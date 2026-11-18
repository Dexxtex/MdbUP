# Fase 10 — CI verde, deduplicazione snapshot e diagnostica storage

**Data:** 2026-11-18
**Stato:** completata lato codice, test e workflow. Verifica live su stack isolato;
il deploy di produzione è gestito dall'operatore tramite Dockhand.

---

## 1. CI principale verde

| Controllo | Esito |
|---|---|
| `mypy app` | **0 errori** |
| `pip-audit` | **0 vulnerabilità** |
| `npm audit --omit=dev` | **0 vulnerabilità** |
| Backend `pytest` | **361 passed** |
| Frontend Vitest | **115 passed** |
| Playwright E2E | **12 passed** |
| `ruff check` / `format --check` | puliti |
| Frontend typecheck / build / lint | verdi |
| Workflow CI GitHub | **success** |
| Workflow Build image | **success** |

Dipendenze aggiornate:

- `cryptography` 45.0.7 → **50.0.2**
- `pytest` 8.4.2 → **9.2.0**
- `pytest-asyncio` 0.26 → **1.5.0**
- `zod` 3 → **4.6.7**
- `react-router-dom` 6 → **7.18.5**
- `@hookform/resolvers` 3 → **7.0.7**

---

## 2. Deduplicazione snapshot invariati

Nuova migrazione `0006_snapshot_dedup`:

- `collection_snapshot.last_verified_at`
- `collection_snapshot.items_from_snapshot_id` (FK verso lo snapshot che possiede
  fisicamente le righe)
- indice `snapshot_items_source_idx`

Comportamento:

1. ogni acquisizione produce comunque una riga snapshot, quindi lo storico delle
   verifiche resta completo;
2. se `checksum` dell'insieme normalizzato è identica all'ultimo snapshot valido,
   il nuovo snapshot punta a quello precedente e **non inserisce** migliaia di
   `snapshot_item`;
3. `last_verified_at` registra ogni verifica;
4. lettori (sync, preview, API snapshot, cambi catalogo, eventi TV) risolvono
   trasparentemente lo snapshot proprietario;
5. la retention non elimina mai uno snapshot referenziato da
   `items_from_snapshot_id`, oltre a proteggere l'ultima baseline valida.

Test aggiunti: snapshot identico con una sola copia degli item, `last_verified_at`,
`ADDED`/`REMOVED` corretti dopo una verifica duplicata, retention dello snapshot
proprietario e migrazione `0006` idempotente.

---

## 3. Diagnostica storage

`GET /api/system/status` espone il blocco:

```json
{
  "storage": {
    "snapshot_bytes": 0,
    "run_bytes": 0,
    "total_bytes": 0,
    "database_bytes": 0,
    "snapshot_rows": 0,
    "snapshot_item_rows": 0,
    "run_rows": 0,
    "size_supported": true
  }
}
```

Su PostgreSQL usa `pg_total_relation_size` e `pg_database_size`; su SQLite
riporta la dimensione del database e `size_supported=false`. La sezione
**Impostazioni → Backup & Manutenzione** mostra storage snapshot, run e database.

---

## 4. Compose automatico

`docker-compose.yml` e `deploy/dockhand-compose.yml` usano **4 servizi**
(`api`, `worker`, `postgres`, `redis`) e soli environment variables, senza
`init`, `.env` o file secrets:

- `POSTGRES_PASSWORD`
- `APP_ENCRYPTION_KEY` (Base64 di 32 byte)
- `BOOTSTRAP_TOKEN`
- `METRICS_TOKEN`

Sono presenti default semplici per il primo avvio, da sostituire prima di
esporre il servizio. All'avvio l'API esegue:

```text
alembic upgrade head
python -m app.cli seed-providers
uvicorn ...
```

Il seed è idempotente e garantisce la presenza di fonti, provider e mapping
prima del primo salvataggio credenziali.

---

## 5. Verifica

Stack isolato con volumi nuovi:

- API **healthy**
- migrazione **`0006_snapshot_dedup`**
- `/api/health` **200**
- seed automatico e credenziali TMDb salvabili

Il nuovo stack parte da volumi `mdbup_v2_*`; le **6 liste MDBList esterne non
sono state modificate** da questa fase. Il database applicativo del nuovo stack
è vuoto: admin, credenziali, collezioni e binding vanno ricreati dal bootstrap.

Nessuna chiamata di scrittura MDBList è stata eseguita durante la Fase 10.
