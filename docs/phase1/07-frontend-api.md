# Fase 1 — Frontend e contratto API

**Stato:** progettazione. Nessuna UI implementata.
**Vincoli dalla ricerca:** TMDb è l'unica fonte abilitata (`AGGREGATOR`, disponibilità corrente, nessuna data di aggiunta); JustWatch è `BLOCCATO`; MDBList supporta reorder ma non idempotenza/atomicità. La UI non promette "aggiunte recenti ufficiali" né "ordine garantito".

---

## 1. Pagine e route

| Route | Pagina | Endpoint principali |
|---|---|---|
| `/login` | Login | `POST /api/v1/auth/login` |
| `/bootstrap` | Primo admin | `POST /api/v1/auth/bootstrap` |
| `/app` | Dashboard | `GET /api/v1/dashboard` |
| `/app/providers` | Provider | `GET /api/v1/providers` |
| `/app/providers/:providerId` | Dettaglio provider | `GET /api/v1/providers/{id}` |
| `/app/collections` | Collezioni | `GET /api/v1/collections` |
| `/app/collections/:collectionId` | Dettaglio collezione | `GET /api/v1/collections/{id}`, `/snapshots` |
| `/app/bindings` | Binding | `GET /api/v1/bindings` |
| `/app/bindings/new` | Wizard binding (8 step) | `/previews`, `/targets`, `/bindings` |
| `/app/bindings/:bindingId` | Dettaglio binding | `GET /api/v1/bindings/{id}`, `/runs` |
| `/app/runs` | Run | `GET /api/v1/runs` |
| `/app/runs/:runId` | Dettaglio sync | `GET /api/v1/runs/{id}`, `/operations` |
| `/app/settings` | Impostazioni | `GET/PATCH /api/v1/settings` |
| `/app/settings/credentials` | Credenziali | `GET/PUT/DELETE /api/v1/credentials` |
| `/app/settings/system` | Sistema | `GET /api/v1/health`, `/ready` |

Guardie:
- `RequireSession`: 401 → `/login?next=...`.
- `RequireAdmin`: bootstrap, settings, credenziali.
- `RequireBootstrap`: se non esiste un admin, redirect a `/bootstrap`.

---

## 2. Componenti e stati

### 2.1 Componenti UI

`components/ui`:
- `Button`, `Input`, `Select`, `Checkbox`, `Dialog`, `Stepper`, `Table`, `Pagination`, `Tabs`, `Toast`.
- `StatusPill`: stato run/operazione con testo + icona, mai solo colore.
- `OriginBadge`: `OFFICIAL` / `AGGREGATOR` / `CUSTOM`.
- `DateBasisBadge`: `PROVIDER_OFFICIAL` / `AGGREGATOR_FIRST_SEEN` / `APP_FIRST_SEEN` / `UNKNOWN`.
- `ErrorState`, `EmptyState`, `Skeleton`, `StaleBanner`, `ConfirmDialog`.
- `QualityBanner`: snapshot incompleto, unresolved, catalogo vuoto, ordine parziale.

### 2.2 Etichette di provenienza

| Origine | Etichetta UI | Forma |
|---|---|---|
| `OFFICIAL` | "Categoria ufficiale del provider" | bordo pieno, icona edificio |
| `AGGREGATOR` | "Raccolta di aggregatore: {source}" | bordo tratteggiato, icona nodo |
| `CUSTOM` | "Filtro personalizzato" | sfondo neutro, icona filtro |

| `date_basis` | Etichetta UI |
|---|---|
| `PROVIDER_OFFICIAL` | "Data dichiarata dal provider" |
| `AGGREGATOR_FIRST_SEEN` | "Prima osservazione JustWatch (aggregatore)" |
| `APP_FIRST_SEEN` | "Prima osservazione dell'app (non ufficiale)" |
| `UNKNOWN` | "Data di aggiunta non disponibile" |

**Regola:** se `date_basis=UNKNOWN`, la UI non mostra "Aggiunte recenti" come titolo; mostra "Disponibilità corrente" o "Raccolta".

### 2.3 Stati di caricamento

