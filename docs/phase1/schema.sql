-- ============================================================
-- MdbUP — schema PostgreSQL di riferimento (Fase 1)
-- ============================================================
-- Questo file è un DDL di progettazione, non una migrazione Alembic.
-- La migrazione 0001_initial di Fase 2 sarà generata da SQLAlchemy/Alembic
-- e dovrà produrre uno schema equivalente.
--
-- Convenzioni:
-- - timestamp sempre TIMESTAMPTZ (UTC); la UI mostra Europe/Rome;
-- - enum tramite TEXT + CHECK (più facili da evolvere delle enum PG);
-- - UUID con gen_random_uuid();
-- - nessun titolo usato come chiave;
-- - film e serie separati da media_type.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- ------------------------------------------------------------
-- Utenti, sessioni, impostazioni
-- ------------------------------------------------------------

CREATE TABLE app_user (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           CITEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    is_admin        BOOLEAN NOT NULL DEFAULT TRUE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ
);

CREATE TABLE session (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    token_hash      BYTEA NOT NULL UNIQUE,
    csrf_hash       BYTEA NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ,
    ip              INET,
    user_agent      TEXT
);
CREATE INDEX session_user_idx ON session (user_id);
CREATE INDEX session_expires_idx ON session (expires_at);

CREATE TABLE app_setting (
    key             TEXT PRIMARY KEY,
    value           JSONB NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by      UUID REFERENCES app_user(id)
);

-- ------------------------------------------------------------
-- Fonti, credenziali, provider
-- ------------------------------------------------------------

CREATE TABLE source (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key                 TEXT NOT NULL UNIQUE,
    name                TEXT NOT NULL,
    type                TEXT NOT NULL CHECK (type IN ('API', 'DATA_EXPORT', 'MANUAL_CSV')),
    base_url            TEXT,
    config              JSONB NOT NULL DEFAULT '{}'::jsonb,
    capabilities        JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_official         BOOLEAN NOT NULL DEFAULT FALSE,
    origin_default      TEXT NOT NULL DEFAULT 'AGGREGATOR'
                        CHECK (origin_default IN ('OFFICIAL', 'AGGREGATOR', 'CUSTOM')),
    requires_contract   BOOLEAN NOT NULL DEFAULT FALSE,
    status              TEXT NOT NULL DEFAULT 'UNCONFIGURED'
                        CHECK (status IN ('UNCONFIGURED', 'OK', 'DEGRADED', 'ERROR', 'DISABLED')),
    status_message      TEXT,
    last_healthcheck_at TIMESTAMPTZ,
    last_success_at     TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (NOT is_official OR origin_default = 'OFFICIAL')
);

CREATE TABLE credential (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope           TEXT NOT NULL CHECK (scope IN ('SOURCE', 'TARGET', 'SYSTEM')),
    source_id       UUID REFERENCES source(id) ON DELETE CASCADE,
    key             TEXT NOT NULL,
    ciphertext      BYTEA NOT NULL,
    nonce           BYTEA NOT NULL,
    algorithm       TEXT NOT NULL DEFAULT 'AES-256-GCM',
    key_version     SMALLINT NOT NULL,
    masked_hint     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at    TIMESTAMPTZ,
    last_verified_at TIMESTAMPTZ,
    CHECK (scope <> 'SOURCE' OR source_id IS NOT NULL),
    CHECK (scope = 'SOURCE' OR source_id IS NULL),
    UNIQUE NULLS NOT DISTINCT (scope, source_id, key)
);

CREATE TABLE provider (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL DEFAULT 'SVOD'
                    CHECK (kind IN ('SVOD', 'TVOD', 'AVOD', 'TVE', 'STORE', 'CINEMA', 'CHANNEL')),
    logo_url        TEXT,
    website_url     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE provider_mapping (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id         UUID NOT NULL REFERENCES provider(id) ON DELETE CASCADE,
    source_id           UUID NOT NULL REFERENCES source(id) ON DELETE CASCADE,
    country_code        CHAR(2) NOT NULL,
    external_provider_id TEXT NOT NULL,
    external_name       TEXT,
    is_primary          BOOLEAN NOT NULL DEFAULT FALSE,
    is_verified         BOOLEAN NOT NULL DEFAULT FALSE,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, country_code, external_provider_id)
);
CREATE INDEX provider_mapping_provider_idx ON provider_mapping (provider_id, country_code);
CREATE UNIQUE INDEX provider_mapping_one_primary
    ON provider_mapping (provider_id, source_id, country_code) WHERE is_primary = TRUE;

