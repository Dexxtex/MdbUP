"""Command line entrypoint: ``python -m app.cli <command>``.

Commands:
  bootstrap-admin    create the first admin (requires BOOTSTRAP_TOKEN or --token)
  seed-providers     upsert demo providers, sources and TMDb mappings (no collections)
  create-collection  create/update a TMDb collection, optionally filtered by genre
  backup-verify      verify the latest encrypted backup and refresh BACKUP_STATUS_FILE
"""

from __future__ import annotations

import argparse
import getpass
import shutil
import sys
from pathlib import Path

from sqlalchemy import delete, select

from app.core.config import Settings, get_settings
from app.core.crypto import ALGORITHM, SecretCipher, build_aad
from app.core.security import (
    PasswordPolicyError,
    constant_time_equals,
    hash_password,
    validate_password_strength,
)
from app.core.time import utcnow
from app.db.models import (
    AppUser,
    Credential,
    NotificationChannel,
    Provider,
    Source,
    UserSession,
)
from app.db.session import session_scope
from app.domain.enums import CollectionKind, CollectionOrigin, DateBasis, MediaType, OfferType
from app.integrations.tmdb.client import TMDbClient
from app.repositories import audit, users
from app.repositories import collections as collections_repo
from app.repositories import providers as providers_repo
from app.seed import seed_reference_data, seed_sources
from app.services import backup as backup_service
from app.services import credentials as credentials_service
from app.services import justwatch_collections
from app.services.availability import backfill_from_snapshots
from app.services.credentials import CredentialKind
from app.services.provider_verification import verify_tmdb_providers
from app.services.tv_events import detect_tv_changes

__all__ = [
    "backfill_from_snapshots",
    "backup_verify",
    "bootstrap_admin",
    "build_parser",
    "create_collection",
    "detect_tv_changes",
    "main",
    "reset_password",
    "rotate_encryption_key",
    "seed_reference_data",
    "verify_tmdb_providers",
]


def _fail(message: str) -> int:
    print(f"errore: {message}", file=sys.stderr)
    return 1


def bootstrap_admin(
    settings: Settings,
    *,
    email: str,
    password: str,
    token: str | None,
) -> int:
    """Create the first admin user from the server console."""
    expected_token = settings.bootstrap_token
    if not expected_token:
        return _fail("BOOTSTRAP_TOKEN non configurato: impostarlo e riprovare.")
    if not token:
        return _fail("token di bootstrap mancante: usare --token.")
    if not constant_time_equals(token, expected_token):
        return _fail("token di bootstrap non valido.")
    try:
        validate_password_strength(password, email)
    except PasswordPolicyError as exc:
        return _fail(str(exc))
    with session_scope() as db:
        if users.count_users(db) > 0:
            return _fail("esiste già un utente: il bootstrap è chiuso.")
        user = users.create_user(db, email=email, password_hash=hash_password(password))
        audit.record(
            db,
            action="bootstrap_completed",
            entity_type="app_user",
            entity_id=user.id,
            actor_user_id=user.id,
            after={"email": user.email, "via": "cli"},
        )
        print(f"admin creato: {user.email} ({user.id})")
    return 0


