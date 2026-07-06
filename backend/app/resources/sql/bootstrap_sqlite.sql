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
    template_type TEXT NOT NULL DEFAULT 'txn_detail',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (template_fingerprint, template_version)
);

CREATE TABLE IF NOT EXISTS meta_field_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_fingerprint TEXT NOT NULL,
    raw_field_name TEXT NOT NULL,
    std_field_name TEXT NOT NULL,
    template_type TEXT NOT NULL DEFAULT 'txn_detail',
    transform_rule TEXT NOT NULL DEFAULT 'identity',
    priority INTEGER NOT NULL DEFAULT 100,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (template_fingerprint, raw_field_name, std_field_name)
);

CREATE TABLE IF NOT EXISTS meta_user_bank_template (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    template_type TEXT NOT NULL,
    bank_display_name TEXT NOT NULL,
    bank_keywords_json TEXT NOT NULL,
    sheet_keywords_json TEXT NOT NULL,
    field_map_json TEXT NOT NULL,
    signature_columns_json TEXT NOT NULL DEFAULT '[]',
    header_row_0based INTEGER,
    match_priority INTEGER NOT NULL DEFAULT 0,
    template_group_id TEXT,
    direction_rules_json TEXT,
    datetime_patterns_json TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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

CREATE TABLE IF NOT EXISTS meta_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ana_task (
    task_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    result_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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

CREATE TABLE IF NOT EXISTS meta_qichacha_query_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    query_keyword TEXT NOT NULL,
    input_source TEXT NOT NULL,
    api_status TEXT,
    api_message TEXT,
    order_number TEXT,
    matched_name TEXT,
    credit_code TEXT,
    duration_ms INTEGER,
    error_detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_qichacha_log_run ON meta_qichacha_query_log(run_id);
CREATE INDEX IF NOT EXISTS idx_qichacha_log_created ON meta_qichacha_query_log(created_at DESC);

CREATE TABLE IF NOT EXISTS std_case (
    case_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rel_case_batch (
    rel_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    import_batch_id TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL DEFAULT '',
    bound_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES std_case(case_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rel_case_batch_case ON rel_case_batch(case_id);

CREATE TABLE IF NOT EXISTS meta_import_batch (
    import_batch_id TEXT PRIMARY KEY,
    batch_name TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_meta_import_batch_updated ON meta_import_batch(updated_at DESC);

CREATE TABLE IF NOT EXISTS std_person (
    person_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    display_name TEXT NOT NULL,
    role_tag TEXT NOT NULL DEFAULT 'unknown',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES std_case(case_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_std_person_case ON std_person(case_id);

CREATE TABLE IF NOT EXISTS std_person_link (
    link_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    identifier_type TEXT NOT NULL,
    identifier_value TEXT NOT NULL,
    identifier_norm TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_ref_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (person_id) REFERENCES std_person(person_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_std_person_link_person ON std_person_link(person_id);
CREATE INDEX IF NOT EXISTS idx_std_person_link_norm ON std_person_link(identifier_type, identifier_norm);

CREATE TABLE IF NOT EXISTS rel_identifier_candidate (
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    identifier_type TEXT NOT NULL,
    identifier_norm TEXT NOT NULL,
    display_value TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT '',
    source_batch_id TEXT NOT NULL DEFAULT '',
    source_ref_json TEXT NOT NULL DEFAULT '{}',
    review_status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES std_case(case_id) ON DELETE CASCADE,
    UNIQUE (case_id, identifier_type, identifier_norm)
);

CREATE INDEX IF NOT EXISTS idx_rel_identifier_candidate_case ON rel_identifier_candidate(case_id, review_status);

CREATE TABLE IF NOT EXISTS meta_ocr_job (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'ocr_running',
    bank_name TEXT NOT NULL DEFAULT '',
    batch_name TEXT NOT NULL DEFAULT '',
    layout_profile_id TEXT NOT NULL DEFAULT 'ceb_txn_v1',
    page_count INTEGER NOT NULL DEFAULT 0,
    header_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meta_ocr_page (
    page_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    page_index INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    ocr_status TEXT NOT NULL DEFAULT 'ready',
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (job_id) REFERENCES meta_ocr_job(job_id) ON DELETE CASCADE,
    UNIQUE (job_id, page_index)
);

CREATE TABLE IF NOT EXISTS meta_ocr_draft_row (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    page_index INTEGER NOT NULL DEFAULT 0,
    row_index INTEGER NOT NULL DEFAULT 0,
    cells_json TEXT NOT NULL DEFAULT '{}',
    confidence_json TEXT NOT NULL DEFAULT '{}',
    is_edited INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (job_id) REFERENCES meta_ocr_job(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_meta_ocr_job_status ON meta_ocr_job(status, created_at);
CREATE INDEX IF NOT EXISTS idx_meta_ocr_draft_row_job ON meta_ocr_draft_row(job_id, page_index, row_index);

INSERT OR IGNORE INTO meta_schema_version (version, description)
VALUES (1, 'Initial local SQLite schema with import, analysis and task tables');

INSERT OR IGNORE INTO meta_schema_version (version, description)
VALUES (2, 'Case, person linking and fusion cockpit tables');

INSERT OR IGNORE INTO meta_schema_version (version, description)
VALUES (3, 'Bank OCR draft jobs for image/PDF statement import');

CREATE TABLE IF NOT EXISTS cfg_fusion_model (
    case_id INTEGER NOT NULL,
    model_key TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    params_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (case_id, model_key),
    FOREIGN KEY (case_id) REFERENCES std_case(case_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cfg_fusion_model_case ON cfg_fusion_model(case_id);

INSERT OR IGNORE INTO meta_schema_version (version, description)
VALUES (4, 'Fusion model config per case for event management');

INSERT OR IGNORE INTO cfg_risk_rule (rule_code, rule_name, enabled, weight, params_json, version) VALUES
('R001', '围标疑似', 1, 1.0, '{"min_shared_inquiries":3,"min_companies_together":3,"note":"同一批项目中多家企业高频共同参标"}', 1),
('R002', '串标疑似', 1, 1.0, '{"min_inquiries":3,"min_pair_overlap_ratio":0.8,"note":"企业对在多个项目中高度同步出现"}', 1),
('R003', '陪标疑似', 1, 1.0, '{"min_participations":4,"max_win_rate":0.15,"min_co_winner_hits":3,"note":"长期少中标且频繁与同一中标方同场"}', 1),
('R004', '关联关系异常', 1, 1.0, '{"note":"同一询价下匹配到的工商主体法定代表人相同"}', 1),
('R005', '报价异常', 1, 1.0, '{"min_suppliers_with_price":3,"max_cv":0.02,"note":"同一询价多家含税单价离散度过低"}', 1),
('R006', '轮流中标', 1, 1.0, '{"min_distinct_winners":3,"window_size":5,"note":"连续多单中标方在固定小集合内轮换"}', 1),
('R007', '协同串标强化', 1, 1.2, '{"min_shared_inquiries":3,"min_jaccard":0.8,"min_inquiries_for_jaccard":3,"note":"围标或串标口径重叠且两企业工商法定代表人为同一人"}', 1),
('R008', '陪标关联分析', 1, 1.0, '{"min_shared_inquiries":3,"min_co_rate":0.25,"max_target_win_rate":0.15,"min_both_lose_rate":0.5,"min_other_win_rate":0.5,"min_rotating_exclusive_wins":4,"min_alternation_score":0.55,"note":"陪标关联分析页面判定阈值"}', 1);