-- ------------------------------------------------------------
-- Media e disponibilità
-- ------------------------------------------------------------

CREATE TABLE media (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    media_type          TEXT NOT NULL CHECK (media_type IN ('MOVIE', 'SHOW')),
    tmdb_id             BIGINT,
    imdb_id             TEXT,
    tvdb_id             BIGINT,
    trakt_id            BIGINT,
    title               TEXT NOT NULL,
    original_title      TEXT,
    release_year        SMALLINT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    resolution_status   TEXT NOT NULL DEFAULT 'RESOLVED'
                        CHECK (resolution_status IN ('RESOLVED', 'UNRESOLVED', 'AMBIGUOUS')),
    not_found_count     INTEGER NOT NULL DEFAULT 0,
    sync_suppressed_until TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (tmdb_id IS NOT NULL OR imdb_id IS NOT NULL OR tvdb_id IS NOT NULL OR trakt_id IS NOT NULL),
    UNIQUE (id, media_type)
);
CREATE UNIQUE INDEX media_tmdb_uq ON media (tmdb_id, media_type) WHERE tmdb_id IS NOT NULL;
CREATE UNIQUE INDEX media_imdb_uq ON media (imdb_id, media_type) WHERE imdb_id IS NOT NULL;
CREATE INDEX media_title_idx ON media (title);

CREATE TABLE availability (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    media_id            UUID NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    provider_id         UUID NOT NULL REFERENCES provider(id),
    country_code        CHAR(2) NOT NULL,
    offer_type          TEXT NOT NULL CHECK (offer_type IN ('FLATRATE', 'RENT', 'BUY', 'ADS', 'FREE')),
    presentation_type   TEXT,
    channel             TEXT,
    plan                TEXT,
    source_id           UUID NOT NULL REFERENCES source(id),
    source_offer_id     TEXT,
    source_date_created DATE,
    first_seen_at       TIMESTAMPTZ NOT NULL,
    last_seen_at        TIMESTAMPTZ NOT NULL,
    last_checked_at     TIMESTAMPTZ NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE NULLS NOT DISTINCT (
        media_id, provider_id, country_code, offer_type,
        presentation_type, channel, plan, source_id
    )
);
CREATE INDEX availability_lookup_idx
    ON availability (provider_id, country_code, offer_type, is_active);
CREATE INDEX availability_media_idx ON availability (media_id);

-- ------------------------------------------------------------
-- Collezioni e snapshot
-- ------------------------------------------------------------

CREATE TABLE collection (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                    TEXT NOT NULL UNIQUE,
    source_id               UUID NOT NULL REFERENCES source(id),
    provider_id             UUID NOT NULL REFERENCES provider(id),
    country_code            CHAR(2) NOT NULL DEFAULT 'IT',
    media_type              TEXT NOT NULL CHECK (media_type IN ('MOVIE', 'SHOW')),
    kind                    TEXT NOT NULL
                            CHECK (kind IN ('CATALOG', 'RECENTLY_ADDED', 'UPCOMING', 'CHART', 'CUSTOM_FILTER')),
    origin                  TEXT NOT NULL CHECK (origin IN ('OFFICIAL', 'AGGREGATOR', 'CUSTOM')),
    date_basis              TEXT NOT NULL
                            CHECK (date_basis IN ('PROVIDER_OFFICIAL', 'AGGREGATOR_FIRST_SEEN', 'APP_FIRST_SEEN', 'UNKNOWN')),
    name                    TEXT NOT NULL,
    description             TEXT,
    source_collection_key   TEXT,
    source_url              TEXT,
    offer_types             TEXT[] NOT NULL DEFAULT ARRAY['FLATRATE'],
    filters                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_flags           JSONB NOT NULL DEFAULT '{}'::jsonb,
    sort_mode               TEXT NOT NULL DEFAULT 'SOURCE_ORDER'
                            CHECK (sort_mode IN ('SOURCE_ORDER', 'POPULARITY', 'TITLE', 'RELEASE_DATE', 'ADDED_DATE', 'CUSTOM')),
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    last_valid_snapshot_id  UUID,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, media_type)
);
CREATE INDEX collection_provider_idx ON collection (provider_id, country_code, media_type);
CREATE INDEX collection_origin_idx ON collection (origin, kind);
CREATE UNIQUE INDEX collection_source_key_uq
    ON collection (source_id, provider_id, country_code, media_type, kind, source_collection_key)
    WHERE source_collection_key IS NOT NULL;