def create_collection(
    *,
    provider_slug: str,
    media_type: str,
    slug: str,
    name: str,
    genre_ids: list[int] | None,
    country: str = "IT",
    description: str | None = None,
) -> int:
    """Create or update a TMDb collection with an optional genre filter."""
    try:
        media = MediaType(media_type.upper())
    except ValueError:
        return _fail(f"media-type non valido: {media_type}")
    country = country.upper()
    if len(country) != 2:
        return _fail("country deve essere un codice ISO a 2 lettere (es. IT).")
    if genre_ids and any(genre_id <= 0 for genre_id in genre_ids):
        return _fail("genre-ids deve contenere solo interi positivi.")
    with session_scope() as db:
        provider = db.scalar(select(Provider).where(Provider.slug == provider_slug))
        if provider is None:
            return _fail(f"provider non trovato: {provider_slug}")
        source = db.scalar(select(Source).where(Source.key == "tmdb"))
        if source is None:
            return _fail("fonte TMDb non trovata: eseguire prima seed-providers.")
        mapping = providers_repo.get_mapping(
            db,
            provider_id=provider.id,
            source_id=source.id,
            country_code=country,
        )
        if mapping is None:
            return _fail(
                f"mapping TMDb mancante per {provider_slug} ({country}): eseguire seed-providers."
            )
        genre_key = ",".join(str(genre_id) for genre_id in genre_ids or [])
        filters: dict[str, object] = {
            "provider_id": int(mapping.external_provider_id),
            "watch_region": country,
            "with_watch_monetization_types": "flatrate",
            "sort_by": "popularity.desc",
        }
        if genre_key:
            filters["with_genres"] = genre_key
        collections_repo.upsert_collection(
            db,
            slug=slug,
            source_id=source.id,
            provider_id=provider.id,
            country_code=country,
            media_type=media.value,
            kind=CollectionKind.CATALOG.value,
            origin=CollectionOrigin.AGGREGATOR.value,
            date_basis=DateBasis.UNKNOWN.value,
            name=name,
            description=description
            or (
                f"Catalogo TMDb {provider.name} {country} — "
                f"{'Film' if media is MediaType.MOVIE else 'Serie'}"
                + (f", generi {genre_key}" if genre_key else "")
                + " (flatrate)."
            ),
            source_collection_key=(
                f"{int(mapping.external_provider_id)}:{media.value}"
                + (f":{genre_key}" if genre_key else "")
            ),
            source_url=None,
            offer_types=[OfferType.FLATRATE.value],
            filters=filters,
            quality_flags={
                "unverified_provider_mapping": True,
                "added_date_missing": True,
                "genre_filter": genre_key or None,
            },
            sort_mode="POPULARITY",
            is_active=True,
        )
        print(f"collezione creata/aggiornata: {slug} ({name})")
    return 0


def rotate_encryption_key(
    settings: Settings,
    *,
    new_version: int,
    dry_run: bool = False,
) -> int:
    """Re-encrypt every stored secret with a new key version.

    The new key must already be present in ``APP_ENCRYPTION_KEYS``; this makes
    the rotation zero-downtime: the running process can still decrypt old rows
    while the CLI rewrites them. After a successful run, set
    ``APP_ENCRYPTION_KEY_VERSION`` to the new version and restart API/worker.
    """
    if new_version <= 0:
        return _fail("new-version deve essere un intero positivo.")
    try:
        cipher = SecretCipher.from_settings(settings)
    except Exception as exc:
        return _fail(f"keyring non valido: {exc}")
    if not cipher.has_version(new_version):
        return _fail(
            f"key_version {new_version} non presente in APP_ENCRYPTION_KEYS: "
            "aggiungere la nuova chiave al keyring e riprovare."
        )
    if new_version == cipher.active_version:
        return _fail("new-version coincide con la versione attiva.")
    new_cipher = SecretCipher({new_version: cipher.key_for(new_version)}, new_version)
    rotated_credentials = 0
    rotated_channels = 0
    with session_scope() as db:
        for row in db.scalars(select(Credential)).all():
            aad = build_aad(
                scope=row.scope,
                source_id=row.source_id,
                key=row.key,
                key_version=row.key_version,
            )
            plaintext = cipher.decrypt(row.ciphertext, row.nonce, row.key_version, aad=aad)
            new_aad = build_aad(
                scope=row.scope,
                source_id=row.source_id,
                key=row.key,
                key_version=new_version,
            )
            encrypted = new_cipher.encrypt(plaintext, aad=new_aad)
            row.ciphertext = encrypted.ciphertext
            row.nonce = encrypted.nonce
            row.algorithm = ALGORITHM
            row.key_version = encrypted.key_version
            rotated_credentials += 1
        for channel in db.scalars(
            select(NotificationChannel).where(NotificationChannel.secret_ciphertext.is_not(None))
        ).all():
            aad = build_aad(
                scope="NOTIFICATION",
                source_id=channel.id,
                key=channel.kind,
                key_version=channel.secret_key_version or 0,
            )
            secret_ciphertext = channel.secret_ciphertext
            secret_nonce = channel.secret_nonce
            if secret_ciphertext is None or secret_nonce is None:
                continue
            plaintext = cipher.decrypt(
                secret_ciphertext,
                secret_nonce,
                channel.secret_key_version or 0,
                aad=aad,
            )
            new_aad = build_aad(
                scope="NOTIFICATION",
                source_id=channel.id,
                key=channel.kind,
                key_version=new_version,
            )
            encrypted = new_cipher.encrypt(plaintext, aad=new_aad)
            channel.secret_ciphertext = encrypted.ciphertext
            channel.secret_nonce = encrypted.nonce
            channel.secret_algorithm = ALGORITHM
            channel.secret_key_version = encrypted.key_version
            rotated_channels += 1
        if dry_run:
            db.rollback()
            print(
                f"dry-run: {rotated_credentials} credenziali e {rotated_channels} canali "
                f"possono essere ruotati alla versione {new_version}."
            )
            return 0
        audit.record(
            db,
            action="encryption_key_rotated",
            entity_type="app_config",
            entity_id="keyring",
            actor_type="SYSTEM",
            after={
                "new_version": new_version,
                "credentials": rotated_credentials,
                "notification_channels": rotated_channels,
            },
        )
        print(
            f"ruotati {rotated_credentials} credenziali e {rotated_channels} canali "
            f"alla key_version {new_version}."
        )
        print(
            "Ora imposta APP_ENCRYPTION_KEY_VERSION="
            f"{new_version} (e la chiave corrispondente) e riavvia api/worker/scheduler."
        )
    return 0


