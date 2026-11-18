"""Export/import of non-secret application configuration.

The JSON document contains providers, TMDb mappings, targets, collections,
bindings/schedules and runtime settings. Credentials, encrypted ciphertext,
users, sessions, runs and snapshots are never exported. Import is an upsert: it
never deletes existing rows.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ValidationError
from app.core.config import APP_VERSION, Settings
from app.core.time import ensure_utc, utcnow
from app.db.models import Collection, NotificationChannel, Provider
from app.domain.enums import AuditActorType
from app.repositories import audit
from app.repositories import bindings as bindings_repo
from app.repositories import collections as collections_repo
from app.repositories import providers as providers_repo
from app.repositories import settings as settings_repo
from app.repositories import sources as sources_repo
from app.repositories import targets as targets_repo
from app.services.bindings import compute_next_run_at

CONFIG_VERSION = 1


def _provider_slug_map(db: Session) -> dict[uuid.UUID, str]:
    return {provider.id: provider.slug for provider in providers_repo.list_providers(db)}


def _collection_slug_map(db: Session) -> dict[uuid.UUID, str]:
    return {collection.id: collection.slug for collection in db.scalars(select(Collection)).all()}


def _export_filters(
    filters: dict[str, Any],
    *,
    collection_slugs: dict[uuid.UUID, str],
    provider_slugs: dict[uuid.UUID, str],
) -> dict[str, Any]:
    exported = dict(filters or {})
    for key, target_key in (
        ("source_collection_id", "source_collection_slug"),
        ("shared_snapshot_collection_id", "shared_snapshot_collection_slug"),
    ):
        raw = exported.pop(key, None)
        if raw:
            with contextlib.suppress(ValueError):
                exported[target_key] = collection_slugs.get(uuid.UUID(str(raw)))
    raw_sources = exported.pop("source_collection_ids", None)
    if isinstance(raw_sources, list):
        exported["source_collection_slugs"] = [
            collection_slugs[uuid.UUID(str(raw))]
            for raw in raw_sources
            if str(raw) in {str(key) for key in collection_slugs}
        ]
    raw_providers = exported.pop("provider_ids", None)
    if isinstance(raw_providers, list):
        exported["provider_slugs"] = [
            provider_slugs[uuid.UUID(str(raw))]
            for raw in raw_providers
            if str(raw) in {str(key) for key in provider_slugs}
        ]
    return exported


def export_config(db: Session, settings: Settings) -> dict[str, Any]:
    """Build a portable, secret-free configuration document."""
    providers = providers_repo.list_providers(db)
    provider_slugs = {provider.id: provider.slug for provider in providers}
    collection_slugs = _collection_slug_map(db)
    mappings_by_provider: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for mapping in providers_repo.list_mappings(db):
        source = sources_repo.get_source(db, mapping.source_id)
        mappings_by_provider.setdefault(mapping.provider_id, []).append(
            {
                "source_key": source.key if source is not None else None,
                "country_code": mapping.country_code,
                "external_provider_id": mapping.external_provider_id,
                "external_name": mapping.external_name,
                "is_primary": mapping.is_primary,
                "is_verified": mapping.is_verified,
                "metadata": mapping.metadata_json or {},
            }
        )
    targets = [
        {
            "remote_list_id": target.remote_list_id,
            "name": target.name,
            "mediatype": target.mediatype,
            "remote_slug": target.remote_slug,
            "remote_url": target.remote_url,
            "is_private": target.is_private,
            "item_count": target.item_count,
        }
        for target in targets_repo.list_targets(db)
    ]
    collections = []
    for collection in db.scalars(select(Collection).order_by(Collection.slug)).all():
        provider = next((item for item in providers if item.id == collection.provider_id), None)
        source = sources_repo.get_source(db, collection.source_id)
        collections.append(
            {
                "slug": collection.slug,
                "provider_slug": provider.slug if provider is not None else None,
                "source_key": source.key if source is not None else None,
                "country_code": collection.country_code,
                "media_type": collection.media_type,
                "kind": collection.kind,
                "origin": collection.origin,
                "date_basis": collection.date_basis,
                "name": collection.name,
                "description": collection.description,
                "source_collection_key": collection.source_collection_key,
                "source_url": collection.source_url,
                "offer_types": list(collection.offer_types or []),
                "filters": _export_filters(
                    dict(collection.filters or {}),
                    collection_slugs=collection_slugs,
                    provider_slugs=provider_slugs,
                ),
                "quality_flags": dict(collection.quality_flags or {}),
                "sort_mode": collection.sort_mode,
                "is_active": collection.is_active,
            }
        )
    bindings = []
    for binding in bindings_repo.list_bindings(db):
        binding_collection = collections_repo.get_collection(db, binding.collection_id)
        binding_target = targets_repo.get_target(db, binding.target_id)
        if binding_collection is None or binding_target is None:
            continue
        bindings.append(
            {
                "collection_slug": binding_collection.slug,
                "target_remote_list_id": binding_target.remote_list_id,
                "media_type": binding.media_type,
                "mode": binding.mode,
                "schedule_cron": binding.schedule_cron,
                "schedule_interval_hours": binding.schedule_interval_hours,
                "timezone": binding.timezone,
                "is_enabled": binding.is_enabled,
                "policy_version": binding.policy_version,
                "max_removal_absolute": binding.max_removal_absolute,
                "max_removal_percent": float(binding.max_removal_percent),
                "max_addition_percent": float(binding.max_addition_percent),
                "preserve_order": binding.preserve_order,
                "reorder_enabled": binding.reorder_enabled,
                "require_manual_review": binding.require_manual_review,
                "schedule_policy": binding.schedule_policy,
                "auto_apply_max_removals": binding.auto_apply_max_removals,
                "auto_apply_max_removal_ratio": float(binding.auto_apply_max_removal_ratio),
                "max_plan_age_minutes": binding.max_plan_age_minutes,
                "next_run_at": binding.next_run_at.isoformat()
                if binding.next_run_at is not None
                else None,
            }
        )
    channels = [
        {
            "name": channel.name,
            "kind": channel.kind,
            "is_enabled": False,
            "events": list(channel.events or []),
            "config": dict(channel.config or {}),
        }
        for channel in db.scalars(select(NotificationChannel)).all()
    ]
    return {
        "version": CONFIG_VERSION,
        "app_version": APP_VERSION,
        "exported_at": utcnow().isoformat(),
        "providers": [
            {
                "slug": provider.slug,
                "name": provider.name,
                "kind": provider.kind,
                "logo_url": provider.logo_url,
                "website_url": provider.website_url,
                "mappings": mappings_by_provider.get(provider.id, []),
            }
            for provider in providers
        ],
        "targets": targets,
        "collections": collections,
        "bindings": bindings,
        "settings": settings_repo.effective_values(db, settings),
        "notification_channels": channels,
    }


def _import_filters(
    filters: dict[str, Any],
    *,
    collections_by_slug: dict[str, Collection],
    providers_by_slug: dict[str, Provider],
) -> dict[str, Any]:
    imported = dict(filters or {})
    for key, target_key in (
        ("source_collection_slug", "source_collection_id"),
        ("shared_snapshot_collection_slug", "shared_snapshot_collection_id"),
    ):
        raw = imported.pop(key, None)
        if raw and raw in collections_by_slug:
            imported[target_key] = str(collections_by_slug[raw].id)
    raw_sources = imported.pop("source_collection_slugs", None)
    if isinstance(raw_sources, list):
        imported["source_collection_ids"] = [
            str(collections_by_slug[slug].id) for slug in raw_sources if slug in collections_by_slug
        ]
    raw_providers = imported.pop("provider_slugs", None)
    if isinstance(raw_providers, list):
        imported["provider_ids"] = [
            str(providers_by_slug[slug].id) for slug in raw_providers if slug in providers_by_slug
        ]
    return imported


def import_config(
    db: Session,
    settings: Settings,
    payload: dict[str, Any],
    *,
    actor_user_id: uuid.UUID | None = None,
) -> dict[str, int]:
    """Upsert a configuration document; never delete existing data."""
    if not isinstance(payload, dict) or payload.get("version") != CONFIG_VERSION:
        raise ValidationError(
            f"Formato configurazione non supportato: attesa versione {CONFIG_VERSION}.",
            code="CONFIG_VERSION_UNSUPPORTED",
        )
    providers_payload = payload.get("providers") or []
    targets_payload = payload.get("targets") or []
    collections_payload = payload.get("collections") or []
    bindings_payload = payload.get("bindings") or []
    settings_payload = payload.get("settings") or {}
    if not all(
        isinstance(value, list)
        for value in (providers_payload, targets_payload, collections_payload, bindings_payload)
    ):
        raise ValidationError("Sezioni della configurazione non valide.", code="CONFIG_INVALID")
    if not isinstance(settings_payload, dict):
        raise ValidationError("Sezione settings non valida.", code="CONFIG_INVALID")

    providers_count = 0
    for item in providers_payload:
        slug = str(item.get("slug") or "").strip()
        name = str(item.get("name") or "").strip()
        if not slug or not name:
            raise ValidationError("Provider senza slug o nome.", code="CONFIG_INVALID")
        provider = providers_repo.upsert_provider(
            db,
            slug=slug,
            name=name,
            kind=str(item.get("kind") or "SVOD"),
            logo_url=item.get("logo_url"),
            website_url=item.get("website_url"),
        )
        providers_count += 1
        for mapping in item.get("mappings") or []:
            source_key = mapping.get("source_key")
            if not source_key:
                continue
            source = sources_repo.get_source_by_key(db, str(source_key))
            if source is None:
                continue
            providers_repo.upsert_mapping(
                db,
                provider_id=provider.id,
                source_id=source.id,
                country_code=str(mapping.get("country_code") or "IT").upper(),
                external_provider_id=str(mapping.get("external_provider_id") or ""),
                external_name=mapping.get("external_name"),
                is_primary=bool(mapping.get("is_primary", True)),
                is_verified=bool(mapping.get("is_verified", False)),
                metadata=dict(mapping.get("metadata") or {}),
            )
    db.flush()

    targets_count = 0
    for item in targets_payload:
        remote_id = item.get("remote_list_id")
        if not isinstance(remote_id, int):
            raise ValidationError("Target senza remote_list_id.", code="CONFIG_INVALID")
        targets_repo.upsert_target(
            db,
            remote_list_id=remote_id,
            name=str(item.get("name") or f"Lista {remote_id}"),
            mediatype=str(item.get("mediatype") or "MOVIE"),
            remote_slug=item.get("remote_slug"),
            remote_url=item.get("remote_url"),
            is_private=bool(item.get("is_private", False)),
            item_count=item.get("item_count"),
        )
        targets_count += 1
    db.flush()

    providers_by_slug = {provider.slug: provider for provider in providers_repo.list_providers(db)}
    # First pass: create/update collection rows without cross-references.
    collections_count = 0
    for item in collections_payload:
        slug = str(item.get("slug") or "").strip()
        provider_slug = item.get("provider_slug")
        source_key = item.get("source_key")
        if not slug or not provider_slug or not source_key:
            raise ValidationError(
                "Collezione senza slug, provider o source_key.",
                code="CONFIG_INVALID",
            )
        provider_row = providers_by_slug.get(str(provider_slug))
        source = sources_repo.get_source_by_key(db, str(source_key))
        if provider_row is None or source is None:
            raise ValidationError(
                f"Provider o fonte non trovati per la collezione '{slug}'.",
                code="CONFIG_INVALID",
            )
        collections_repo.upsert_collection(
            db,
            slug=slug,
            source_id=source.id,
            provider_id=provider_row.id,
            country_code=str(item.get("country_code") or "IT").upper(),
            media_type=str(item.get("media_type") or "MOVIE"),
            kind=str(item.get("kind") or "CATALOG"),
            origin=str(item.get("origin") or "AGGREGATOR"),
            date_basis=str(item.get("date_basis") or "UNKNOWN"),
            name=str(item.get("name") or slug),
            description=item.get("description"),
            source_collection_key=item.get("source_collection_key"),
            source_url=item.get("source_url"),
            offer_types=list(item.get("offer_types") or ["FLATRATE"]),
            filters={},
            quality_flags=dict(item.get("quality_flags") or {}),
            sort_mode=str(item.get("sort_mode") or "POPULARITY"),
            is_active=bool(item.get("is_active", True)),
        )
        collections_count += 1
    db.flush()

    collections_by_slug = {
        collection.slug: collection for collection in db.scalars(select(Collection)).all()
    }
    # Second pass: resolve cross-references by slug.
    for item in collections_payload:
        slug = str(item.get("slug") or "")
        collection = collections_by_slug.get(slug)
        if collection is None:
            continue
        collection.filters = _import_filters(
            dict(item.get("filters") or {}),
            collections_by_slug=collections_by_slug,
            providers_by_slug=providers_by_slug,
        )
    db.flush()

    bindings_count = 0
    for item in bindings_payload:
        collection = collections_by_slug.get(str(item.get("collection_slug") or ""))
        remote_id = item.get("target_remote_list_id")
        target = (
            targets_repo.get_by_remote_list_id(db, int(remote_id))
            if isinstance(remote_id, int)
            else None
        )
        if collection is None or target is None:
            raise ValidationError(
                "Binding con collezione o target non risolvibile.",
                code="CONFIG_INVALID",
            )
        binding = bindings_repo.get_by_collection_target(
            db, collection_id=collection.id, target_id=target.id
        )
        enabled = bool(item.get("is_enabled", False))
        policy_version = item.get("policy_version")
        if enabled and not policy_version:
            policy_version = "planning-v1"
        accepted_at = utcnow() if enabled else None
        interval = item.get("schedule_interval_hours")
        schedule_cron = "" if interval else str(item.get("schedule_cron") or "")
        next_run_at = None
        raw_next = item.get("next_run_at")
        if isinstance(raw_next, str) and raw_next:
            try:
                next_run_at = ensure_utc(datetime.fromisoformat(raw_next))
            except ValueError:
                next_run_at = None
        if enabled and next_run_at is None:
            if interval:
                next_run_at = utcnow() + timedelta(hours=int(interval))
            elif schedule_cron:
                next_run_at = compute_next_run_at(
                    schedule_cron, str(item.get("timezone") or "Europe/Rome")
                )
        values = {
            "media_type": collection.media_type,
            "mode": str(item.get("mode") or "MIRROR"),
            "schedule_cron": schedule_cron,
            "schedule_interval_hours": int(interval) if interval else None,
            "timezone": str(item.get("timezone") or "Europe/Rome"),
            "is_enabled": enabled,
            "policy_version": policy_version,
            "policy_accepted_at": accepted_at,
            "policy_accepted_by": actor_user_id if enabled else None,
            "max_removal_absolute": int(item.get("max_removal_absolute", 50)),
            "max_removal_percent": float(item.get("max_removal_percent", 10)),
            "max_addition_percent": float(item.get("max_addition_percent", 50)),
            "preserve_order": bool(item.get("preserve_order", False)),
            "reorder_enabled": bool(item.get("reorder_enabled", True)),
            "require_manual_review": bool(item.get("require_manual_review", True)),
            "schedule_policy": str(item.get("schedule_policy") or "AUTO_APPLY_IF_SAFE"),
            "auto_apply_max_removals": int(item.get("auto_apply_max_removals", 5)),
            "auto_apply_max_removal_ratio": float(item.get("auto_apply_max_removal_ratio", 2.0)),
            "max_plan_age_minutes": int(item.get("max_plan_age_minutes", 60)),
            "next_run_at": next_run_at,
        }
        if binding is None:
            bindings_repo.create_binding(
                db,
                collection_id=collection.id,
                target_id=target.id,
                **values,
            )
        else:
            for key, value in values.items():
                setattr(binding, key, value)
        bindings_count += 1
    db.flush()

    settings_count = 0
    for key, value in settings_payload.items():
        spec = settings_repo.SETTING_SPECS.get(str(key))
        if spec is None:
            continue
        try:
            settings_repo.set_value(
                db, spec.key, settings_repo.coerce_value(spec, value), updated_by=actor_user_id
            )
            settings_count += 1
        except settings_repo.InvalidSettingValueError as exc:
            raise ValidationError(
                f"Impostazione non valida '{key}': {exc}",
                code="CONFIG_INVALID",
            ) from exc
    db.flush()

    audit.record(
        db,
        action="config_imported",
        entity_type="app_config",
        entity_id="json",
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={
            "providers": providers_count,
            "targets": targets_count,
            "collections": collections_count,
            "bindings": bindings_count,
            "settings": settings_count,
        },
    )
    db.commit()
    return {
        "providers": providers_count,
        "targets": targets_count,
        "collections": collections_count,
        "bindings": bindings_count,
        "settings": settings_count,
    }