CREATE TABLE job_execution (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         TEXT UNIQUE,
    task_name       TEXT NOT NULL,
    queue           TEXT NOT NULL,
    status          TEXT NOT NULL
                    CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'RETRY', 'CANCELLED')),
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    result          JSONB,
    error_code      TEXT,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX job_execution_status_idx ON job_execution (status, created_at);

CREATE TABLE collection_snapshot (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id       UUID NOT NULL REFERENCES collection(id) ON DELETE CASCADE,
    status              TEXT NOT NULL
                        CHECK (status IN ('RUNNING', 'COMPLETE', 'INCOMPLETE', 'FAILED', 'CANCELLED')),
    quality             TEXT NOT NULL DEFAULT 'CLEAN'
                        CHECK (quality IN ('CLEAN', 'WARNINGS', 'ANOMALY')),
    is_valid            BOOLEAN NOT NULL DEFAULT FALSE,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,
    pages_expected      INTEGER,
    pages_fetched       INTEGER NOT NULL DEFAULT 0,
    items_count         INTEGER NOT NULL DEFAULT 0,
    resolved_count      INTEGER NOT NULL DEFAULT 0,
    unresolved_count    INTEGER NOT NULL DEFAULT 0,
    duplicate_count     INTEGER NOT NULL DEFAULT 0,
    error_count         INTEGER NOT NULL DEFAULT 0,
    errors              JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings            JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_revision     TEXT,
    checksum            TEXT,
    invalid_reason      TEXT,
    job_execution_id    UUID REFERENCES job_execution(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (quality <> 'CLEAN' OR unresolved_count = 0),
    CHECK (NOT is_valid OR (
        status = 'COMPLETE'
        AND quality = 'CLEAN'
        AND items_count > 0
        AND error_count = 0
        AND unresolved_count = 0
    ))
);
CREATE UNIQUE INDEX snapshot_one_running_uq
    ON collection_snapshot (collection_id) WHERE status = 'RUNNING';
CREATE INDEX snapshot_collection_idx ON collection_snapshot (collection_id, started_at DESC);

ALTER TABLE collection
    ADD CONSTRAINT collection_last_valid_snapshot_fk
    FOREIGN KEY (last_valid_snapshot_id) REFERENCES collection_snapshot(id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE snapshot_item (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id         UUID NOT NULL REFERENCES collection_snapshot(id) ON DELETE CASCADE,
    media_id            UUID REFERENCES media(id),
    position            INTEGER NOT NULL,
    source_item_id      TEXT,
    source_payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_date_created DATE,
    date_basis          TEXT NOT NULL
                        CHECK (date_basis IN ('PROVIDER_OFFICIAL', 'AGGREGATOR_FIRST_SEEN', 'APP_FIRST_SEEN', 'UNKNOWN')),
    resolution_status   TEXT NOT NULL
                        CHECK (resolution_status IN ('RESOLVED', 'UNRESOLVED', 'AMBIGUOUS')),
    resolution_error    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, position)
);
CREATE UNIQUE INDEX snapshot_item_media_uq
    ON snapshot_item (snapshot_id, media_id) WHERE media_id IS NOT NULL;
CREATE INDEX snapshot_item_media_idx ON snapshot_item (media_id);

-- ------------------------------------------------------------
-- Target MDBList e sincronizzazione
-- ------------------------------------------------------------

CREATE TABLE mdblist_target (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    remote_list_id      BIGINT NOT NULL UNIQUE,
    remote_slug         TEXT NOT NULL,
    remote_url          TEXT,
    name                TEXT NOT NULL,
    mediatype           TEXT NOT NULL CHECK (mediatype IN ('MOVIE', 'SHOW', 'SEASON', 'EPISODE')),
    is_private          BOOLEAN NOT NULL DEFAULT FALSE,
    item_count          INTEGER,
    last_verified_at    TIMESTAMPTZ,
    last_remote_read_at TIMESTAMPTZ,
    capabilities        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, mediatype)
);

