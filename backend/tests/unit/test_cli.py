"""CLI entrypoints: validation, dispatch and operational error paths."""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app import cli
from app.core.config import Settings
from app.db.models import Provider
from app.db.session import get_session_factory
from app.repositories import collections as collections_repo
from app.repositories import users
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, BOOTSTRAP_TOKEN


def _session():
    return get_session_factory()()


def test_bootstrap_admin_validates_token_and_password(db, app_settings, capsys) -> None:
    assert (
        cli.bootstrap_admin(app_settings, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, token=None)
        == 1
    )
    assert (
        cli.bootstrap_admin(app_settings, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, token="bad")
        == 1
    )
    weak = cli.bootstrap_admin(
        app_settings, email=ADMIN_EMAIL, password="short", token=BOOTSTRAP_TOKEN
    )
    assert weak == 1
    assert (
        cli.bootstrap_admin(
            app_settings, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, token=BOOTSTRAP_TOKEN
        )
        == 0
    )
    assert "admin creato" in capsys.readouterr().out
    # Bootstrap is closed after the first user.
    assert (
        cli.bootstrap_admin(
            app_settings, email="second@example.com", password=ADMIN_PASSWORD, token=BOOTSTRAP_TOKEN
        )
        == 1
    )


def test_bootstrap_admin_without_configured_token(db) -> None:
    settings = Settings(database_url="sqlite://", bootstrap_token="", redis_url="")
    assert cli.bootstrap_admin(settings, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, token="x") == 1


def test_create_collection_validates_cli_arguments(db, seeded) -> None:
    assert (
        cli.create_collection(
            provider_slug="netflix", media_type="bad", slug="x", name="X", genre_ids=None
        )
        == 1
    )
    assert (
        cli.create_collection(
            provider_slug="netflix",
            media_type="movie",
            slug="x",
            name="X",
            genre_ids=None,
            country="ITA",
        )
        == 1
    )
    assert (
        cli.create_collection(
            provider_slug="netflix", media_type="movie", slug="x", name="X", genre_ids=[0]
        )
        == 1
    )
    assert (
        cli.create_collection(
            provider_slug="missing", media_type="movie", slug="x", name="X", genre_ids=None
        )
        == 1
    )


def test_create_collection_creates_and_updates(db, seeded, capsys) -> None:
    assert (
        cli.create_collection(
            provider_slug="netflix",
            media_type="movie",
            slug="cli-netflix-azione",
            name="CLI Netflix Azione",
            genre_ids=[28, 12],
            description="descrizione CLI",
        )
        == 0
    )
    with _session() as session:
        collection = collections_repo.get_collection_by_slug(session, "cli-netflix-azione")
        assert collection is not None
        assert collection.description == "descrizione CLI"
    assert "collezione creata/aggiornata" in capsys.readouterr().out
    # Upsert with default description and no genres.
    assert (
        cli.create_collection(
            provider_slug="netflix",
            media_type="show",
            slug="cli-netflix-serie",
            name="CLI Netflix Serie",
            genre_ids=[18],
            country="it",
        )
        == 0
    )


def test_reset_password_and_main_dispatch(db, seeded, app_settings, monkeypatch, capsys) -> None:
    assert cli.reset_password(email=ADMIN_EMAIL, password="short") == 1
    assert cli.reset_password(email="missing@example.com", password=ADMIN_PASSWORD) == 1
    with _session() as session:
        user = users.create_user(session, email=ADMIN_EMAIL, password_hash="old")
        session.commit()
        user_id = user.id
    assert cli.reset_password(email=ADMIN_EMAIL.upper(), password=ADMIN_PASSWORD) == 0
    with _session() as session:
        refreshed = session.get(type(user), user_id)
        assert refreshed is not None
        assert refreshed.password_hash != "old"

    assert cli.main(["seed-providers"]) == 0
    assert (
        cli.main(
            [
                "create-collection",
                "--provider",
                "netflix",
                "--media-type",
                "movie",
                "--slug",
                "cli-main",
                "--name",
                "CLI Main",
                "--genre-ids",
                "bad",
            ]
        )
        == 1
    )
    assert (
        cli.main(
            [
                "create-collection",
                "--provider",
                "netflix",
                "--media-type",
                "movie",
                "--slug",
                "cli-main",
                "--name",
                "CLI Main",
                "--genre-ids",
                "28",
            ]
        )
        == 0
    )
    assert cli.main(["reset-password", "--email", ADMIN_EMAIL, "--password", ADMIN_PASSWORD]) == 0
    assert "password aggiornata" in capsys.readouterr().out


