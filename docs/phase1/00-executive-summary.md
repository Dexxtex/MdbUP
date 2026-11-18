# Fase 1 — Sintesi esecutiva

**Data:** 2026-11-17
**Esito:** Fase 1 completata (verifica fonti + progettazione). **Nessun connettore reale è stato implementato o dichiarato funzionante.** Il progetto non è ancora eseguibile end-to-end: la Fase 2 (fondamenta) e la Fase 3 (prima integrazione reale) sono da avviare.

---

## 1. Cosa abbiamo verificato davvero

| Fonte | Esito | Conseguenza |
|---|---|---|
| **MDBList** | API documentata e utilizzabile con API key. Creazione liste, lettura a cursore, add/remove, reorder (max 1.000 per chiamata), rate limit 1.000 read/300 write per 5 min. | È la **destinazione** del progetto. Serve una API key e una lista di test. |
| **TMDb** | API ufficiale, disponibilità corrente per l'Italia, cinque tipi di offerta. **Nessuna data di aggiunta**, discover limitato a 500 pagine. Dati watch provider forniti da JustWatch. | È la **prima fonte reale** per la Fase 3, etichettata `AGGREGATOR`. Non può alimentare "Aggiunte recenti" con date dichiarate. |
| **JustWatch Partner API / Data Export** | Documentazione pubblica completa; accesso solo con contratto, token e credenziali S3. `date_created` = prima osservazione JustWatch. | **BLOCCATO.** È la fonte corretta per date di aggiunta reali e catalogo completo, ma serve un contratto. |
| **JustWatch sito pubblico / GraphQL** | GraphQL non documentato; ToS §7.1 vieta scraping/data mining. | **ESCLUSO.** Nessun connettore, nessun fallback. |
| **Movieplayer / ComingSoon** | Editoriali, senza API pubblica; robots/ToS contrari; cataloghi parziali. | **NON IDONEI** come connettori. Solo link-out manuale. |
| **PlayPilot** | 403 anti-bot, nessuna API pubblica documentata. | **ESCLUSO.** |
| **Top 10 ufficiale provider** | Nessuna API ufficiale verificata. | **NON IMPLEMENTARE** finché non esiste una fonte ufficiale verificata e un uso consentito. |

---

## 2. Le tre etichette che non si possono confondere

| Origine | Significato | Esempio |
|---|---|---|
| `OFFICIAL` | Categoria pubblicata ufficialmente dal provider. | "Netflix IT — Top 10 ufficiale" **solo** con fonte ufficiale verificata. |
| `AGGREGATOR` | Raccolta costruita da un aggregatore (JustWatch, TMDb). | "Netflix IT — Disponibilità corrente — Fonte TMDb/JustWatch". |
| `CUSTOM` | Filtro o derivazione dell'app. | "Netflix IT — Thriller — Filtro personalizzato"; "Aggiunte recenti rilevate dall'app". |

A queste si aggiunge `date_basis`:

| `date_basis` | Significato | Disponibilità |
|---|---|---|
| `PROVIDER_OFFICIAL` | Data dichiarata ufficialmente dal provider. | Nessuna fonte verificata. |
| `AGGREGATOR_FIRST_SEEN` | Prima osservazione dell'aggregatore (JustWatch `date_created`). | Solo con contratto JustWatch. |
| `APP_FIRST_SEEN` | Prima osservazione della nostra app (`first_seen_at`). | Disponibile con TMDb, ma è una derivazione `CUSTOM`. |
| `UNKNOWN` | Nessuna data. | TMDb current availability. |

**Regola:** l'UI mostra sempre origine e `date_basis`. Non si sostituisce silenziosamente una fonte con un'altra.

---

## 3. Decisioni architetturali chiave

1. **Monolite modulare** con processi separati `web`, `api`, `worker`, `scheduler`, più `postgres`, `redis`, `migrate`.
2. **PostgreSQL fonte di verità**; Redis solo broker/cache.
3. **Snapshot immutabili** con flag di completezza; solo snapshot validi alimentano le sync.
4. **Connettori con capability flags**: ogni fonte dichiara cosa supporta davvero.
5. **Operation ledger** per MDBList: nessuna transazione distribuita; riconciliazione dopo timeout.
6. **Lock per target** (advisory lock PostgreSQL + unique partial index) per impedire sync concorrenti.
7. **Soglie di sicurezza** assolute e percentuali; blocco su snapshot incompleto o vuoto; revisione manuale.
8. **Segreti cifrati a riposo** con AES-256-GCM e chiave esterna al DB.
9. **Frontend SPA** con client generato da OpenAPI; nessun segreto nel browser.
10. **MDBList ID numerico** come chiave stabile; slug/URL solo display.

