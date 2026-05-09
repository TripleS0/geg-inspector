CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS std;

CREATE TABLE IF NOT EXISTS meta.bank_files (
    file_id BIGSERIAL PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    import_batch_id TEXT NOT NULL,
    imported_at TIMESTAMP NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'imported'
);

CREATE TABLE IF NOT EXISTS meta.bank_sheets (
    sheet_id BIGSERIAL PRIMARY KEY,
    file_id BIGINT NOT NULL REFERENCES meta.bank_files(file_id),
    sheet_name TEXT NOT NULL,
    header_row_no INT NOT NULL DEFAULT 1,
    template_fingerprint TEXT NOT NULL,
    raw_table_name TEXT NOT NULL,
    rows_imported INT NOT NULL DEFAULT 0,
    imported_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meta.schema_registry (
    schema_id BIGSERIAL PRIMARY KEY,
    bank_name TEXT NOT NULL,
    template_fingerprint TEXT NOT NULL,
    template_version INT NOT NULL DEFAULT 1,
    sheet_name TEXT NOT NULL,
    raw_table_name TEXT NOT NULL,
    schema_json JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_mapping',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (template_fingerprint, template_version)
);

CREATE TABLE IF NOT EXISTS meta.field_mapping (
    mapping_id BIGSERIAL PRIMARY KEY,
    template_fingerprint TEXT NOT NULL,
    raw_field_name TEXT NOT NULL,
    std_field_name TEXT NOT NULL,
    transform_rule TEXT NOT NULL DEFAULT 'identity',
    priority INT NOT NULL DEFAULT 100,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (template_fingerprint, raw_field_name, std_field_name)
);

CREATE TABLE IF NOT EXISTS meta.ingest_logs (
    log_id BIGSERIAL PRIMARY KEY,
    import_batch_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS std.bank_txn (
    std_id BIGSERIAL PRIMARY KEY,
    import_batch_id TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    source_file_id BIGINT,
    source_sheet TEXT NOT NULL,
    template_fingerprint TEXT NOT NULL,
    txn_time TEXT,
    txn_amount TEXT,
    balance TEXT,
    counterparty_name TEXT,
    counterparty_account TEXT,
    summary TEXT,
    raw_payload JSONB NOT NULL,
    standardized_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bank_files_hash ON meta.bank_files(file_hash);
CREATE INDEX IF NOT EXISTS idx_bank_sheets_fp ON meta.bank_sheets(template_fingerprint);
CREATE INDEX IF NOT EXISTS idx_schema_registry_fp ON meta.schema_registry(template_fingerprint);
CREATE INDEX IF NOT EXISTS idx_field_mapping_fp ON meta.field_mapping(template_fingerprint);
CREATE INDEX IF NOT EXISTS idx_std_bank_txn_bank_time ON std.bank_txn(bank_name, standardized_at);