CREATE TABLE sync_binding (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id           UUID NOT NULL,
    target_id               UUID NOT NULL,
    media_type              TEXT NOT NULL CHECK (media_type IN ('MOVIE', 'SHOW')),
    mode                    TEXT NOT NULL CHECK (mode IN ('MIRROR', 'APPEND_ONLY')),
    schedule_cron           TEXT NOT NULL,
    timezone                TEXT NOT NULL DEFAULT 'Europe/Rome',
    is_enabled              BOOLEAN NOT NULL DEFAULT FALSE,
    policy_version          TEXT,
    policy_accepted_at      TIMESTAMPTZ,
    policy_accepted_by      UUID REFERENCES app_user(id),
    max_removal_absolute    INTEGER NOT NULL DEFAULT 50,
    max_removal_percent     NUMERIC(5,2) NOT NULL DEFAULT 10.00,
    max_addition_percent    NUMERIC(5,2) NOT NULL DEFAULT 50.00,
    preserve_order          BOOLEAN NOT NULL DEFAULT FALSE,
    reorder_enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    require_manual_review   BOOLEAN NOT NULL DEFAULT TRUE,
    schedule_policy         TEXT NOT NULL DEFAULT 'AUTO_APPLY_IF_SAFE'
                            CHECK (schedule_policy IN ('AUTO_APPLY_IF_SAFE', 'ALWAYS_APPROVE', 'DRY_RUN_ONLY')),
    auto_apply_max_removals INTEGER NOT NULL DEFAULT 5,
    auto_apply_max_removal_ratio NUMERIC(5,2) NOT NULL DEFAULT 2.00,
    max_plan_age_minutes    INTEGER NOT NULL DEFAULT 60,
    last_run_id             UUID,
    next_run_at             TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (collection_id, target_id),
    UNIQUE (id, media_type),
    FOREIGN KEY (collection_id, media_type) REFERENCES collection(id, media_type) ON DELETE CASCADE,
    FOREIGN KEY (target_id, media_type) REFERENCES mdblist_target(id, mediatype) ON DELETE CASCADE,
    CHECK (max_removal_absolute >= 0),
    CHECK (max_removal_percent >= 0 AND max_removal_percent <= 100),
    CHECK (max_addition_percent >= 0 AND max_addition_percent <= 100),
    CHECK (NOT is_enabled OR (policy_accepted_at IS NOT NULL AND policy_version IS NOT NULL))
);
CREATE UNIQUE INDEX binding_one_active_target_uq
    ON sync_binding (target_id) WHERE is_enabled = TRUE;
CREATE INDEX binding_due_idx
    ON sync_binding (next_run_at) WHERE is_enabled = TRUE;

