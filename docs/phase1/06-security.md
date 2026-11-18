# Fase 1 — Sicurezza

**Stato:** progettazione. Nessun codice di produzione implementato.
**Modello:** app privata, single-user, esposta su Internet solo dopo security review.

---

## 1. Threat model

### Asset

| Asset | Perché è critico |
|---|---|
| API key MDBList | Può leggere/scrivere tutte le liste dell'account. |
| API key TMDb | Accesso all'API, quota e attribuzione. |
| Token/credenziali JustWatch | Accesso a dati commerciali e S3. |
| `APP_ENCRYPTION_KEY` | Decifra tutte le credenziali salvate. |
| Sessioni admin | Accesso completo all'app. |
| Database PostgreSQL | Snapshot, cronologia, configurazioni. |
| Backup | Copia completa del database. |
| Log | Possono contenere segreti se non redatti. |

### Attori e superfici

| Attore | Superficie | Minaccia |
|---|---|---|
| Internet anonimo | Login, bootstrap, API | Brute force, credential stuffing, scansione. |
| Utente malintenzionato con sessione | API | CSRF, privilege escalation, accesso a segreti. |
| Dipendenza compromessa | Build/container | Supply chain, esfiltrazione. |
| Errore operativo | Log/export/backup | Leak di segreti. |
| SSRF | URL forniti dall'utente | Accesso a metadata cloud/rete interna. |

### Minacce principali e mitigazioni

| Minaccia | Mitigazione |
|---|---|
| Credenziali predefinite | Nessuna; bootstrap con token monouso. |
| Brute force login | Argon2id + rate limit per IP+email + lockout progressivo + audit. |
| Sessione rubata | Cookie HttpOnly/Secure/SameSite, rotazione, revoca, scadenza. |
| CSRF | Double-submit + Origin/Referer check. |
| XSS | CSP strict, React escaping, nessun `dangerouslySetInnerHTML`. |
| Segreti nei log | Redazione centralizzata, test automatici. |
| Segreti nel browser | Nessun endpoint restituisce segreti; solo `masked_hint`. |
| SSRF | Host allowlist, nessun URL utente, redirect disabilitati. |
| Perdita chiave di cifratura | Custodia separata, backup offline, procedura di rotazione. |
| Backup rubato | Cifratura `age` con chiave pubblica; privata offline. |
| Supply chain | Lockfile, pin digest, `pip-audit`, `npm audit`, `trivy`. |

---

## 2. Bootstrap del primo admin

**Requisiti:**
- Nessuna credenziale predefinita.
- Il primo admin si crea una sola volta, con un token monouso.
- Dopo la creazione, il bootstrap è disabilitato.

