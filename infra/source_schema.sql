-- Owned by the setup role; runtime importers receive insert-only privileges.
CREATE SCHEMA IF NOT EXISTS kedrogy_source;
CREATE TABLE IF NOT EXISTS kedrogy_source.collection (
    id uuid CONSTRAINT source_collection_pk PRIMARY KEY,
    source_key varchar(128) NOT NULL CONSTRAINT source_collection_key UNIQUE,
    identity_policy varchar(32) NOT NULL CONSTRAINT source_identity_policy
        CHECK (identity_policy IN ('upstream-id-v1', 'content-addressed-v1')),
    CONSTRAINT source_key_nonempty CHECK (length(source_key) > 0)
);
CREATE TABLE IF NOT EXISTS kedrogy_source.record (
    id uuid CONSTRAINT source_record_pk PRIMARY KEY,
    source_id uuid NOT NULL CONSTRAINT source_record_collection REFERENCES kedrogy_source.collection(id) ON DELETE RESTRICT,
    external_key varchar(512) NOT NULL,
    text text NOT NULL,
    provenance jsonb NOT NULL,
    content_digest char(64) NOT NULL,
    CONSTRAINT source_external_key UNIQUE (source_id, external_key),
    CONSTRAINT source_record_values CHECK (length(external_key) > 0 AND length(text) > 0
        AND octet_length(text) <= 60000 AND jsonb_typeof(provenance) = 'object'
        AND content_digest ~ '^[0-9a-f]{64}$')
);
CREATE TABLE IF NOT EXISTS kedrogy_source.import_receipt (
    id uuid CONSTRAINT source_import_pk PRIMARY KEY,
    source_id uuid NOT NULL CONSTRAINT source_import_collection REFERENCES kedrogy_source.collection(id) ON DELETE RESTRICT,
    request_key varchar(128) NOT NULL,
    fingerprint char(64) NOT NULL,
    parser_version varchar(32) NOT NULL,
    identity_policy varchar(32) NOT NULL,
    input_count integer NOT NULL,
    inserted_count integer NOT NULL,
    unchanged_count integer NOT NULL,
    duplicate_count integer NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT source_import_request UNIQUE (source_id, request_key),
    CONSTRAINT source_import_counts CHECK (input_count > 0 AND inserted_count >= 0 AND unchanged_count >= 0
        AND duplicate_count >= 0 AND input_count = inserted_count + unchanged_count + duplicate_count),
    CONSTRAINT source_import_fingerprint CHECK (fingerprint ~ '^[0-9a-f]{64}$')
);