CREATE TABLE sync_run (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    binding_id          UUID NOT NULL,
    target_id           UUID NOT NULL,
    media_type          TEXT NOT NULL CHECK (media_type IN ('MOVIE', 'SHOW')),
    snapshot_id         UUID NOT NULL REFERENCES collection_snapshot(id),
    mode                TEXT NOT NULL CHECK (mode IN ('MIRROR', 'APPEND_ONLY')),
    status              TEXT NOT NULL
                        CHECK (status IN ('PENDING', 'PREFLIGHT', 'PLANNING', 'AWAITING_APPROVAL',
                                          'APPLYING', 'VERIFYING', 'SUCCEEDED', 'PARTIAL',
                                          'FAILED', 'BLOCKED', 'CANCELLED')),
    is_dry_run          BOOLEAN NOT NULL DEFAULT FALSE,
    trigger             TEXT NOT NULL CHECK (trigger IN ('MANUAL', 'SCHEDULED', 'RETRY')),
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    source_item_count   INTEGER NOT NULL DEFAULT 0,
    remote_item_count   INTEGER NOT NULL DEFAULT 0,
    to_add_count        INTEGER NOT NULL DEFAULT 0,
    to_remove_count     INTEGER NOT NULL DEFAULT 0,
    added_count         INTEGER NOT NULL DEFAULT 0,
    removed_count       INTEGER NOT NULL DEFAULT 0,
    failed_count        INTEGER NOT NULL DEFAULT 0,
    uncertain_count     INTEGER NOT NULL DEFAULT 0,
    threshold_breached  BOOLEAN NOT NULL DEFAULT FALSE,
    requires_approval   BOOLEAN NOT NULL DEFAULT FALSE,
    approved_at         TIMESTAMPTZ,
    approved_by         UUID REFERENCES app_user(id),
    plan_hash           TEXT,
    snapshot_hash       TEXT,
    order_enforced      BOOLEAN NOT NULL DEFAULT FALSE,
    warnings            JSONB NOT NULL DEFAULT '[]'::jsonb,
    parent_run_id       UUID REFERENCES sync_run(id),
    not_before          TIMESTAMPTZ,
    abort_reason        TEXT,
    correlation_id      UUID NOT NULL DEFAULT gen_random_uuid(),
    error_code          TEXT,
    error_message       TEXT,
    summary             JSONB NOT NULL DEFAULT '{}'::jsonb,
    lock_key            TEXT,
    requested_by        UUID REFERENCES app_user(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (binding_id, media_type) REFERENCES sync_binding(id, media_type) ON DELETE CASCADE,
    FOREIGN KEY (target_id, media_type) REFERENCES mdblist_target(id, mediatype),
    CHECK (NOT is_dry_run OR (added_count = 0 AND removed_count = 0)),
    CHECK (status NOT IN ('SUCCEEDED', 'PARTIAL', 'FAILED', 'BLOCKED', 'CANCELLED') OR finished_at IS NOT NULL)
);
CREATE UNIQUE INDEX run_one_active_binding_uq
    ON sync_run (binding_id)
    WHERE status IN ('PENDING', 'PREFLIGHT', 'PLANNING', 'AWAITING_APPROVAL', 'APPLYING', 'VERIFYING');
CREATE UNIQUE INDEX run_one_active_target_uq
    ON sync_run (target_id)
    WHERE status IN ('PENDING', 'PREFLIGHT', 'PLANNING', 'AWAITING_APPROVAL', 'APPLYING', 'VERIFYING');
CREATE INDEX run_binding_idx ON sync_run (binding_id, created_at DESC);

ALTER TABLE sync_binding
    ADD CONSTRAINT sync_binding_last_run_fk
    FOREIGN KEY (last_run_id) REFERENCES sync_run(id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE sync_operation (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID NOT NULL REFERENCES sync_run(id) ON DELETE CASCADE,
    batch_id            UUID,
    action              TEXT NOT NULL CHECK (action IN ('ADD', 'REMOVE', 'REORDER')),
    media_id            UUID REFERENCES media(id),
    remote_id           TEXT,
    idempotency_key     TEXT NOT NULL UNIQUE,
    status              TEXT NOT NULL
                        CHECK (status IN ('PENDING', 'IN_FLIGHT', 'SUCCEEDED', 'FAILED', 'UNCERTAIN', 'SKIPPED')),
    attempt             INTEGER NOT NULL DEFAULT 0,
    max_attempts        INTEGER NOT NULL DEFAULT 5,
    next_retry_at       TIMESTAMPTZ,
    reconciled_at       TIMESTAMPTZ,
    http_status         INTEGER,
    duration_ms         INTEGER,
    request_hash        TEXT,
    response            JSONB,
    error_code          TEXT,
    error_message       TEXT,
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (action = 'REORDER' OR media_id IS NOT NULL),
    UNIQUE (run_id, action, media_id)
);
CREATE INDEX sync_operation_run_idx ON sync_operation (run_id, status);
CREATE INDEX sync_operation_batch_idx ON sync_operation (batch_id);

CREATE TABLE sync_run_event (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES sync_run(id) ON DELETE CASCADE,
    from_status     TEXT,
    to_status       TEXT NOT NULL,
    message         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX sync_run_event_run_idx ON sync_run_event (run_id, created_at);

-- ------------------------------------------------------------
-- Eventi stagioni/episodi (senza duplicare la serie)
-- ------------------------------------------------------------

CREATE TABLE episode_event (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    show_media_id       UUID NOT NULL,
    media_type          TEXT NOT NULL DEFAULT 'SHOW' CHECK (media_type = 'SHOW'),
    provider_id         UUID NOT NULL REFERENCES provider(id),
    country_code        CHAR(2) NOT NULL,
    source_id           UUID NOT NULL REFERENCES source(id),
    snapshot_id         UUID REFERENCES collection_snapshot(id),
    event_type          TEXT NOT NULL
                        CHECK (event_type IN ('SEASON_ADDED', 'SEASON_REMOVED', 'EPISODE_ADDED', 'EPISODE_REMOVED')),
    season_number       INTEGER NOT NULL,
    episode_number      INTEGER,
    occurred_at         TIMESTAMPTZ,
    source_payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (show_media_id, media_type) REFERENCES media(id, media_type) ON DELETE CASCADE,
    UNIQUE NULLS NOT DISTINCT (
        show_media_id, provider_id, country_code, source_id,
        event_type, season_number, episode_number
    )
);
CREATE INDEX episode_event_show_idx ON episode_event (show_media_id, occurred_at DESC);

-- ------------------------------------------------------------
-- Audit e healthcheck
-- ------------------------------------------------------------

CREATE TABLE audit_log (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_user_id   UUID REFERENCES app_user(id),
    actor_type      TEXT NOT NULL CHECK (actor_type IN ('USER', 'SYSTEM', 'SCHEDULER')),
    action          TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_id       TEXT,
    before          JSONB,
    after           JSONB,
    ip              INET,
    user_agent      TEXT,
    request_id      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audit_entity_idx ON audit_log (entity_type, entity_id, created_at DESC);
CREATE INDEX audit_created_idx ON audit_log (created_at DESC);

CREATE TABLE source_healthcheck (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id       UUID NOT NULL REFERENCES source(id) ON DELETE CASCADE,
    status          TEXT NOT NULL,
    latency_ms      INTEGER,
    message         TEXT,
    details         JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX source_healthcheck_source_idx ON source_healthcheck (source_id, checked_at DESC);

-- ------------------------------------------------------------
-- Trigger e guardie di integrità
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'app_user', 'source', 'credential', 'provider', 'provider_mapping',
        'media', 'collection', 'mdblist_target', 'sync_binding', 'sync_run',
        'sync_operation', 'app_setting', 'job_execution'
    ]
    LOOP
        EXECUTE format(
            'CREATE TRIGGER %I_touch BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at()',
            t, t
        );
    END LOOP;
END;
$$;

-- OFFICIAL solo da una fonte ufficiale; AGGREGATOR solo da una fonte aggregatore.
CREATE OR REPLACE FUNCTION enforce_collection_origin() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    src_official boolean;
    src_origin text;
BEGIN
    SELECT is_official, origin_default INTO src_official, src_origin
    FROM source WHERE id = NEW.source_id;

    IF NEW.origin = 'OFFICIAL' AND NOT COALESCE(src_official, false) THEN
        RAISE EXCEPTION 'collection %: origine OFFICIAL richiede una fonte ufficiale', NEW.slug;
    END IF;

    IF NEW.origin = 'AGGREGATOR' AND src_origin IS DISTINCT FROM 'AGGREGATOR' THEN
        RAISE EXCEPTION 'collection %: origine AGGREGATOR richiede una fonte aggregatore', NEW.slug;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER collection_origin_guard
BEFORE INSERT OR UPDATE OF origin, source_id ON collection
FOR EACH ROW EXECUTE FUNCTION enforce_collection_origin();

-- Un sync_run può usare solo uno snapshot della stessa collezione,
-- dello stesso media type e con completezza sufficiente.
CREATE OR REPLACE FUNCTION enforce_sync_run_snapshot() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    snap_collection uuid;
    snap_status text;
    snap_valid boolean;
    snap_items integer;
    bind_collection uuid;
    bind_target uuid;
    bind_media_type text;
BEGIN
    SELECT collection_id, status, is_valid, items_count
    INTO snap_collection, snap_status, snap_valid, snap_items
    FROM collection_snapshot WHERE id = NEW.snapshot_id;

    SELECT collection_id, target_id, media_type
    INTO bind_collection, bind_target, bind_media_type
    FROM sync_binding WHERE id = NEW.binding_id;

    IF snap_collection IS DISTINCT FROM bind_collection THEN
        RAISE EXCEPTION 'sync_run: snapshot % non appartiene alla collezione del binding', NEW.snapshot_id;
    END IF;

    IF NEW.target_id IS DISTINCT FROM bind_target THEN
        RAISE EXCEPTION 'sync_run: target % diverso dal target del binding', NEW.target_id;
    END IF;

    IF NEW.media_type IS DISTINCT FROM bind_media_type THEN
        RAISE EXCEPTION 'sync_run: media_type % diverso dal binding', NEW.media_type;
    END IF;

    IF NEW.mode IS DISTINCT FROM (SELECT mode FROM sync_binding WHERE id = NEW.binding_id) THEN
        RAISE EXCEPTION 'sync_run: mode % diverso dal binding', NEW.mode;
    END IF;

    IF snap_status = 'RUNNING' THEN
        RAISE EXCEPTION 'sync_run: snapshot % ancora in esecuzione', NEW.snapshot_id;
    END IF;

    IF NEW.mode = 'MIRROR' AND NOT COALESCE(snap_valid, false) THEN
        RAISE EXCEPTION 'sync_run: snapshot % non valido per MIRROR', NEW.snapshot_id;
    END IF;

    IF NEW.mode = 'APPEND_ONLY' AND (snap_status <> 'COMPLETE' OR snap_items = 0) THEN
        RAISE EXCEPTION 'sync_run: snapshot % incompleto o vuoto per APPEND_ONLY', NEW.snapshot_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER sync_run_snapshot_guard
BEFORE INSERT OR UPDATE OF snapshot_id, binding_id, target_id, media_type, mode ON sync_run
FOR EACH ROW EXECUTE FUNCTION enforce_sync_run_snapshot();

-- Un'operazione ADD/REMOVE deve riferirsi a un media dello stesso tipo del run.
CREATE OR REPLACE FUNCTION enforce_sync_operation_media_type() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    run_type text;
    media_type text;
BEGIN
    IF NEW.action = 'REORDER' THEN
        RETURN NEW;
    END IF;

    SELECT media_type INTO run_type FROM sync_run WHERE id = NEW.run_id;
    SELECT media_type INTO media_type FROM media WHERE id = NEW.media_id;

    IF media_type IS DISTINCT FROM run_type THEN
        RAISE EXCEPTION 'sync_operation: media % non coerente con il media_type del run', NEW.media_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER sync_operation_media_type_guard
BEFORE INSERT OR UPDATE OF run_id, media_id, action ON sync_operation
FOR EACH ROW EXECUTE FUNCTION enforce_sync_operation_media_type();

-- audit_log append-only.
CREATE OR REPLACE FUNCTION reject_audit_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log è append-only';
END;
$$;

CREATE TRIGGER audit_log_append_only
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();
