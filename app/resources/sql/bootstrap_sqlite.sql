CREATE TABLE IF NOT EXISTS meta_bank_files (
    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'bank',
    import_batch_id TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'imported'
);

CREATE TABLE IF NOT EXISTS meta_bank_sheets (
    sheet_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    sheet_name TEXT NOT NULL,
    header_row_no INTEGER NOT NULL DEFAULT 1,
    template_fingerprint TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'bank',
    raw_table_name TEXT NOT NULL,
    rows_imported INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meta_schema_registry (
    schema_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_name TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'bank',
    template_fingerprint TEXT NOT NULL,
    template_version INTEGER NOT NULL DEFAULT 1,
    sheet_name TEXT NOT NULL,
    raw_table_name TEXT NOT NULL,
    schema_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_mapping',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (template_fingerprint, template_version)
);

CREATE TABLE IF NOT EXISTS meta_field_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_fingerprint TEXT NOT NULL,
    raw_field_name TEXT NOT NULL,
    std_field_name TEXT NOT NULL,
    transform_rule TEXT NOT NULL DEFAULT 'identity',
    priority INTEGER NOT NULL DEFAULT 100,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (template_fingerprint, raw_field_name, std_field_name)
);

CREATE TABLE IF NOT EXISTS meta_desc_template (
    template_id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_tag TEXT NOT NULL UNIQUE,
    template_text TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meta_ingest_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS std_bank_txn (
    std_id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'bank',
    source_file_id INTEGER,
    source_sheet TEXT NOT NULL,
    template_fingerprint TEXT NOT NULL,
    person_name TEXT,
    acct_no TEXT,
    txn_time TEXT,
    txn_amount TEXT,
    currency TEXT,
    txn_direction TEXT,
    balance TEXT,
    counterparty_name TEXT,
    counterparty_account TEXT,
    summary TEXT,
    txn_org_no TEXT,
    txn_org_name TEXT,
    source_name TEXT,
    remark TEXT,
    raw_payload TEXT NOT NULL,
    standardized_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS std_bank_account (
    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'bank',
    source_file_id INTEGER,
    source_sheet TEXT NOT NULL,
    template_fingerprint TEXT NOT NULL,
    person_name TEXT,
    acct_no TEXT NOT NULL,
    id_no TEXT,
    mobile TEXT,
    open_date TEXT,
    source_name TEXT,
    raw_payload TEXT NOT NULL,
    standardized_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS std_bank_account_conflict (
    conflict_id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    acct_no TEXT NOT NULL,
    conflict_reason TEXT NOT NULL,
    conflict_payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_std_bank_txn_batch ON std_bank_txn(import_batch_id);
CREATE INDEX IF NOT EXISTS idx_std_bank_txn_acct ON std_bank_txn(bank_name, acct_no);
CREATE INDEX IF NOT EXISTS idx_std_bank_txn_time ON std_bank_txn(txn_time);
CREATE INDEX IF NOT EXISTS idx_std_bank_account_batch ON std_bank_account(import_batch_id);
CREATE INDEX IF NOT EXISTS idx_std_bank_account_bank_acct ON std_bank_account(bank_name, acct_no);
CREATE INDEX IF NOT EXISTS idx_std_bank_account_person ON std_bank_account(person_name);

CREATE TABLE IF NOT EXISTS std_enterprise_profile (
    enterprise_id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id TEXT NOT NULL,
    source_file_name TEXT NOT NULL,
    enterprise_name TEXT NOT NULL,
    enterprise_name_norm TEXT NOT NULL,
    credit_code TEXT,
    reg_status TEXT,
    legal_person TEXT,
    reg_capital TEXT,
    establish_date TEXT,
    industry TEXT,
    region TEXT,
    shareholders_json TEXT NOT NULL DEFAULT '[]',
    key_persons_json TEXT NOT NULL DEFAULT '[]',
    raw_payload TEXT NOT NULL DEFAULT '{}',
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rel_biz_enterprise_match (
    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id TEXT NOT NULL,
    inquiry_no TEXT NOT NULL DEFAULT '',
    biz_company_name TEXT NOT NULL,
    biz_company_name_norm TEXT NOT NULL,
    enterprise_id INTEGER NOT NULL,
    enterprise_name TEXT NOT NULL,
    match_score REAL NOT NULL DEFAULT 0,
    match_method TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cfg_risk_rule (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_code TEXT NOT NULL UNIQUE,
    rule_name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    weight REAL NOT NULL DEFAULT 1.0,
    params_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ana_risk_event (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id TEXT NOT NULL,
    rule_code TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'medium',
    risk_score REAL NOT NULL DEFAULT 0,
    enterprise_name TEXT NOT NULL,
    inquiry_no TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ana_risk_summary (
    summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id TEXT NOT NULL,
    enterprise_name TEXT NOT NULL,
    total_score REAL NOT NULL DEFAULT 0,
    hit_count INTEGER NOT NULL DEFAULT 0,
    risk_level TEXT NOT NULL DEFAULT 'low',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_std_enterprise_profile_batch ON std_enterprise_profile(import_batch_id);
CREATE INDEX IF NOT EXISTS idx_std_enterprise_profile_name_norm ON std_enterprise_profile(enterprise_name_norm);
CREATE INDEX IF NOT EXISTS idx_rel_biz_enterprise_match_batch ON rel_biz_enterprise_match(import_batch_id);
CREATE INDEX IF NOT EXISTS idx_rel_biz_enterprise_match_company ON rel_biz_enterprise_match(biz_company_name_norm);
CREATE INDEX IF NOT EXISTS idx_ana_risk_event_batch ON ana_risk_event(import_batch_id);
CREATE INDEX IF NOT EXISTS idx_ana_risk_summary_batch ON ana_risk_summary(import_batch_id);

INSERT OR IGNORE INTO cfg_risk_rule (rule_code, rule_name, enabled, weight, params_json, version) VALUES
('R001', '围标疑似', 1, 1.0, '{"min_shared_inquiries":3,"min_companies_together":3,"note":"同一批项目中多家企业高频共同参标"}', 1),
('R002', '串标疑似', 1, 1.0, '{"min_inquiries":3,"min_pair_overlap_ratio":0.8,"note":"企业对在多个项目中高度同步出现"}', 1),
('R003', '陪标疑似', 1, 1.0, '{"min_participations":4,"max_win_rate":0.15,"min_co_winner_hits":3,"note":"长期少中标且频繁与同一中标方同场"}', 1),
('R004', '关联关系异常', 1, 1.0, '{"note":"同一询价下匹配到的工商主体法定代表人相同"}', 1),
('R005', '报价异常', 1, 1.0, '{"min_suppliers_with_price":3,"max_cv":0.02,"note":"同一询价多家含税单价离散度过低"}', 1),
('R006', '轮流中标', 1, 1.0, '{"min_distinct_winners":3,"window_size":5,"note":"连续多单中标方在固定小集合内轮换"}', 1);