| Stato | Trigger | Resa |
|---|---|---|
| loading | `isPending` | skeleton con la geometria della tabella |
| empty | `items.length === 0` senza errore | `EmptyState` con azione contestuale |
| error | `isError` | `ErrorState` con categoria, `request_id`, "Riprova" |
| stale | `dataUpdatedAt` oltre soglia | `StaleBanner` non bloccante con ora ultimo aggiornamento |
| blocked | `409 policy_*` o preview `BLOCKED` | motivo, soglia superata, link alla revisione |
| partial | run `PARTIAL` | banner con operazioni fallite/incerte e "Riprendi" |

### 2.4 TanStack Query

- `staleTime: 30_000`.
- `retry`: solo `5xx`, max 2.
- `refetchOnWindowFocus`: solo per run attivi.
- Polling:

| Query | Polling | Note |
|---|---|---|
| `dashboard`, `health` | 30 s | sospeso con `document.hidden` |
| `runs` | 5 s se esiste un run non terminale | `refetchIntervalInBackground: false` |
| `run` | 2 s finché `status ∈ {PENDING, PREFLIGHT, PLANNING, AWAITING_APPROVAL, APPLYING, VERIFYING}` | stop su stato terminale |
| `preview`, `job` | 1,5–2 s finché `RUNNING` | stop su `READY`/`BLOCKED`/`FAILED` |
| collezioni, provider, binding, settings | nessuno | invalidazione esplicita |

Invalidazione:
- snapshot creato → `snapshot*`, `collection`, `collections`, `dashboard`.
- binding creato/aggiornato/eliminato → `bindings`, `binding`, `dashboard`.
- run avviato/terminale → `runs`, `run`, `binding`, `dashboard`, `target`.
- credenziale/settings → `credentials`, `health`, `sources`, `settings`.

---

## 3. Wizard a 8 step

Un solo `useForm<BindingDraft>` con `zodResolver`; ogni step valida il proprio sotto-schema; il submit valida l'intero oggetto. Bozza in `sessionStorage` (`binding-draft:v1`, TTL 24 h, cancellata su submit/annulla), mai `localStorage`, nessun segreto.

| Step | Campo | Validazione | Dati |
|---|---|---|---|
| 1. Provider e paese | `country` (`IT`), `providerId` | provider abilitato | `/providers?country=IT` |
| 2. Fonte | `sourceId` | fonte `OK`/`DEGRADED` con capacità `catalog` | `/sources` |
| 3. Collezione | `collectionId` | coerente con provider e fonte | `/collections` |
| 4. Film o serie | `mediaType` | `MOVIE`/`SHOW`, coerente con la collezione | locale |
| 5. Anteprima | `previewId`, `snapshotId`, `acknowledged` | snapshot `valid`; conferma se `to_remove > 0` | `POST /previews` |
| 6. Lista | `targetMode`, `targetId`/`newListName`, `private` | nome 3–80 caratteri | `/targets/discover`, `POST /previews` |
| 7. Modo e soglie | `mode`, `schedule`, `scheduleTime`, `maxRemovalPct`, `maxRemovalAbs`, `preserveOrder`, `reorderEnabled`, `schedulePolicy`, `requireReview` | soglie > 0; orario `HH:MM` | `/bindings/defaults` |
| 8. Conferma | `policyAccepted`, `confirmName` | spunta; nome collezione digitato | `POST /bindings` |

```ts
const step6Schema = z.object({
  targetMode: z.enum(["existing", "new"]),
  targetId: z.string().uuid().optional(),
  newListName: z.string().trim().min(3).max(80).optional(),
}).superRefine((v, ctx) => {
  if (v.targetMode === "existing" && !v.targetId)
    ctx.addIssue({ code: "custom", path: ["targetId"], message: "Seleziona una lista." });
  if (v.targetMode === "new" && !v.newListName)
    ctx.addIssue({ code: "custom", path: ["newListName"], message: "Inserisci un nome." });
});

const step7Schema = z.object({
  mode: z.enum(["MIRROR", "APPEND_ONLY"]),
  schedule: z.enum(["MANUAL", "DAILY", "WEEKLY"]),
  scheduleTime: z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, "Orario non valido (HH:MM)."),
  maxRemovalPct: z.number().min(0).max(50),
  maxRemovalAbs: z.number().int().min(0).max(5000),
  preserveOrder: z.boolean(),
  reorderEnabled: z.boolean(),
  schedulePolicy: z.enum(["AUTO_APPLY_IF_SAFE", "ALWAYS_APPROVE", "DRY_RUN_ONLY"]),
  requireReview: z.boolean(),
});
```

