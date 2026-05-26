-- TimescaleDB initialization for audit_entries hypertable
-- Run AFTER Alembic migrations have created the tables.
-- This script is intended for docker-entrypoint-initdb.d or manual execution.

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Convert audit_entries to hypertable (partitioned by created_at, 1-day chunks)
-- Table must already exist (created by Alembic migration 001_v2_initial)
SELECT create_hypertable(
    'audit_entries',
    'created_at',
    chunk_time_interval => INTERVAL '1 day',
    migrate_data => TRUE
);

-- Compression settings for efficient storage of older audit data
ALTER TABLE audit_entries SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'shot_card_id',
    timescaledb.compress_orderby = 'created_at DESC'
);

-- Auto-compress audit entries older than 7 days
SELECT add_compression_policy('audit_entries', INTERVAL '7 days');

-- Retention policy: drop chunks older than 30 days (hot tier rolling window)
SELECT add_retention_policy('audit_entries', INTERVAL '30 days');

-- Create indexes (idempotent -- Alembic may have already created these)
CREATE INDEX IF NOT EXISTS ix_audit_shot_created
    ON audit_entries (shot_card_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_action_created
    ON audit_entries (action, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_actor_created
    ON audit_entries (actor, created_at DESC);

-- Audit immutability trigger: prevent UPDATE and DELETE on audit_entries
CREATE OR REPLACE FUNCTION enforce_audit_immutability()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_entries table is immutable: % operations are not permitted', TG_OP;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_immutability ON audit_entries;
CREATE TRIGGER trg_audit_immutability
    BEFORE UPDATE OR DELETE ON audit_entries
    FOR EACH ROW
    EXECUTE FUNCTION enforce_audit_immutability();
