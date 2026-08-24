-- AirAlert Monitor — schemat bazy (PostgreSQL 16 + PostGIS)
-- Retencja i polityka prywatności: docs/06-retencja-i-prywatnosc.md

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============ ŹRÓDŁA ============
CREATE TABLE sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    source_type     TEXT NOT NULL CHECK (source_type IN
                        ('official_government','official_military','verified_media',
                         'telegram','osint_channel','unverified')),
    country         TEXT NOT NULL DEFAULT 'PL',           -- PL | UA | other
    url             TEXT NOT NULL,
    ingest_kind     TEXT NOT NULL DEFAULT 'rss',          -- rss | html | manual | webhook
    trust_tier      INT  NOT NULL CHECK (trust_tier BETWEEN 1 AND 5), -- 1=najwyższy
    requires_manual_approval BOOLEAN NOT NULL DEFAULT false,
    enabled         BOOLEAN NOT NULL DEFAULT true,
    fetch_interval_s INT NOT NULL DEFAULT 120,
    rate_limit_per_min INT NOT NULL DEFAULT 30,
    domain_pin      TEXT,                                  -- oczekiwana domena (anti-spoofing)
    last_success_at TIMESTAMPTZ,
    last_failure_at TIMESTAMPTZ,
    last_error      TEXT,
    consecutive_failures INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============ SUROWE KOMUNIKATY (kopia audytowa, niezmienialna) ============
CREATE TABLE raw_messages (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id     UUID NOT NULL REFERENCES sources(id),
    external_id   TEXT NOT NULL,                 -- guid/link wpisu u źródła
    url           TEXT,
    published_at  TIMESTAMPTZ,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_hash  TEXT NOT NULL,                 -- sha256 znormalizowanej treści
    raw_payload   JSONB NOT NULL,                -- surowa kopia (audyt)
    ingest_status TEXT NOT NULL DEFAULT 'new'    -- new | normalized | rejected
                  CHECK (ingest_status IN ('new','normalized','rejected')),
    reject_reason TEXT,
    UNIQUE (source_id, external_id)
);
CREATE INDEX idx_raw_messages_fetched ON raw_messages (fetched_at DESC);

-- ============ ZDARZENIA (model kanoniczny) ============
CREATE TABLE events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type          TEXT NOT NULL DEFAULT 'unknown'
                        CHECK (event_type IN ('air_alert','missile_activity',
                              'aircraft_scramble','airspace_incident','explosion',
                              'infrastructure_threat','exercise','weather','unknown')),
    severity            TEXT NOT NULL DEFAULT 'informational'
                        CHECK (severity IN ('informational','low','moderate','high','critical')),
    urgency             TEXT NOT NULL DEFAULT 'routine'
                        CHECK (urgency IN ('routine','elevated','urgent','immediate')),
    confidence          NUMERIC(3,2) NOT NULL DEFAULT 0 CHECK (confidence BETWEEN 0 AND 1),
    verification_status TEXT NOT NULL DEFAULT 'unverified'
                        CHECK (verification_status IN ('unverified','single_source',
                               'corroborated','officially_confirmed')),
    language            TEXT NOT NULL DEFAULT 'pl' CHECK (language IN ('pl','uk','en','other')),
    title               TEXT NOT NULL,
    original_text       TEXT NOT NULL,
    translated_text     TEXT,
    published_at        TIMESTAMPTZ NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    alert_level         TEXT NOT NULL DEFAULT 'green'
                        CHECK (alert_level IN ('green','yellow','orange','red')),
    alert_level_basis   JSONB NOT NULL DEFAULT '[]',   -- jawna podstawa klasyfikacji
    confidence_breakdown JSONB NOT NULL DEFAULT '{}',  -- sposób wyliczenia score

    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('pending_review','active','resolved',
                                          'superseded','retracted')),
    dedup_key           TEXT,                          -- hash kanoniczny do szybkiego porównania
    red_requires_operator BOOLEAN NOT NULL DEFAULT false,
    superseded_by       UUID REFERENCES events(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_change_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_published ON events (published_at DESC);
CREATE INDEX idx_events_level_status ON events (alert_level, status) WHERE status = 'active';
CREATE INDEX idx_events_dedup ON events (dedup_key);
CREATE INDEX idx_events_fts ON events USING gin (to_tsvector('simple', title || ' ' || original_text));

-- ============ LOKALIZACJE ZDARZEŃ ============
CREATE TABLE event_locations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id     UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    country      TEXT NOT NULL DEFAULT 'PL',
    voivodeship  TEXT,                    -- kod TERC / nazwa urzędowa
    powiat       TEXT,
    geom         GEOMETRY(Point, 4326),   -- TYLKO dla precision city/approximate i obiektów cywilnych
    precision    TEXT NOT NULL CHECK (precision IN ('country','region','city','approximate'))
);