Navigazione:
- `?step=1..8` nell'URL; `Stepper` con `aria-current="step"`.
- "Indietro" è un link (tasto back); "Avanti" valida e aggiorna la history.
- Aprendo uno step con i precedenti incompleti si torna al primo step invalido.
- Cambiare provider o collezione azzera `snapshotId`, `targetId` e preview, con conferma.

Step 5/6:
- La preview risponde `202`; lo step mostra skeleton e contatori; "Avanti" resta disabilitato finché `state !== "READY"`.
- Con `state === "BLOCKED"` si prosegue solo attivando `requireReview`; lo step 8 mostra l'avviso.
- Step 7 rifiuta `MIRROR` con entrambe le soglie a 0 (anche lato server: `422 thresholds_required`).
- Step 8 riepiloga `to_add`, `to_remove`, `unchanged`, `unresolved`, modo, frequenza, soglie, `preserve_order` e target; invia `policy_version`.

**Testo obbligatorio per liste esistenti:**
> "MIRROR rimuoverà dalla lista gli elementi non presenti nella collezione, inclusi quelli aggiunti manualmente. L'operazione è tracciata e reversibile solo con un nuovo snapshot/sync."

---

## 4. Contratto API REST

Base `/api/v1`, stessa origine, JSON `snake_case`, timestamp ISO 8601 UTC. Envelope errore unico. Paginazione: `page` (1-based), `page_size` (default 25, max 100) → `{items, page, page_size, total, has_more}`.

### 4.1 Auth

| Endpoint | Contratto | Errori |
|---|---|---|
| `POST /auth/bootstrap` | `{token,email,password}` → `201 {user}` | `400 invalid_token`, `409 already_bootstrapped`, `422 weak_password` |
| `POST /auth/login` | `{email,password}` → `204` + cookie sessione + cookie CSRF | `401 invalid_credentials`, `429 rate_limited`, `403 account_locked` |
| `POST /auth/logout` | — → `204` | `401` |
| `GET /auth/session` | → `{user:{id,email,role}, expires_at, csrf_required}` | `401 unauthenticated` |
| `POST /auth/change-password` | `{current_password,new_password}` → `204` | `401`, `422` |

### 4.2 Dashboard e sistema

| Endpoint | Contratto |
|---|---|
| `GET /dashboard` | `{counts:{providers,collections,bindings,active_runs}, last_runs, alerts:[{code,severity,message,resource}], stale_snapshots, sources:[{source_id,status,last_check_at}]}` |
| `GET /health` | `{status:"ok",version}` — liveness, nessuna dipendenza |
| `GET /ready` | `{status:"ok"\|"degraded",checks:{db,redis,migrations,encryption_key}}` — 503 se critico |
| `GET /jobs/{job_id}` | `{id,type,status,progress,result_ref,error}` |

### 4.3 Provider e fonti

| Endpoint | Contratto | Errori |
|---|---|---|
| `GET /providers` | `country&q&enabled&page` → `Page<Provider>` | — |
| `GET /providers/{id}` | → `Provider & {mappings, collections_count}` | `404` |
| `PATCH /providers/{id}` | `{enabled?, display_name?}` → `Provider` | `404`, `422` |
| `GET /sources` | → `[{id,key,name,status,capabilities,last_check_at,last_error}]` | — |
| `POST /sources/{id}/healthcheck` | → `202 {job_id}` | `404`, `409 source_disabled` |