def test_main_operational_commands_are_dispatched(db, seeded, app_settings, monkeypatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(cli, "backup_verify", lambda *a, **k: called.append("backup") or 0)
    assert cli.main(["backup-verify", "--backup-dir", "/tmp"]) == 0
    assert called == ["backup"]

    monkeypatch.setattr(
        cli.justwatch_collections,
        "sync_collections",
        lambda *a, **k: SimpleNamespace(
            mappings=2,
            collections_created=1,
            collections_updated=0,
            skipped_providers={"x"},
            unverified_providers={"y"},
            unmapped_packages={"z"},
        ),
    )
    assert cli.main(["justwatch-collections", "--provider", "netflix"]) == 0

    monkeypatch.setattr(
        cli,
        "backfill_from_snapshots",
        lambda *a, **k: SimpleNamespace(
            snapshots=3,
            items=10,
            created_or_updated=4,
        ),
    )
    assert cli.main(["backfill-availability"]) == 0

    monkeypatch.setattr(
        cli,
        "verify_tmdb_providers",
        lambda *a, **k: [
            SimpleNamespace(
                slug="netflix",
                movie_provider_id="8",
                tv_provider_id=None,
                movie_name="Netflix",
                tv_name=None,
                deactivated_movie=0,
                deactivated_show=1,
            ),
        ],
    )
    assert cli.main(["verify-providers", "--country", "it"]) == 0

    class FakeTMDb:
        def __init__(self, token):
            self.token = token

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(cli.credentials_service, "get_secret", lambda *a, **k: "token")
    monkeypatch.setattr(cli, "TMDbClient", FakeTMDb)
    monkeypatch.setattr(
        cli,
        "detect_tv_changes",
        lambda *a, **k: SimpleNamespace(
            checked=1,
            season_events=2,
            episode_events=3,
            errors=0,
        ),
    )
    assert cli.main(["detect-tv-changes", "--limit", "5"]) == 0


def test_read_password_and_parser(monkeypatch) -> None:
    assert cli._read_password(argparse.Namespace(password="x")) == "x"
    passwords = iter(["a", "b"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: next(passwords))
    with pytest.raises(SystemExit):
        cli._read_password(argparse.Namespace(password=None))
    parser = cli.build_parser()
    assert parser.parse_args(["seed-providers"]).command == "seed-providers"
    args = parser.parse_args(
        ["create-collection", "--provider", "netflix", "--slug", "s", "--name", "N"]
    )
    assert args.media_type == "movie"


def test_remove_demo_collections_dry_run_then_apply(db, seeded, capsys) -> None:
    from app.seed import remove_demo_collections

    assert remove_demo_collections() == 0
    assert "senza binding: 23" in capsys.readouterr().out
    with _session() as session:
        assert len(collections_repo.list_collections(session)) == 23

    assert remove_demo_collections(apply=True) == 0
    with _session() as session:
        assert collections_repo.list_collections(session) == []


def test_remove_demo_providers_after_collections(db, seeded, capsys) -> None:
    from app.seed import remove_demo_collections, remove_demo_providers

    assert remove_demo_collections(apply=True) == 0
    assert remove_demo_providers(apply=True) == 0
    with _session() as session:
        assert collections_repo.list_collections(session) == []
        assert session.scalar(select(Provider).limit(1)) is None
