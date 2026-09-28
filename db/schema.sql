-- Genomics Data API - relational schema (SQLite)
-- Represents a simplified clinical genomics data warehouse:
-- patients -> samples -> sequencing_runs -> variants -> variant_annotations
-- plus clinical_reports, workflows/workflow_runs, users, and an access_log audit trail.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS patients (
    patient_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    mrn             TEXT UNIQUE NOT NULL,          -- medical record number
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    date_of_birth   TEXT NOT NULL,
    sex             TEXT NOT NULL CHECK (sex IN ('M', 'F', 'U')),
    ethnicity       TEXT,
    diagnosis       TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS samples (
    sample_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      INTEGER NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    sample_type     TEXT NOT NULL CHECK (sample_type IN ('blood', 'saliva', 'tumor', 'tissue', 'plasma')),
    collection_date TEXT NOT NULL,
    tissue_site     TEXT,
    status          TEXT NOT NULL DEFAULT 'received'
                    CHECK (status IN ('received', 'processing', 'sequenced', 'failed', 'archived')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sequencing_runs (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id       INTEGER NOT NULL REFERENCES samples(sample_id) ON DELETE CASCADE,
    platform        TEXT NOT NULL CHECK (platform IN ('Illumina NovaSeq', 'PacBio Revio', 'Oxford Nanopore', 'Ion Torrent')),
    assay_type      TEXT NOT NULL CHECK (assay_type IN ('WGS', 'WES', 'targeted_panel', 'RNA-seq')),
    run_date        TEXT NOT NULL,
    coverage_depth  REAL,
    status          TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'running', 'complete', 'failed')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS variants (
    variant_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES sequencing_runs(run_id) ON DELETE CASCADE,
    chromosome      TEXT NOT NULL,
    position        INTEGER NOT NULL,
    ref_allele      TEXT NOT NULL,
    alt_allele      TEXT NOT NULL,
    gene_symbol     TEXT,
    variant_type    TEXT NOT NULL CHECK (variant_type IN ('SNV', 'insertion', 'deletion', 'CNV', 'fusion')),
    zygosity        TEXT CHECK (zygosity IN ('heterozygous', 'homozygous', 'hemizygous')),
    allele_frequency REAL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS variant_annotations (
    annotation_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    variant_id          INTEGER NOT NULL REFERENCES variants(variant_id) ON DELETE CASCADE,
    clinical_significance TEXT NOT NULL
                    CHECK (clinical_significance IN ('pathogenic', 'likely_pathogenic', 'VUS', 'likely_benign', 'benign')),
    condition           TEXT,
    source_db           TEXT DEFAULT 'ClinVar',
    review_status        TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clinical_reports (
    report_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      INTEGER NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    sample_id       INTEGER NOT NULL REFERENCES samples(sample_id) ON DELETE CASCADE,
    summary         TEXT,
    report_status   TEXT NOT NULL DEFAULT 'draft'
                    CHECK (report_status IN ('draft', 'pending_review', 'finalized', 'amended')),
    signed_by       TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finalized_at    TEXT
);

CREATE TABLE IF NOT EXISTS workflows (
    workflow_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT UNIQUE NOT NULL,
    description     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    workflow_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id     INTEGER NOT NULL REFERENCES workflows(workflow_id) ON DELETE CASCADE,
    sample_id       INTEGER REFERENCES samples(sample_id) ON DELETE SET NULL,
    patient_id      INTEGER REFERENCES patients(patient_id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'triggered'
                    CHECK (status IN ('triggered', 'in_progress', 'complete', 'failed')),
    triggered_by    TEXT,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('admin', 'clinician', 'lab_tech', 'analyst')),
    password_hash   TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS access_log (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT,
    endpoint        TEXT NOT NULL,
    method          TEXT NOT NULL,
    resource_id     TEXT,
    status_code     INTEGER,
    accessed_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_samples_patient ON samples(patient_id);
CREATE INDEX IF NOT EXISTS idx_runs_sample ON sequencing_runs(sample_id);
CREATE INDEX IF NOT EXISTS idx_variants_run ON variants(run_id);
CREATE INDEX IF NOT EXISTS idx_variants_gene ON variants(gene_symbol);
CREATE INDEX IF NOT EXISTS idx_annotations_variant ON variant_annotations(variant_id);
CREATE INDEX IF NOT EXISTS idx_reports_patient ON clinical_reports(patient_id);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow ON workflow_runs(workflow_id);
CREATE INDEX IF NOT EXISTS idx_access_log_username ON access_log(username);