`Provider`: `{id,name,slug,country,enabled,logo_url,source_id,last_seen_at}`.
`capabilities`: `catalog`, `recently_added`, `upcoming`, `charts`, `ordering`, `added_dates`, `seasons_episodes`, `full_pagination`, `data_export`, `requires_contract`.

### 4.4 Collezioni e snapshot

| Endpoint | Contratto | Errori |
|---|---|---|
| `GET /collections` | `provider_id&origin&media_type&q&page` → `Page<Collection>` | — |
| `GET /collections/{id}` | → `Collection & {latest_snapshot, binding_ids}` | `404` |
| `POST /collections` | `{provider_id,name,media_type,filter}` → `201` (`origin:"CUSTOM"`) | `422`, `409 duplicate_name` |
| `PATCH /collections/{id}` | `{name?,filter?,enabled?}` → `Collection` | `409 origin_immutable` |
| `DELETE /collections/{id}` | → `204` | `409 collection_in_use` |
| `POST /collections/{id}/snapshots` | `{reason?}` → `202 {job_id,snapshot_id}` | `409 acquisition_running` |
| `GET /collections/{id}/snapshots` | `page` → `Page<Snapshot>` | `404` |
| `GET /snapshots/{id}` | → `Snapshot` | `404` |
| `GET /snapshots/{id}/items` | `q&media_type&page` → `Page<SnapshotItem>` | `404` |

`Collection`: `{id,slug,name,provider,country,media_type,kind,origin,date_basis,source,source_url,offer_types,sort_mode,last_valid_snapshot,quality_flags}`.
`Snapshot`: `{id,collection_id,status:"RUNNING"|"COMPLETE"|"INCOMPLETE"|"FAILED",quality:"CLEAN"|"WARNINGS"|"ANOMALY",valid,expected_pages,obtained_pages,item_count,unresolved_count,error_count,started_at,finished_at,completeness_reason}`.
`valid` è calcolato dal backend, mai dalla UI.

### 4.5 Target MDBList

| Endpoint | Contratto | Errori |
|---|---|---|
| `GET /targets` | `media_type&page` → `Page<Target>` | — |
| `GET /targets/discover` | `media_type` → `{items:[{remote_list_id,name,item_count,private,already_linked}]}` | `502 mdblist_upstream_error` |
| `POST /targets` | `{mode,remote_list_id?,name?,private?}` → `201 Target` | `409 list_limit_reached`, `409 target_already_linked` |
| `POST /targets/{id}/verify` | → `202 {job_id}` | `502` |

`Target`: `{id,remote_list_id,remote_slug,remote_url,name,mediatype,private,item_count,last_verified_at,capabilities}`.
**Nota:** `remote_list_id` è la chiave; `remote_slug`/`remote_url` sono display e possono cambiare.

### 4.6 Binding, preview, run

| Endpoint | Contratto | Errori |
|---|---|---|
| `GET /bindings` | `collection_id&enabled&page` → `Page<Binding>` | — |
| `GET /bindings/{id}` | → `Binding` | `404` |
| `GET /bindings/defaults` | → `{mode,schedule,schedule_time,max_removal_pct,max_removal_abs,preserve_order,reorder_enabled,schedule_policy,require_review}` | — |
| `POST /bindings` | `{collection_id,target_id,mode,schedule,schedule_time,thresholds,preserve_order,reorder_enabled,schedule_policy,enabled,policy_version}` → `201` | `409 binding_exists`, `409 target_locked`, `422 thresholds_required`, `422 policy_not_accepted` |
| `PATCH /bindings/{id}` | campi modificabili → `Binding` | `409 run_in_progress` |
| `DELETE /bindings/{id}` | → `204` | `409 run_in_progress` |
| `POST /bindings/{id}/policy-accept` | `{policy_version}` → `Binding` | `422 policy_version_mismatch` |
| `POST /previews` | `{collection_id,target_id?,mode?,thresholds?}` → `202 {preview_id}` | `409 target_locked`, `422 snapshot_invalid` |
| `GET /previews/{id}` | → `Preview` | `404` |
| `POST /bindings/{id}/runs` | `{dry_run?,idempotency_key}` → `202 {run_id}` | `409 run_in_progress`, `409 snapshot_invalid`, `409 policy_not_accepted`, `409 thresholds_exceeded` |
| `GET /runs` | `binding_id&status&page` → `Page<RunSummary>` | — |
| `GET /runs/{id}` | → `Run` | `404` |
| `GET /runs/{id}/operations` | `status&action&page` → `Page<Operation>` | `404` |
| `POST /runs/{id}/approve` | `{plan_hash,note?}` → `202 {job_id}` | `409 run_not_awaiting_approval`, `409 stale_plan` |
| `POST /runs/{id}/cancel` | → `202 {job_id}` | `409 run_terminal` |
| `POST /runs/{id}/reconcile` | → `202 {job_id}` | `409 run_not_uncertain` |
| `POST /runs/{id}/resume` | → `202 {job_id}` | `409 run_not_resumable` |