def reset_password(*, email: str, password: str) -> int:
    """Reset an admin password and revoke all of that user's sessions."""
    email = email.strip().lower()
    try:
        validate_password_strength(password, email)
    except PasswordPolicyError as exc:
        return _fail(str(exc))
    with session_scope() as db:
        user = db.scalar(select(AppUser).where(AppUser.email == email))
        if user is None:
            return _fail(f"utente non trovato: {email}")
        user.password_hash = hash_password(password)
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        audit.record(
            db,
            action="password_reset",
            entity_type="app_user",
            entity_id=user.id,
            after={"email": user.email, "via": "cli", "at": utcnow().isoformat()},
        )
        print(f"password aggiornata per: {user.email}; sessioni revocate.")
    return 0


def backup_verify(
    settings: Settings,
    *,
    backup_dir: str | None = None,
    status_file: str | None = None,
    identity_file: str | None = None,
) -> int:
    """Verify the newest ``mdbup-*.dump.age`` and refresh ``BACKUP_STATUS_FILE``.

    A read-only backup directory still verifies (checksum, size, age header);
    only the status file update is skipped in that case.
    """
    directory = Path(backup_dir or settings.backup_dir)
    status_path = Path(status_file or settings.effective_backup_status_file)
    identity = identity_file or settings.backup_age_identity_file.strip()
    verification = backup_service.verify_latest_backup(
        backup_dir=directory,
        status_file=status_path,
        age_identity_file=Path(identity) if identity else None,
        age_binary=shutil.which("age"),
    )
    print(f"archivio: {verification.file or '-'}")
    print(f"dimensione: {verification.size_bytes} byte")
    print(f"sha256: {verification.sha256 or '-'}")
    print(f"stato: {verification.status}")
    print(f"decifrato: {'sì' if verification.decrypted else 'no'}")
    if not verification.age_available:
        print("age: non disponibile, verifica limitata a checksum e header")
    elif not verification.decrypted:
        print("identità age non disponibile nel container: verifica limitata a checksum e header")
    if verification.error:
        print(f"errore: {verification.error}")
    print(f"status file: {status_path}")
    return 0 if verification.ok else 1