-- ============ POWIĄZANIA ZDARZENIE <-> SUROWY KOMUNIKAT ============
CREATE TABLE event_sources (
    event_id        UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    raw_message_id  UUID NOT NULL REFERENCES raw_messages(id),
    role            TEXT NOT NULL DEFAULT 'primary'  -- primary | corroborating | conflicting | retraction
                    CHECK (role IN ('primary','corroborating','conflicting','retraction')),
    added_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, raw_message_id)
);

-- ============ HISTORIA STATUSÓW ============
CREATE TABLE status_history (
    id          BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,               -- event | global
    entity_id   UUID,                        -- NULL dla global
    old_level   TEXT,
    new_level   TEXT,
    reason      TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'system',  -- system | operator:<name>
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_status_history_entity ON status_history (entity_type, entity_id, changed_at DESC);

-- ============ DZIENNIK AUDYTU (append-only) ============
CREATE TABLE audit_log (
    id         BIGSERIAL PRIMARY KEY,
    at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    entity     TEXT NOT NULL,
    entity_id  TEXT,
    before     JSONB,
    after      JSONB
);

-- ============ POWIADOMIENIA ============
CREATE TABLE push_subscriptions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_encrypted BYTEA NOT NULL,           -- FCM/APNs token, szyfrowany (AES-GCM)
    platform       TEXT NOT NULL CHECK (platform IN ('android','ios','web')),
    voivodeships   TEXT[] NOT NULL DEFAULT '{}',
    min_level      TEXT NOT NULL DEFAULT 'orange'
                   CHECK (min_level IN ('yellow','orange','red')),
    official_only  BOOLEAN NOT NULL DEFAULT true,
    muted          BOOLEAN NOT NULL DEFAULT false,
    locale         TEXT NOT NULL DEFAULT 'pl',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE notification_log (
    id            BIGSERIAL PRIMARY KEY,
    subscription_id UUID NOT NULL REFERENCES push_subscriptions(id) ON DELETE CASCADE,
    event_id      UUID REFERENCES events(id),
    sent_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    style         TEXT NOT NULL DEFAULT 'silent'  -- silent | loud
                  CHECK (style IN ('silent','loud')),
    merge_window_key TEXT                        -- np. "mazowieckie:2026-08-23T17:35"
);

-- ============ ZGŁOSZENIA UŻYTKOWNIKÓW (anonimowe) ============
CREATE TABLE user_reports (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id   UUID REFERENCES events(id),
    category   TEXT NOT NULL CHECK (category IN ('wrong_classification','wrong_location','stale','other')),
    message    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============ KONFIGURACJA / STAN GLOBALNY ============
CREATE TABLE global_state (
    id           INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    global_level TEXT NOT NULL DEFAULT 'green'
                 CHECK (global_level IN ('green','yellow','orange','red')),
    level_basis  JSONB NOT NULL DEFAULT '[]',
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO global_state (id) VALUES (1) ON CONFLICT DO NOTHING;