`Preview`: `{id,state:"RUNNING"|"READY"|"BLOCKED"|"FAILED",counts:{to_add?,to_remove?,unchanged,unresolved,unmapped_remote,remote_duplicates},blocked:{reason,threshold,observed}|null,sample,snapshot_id,snapshot_hash,plan_hash,order_enforced,generated_at}`.
`Run`: `{id,binding_id,status,started_at,finished_at,counters:{planned,applied,skipped,not_found,failed,uncertain},snapshot_id,preview_id,plan_hash,snapshot_hash,error,reconcile_required,order_enforced,warnings,idempotency_key}`.
`Operation`: `{id,run_id,action:"ADD"|"REMOVE"|"REORDER",media_id,media,status:"PENDING"|"IN_FLIGHT"|"SUCCEEDED"|"SKIPPED"|"FAILED"|"UNCERTAIN",attempt,error,updated_at}`.

### 4.7 Settings e credenziali

| Endpoint | Contratto | Errori |
|---|---|---|
| `GET /settings` | → `Settings` redatto | — |
| `PATCH /settings` | campi parziali → `Settings` | `422` |
| `GET /credentials` | → `[{kind,configured,masked_hint,key_version,updated_at,last_verified_at,status}]` | — |
| `PUT /credentials/{kind}` | `{secret_fields}` → `204`, nessun segreto in risposta | `400 encryption_key_missing`, `422` |
| `DELETE /credentials/{kind}` | → `204` | `404` |
| `POST /credentials/{kind}/verify` | → `202 {job_id}` | `409 credential_missing` |

`kind ∈ {TMDB, MDBLIST, JUSTWATCH}`. `JUSTWATCH` risponde `409 source_not_available` finché non esiste contratto. Nessun endpoint restituisce segreti.

---

## 5. Tipi TypeScript e generazione client

`openapi-typescript` genera `src/api/generated/schema.d.ts` da `GET /api/openapi.json`; `openapi-fetch` fornisce il client tipizzato. `npm run api:generate` in locale; `npm run api:check` in CI (fallisce sul drift).

```ts
import type { components } from "./generated/schema";

export type MediaType = components["schemas"]["MediaType"];          // "MOVIE" | "SHOW"
export type Origin = components["schemas"]["Origin"];                // "OFFICIAL" | "AGGREGATOR" | "CUSTOM"
export type DateBasis = components["schemas"]["DateBasis"];          // ...
export type SyncMode = components["schemas"]["SyncMode"];            // "MIRROR" | "APPEND_ONLY"
export type RunStatus = components["schemas"]["RunStatus"];
export type OperationStatus = components["schemas"]["OperationStatus"];
export type OfferType = components["schemas"]["OfferType"];          // "FLATRATE" | ...
export type ApiError = components["schemas"]["ErrorEnvelope"];
```

- Un solo spelling: TMDb `tv` → `SHOW`, MDBList `shows` → `SHOW`, `movies` → `MOVIE`; la conversione avviene solo nei connettori backend.
- Client: `baseUrl: "/api/v1"`, `credentials: "same-origin"`, header `X-CSRF-Token` letto dal cookie CSRF per i metodi non sicuri; `401` → login; `request_id` propagato.
- Nessun tipo scritto a mano per i payload API: si usano quelli generati.