def _read_password(args: argparse.Namespace) -> str:
    if args.password:
        return args.password
    first = getpass.getpass("password: ")
    second = getpass.getpass("ripeti password: ")
    if first != second:
        raise SystemExit("errore: le password non coincidono.")
    return first


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="MdbUP CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap-admin", help="Crea il primo utente admin")
    bootstrap.add_argument("--email", required=True, help="Email dell'admin")
    bootstrap.add_argument("--password", help="Password (altrimenti richiesta a terminale)")
    bootstrap.add_argument("--token", help="Token di bootstrap (default: BOOTSTRAP_TOKEN)")

    subparsers.add_parser(
        "seed-sources",
        help="Inserisce solo le fonti (nessun provider o collezione)",
    )
    subparsers.add_parser(
        "seed-providers",
        help="Inserisce dati dimostrativi: provider, fonti e mapping; non crea collezioni",
    )
    remove_demo = subparsers.add_parser(
        "remove-demo-collections",
        help="Rimuove le collezioni TMDb demo (default: dry-run)",
    )
    remove_demo.add_argument(
        "--apply", action="store_true", help="Applica la rimozione (default: dry-run)"
    )
    remove_demo.add_argument(
        "--force",
        action="store_true",
        help="Rimuove anche le collezioni demo con binding attivi (operazione distruttiva)",
    )
    verify = subparsers.add_parser(
        "verify-providers",
        help="Verifica live gli ID TMDb movie/tv per l'Italia e aggiorna i mapping",
    )
    verify.add_argument("--country", default="IT", help="Codice paese (default IT)")
    subparsers.add_parser(
        "backfill-availability",
        help="Popola Availability dagli snapshot storici (baseline first_seen_at)",
    )
    tv = subparsers.add_parser(
        "detect-tv-changes",
        help="Rileva nuove stagioni/episodi e registra eventi sulla serie madre",
    )
    tv.add_argument("--limit", type=int, default=50, help="Numero massimo di serie da controllare")

    create = subparsers.add_parser(
        "create-collection",
        help="Crea/aggiorna una collezione TMDb (filtro genere opzionale)",
    )
    create.add_argument("--provider", required=True, help="Slug provider (es. netflix)")
    create.add_argument(
        "--media-type", choices=["movie", "show"], default="movie", help="Tipo media"
    )
    create.add_argument("--slug", required=True, help="Slug stabile della collezione")
    create.add_argument("--name", required=True, help="Nome visualizzato")
    create.add_argument(
        "--genre-ids",
        help="ID genere TMDb separati da virgola (es. 28,12,27)",
    )
    create.add_argument("--country", default="IT", help="Codice paese (default IT)")
    create.add_argument("--description", help="Descrizione opzionale")

    jw = subparsers.add_parser(
        "justwatch-collections",
        help="Crea/aggiorna le collezioni JustWatch per i provider mappati",
    )
    jw.add_argument("--country", default="IT", help="Codice paese (default IT)")
    jw.add_argument(
        "--provider",
        action="append",
        help="Slug provider da includere (ripetibile; default: tutti i mappati)",
    )

    reset = subparsers.add_parser(
        "reset-password", help="Reimposta la password di un admin e revoca le sessioni"
    )
    reset.add_argument("--email", required=True, help="Email dell'admin")
    reset.add_argument("--password", help="Nuova password (altrimenti richiesta a terminale)")

    rotate = subparsers.add_parser(
        "rotate-encryption-key",
        help="Re-cifra credenziali e segreti notifiche con una nuova key_version",
    )
    rotate.add_argument("--new-version", type=int, required=True, help="Nuova key_version")
    rotate.add_argument(
        "--dry-run", action="store_true", help="Verifica senza scrivere nel database"
    )

    verify_backup = subparsers.add_parser(
        "backup-verify",
        help="Verifica l'ultimo backup cifrato e aggiorna BACKUP_STATUS_FILE",
    )
    verify_backup.add_argument("--backup-dir", help="Directory dei backup (default: BACKUP_DIR)")
    verify_backup.add_argument("--status-file", help="File di stato (default: BACKUP_STATUS_FILE)")
    verify_backup.add_argument(
        "--identity-file",
        help="Chiave privata age per verificare il magic PGDMP (default: BACKUP_AGE_IDENTITY_FILE)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.command == "bootstrap-admin":
        return bootstrap_admin(
            settings,
            email=args.email,
            password=_read_password(args),
            token=args.token,
        )
    if args.command == "seed-sources":
        return seed_sources()
    if args.command == "seed-providers":
        return seed_reference_data()
    if args.command == "remove-demo-collections":
        from app.seed import remove_demo_collections

        return remove_demo_collections(apply=args.apply, force=args.force)
    if args.command == "detect-tv-changes":
        with session_scope() as db:
            token = credentials_service.get_secret(db, settings, CredentialKind.TMDB)
            with TMDbClient(token) as client:
                tv_outcome = detect_tv_changes(db, client, limit=args.limit)
        print(
            f"serie controllate: {tv_outcome.checked}, "
            f"eventi stagioni: {tv_outcome.season_events}, "
            f"eventi episodi: {tv_outcome.episode_events}, errori: {tv_outcome.errors}"
        )
        return 0
    if args.command == "justwatch-collections":
        with session_scope() as db:
            justwatch_outcome = justwatch_collections.sync_collections(
                db, settings, country_code=args.country, provider_slugs=args.provider
            )
        print(
            f"mapping verificati: {justwatch_outcome.mappings}, "
            f"collezioni create: {justwatch_outcome.collections_created}, "
            f"aggiornate: {justwatch_outcome.collections_updated}, "
            f"provider senza flatrate: {len(justwatch_outcome.skipped_providers)}, "
            f"provider non verificati: {len(justwatch_outcome.unverified_providers)}"
        )
        if justwatch_outcome.skipped_providers:
            print(
                "saltati (nessun flatrate): "
                + ", ".join(sorted(justwatch_outcome.skipped_providers))
            )
        if justwatch_outcome.unverified_providers:
            print("non verificati: " + ", ".join(sorted(justwatch_outcome.unverified_providers)))
        if justwatch_outcome.unmapped_packages:
            print("package senza mapping: " + ", ".join(justwatch_outcome.unmapped_packages))
        return 0
    if args.command == "backfill-availability":
        with session_scope() as db:
            backfill_outcome = backfill_from_snapshots(db)
        print(
            f"snapshot analizzati: {backfill_outcome.snapshots}, "
            f"item osservati: {backfill_outcome.items}, "
            f"availability create/aggiornate: {backfill_outcome.created_or_updated}"
        )
        return 0
    if args.command == "verify-providers":
        with session_scope() as db:
            results = verify_tmdb_providers(db, settings, country_code=args.country.upper())
        print(
            f"{'provider':24} {'movie':>7} {'tv':>7} {'movie name':28} {'tv name':28} "
            f"{'off M':>5} {'off TV':>6}"
        )
        for item in results:
            print(
                f"{item.slug:24} {item.movie_provider_id or '-':>7} "
                f"{item.tv_provider_id or '-':>7} {item.movie_name or '-':28} "
                f"{item.tv_name or '-':28} {item.deactivated_movie:>5} {item.deactivated_show:>6}"
            )
        return 0
    if args.command == "backup-verify":
        return backup_verify(
            settings,
            backup_dir=args.backup_dir,
            status_file=args.status_file,
            identity_file=args.identity_file,
        )
    if args.command == "reset-password":
        return reset_password(email=args.email, password=_read_password(args))
    if args.command == "rotate-encryption-key":
        return rotate_encryption_key(settings, new_version=args.new_version, dry_run=args.dry_run)
    if args.command == "create-collection":
        genre_ids = None
        if args.genre_ids:
            try:
                genre_ids = [int(value) for value in args.genre_ids.split(",") if value]
            except ValueError:
                return _fail("genre-ids deve essere una lista di interi separati da virgola.")
        return create_collection(
            provider_slug=args.provider,
            media_type=args.media_type,
            slug=args.slug,
            name=args.name,
            genre_ids=genre_ids,
            country=args.country.upper(),
            description=args.description,
        )
    parser.error(f"comando sconosciuto: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover - console entrypoint
    raise SystemExit(main())