**Flusso:**
1. Al primo avvio, l'app genera/richiede `BOOTSTRAP_TOKEN` (32 byte random, da Docker secret o file).
2. `GET /api/auth/setup` mostra la pagina di bootstrap solo se `users` è vuoto.
3. `POST /api/auth/setup` con `{token, email, password}`:
   - confronto del token in tempo costante;
   - verifica che non esistano utenti;
   - password policy (min 12 caratteri, non compromessa, non uguale all'email);
   - crea l'utente con Argon2id;
   - invalida il token (flag `bootstrap_completed=true`);
   - scrive `audit_log`.
4. Ogni tentativo con token errato è rate-limited e loggato.
5. Se `users` non è vuoto, l'endpoint risponde `409 already_bootstrapped` senza rivelare dettagli.

**Codice di esempio:**

```python
async def setup_admin(token: str, email: str, password: str) -> User:
    if await users.count() > 0:
        raise Conflict("already_bootstrapped")
    if not secrets.compare_digest(token, settings.bootstrap_token):
        await audit.record("bootstrap_failed", ip=request.ip)
        raise AuthError("invalid_token")
    validate_password(password, email)
    user = await users.create(
        email=email,
        password_hash=hash_password(password),
        is_admin=True,
    )
    await settings.set("bootstrap_completed", True)
    await audit.record("bootstrap_completed", actor=user)
    return user
```

---

## 3. Password

- **Algoritmo:** Argon2id (`argon2-cffi`).
- **Parametri:** `time_cost=3`, `memory_cost=65536` (64 MiB), `parallelism=4`, `hash_len=32`, `salt_len=16`.
- **Policy:** minimo 12 caratteri; massimo 128; consigliato generatore; nessun limite di caratteri speciali.
- **Rehash:** al login, se i parametri sono cambiati, rifare l'hash e aggiornare.
- **Reset:** non c'è reset via email in Fase 1; procedura CLI con accesso al server.
- **Audit:** login riuscito/fallito, cambio password, revoca sessioni.

```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(hash_: str, password: str) -> bool:
    try:
        return ph.verify(hash_, password)
    except VerifyMismatchError:
        return False
```

---

## 4. Sessioni

- Token opaco: `secrets.token_urlsafe(32)`.
- Nel DB si salva solo `sha256(token)`.
- Cookie: `__Host-mdbsync-session` in produzione (`Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, nessun `Domain`).
- In sviluppo HTTP: `mdbsync-session` con `Secure=false`, mai in produzione.
- Scadenza assoluta: 7 giorni; idle: 12 ore; rotazione al login e dopo privilege change.
- Logout: revoca della sessione corrente; "logout globale" revoca tutte.
- `last_seen_at` aggiornato al massimo una volta ogni 5 minuti per ridurre le scritture.

```python
def issue_session(user_id: UUID, ip: str, user_agent: str) -> tuple[str, Session]:
    token = secrets.token_urlsafe(32)
    session = sessions.create(
        user_id=user_id,
        token_hash=sha256(token.encode()),
        csrf_hash=sha256(secrets.token_bytes(32)),
        expires_at=now_utc() + timedelta(days=7),
        ip=ip,
        user_agent=user_agent,
    )
    return token, session
```

---

## 5. CSRF

- **Double-submit:** cookie `__Host-mdbsync-csrf` (non HttpOnly) con token random; header `X-CSRF-Token` obbligatorio per `POST/PUT/PATCH/DELETE`.
- Il server conserva `csrf_hash` nella sessione e confronta in tempo costante.
- **Origin/Referer check:** l'origine deve corrispondere a `APP_BASE_URL`; se assente, rifiutare per i metodi non sicuri.
- **SameSite=Lax** come difesa aggiuntiva.
- **Esclusioni:** nessuna per le mutazioni; il login è protetto da Origin check + rate limit (non ha sessione).
- **Errori:** `403 CSRF_INVALID`, senza dettagli sul token.

```python
def verify_csrf(request: Request, session: Session) -> None:
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != settings.base_url.rstrip("/"):
        raise Forbidden("csrf_origin")
    header = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get(settings.csrf_cookie_name, "")
    if not header or not cookie or not secrets.compare_digest(header, cookie):
        raise Forbidden("csrf_token")
    if not secrets.compare_digest(sha256(header.encode()), session.csrf_hash):
        raise Forbidden("csrf_token")
```

---

## 6. Rate limit e lockout

| Endpoint | Limite | Finestra | Chiave |
|---|---|---|---|
| `POST /auth/login` | 5 tentativi | 15 min | IP + email |
| `POST /auth/setup` | 3 tentativi | 15 min | IP |
| `POST /auth/change-password` | 3 | 15 min | utente |
| `POST /bindings/{id}/runs` | 5 | 1 min | utente |
| API globale | 300 richieste | 1 min | sessione/IP |

- Redis `INCR` + `EXPIRE`; se Redis non è disponibile, fallback in memoria con limite più severo (fail-closed per login).
- Lockout progressivo: dopo 5 fallimenti, 15 min; dopo 10, 60 min; dopo 20, blocco manuale.
- Messaggi generici: "Credenziali non valide" (non rivelare se l'email esiste).
- Audit di ogni lockout.

---

## 7. Credenziali delle integrazioni

### 7.1 Cifratura

- **Algoritmo:** AES-256-GCM (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`).
- **Chiave:** 32 byte, da `APP_ENCRYPTION_KEY` (base64) o Docker secret; mai nel DB.
- **Nonce:** 12 byte random per ogni cifratura.
- **AAD:** `scope|source_id|key|key_version` per legare il ciphertext al contesto.
- **key_version:** permette la rotazione; il decrypt usa la versione salvata.
- **Storage:** `ciphertext`, `nonce`, `key_version`, `masked_hint`.
- **Masking:** mostra solo gli ultimi 4 caratteri, es. `••••a1b2`.
- **Mai in risposta:** gli endpoint restituiscono solo `configured`, `masked_hint`, `key_version`, `last_verified_at`.

```python
import os, base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def encrypt_secret(plaintext: str, key: bytes, aad: bytes) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode(), aad)
    return ct, nonce

def decrypt_secret(ct: bytes, nonce: bytes, key: bytes, aad: bytes) -> str:
    return AESGCM(key).decrypt(nonce, ct, aad).decode()
```

### 7.2 Rotazione

1. Aggiungere la nuova chiave a `APP_ENCRYPTION_KEYS` con un nuovo `key_version`.
2. Impostare `APP_ENCRYPTION_ACTIVE_VERSION` alla nuova versione.
3. Eseguire `python -m app.cli rotate-credentials`: decifra con la vecchia, cifra con la nuova, aggiorna `key_version`.
4. Verificare che tutti i record siano alla nuova versione.
5. Rimuovere la vecchia chiave solo dopo il backup e la verifica.

### 7.3 Redazione

- Redigere: `Authorization`, `apikey`, `token`, `password`, `secret`, `access_key`, `secret_key`, `cookie`, `set-cookie`.
- Redigere le query string che contengono `apikey`/`token`.
- Non loggare i body delle richieste di credenziali.
- Test automatico: cercare pattern di API key nei log.

---

## 8. SSRF

- **Nessun URL arbitrario** fornito dall'utente viene fetchato.
- I connettori usano base URL fisse e allowlist di host:
  - `api.themoviedb.org`
  - `api.mdblist.com`
  - `apis.justwatch.com` (solo se contratto)
  - `jw-data-partner-out.s3.amazonaws.com` (solo se contratto)
- L'import di una lista MDBList accetta solo ID o URL `mdblist.com/lists/...`; il backend estrae l'ID e chiama l'API, non fetcha l'URL.
- HTTPX: `follow_redirects=False`, timeout 20 s, limite dimensione risposta.
- Risoluzione DNS: se un host allowlist risolve a IP privato/link-local, rifiutare (protezione DNS rebinding).
- Nessun proxy utente.

---

## 9. Logging e audit

- **Formato:** JSON strutturato, timestamp UTC, `level`, `logger`, `message`, `request_id`, `user_id`, `source_id`, `target_id`, `run_id`, `job_id`, `duration_ms`, `outcome`.
- **Redazione:** centralizzata nel processor di logging; nessuna eccezione.
- **Audit:** login, logout, bootstrap, cambio password, creazione/modifica/eliminazione binding, cambio credenziali, avvio sync, approvazione soglie, export.
- **Retention:** log 30 giorni; audit 180 giorni.
- **Accesso:** i log non sono esposti via API; solo l'admin via filesystem/console.

---

## 10. Header, CORS, TLS

### Header (Caddy/API)

```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https://image.tmdb.org; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
X-Frame-Options: DENY
```

- **CORS:** nessuna origine cross-site in produzione; stessa origine. In sviluppo, `http://localhost:5173` esplicitamente.
- **TLS:** Caddy con Let's Encrypt; HSTS solo dopo aver verificato HTTPS.
- **Cookie:** `__Host-` richiede `Secure`, `Path=/`, nessun `Domain`.

---

## 11. Backup e ripristino

- **Cosa:** solo PostgreSQL (`pg_dump -Fc`); Redis non è un asset.
- **Cifratura:** `age` con chiave pubblica; la privata è offline.
- **Retention:** 7 giornalieri, 4 settimanali, 6 mensili.
- **Verifica:** restore mensile su DB scratch; `alembic current` e conteggi.
- **Chiave di cifratura:** backup separato, mai nello stesso bucket del DB.
- **Disaster recovery:** RPO 24 h, RTO 2 h; scheduler fermo finché i run non terminali non sono riconciliati.

---

## 12. Supply chain

- Lockfile Python (`uv.lock`) e Node (`package-lock.json`).
- Pin delle immagini Docker per digest.
- `pip-audit`, `npm audit --omit=dev`, `trivy fs`, `gitleaks` in CI.
- Container non-root, `read_only`, `cap_drop: ALL`, `no-new-privileges`.
- Nessuna dipendenza non necessaria; rivedere le nuove dipendenze.
- SBOM generato in CI (opzionale ma consigliato).

---

## 13. Test di sicurezza

| Test | Cosa verifica |
|---|---|
| `test_bootstrap_once.py` | Il bootstrap funziona una sola volta; token errato non crea utenti. |
| `test_password_hash.py` | Argon2id, rehash, policy. |
| `test_session_cookie.py` | Flag HttpOnly/Secure/SameSite, scadenza, revoca. |
| `test_csrf.py` | Mutazione senza token → 403; Origin errata → 403. |
| `test_login_rate_limit.py` | Lockout dopo N tentativi; messaggio generico. |
| `test_crypto_roundtrip.py` | Encrypt/decrypt, AAD errata, key_version. |
| `test_log_redaction.py` | Nessun token/apikey/cookie nei log. |
| `test_ssrf_allowlist.py` | Host non allowlist → errore; redirect → errore. |
| `test_secret_not_in_api.py` | Le risposte non contengono segreti. |
| `test_backup_encryption.py` | Il dump è cifrato e ripristinabile. |
| `test_prod_guards.py` | `APP_ENV=production` rifiuta mock/URL non ufficiali. |

---

## 14. Cosa non fare

- Non inserire segreti in `.env` in produzione se è disponibile un secret store.
- Non restituire mai una API key, nemmeno mascherata in parte, se non gli ultimi 4 caratteri.
- Non loggare URL completi con `apikey`/`token`.
- Non accettare URL arbitrari per import/fetch.
- Non usare `SameSite=None` senza necessità.
- Non disabilitare la verifica TLS.
- Non usare `pickle`/`eval` su payload esterni.
- Non fidarsi dei dati della fonte per costruire HTML.