---

## 6. Tassonomia errori UI

Il backend restituisce:

```json
{
  "error": {
    "code": "MDBLIST_RATE_LIMITED",
    "category": "TARGET",
    "message": "Limite di scrittura MDBList raggiunto.",
    "retryable": true,
    "retry_after_s": 42,
    "request_id": "req_01H...",
    "details": {"target_id": 3}
  }
}
```

`category ∈ {AUTH, VALIDATION, SOURCE, TARGET, POLICY, CONFLICT, INTERNAL}`; il frontend aggiunge solo `NETWORK`.

| Categoria | Titolo | Messaggio | Azione |
|---|---|---|---|
| `SOURCE` | "Errore della fonte" | "La fonte {name} non ha risposto correttamente. Lo snapshot non è stato considerato valido." | Riprova; nessuna rimozione |
| `TARGET` | "Errore MDBList" | "MDBList ha rifiutato la richiesta. Riprova tra {retry_after} s." | Attesa e ripresa |
| `POLICY` | "Operazione bloccata dalle soglie" | "La rimozione prevista ({observed}) supera la soglia ({threshold}). Serve una revisione manuale." | Vai alla revisione |
| `AUTH` | "Sessione scaduta" | "Accedi di nuovo per continuare." | Login |
| `VALIDATION` | "Dati non validi" | "Controlla i campi evidenziati." | Focus sul campo |
| `CONFLICT` | "Operazione già in corso" | "Un'altra operazione è in corso su questa lista." | Attendi |
| `WARNING` | "Ordine non applicato" | "Gli elementi sono corretti, ma MDBList non ha confermato l'ordine. Nessuna lista è stata ricreata." | Dettagli |
| `NETWORK` | "Connessione assente" | "Impossibile raggiungere il server. Verifica la rete." | Riprova |
| `INTERNAL` | "Errore interno" | "Errore imprevisto. Codice richiesta: {request_id}." | Copia codice |

**Regole:**
- Il testo grezzo del server non viene mai mostrato; si usa `message` solo per categorie mappate.
- `409 thresholds_exceeded` e `409 snapshot_invalid` sono warning con percorso di sblocco, non errori rossi.
- `429` mostra un countdown.
- I `422` sono mappati sui campi via `details.fields`.
- Un errore `SOURCE` non deve mai essere mostrato come errore MDBList, e viceversa.

---

## 7. Accessibilità e responsive

- Skip link, un solo `h1`, focus su `main` al cambio route con annuncio `aria-live="polite"`.
- Wizard: `nav aria-label="Passaggi"`, `aria-current="step"`, `aria-invalid` e `aria-describedby`, focus sul primo campo invalido al submit.
- Tabelle con `<caption>`, `scope="col"`, `aria-sort`; stato run come testo + icona, mai solo colore.
- Polling annunciato in `aria-live` con throttle (max 1/5 s) e `aria-busy` sulla regione.
- Dialog con focus trap, `Esc`, ripristino del focus; `ConfirmDialog` non chiudibile con click fuori.
- Contrasto testo ≥ 4.5:1, UI ≥ 3:1, focus ring 2 px, verificato con axe.
- `prefers-reduced-motion` disattiva transizioni e skeleton pulsanti.
- Breakpoint `sm 640 / md 768 / lg 1024 / xl 1280`; sotto `md` tabelle come card `<dl>`, wizard a step singolo, target touch ≥ 44×44 px, nessuno scroll orizzontale a 320 px.

---

## 8. Sicurezza frontend

- Nessun segreto nel bundle: le API key restano nel backend cifrate.
- Sessione solo in cookie `HttpOnly; Secure; SameSite=Lax; Path=/`; nessun token in `localStorage`/`sessionStorage`, dove sta solo la bozza del wizard.
- CSRF double-submit (`__Host-mdbsync-csrf` + `X-CSRF-Token`) su ogni metodo non sicuro.
- CSP dal reverse proxy: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https://image.tmdb.org; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'`. Nessuno script inline, nessun CDN.
- Altri header: `nosniff`, `Referrer-Policy: same-origin`, `Permissions-Policy` minimale, HSTS.
- Nessun `dangerouslySetInnerHTML`; testi delle fonti resi come testo; link esterni con `rel="noopener noreferrer"`.
- Error boundary senza stack trace; log senza PII; lockfile e `npm audit` in CI.

