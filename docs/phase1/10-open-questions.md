# Domande aperte e input necessari

**Stato:** Fase 1 completata. Le risposte sotto sbloccano la Fase 2 e la Fase 3.

---

## 1. Credenziali e accessi

| # | Domanda | Perché serve | Default proposto |
|---|---|---|---|
| 1 | Fornisci una **TMDb API key** (read access token). | Prima fonte reale di disponibilità IT. | Nessun default: senza key, la Fase 3 non parte. |
| 2 | Fornisci una **MDBList API key**. | Destinazione delle sync. | Nessun default. |
| 3 | Qual è il **piano MDBList** (free/supporter)? | Limite liste statiche (free: 4) e rate. | Free per il test; supporter se servono più liste. |
| 4 | Quale **lista MDBList di test** usare? | Evitare di toccare liste personali. | Crearne una nuova, privata, dedicata. |
| 5 | Hai un **contratto JustWatch Partner** o accesso al data export S3? | Date di aggiunta reali e catalogo completo. | No: la Fase 3 userà TMDb e dichiarerà "disponibilità corrente". |
| 6 | Se sì, fornisci **partner token** e **credenziali S3** (Access Key, Secret, directory). | Connettore JustWatch. | Nessun default. |

**Nota:** le credenziali non vanno inviate in chat né messe in `.env`. Vanno inserite dall'interfaccia Impostazioni dopo la Fase 2, oppure caricate come Docker secret. In questa fase è sufficiente sapere se sono disponibili.

---

## 2. Deployment

| # | Domanda | Default proposto |
|---|---|---|
| 7 | Quale **dominio** userai? | `mdblist-sync.example.com` (placeholder). |
| 8 | TLS con **Let's Encrypt/Caddy** o certificato esistente? | Caddy + Let's Encrypt. |
| 9 | Quale **email** per il primo admin e per ACME? | `admin@example.com` (placeholder). |
| 10 | Il server ha **Docker Compose** e almeno 2 GB RAM / 10 GB disco? | Sì, ambiente Linux. |
| 11 | Vuoi esporre l'app su Internet o solo su VPN/LAN? | VPN/LAN in Fase 2; Internet solo dopo security review. |

---

## 3. Policy di sincronizzazione

| # | Domanda | Default proposto |
|---|---|---|
| 12 | Quali **tipi di offerta** includere? | Solo `flatrate` (abbonamento). Rent/buy/ads/free disattivati. |
| 13 | Le liste devono includere **film e serie insieme** o separate? | Separate: una lista movie e una show. |
| 14 | **Soglia rimozioni assoluta**? | 50 elementi. |
| 15 | **Soglia rimozioni percentuale**? | 10%. |
| 16 | **Soglia aggiunte percentuale**? | 50%. |
| 17 | Le sync pianificate devono richiedere approvazione a ogni run? | No, se il binding è abilitato con policy accettata; blocco solo se si superano le soglie. |
| 18 | Cosa fare se uno snapshot è incompleto? | Nessuna rimozione; `BLOCKED`; notifica in dashboard. |
| 19 | Cosa fare se uno snapshot è vuoto? | `BLOCKED`; nessuna scrittura. |
| 20 | Cosa fare con elementi non risolti (senza TMDb ID)? | Non includerli; MIRROR bloccato se superano la soglia; mostrare il conteggio. |
| 21 | **Ordine** delle liste: preservarlo? | Default `false`; opzione `preserve_order=true` con reorder best-effort (max 1.000 per chiamata, non atomico). |
| 22 | Retention snapshot/run/operazioni? | 90 giorni snapshot, 180 giorni run/operazioni, audit 180 giorni. |

---

## 4. Provenienza e contenuti

| # | Domanda | Default proposto |
|---|---|---|
| 23 | Vuoi collezioni **"Aggiunte recenti"** derivate dall'app? | Sì, ma etichettate `CUSTOM` / `APP_FIRST_SEEN`, non "ufficiali". |
| 24 | Vuoi collezioni **"Top 10 ufficiale"**? | Non ora: nessuna fonte ufficiale verificata. |
| 25 | Vuoi includere **prossime uscite**? | Solo se JustWatch contract; TMDb non basta per lo streaming. |
| 26 | Vuoi includere **classifiche**? | Solo con JustWatch contract; MDBList JustWatch charts non copre l'Italia. |
| 27 | Quali provider italiani prioritari? | Netflix, Prime Video, Disney+, NOW, Timvision, Infinity+, Rakuten TV, MUBI. |
| 28 | Vuoi l'**audio italiano** come filtro? | No: la disponibilità in Italia non implica audio italiano. Nessun dato verificato. |
| 29 | Vuoi **canali aggiuntivi** (es. Amazon Channels)? | No di default; configurabile per collezione. |

---

## 5. Sicurezza e operazioni

| # | Domanda | Default proposto |
|---|---|---|
| 30 | Come custodisci `APP_ENCRYPTION_KEY`? | Password manager + backup offline; mai nel repo. |
| 31 | Quale **recipient age** per i backup? | Chiave pubblica `age1...`; privata offline. |
| 32 | Backup su volume locale o off-site? | Locale + copia off-site cifrata. |
| 33 | Vuoi **MFA** per l'admin? | Non in Fase 1; valutare in Fase 5. |
| 34 | Vuoi **notifiche** (email/webhook) per sync fallite/soglie? | Dashboard in Fase 2; webhook in Fase 4. |
| 35 | Log retention? | 30 giorni, JSON, senza segreti. |

---

## 6. Legale e attribuzione

| # | Domanda | Default proposto |
|---|---|---|
| 36 | Confermi uso **personale/non commerciale** di TMDb? | Sì. |
| 37 | Accetti l'attribuzione **TMDb + JustWatch** in UI? | Sì, obbligatoria per i dati watch provider. |
| 38 | Hai letto i **Termini TMDb** (pagina 403 al fetcher)? | Da leggere manualmente prima della Fase 3. |
| 39 | Accetti di **non usare** scraping/GraphQL JustWatch? | Sì, vincolo di progetto. |
| 40 | Vuoi una **revisione legale** prima della Fase 3? | Consigliata. |

---

## 7. Decisioni già prese (non serve rispondere)

- Monolite modulare, non microservizi.
- PostgreSQL fonte di verità, Redis broker/cache.
- Snapshot immutabili, solo snapshot validi per le sync.
- MIRROR/APPEND_ONLY, soglie, lock, idempotenza, riconciliazione.
- Segreti cifrati a riposo, sessioni HttpOnly, CSRF, rate limit login.
- UI e documentazione in italiano; identificatori in inglese.
- Nessun connettore mock in produzione.
- Nessuna lista "Top 10 ufficiale" senza fonte verificata.
- Film e serie separati.
- MDBList ID numerico come chiave; slug/URL solo display.

---

## 8. Risposte minime per partire con la Fase 2

La Fase 2 non richiede credenziali esterne. Per partire bastano:

1. conferma di procedere;
2. dominio (anche placeholder) e email admin;
3. decisione su Docker secrets vs `.env` per i segreti;
4. conferma della policy di backup.

Per la Fase 3 servono TMDb key, MDBList key e lista di test. Senza queste, la Fase 3 resta bloccata e non va simulata.
