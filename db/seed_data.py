"""
Seed the SQLite genomics database with realistic synthetic clinical genomic data.

Usage:
    python3 db/seed_data.py

Generates (fixed random seed = 42, reproducible):
    - 120 patients
    - ~220 samples
    - ~220 sequencing runs
    - ~1200 variants
    - ~1400 variant annotations
    - ~150 clinical reports
    - 12 workflows + ~300 workflow runs
    - 5 users
    - ~50 access_log rows
"""
import os
import random
import sqlite3
import datetime

random.seed(42)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "genomics.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "db", "schema.sql")

FIRST_NAMES = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
               "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
               "Thomas", "Sarah", "Charles", "Karen", "Ananya", "Wei", "Fatima", "Carlos", "Yuki"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
              "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
              "Patel", "Chen", "Kim", "Nguyen", "Khan"]
DIAGNOSES = ["Breast Cancer", "Lung Adenocarcinoma", "Cystic Fibrosis", "Hereditary Colon Cancer",
             "Li-Fraumeni Syndrome", "BRCA-related Cancer Risk", "Congenital Heart Defect",
             "Neurodevelopmental Disorder", "Familial Hypercholesterolemia", "Melanoma"]
ETHNICITIES = ["European", "African", "East Asian", "South Asian", "Hispanic/Latino", "Mixed", "Other"]
SAMPLE_TYPES = ["blood", "saliva", "tumor", "tissue", "plasma"]
TISSUE_SITES = ["breast", "lung", "colon", "skin", "blood", "liver", "brain", None]
PLATFORMS = ["Illumina NovaSeq", "PacBio Revio", "Oxford Nanopore", "Ion Torrent"]
ASSAYS = ["WGS", "WES", "targeted_panel", "RNA-seq"]
GENES = ["BRCA1", "BRCA2", "TP53", "EGFR", "KRAS", "CFTR", "APC", "MLH1", "MSH2", "PTEN",
         "RB1", "APOB", "LDLR", "MYH7", "SCN5A", "PALB2", "ATM", "CHEK2", "RET", "VHL"]
VARIANT_TYPES = ["SNV", "insertion", "deletion", "CNV", "fusion"]
ZYGOSITY = ["heterozygous", "homozygous", "hemizygous"]
CLIN_SIG = ["pathogenic", "likely_pathogenic", "VUS", "likely_benign", "benign"]
CONDITIONS = ["Hereditary Breast/Ovarian Cancer", "Lynch Syndrome", "Cystic Fibrosis",
              "Li-Fraumeni Syndrome", "Familial Hypercholesterolemia", "Long QT Syndrome", None]
ROLES = ["admin", "clinician", "lab_tech", "analyst"]

WORKFLOWS = [
    ("patient_onboarding", "Register a new patient and capture demographics/consent."),
    ("sample_intake", "Log a new biological sample and assign initial status."),
    ("sequencing_run_request", "Queue a sequencing run for a received sample."),
    ("variant_calling_request", "Trigger variant calling on a completed sequencing run."),
    ("variant_annotation_pipeline", "Annotate called variants with clinical significance."),
    ("clinical_report_generation", "Draft a clinical report from annotated variants."),
    ("report_review_and_signoff", "Route a draft report for review and finalize it."),
    ("patient_variant_lookup", "Search and retrieve all variants for a given patient."),
    ("bulk_cohort_export", "Export variant/report data for a patient cohort."),
    ("sample_reprocessing", "Re-queue a failed sample/run for reprocessing."),
    ("audit_compliance_review", "Query the access log for a compliance audit."),
    ("user_access_provisioning", "Provision a new user account with a role."),
]


def random_date(start_year=2018, end_year=2025):
    start = datetime.date(start_year, 1, 1)
    end = datetime.date(end_year, 12, 31)
    delta = (end - start).days
    return (start + datetime.timedelta(days=random.randint(0, delta))).isoformat()