---

## 9. Albero frontend e wireframe

```text
frontend/
  index.html  vite.config.ts  tailwind.config.ts  tsconfig.json
  src/
    main.tsx
    app/         App.tsx router.tsx providers.tsx error-boundary.tsx
    api/         client.ts generated/schema.d.ts queries/ mutations/
    components/  ui/ (Button Table StatusPill OriginBadge DateBasisBadge Dialog
                 Stepper Pagination Skeleton EmptyState ErrorState StaleBanner
                 ConfirmDialog QualityBanner)
    features/    auth/ dashboard/ providers/ collections/ bindings/wizard/ runs/ settings/
    lib/         errors.ts query-keys.ts format.ts dates.ts validation/
    pages/       Login Bootstrap Dashboard Providers Collections Bindings Wizard Run Settings
    test/        setup.ts mocks/handlers.ts mocks/fixtures/
  e2e/           wizard.spec.ts run.spec.ts auth.spec.ts
```

Dashboard:

```text
┌ Header: logo · stato sistema ● ok · utente ▾ ─────────────┐
│ KPI: Provider 12 · Collezioni 34 · Binding 8 · Run attivi 1│
│ Sync recenti (binding · modo · stato · contatori)          │
│ Snapshot non validi (collezione · motivo · data)           │
│ Avvisi: JustWatch non configurato · TMDb senza date        │
└────────────────────────────────────────────────────────────┘
```

Wizard, step 7:

```text
┌ Passaggi: 1 2 3 4 5 6 [7] 8 ──────────────────────────────┐
│ Modo: (•) MIRROR — rispecchia  ( ) APPEND_ONLY — solo agg. │
│ Frequenza [Giornaliera ▾]  Ora [03:00]                     │
│ Soglie: rimozioni max [10] %  e [50] elementi              │
│ [ ] Preserva l'ordine (best-effort; max 1.000 per blocco)  │
│ [x] Richiedi revisione manuale oltre soglia                │
│ Anteprima: +128 / −3 / =412 / !5 non risolti               │
│                                   [Indietro] [Avanti →]    │
└────────────────────────────────────────────────────────────┘
```

Dettaglio run:

```text
┌ Run #1234 · "Netflix IT → Lista film" · APPLYING ──────────┐
│ Snapshot valido · piano +128 −3 · applicate 96/131         │
│ [Annulla] [Riconcilia]                                     │
│ Operazioni: [Tutte ▾] azione · titolo · stato · tentativi  │
└────────────────────────────────────────────────────────────┘
```

---

## 10. Test frontend e contract test

| Livello | Strumento | Copertura |
|---|---|---|
| Unit | Vitest | schemi Zod (8 step, soglie, nome lista), `lib/errors.ts`, formattazione |
| Component | Testing Library + `jest-axe` | stati loading/empty/error/stale/blocked, `OriginBadge`, `DateBasisBadge`, focus trap, `aria-current`, tastiera |
| Integration | MSW con fixture sintetiche | wizard con preview asincrona, polling che si ferma su stato terminale, invalidazione, `401` → login |
| Contract | `openapi-typescript` + `openapi-msw` | handler MSW validati contro lo schema OpenAPI; `npm run api:check` per il drift |
| Contract backend | Schemathesis sull'app FastAPI | risposte, envelope errori, paginazione, `401/403/409` |
| E2E | Playwright su Compose (profilo `test`) | login → snapshot (connettore fixture) → wizard → dry-run → sync → verifica; axe su ogni pagina |

Fixture sintetiche e marcate (`fixture: true`); nessuna lista MDBList reale modificata; connettore fixture escluso dal build di produzione. I test di errore coprono una risposta per categoria e i `409` di soglia e snapshot invalido.