---

## 4. Cosa è pronto e cosa manca

| Area | Stato |
|---|---|
| Matrice fonti e capacità | ✅ Documentata con evidenze |
| Verifica MDBList | ✅ Endpoint, limiti, payload, rischi |
| Architettura e struttura repo | ✅ Documentata |
| Modello dati e schema | ✅ Documentato (DDL in `schema.sql`) |
| Motore di sync e sicurezza | ✅ Progettato |
| Frontend e contratto API | ✅ Progettato |
| Docker Compose, migrazioni, auth | ⏳ Fase 2 |
| Connettore TMDb reale | ⏳ Fase 3 (serve API key) |
| Connettore MDBList reale | ⏳ Fase 3 (serve API key) |
| Connettore JustWatch | ⛔ Bloccato da contratto |
| "Aggiunte recenti" con data JustWatch | ⛔ Bloccato da contratto |
| "Top 10 ufficiale" | ⛔ Nessuna fonte ufficiale verificata |

---

## 5. Cosa serve per proseguire

### Per la Fase 2 (fondamenta eseguibili)
Nessuna credenziale esterna. Servono solo:
- decisione sul dominio/TLS e sull'email del primo admin;
- conferma della policy di backup e custodia di `APP_ENCRYPTION_KEY`.

### Per la Fase 3 (prima integrazione reale)
1. **TMDb API key** (read access token).
2. **MDBList API key** e piano (free/supporter).
3. **Lista MDBList di test** dedicata (non una lista personale).
4. **Decisione su JustWatch:** contratto Partner + credenziali S3, oppure accettare che la Fase 3 mostri "disponibilità corrente" e non "aggiunte recenti".
5. **Conferma legale** su uso non commerciale TMDb e attribuzione JustWatch.

### Per la Fase 4-5
- Contratto JustWatch (se si vogliono date reali e catalogo completo).
- Eventuale fonte ufficiale per Top 10 (solo se verificata e consentita).
- Più provider/collezioni e feedback sull'UI.

---

## 6. Rischi principali

| Rischio | Impatto | Mitigazione |
|---|---|---|
| JustWatch non ottenibile | Nessuna data di aggiunta reale | TMDb current availability + etichetta `CUSTOM`/`APP_FIRST_SEEN`; connettore disabilitato |
| TMDb discover limitato a 500 pagine | Catalogo parziale | Partizionamento per anno/genere; snapshot incompleto = nessuna rimozione |
| MDBList 300 scritture/5 min | Sync lente o bloccate | Batch, token bucket, ripresa, `Retry-After` |
| Timeout MDBList con esito incerto | Doppie aggiunte/rimozioni | `UNCERTAIN` + rilettura remota prima del retry |
| Snapshot anomalo | Rimozioni massive | Soglie, revisione manuale, blocco su snapshot invalido/vuoto |
| Perdita chiave di cifratura | Credenziali irrecuperabili | Backup separato della chiave, procedura documentata |
| Violazione ToS | Blocco/legale | Solo endpoint documentati; niente scraping; attribuzione |

---

## 7. Prossimo passo consigliato

1. Approvare la matrice fonti e le decisioni di Fase 1.
2. Fornire TMDb API key e MDBList API key (e la lista di test).
3. Avviare la **Fase 2**: Docker Compose, PostgreSQL, Alembic, auth, healthcheck, frontend shell, CI.
4. Solo dopo, avviare la **Fase 3** con TMDb + MDBList su una lista di test, senza dichiarare "aggiunte recenti" finché non c'è JustWatch.

**Nota:** la Fase 1 non contiene codice di produzione né connettori reali. Questo è intenzionale: il vincolo del progetto è non dichiarare funzionante ciò che non è stato verificato con accessi reali.