def build():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())

    cur = conn.cursor()

    # ---- patients ----
    patient_ids = []
    for i in range(120):
        mrn = f"MRN-{100000 + i}"
        fn = random.choice(FIRST_NAMES)
        ln = random.choice(LAST_NAMES)
        dob = random_date(1940, 2015)
        sex = random.choice(["M", "F", "U"])
        eth = random.choice(ETHNICITIES)
        dx = random.choice(DIAGNOSES)
        cur.execute(
            "INSERT INTO patients (mrn, first_name, last_name, date_of_birth, sex, ethnicity, diagnosis) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mrn, fn, ln, dob, sex, eth, dx),
        )
        patient_ids.append(cur.lastrowid)

    # ---- samples (1-3 per patient) ----
    sample_ids = []
    sample_patient = {}
    for pid in patient_ids:
        for _ in range(random.randint(1, 3)):
            stype = random.choice(SAMPLE_TYPES)
            coll_date = random_date(2019, 2025)
            tissue = random.choice(TISSUE_SITES)
            status = random.choice(["received", "processing", "sequenced", "failed", "archived"])
            cur.execute(
                "INSERT INTO samples (patient_id, sample_type, collection_date, tissue_site, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (pid, stype, coll_date, tissue, status),
            )
            sid = cur.lastrowid
            sample_ids.append(sid)
            sample_patient[sid] = pid

    # ---- sequencing runs (1 per sample) ----
    run_ids = []
    run_sample = {}
    for sid in sample_ids:
        platform = random.choice(PLATFORMS)
        assay = random.choice(ASSAYS)
        run_date = random_date(2019, 2025)
        depth = round(random.uniform(30, 300), 1)
        status = random.choice(["queued", "running", "complete", "failed"])
        cur.execute(
            "INSERT INTO sequencing_runs (sample_id, platform, assay_type, run_date, coverage_depth, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (sid, platform, assay, run_date, depth, status),
        )
        rid = cur.lastrowid
        run_ids.append(rid)
        run_sample[rid] = sid

    # ---- variants (~5-7 per run) ----
    variant_ids = []
    for rid in run_ids:
        for _ in range(random.randint(4, 7)):
            chrom = str(random.choice(list(range(1, 23)) + ["X", "Y"]))
            pos = random.randint(100000, 249000000)
            ref = random.choice(["A", "C", "G", "T"])
            alt = random.choice(["A", "C", "G", "T"])
            gene = random.choice(GENES)
            vtype = random.choice(VARIANT_TYPES)
            zyg = random.choice(ZYGOSITY)
            af = round(random.uniform(0.001, 0.5), 4)
            cur.execute(
                "INSERT INTO variants (run_id, chromosome, position, ref_allele, alt_allele, "
                "gene_symbol, variant_type, zygosity, allele_frequency) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rid, chrom, pos, ref, alt, gene, vtype, zyg, af),
            )
            variant_ids.append(cur.lastrowid)

    # ---- variant annotations (most variants get 1, some get 0-2) ----
    for vid in variant_ids:
        n = random.choices([0, 1, 2], weights=[0.15, 0.65, 0.20])[0]
        for _ in range(n):
            sig = random.choice(CLIN_SIG)
            cond = random.choice(CONDITIONS)
            cur.execute(
                "INSERT INTO variant_annotations (variant_id, clinical_significance, condition, "
                "source_db, review_status) VALUES (?, ?, ?, ?, ?)",
                (vid, sig, cond, "ClinVar", random.choice(["reviewed", "criteria_provided", "no_assertion"])),
            )

    # ---- clinical reports (~70% of samples get a report) ----
    for sid in sample_ids:
        if random.random() < 0.7:
            pid = sample_patient[sid]
            status = random.choice(["draft", "pending_review", "finalized", "amended"])
            finalized_at = random_date(2020, 2025) if status in ("finalized", "amended") else None
            cur.execute(
                "INSERT INTO clinical_reports (patient_id, sample_id, summary, report_status, "
                "signed_by, finalized_at) VALUES (?, ?, ?, ?, ?, ?)",
                (pid, sid, f"Genomic findings summary for sample {sid}.", status,
                 random.choice(["Dr. Patel", "Dr. Nguyen", "Dr. Osei", None]), finalized_at),
            )

    # ---- workflows ----
    workflow_ids = {}
    for name, desc in WORKFLOWS:
        cur.execute("INSERT INTO workflows (name, description) VALUES (?, ?)", (name, desc))
        workflow_ids[name] = cur.lastrowid

    # ---- workflow runs (~300) ----
    wf_names = list(workflow_ids.keys())
    for _ in range(300):
        wf_name = random.choice(wf_names)
        sid = random.choice(sample_ids)
        pid = sample_patient[sid]
        status = random.choice(["triggered", "in_progress", "complete", "failed"])
        completed_at = random_date(2020, 2025) if status == "complete" else None
        cur.execute(
            "INSERT INTO workflow_runs (workflow_id, sample_id, patient_id, status, triggered_by, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (workflow_ids[wf_name], sid, pid, status, "seed_script", completed_at),
        )

    # ---- users ----
    users = [
        ("admin", "admin", "pbkdf2:sha256:seeded$admin"),
        ("dr_patel", "clinician", "pbkdf2:sha256:seeded$patel"),
        ("dr_nguyen", "clinician", "pbkdf2:sha256:seeded$nguyen"),
        ("lab_tech_1", "lab_tech", "pbkdf2:sha256:seeded$labtech1"),
        ("analyst_1", "analyst", "pbkdf2:sha256:seeded$analyst1"),
    ]
    for username, role, pw_hash in users:
        cur.execute(
            "INSERT INTO users (username, role, password_hash) VALUES (?, ?, ?)",
            (username, role, pw_hash),
        )

    # ---- access_log (~50 rows) ----
    endpoints = ["/api/patients", "/api/samples", "/api/variants", "/api/reports"]
    for _ in range(50):
        cur.execute(
            "INSERT INTO access_log (username, endpoint, method, resource_id, status_code) VALUES (?, ?, ?, ?, ?)",
            (random.choice([u[0] for u in users]), random.choice(endpoints),
             random.choice(["GET", "POST", "PUT"]), str(random.randint(1, 200)), 200),
        )

    conn.commit()

    counts = {}
    for table in ["patients", "samples", "sequencing_runs", "variants", "variant_annotations",
                  "clinical_reports", "workflows", "workflow_runs", "users", "access_log"]:
        counts[table] = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    conn.close()
    return counts


if __name__ == "__main__":
    counts = build()
    print(f"Seeded database at {DB_PATH}")
    for table, count in counts.items():
        print(f"  {table}: {count} rows")
