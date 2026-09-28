"""
Genomics Data API - a real, runnable Flask REST/JSON API over a real SQLite
clinical genomics database (see db/schema.sql, db/seed_data.py).

Run directly:
    python3 app/main.py

Endpoints are organized by resource: patients, samples, sequencing_runs,
variants, variant_annotations, clinical_reports, workflows/workflow_runs,
plus search, bulk-export, auth, health/status, and audit-log endpoints.
See docs/endpoints.md for the full documented list (45 endpoints).
"""
import sqlite3
import time

from flask import Flask, jsonify, request, g

from app.db import get_connection, row_to_dict, rows_to_list

app = Flask(__name__)

APP_START_TIME = time.time()


# ---------------------------------------------------------------------------
# Audit logging: every request is recorded to access_log (the audit trail).
# ---------------------------------------------------------------------------
@app.before_request
def start_timer():
    g._start = time.time()


@app.after_request
def log_access(response):
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO access_log (username, endpoint, method, resource_id, status_code) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                request.headers.get("X-User", "anonymous"),
                request.path,
                request.method,
                request.view_args.get("id") if request.view_args else None,
                response.status_code,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # audit logging must never break the API response
    return response


def paginate_args():
    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 20)), 1), 200)
    except ValueError:
        page, per_page = 1, 20
    return page, per_page


def not_found(resource):
    return jsonify({"error": f"{resource} not found"}), 404


# ===========================================================================
# 1-2. Health / status
# ===========================================================================
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/status", methods=["GET"])
def status():
    conn = get_connection()
    counts = {}
    for table in ["patients", "samples", "sequencing_runs", "variants", "clinical_reports"]:
        counts[table] = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
    conn.close()
    return jsonify({
        "status": "running",
        "uptime_seconds": round(time.time() - APP_START_TIME, 2),
        "row_counts": counts,
    })


# ===========================================================================
# 3-8. Patients
# ===========================================================================
@app.route("/api/patients", methods=["GET"])
def list_patients():
    page, per_page = paginate_args()
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) AS c FROM patients").fetchone()["c"]
    rows = conn.execute(
        "SELECT * FROM patients ORDER BY patient_id LIMIT ? OFFSET ?",
        (per_page, (page - 1) * per_page),
    ).fetchall()
    conn.close()
    return jsonify({"page": page, "per_page": per_page, "total": total, "items": rows_to_list(rows)})


@app.route("/api/patients", methods=["POST"])
def create_patient():
    data = request.get_json(force=True, silent=True) or {}
    required = ["mrn", "first_name", "last_name", "date_of_birth", "sex"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"missing fields: {missing}"}), 400
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO patients (mrn, first_name, last_name, date_of_birth, sex, ethnicity, diagnosis) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (data["mrn"], data["first_name"], data["last_name"], data["date_of_birth"],
             data["sex"], data.get("ethnicity"), data.get("diagnosis")),
        )
        conn.commit()
        new_id = cur.lastrowid
    except sqlite3.IntegrityError as e:
        conn.close()
        return jsonify({"error": str(e)}), 409
    row = conn.execute("SELECT * FROM patients WHERE patient_id = ?", (new_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201


@app.route("/api/patients/<int:id>", methods=["GET"])
def get_patient(id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM patients WHERE patient_id = ?", (id,)).fetchone()
    conn.close()
    if row is None:
        return not_found("patient")
    return jsonify(row_to_dict(row))


@app.route("/api/patients/<int:id>", methods=["PUT"])
def update_patient(id):
    data = request.get_json(force=True, silent=True) or {}
    conn = get_connection()
    row = conn.execute("SELECT * FROM patients WHERE patient_id = ?", (id,)).fetchone()
    if row is None:
        conn.close()
        return not_found("patient")
    fields = ["first_name", "last_name", "date_of_birth", "sex", "ethnicity", "diagnosis"]
    updates = {f: data[f] for f in fields if f in data}
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE patients SET {set_clause} WHERE patient_id = ?", (*updates.values(), id))
        conn.commit()
    row = conn.execute("SELECT * FROM patients WHERE patient_id = ?", (id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))


@app.route("/api/patients/<int:id>", methods=["DELETE"])
def delete_patient(id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM patients WHERE patient_id = ?", (id,)).fetchone()
    if row is None:
        conn.close()
        return not_found("patient")
    conn.execute("DELETE FROM patients WHERE patient_id = ?", (id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/patients/<int:id>/samples", methods=["GET"])
def patient_samples(id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM samples WHERE patient_id = ? ORDER BY sample_id", (id,)).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


# ===========================================================================
# 9-14. Samples
# ===========================================================================
@app.route("/api/samples", methods=["GET"])
def list_samples():
    page, per_page = paginate_args()
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) AS c FROM samples").fetchone()["c"]
    rows = conn.execute(
        "SELECT * FROM samples ORDER BY sample_id LIMIT ? OFFSET ?",
        (per_page, (page - 1) * per_page),
    ).fetchall()
    conn.close()
    return jsonify({"page": page, "per_page": per_page, "total": total, "items": rows_to_list(rows)})


@app.route("/api/samples", methods=["POST"])
def create_sample():
    data = request.get_json(force=True, silent=True) or {}
    required = ["patient_id", "sample_type", "collection_date"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"missing fields: {missing}"}), 400
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO samples (patient_id, sample_type, collection_date, tissue_site, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (data["patient_id"], data["sample_type"], data["collection_date"],
             data.get("tissue_site"), data.get("status", "received")),
        )
        conn.commit()
        new_id = cur.lastrowid
    except sqlite3.IntegrityError as e:
        conn.close()
        return jsonify({"error": str(e)}), 409
    row = conn.execute("SELECT * FROM samples WHERE sample_id = ?", (new_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201


@app.route("/api/samples/<int:id>", methods=["GET"])
def get_sample(id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM samples WHERE sample_id = ?", (id,)).fetchone()
    conn.close()
    if row is None:
        return not_found("sample")
    return jsonify(row_to_dict(row))


@app.route("/api/samples/<int:id>", methods=["PUT"])
def update_sample(id):
    data = request.get_json(force=True, silent=True) or {}
    conn = get_connection()
    row = conn.execute("SELECT * FROM samples WHERE sample_id = ?", (id,)).fetchone()
    if row is None:
        conn.close()
        return not_found("sample")
    fields = ["sample_type", "collection_date", "tissue_site", "status"]
    updates = {f: data[f] for f in fields if f in data}
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE samples SET {set_clause} WHERE sample_id = ?", (*updates.values(), id))
        conn.commit()
    row = conn.execute("SELECT * FROM samples WHERE sample_id = ?", (id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))


@app.route("/api/samples/<int:id>", methods=["DELETE"])
def delete_sample(id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM samples WHERE sample_id = ?", (id,)).fetchone()
    if row is None:
        conn.close()
        return not_found("sample")
    conn.execute("DELETE FROM samples WHERE sample_id = ?", (id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/samples/<int:id>/sequencing_runs", methods=["GET"])
def sample_sequencing_runs(id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM sequencing_runs WHERE sample_id = ? ORDER BY run_id", (id,)).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


# ===========================================================================
# 15-20. Sequencing runs
# ===========================================================================
@app.route("/api/sequencing_runs", methods=["GET"])
def list_sequencing_runs():
    page, per_page = paginate_args()
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) AS c FROM sequencing_runs").fetchone()["c"]
    rows = conn.execute(
        "SELECT * FROM sequencing_runs ORDER BY run_id LIMIT ? OFFSET ?",
        (per_page, (page - 1) * per_page),
    ).fetchall()
    conn.close()
    return jsonify({"page": page, "per_page": per_page, "total": total, "items": rows_to_list(rows)})


@app.route("/api/sequencing_runs", methods=["POST"])
def create_sequencing_run():
    data = request.get_json(force=True, silent=True) or {}
    required = ["sample_id", "platform", "assay_type", "run_date"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"missing fields: {missing}"}), 400
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO sequencing_runs (sample_id, platform, assay_type, run_date, coverage_depth, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (data["sample_id"], data["platform"], data["assay_type"], data["run_date"],
             data.get("coverage_depth"), data.get("status", "queued")),
        )
        conn.commit()
        new_id = cur.lastrowid
    except sqlite3.IntegrityError as e:
        conn.close()
        return jsonify({"error": str(e)}), 409
    row = conn.execute("SELECT * FROM sequencing_runs WHERE run_id = ?", (new_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201


@app.route("/api/sequencing_runs/<int:id>", methods=["GET"])
def get_sequencing_run(id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM sequencing_runs WHERE run_id = ?", (id,)).fetchone()
    conn.close()
    if row is None:
        return not_found("sequencing_run")
    return jsonify(row_to_dict(row))


@app.route("/api/sequencing_runs/<int:id>", methods=["PUT"])
def update_sequencing_run(id):
    data = request.get_json(force=True, silent=True) or {}
    conn = get_connection()
    row = conn.execute("SELECT * FROM sequencing_runs WHERE run_id = ?", (id,)).fetchone()
    if row is None:
        conn.close()
        return not_found("sequencing_run")
    fields = ["platform", "assay_type", "run_date", "coverage_depth", "status"]
    updates = {f: data[f] for f in fields if f in data}
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE sequencing_runs SET {set_clause} WHERE run_id = ?", (*updates.values(), id))
        conn.commit()
    row = conn.execute("SELECT * FROM sequencing_runs WHERE run_id = ?", (id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))


@app.route("/api/sequencing_runs/<int:id>", methods=["DELETE"])
def delete_sequencing_run(id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM sequencing_runs WHERE run_id = ?", (id,)).fetchone()
    if row is None:
        conn.close()
        return not_found("sequencing_run")
    conn.execute("DELETE FROM sequencing_runs WHERE run_id = ?", (id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/sequencing_runs/<int:id>/variants", methods=["GET"])
def run_variants(id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM variants WHERE run_id = ? ORDER BY variant_id", (id,)).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


# ===========================================================================
# 21-25. Variants (query/filter/pagination + CRUD)
# ===========================================================================
@app.route("/api/variants", methods=["GET"])
def list_variants():
    page, per_page = paginate_args()
    conn = get_connection()
    clauses, params = [], []
    if gene := request.args.get("gene_symbol"):
        clauses.append("gene_symbol = ?")
        params.append(gene)
    if chrom := request.args.get("chromosome"):
        clauses.append("chromosome = ?")
        params.append(chrom)
    if vtype := request.args.get("variant_type"):
        clauses.append("variant_type = ?")
        params.append(vtype)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = conn.execute(f"SELECT COUNT(*) AS c FROM variants {where}", params).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM variants {where} ORDER BY variant_id LIMIT ? OFFSET ?",
        (*params, per_page, (page - 1) * per_page),
    ).fetchall()
    conn.close()
    return jsonify({"page": page, "per_page": per_page, "total": total, "items": rows_to_list(rows)})


@app.route("/api/variants", methods=["POST"])
def create_variant():
    data = request.get_json(force=True, silent=True) or {}
    required = ["run_id", "chromosome", "position", "ref_allele", "alt_allele", "variant_type"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"missing fields: {missing}"}), 400
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO variants (run_id, chromosome, position, ref_allele, alt_allele, "
            "gene_symbol, variant_type, zygosity, allele_frequency) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (data["run_id"], data["chromosome"], data["position"], data["ref_allele"], data["alt_allele"],
             data.get("gene_symbol"), data["variant_type"], data.get("zygosity"), data.get("allele_frequency")),
        )
        conn.commit()
        new_id = cur.lastrowid
    except sqlite3.IntegrityError as e:
        conn.close()
        return jsonify({"error": str(e)}), 409
    row = conn.execute("SELECT * FROM variants WHERE variant_id = ?", (new_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201


@app.route("/api/variants/<int:id>", methods=["GET"])
def get_variant(id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM variants WHERE variant_id = ?", (id,)).fetchone()
    conn.close()
    if row is None:
        return not_found("variant")
    return jsonify(row_to_dict(row))


@app.route("/api/variants/<int:id>", methods=["PUT"])
def update_variant(id):
    data = request.get_json(force=True, silent=True) or {}
    conn = get_connection()
    row = conn.execute("SELECT * FROM variants WHERE variant_id = ?", (id,)).fetchone()
    if row is None:
        conn.close()
        return not_found("variant")
    fields = ["chromosome", "position", "ref_allele", "alt_allele", "gene_symbol",
              "variant_type", "zygosity", "allele_frequency"]
    updates = {f: data[f] for f in fields if f in data}
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE variants SET {set_clause} WHERE variant_id = ?", (*updates.values(), id))
        conn.commit()
    row = conn.execute("SELECT * FROM variants WHERE variant_id = ?", (id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))


@app.route("/api/variants/<int:id>", methods=["DELETE"])
def delete_variant(id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM variants WHERE variant_id = ?", (id,)).fetchone()
    if row is None:
        conn.close()
        return not_found("variant")
    conn.execute("DELETE FROM variants WHERE variant_id = ?", (id,))
    conn.commit()
    conn.close()
    return "", 204


# ===========================================================================
# 26-30. Variant annotations
# ===========================================================================
@app.route("/api/variants/<int:id>/annotations", methods=["GET"])
def list_variant_annotations(id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM variant_annotations WHERE variant_id = ? ORDER BY annotation_id", (id,)
    ).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


@app.route("/api/variants/<int:id>/annotations", methods=["POST"])
def create_variant_annotation(id):
    data = request.get_json(force=True, silent=True) or {}
    if "clinical_significance" not in data:
        return jsonify({"error": "missing field: clinical_significance"}), 400
    conn = get_connection()
    variant = conn.execute("SELECT * FROM variants WHERE variant_id = ?", (id,)).fetchone()
    if variant is None:
        conn.close()
        return not_found("variant")
    try:
        cur = conn.execute(
            "INSERT INTO variant_annotations (variant_id, clinical_significance, condition, "
            "source_db, review_status) VALUES (?, ?, ?, ?, ?)",
            (id, data["clinical_significance"], data.get("condition"),
             data.get("source_db", "ClinVar"), data.get("review_status")),
        )
        conn.commit()
        new_id = cur.lastrowid
    except sqlite3.IntegrityError as e:
        conn.close()
        return jsonify({"error": str(e)}), 409
    row = conn.execute("SELECT * FROM variant_annotations WHERE annotation_id = ?", (new_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201


@app.route("/api/annotations/<int:id>", methods=["GET"])
def get_annotation(id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM variant_annotations WHERE annotation_id = ?", (id,)).fetchone()
    conn.close()
    if row is None:
        return not_found("annotation")
    return jsonify(row_to_dict(row))


@app.route("/api/annotations/<int:id>", methods=["PUT"])
def update_annotation(id):
    data = request.get_json(force=True, silent=True) or {}
    conn = get_connection()
    row = conn.execute("SELECT * FROM variant_annotations WHERE annotation_id = ?", (id,)).fetchone()
    if row is None:
        conn.close()
        return not_found("annotation")
    fields = ["clinical_significance", "condition", "source_db", "review_status"]
    updates = {f: data[f] for f in fields if f in data}
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE variant_annotations SET {set_clause} WHERE annotation_id = ?", (*updates.values(), id))
        conn.commit()
    row = conn.execute("SELECT * FROM variant_annotations WHERE annotation_id = ?", (id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))


@app.route("/api/annotations/<int:id>", methods=["DELETE"])
def delete_annotation(id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM variant_annotations WHERE annotation_id = ?", (id,)).fetchone()
    if row is None:
        conn.close()
        return not_found("annotation")
    conn.execute("DELETE FROM variant_annotations WHERE annotation_id = ?", (id,))
    conn.commit()
    conn.close()
    return "", 204


# ===========================================================================
# 31-36. Clinical reports
# ===========================================================================
@app.route("/api/reports", methods=["GET"])
def list_reports():
    page, per_page = paginate_args()
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) AS c FROM clinical_reports").fetchone()["c"]
    rows = conn.execute(
        "SELECT * FROM clinical_reports ORDER BY report_id LIMIT ? OFFSET ?",
        (per_page, (page - 1) * per_page),
    ).fetchall()
    conn.close()
    return jsonify({"page": page, "per_page": per_page, "total": total, "items": rows_to_list(rows)})


@app.route("/api/reports", methods=["POST"])
def create_report():
    data = request.get_json(force=True, silent=True) or {}
    required = ["patient_id", "sample_id"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"missing fields: {missing}"}), 400
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO clinical_reports (patient_id, sample_id, summary, report_status, signed_by) "
            "VALUES (?, ?, ?, ?, ?)",
            (data["patient_id"], data["sample_id"], data.get("summary"),
             data.get("report_status", "draft"), data.get("signed_by")),
        )
        conn.commit()
        new_id = cur.lastrowid
    except sqlite3.IntegrityError as e:
        conn.close()
        return jsonify({"error": str(e)}), 409
    row = conn.execute("SELECT * FROM clinical_reports WHERE report_id = ?", (new_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201


@app.route("/api/reports/<int:id>", methods=["GET"])
def get_report(id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM clinical_reports WHERE report_id = ?", (id,)).fetchone()
    conn.close()
    if row is None:
        return not_found("report")
    return jsonify(row_to_dict(row))


@app.route("/api/reports/<int:id>", methods=["PUT"])
def update_report(id):
    data = request.get_json(force=True, silent=True) or {}
    conn = get_connection()
    row = conn.execute("SELECT * FROM clinical_reports WHERE report_id = ?", (id,)).fetchone()
    if row is None:
        conn.close()
        return not_found("report")
    fields = ["summary", "report_status", "signed_by"]
    updates = {f: data[f] for f in fields if f in data}
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE clinical_reports SET {set_clause} WHERE report_id = ?", (*updates.values(), id))
        conn.commit()
    row = conn.execute("SELECT * FROM clinical_reports WHERE report_id = ?", (id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))


@app.route("/api/reports/<int:id>", methods=["DELETE"])
def delete_report(id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM clinical_reports WHERE report_id = ?", (id,)).fetchone()
    if row is None:
        conn.close()
        return not_found("report")
    conn.execute("DELETE FROM clinical_reports WHERE report_id = ?", (id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/reports/<int:id>/finalize", methods=["POST"])
def finalize_report(id):
    data = request.get_json(force=True, silent=True) or {}
    conn = get_connection()
    row = conn.execute("SELECT * FROM clinical_reports WHERE report_id = ?", (id,)).fetchone()
    if row is None:
        conn.close()
        return not_found("report")
    conn.execute(
        "UPDATE clinical_reports SET report_status = 'finalized', signed_by = ?, "
        "finalized_at = datetime('now') WHERE report_id = ?",
        (data.get("signed_by", "unspecified"), id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM clinical_reports WHERE report_id = ?", (id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))


# ===========================================================================
# 37-41. Workflows + workflow runs
# ===========================================================================
@app.route("/api/workflows", methods=["GET"])
def list_workflows():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM workflows ORDER BY workflow_id").fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


@app.route("/api/workflows/<int:id>", methods=["GET"])
def get_workflow(id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM workflows WHERE workflow_id = ?", (id,)).fetchone()
    conn.close()
    if row is None:
        return not_found("workflow")
    return jsonify(row_to_dict(row))


@app.route("/api/workflows/<int:id>/trigger", methods=["POST"])
def trigger_workflow(id):
    data = request.get_json(force=True, silent=True) or {}
    conn = get_connection()
    workflow = conn.execute("SELECT * FROM workflows WHERE workflow_id = ?", (id,)).fetchone()
    if workflow is None:
        conn.close()
        return not_found("workflow")
    cur = conn.execute(
        "INSERT INTO workflow_runs (workflow_id, sample_id, patient_id, status, triggered_by) "
        "VALUES (?, ?, ?, 'triggered', ?)",
        (id, data.get("sample_id"), data.get("patient_id"), data.get("triggered_by", "api_user")),
    )
    conn.commit()
    new_id = cur.lastrowid
    row = conn.execute("SELECT * FROM workflow_runs WHERE workflow_run_id = ?", (new_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201


@app.route("/api/workflows/<int:id>/runs", methods=["GET"])
def workflow_runs_for_workflow(id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM workflow_runs WHERE workflow_id = ? ORDER BY workflow_run_id", (id,)
    ).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


@app.route("/api/workflow_runs/<int:id>", methods=["GET"])
def get_workflow_run(id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM workflow_runs WHERE workflow_run_id = ?", (id,)).fetchone()
    conn.close()
    if row is None:
        return not_found("workflow_run")
    return jsonify(row_to_dict(row))


# ===========================================================================
# 42-45. Search, bulk export, auth stub, audit log
# ===========================================================================
@app.route("/api/search", methods=["GET"])
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "missing query param 'q'"}), 400
    like = f"%{q}%"
    conn = get_connection()
    patients = conn.execute(
        "SELECT patient_id, mrn, first_name, last_name FROM patients "
        "WHERE mrn LIKE ? OR first_name LIKE ? OR last_name LIKE ? LIMIT 20",
        (like, like, like),
    ).fetchall()
    genes = conn.execute(
        "SELECT variant_id, gene_symbol, chromosome, position FROM variants "
        "WHERE gene_symbol LIKE ? LIMIT 20",
        (like,),
    ).fetchall()
    conn.close()
    return jsonify({"patients": rows_to_list(patients), "variants": rows_to_list(genes)})


@app.route("/api/export/patient/<int:id>", methods=["GET"])
def export_patient(id):
    """Bulk export: full genomic record for one patient, joined across
    samples -> sequencing_runs -> variants -> variant_annotations, plus reports.
    This is the 'genomic data access' query used in the latency benchmark."""
    conn = get_connection()
    patient = conn.execute("SELECT * FROM patients WHERE patient_id = ?", (id,)).fetchone()
    if patient is None:
        conn.close()
        return not_found("patient")

    samples = conn.execute("SELECT * FROM samples WHERE patient_id = ?", (id,)).fetchall()
    sample_export = []
    for s in samples:
        runs = conn.execute("SELECT * FROM sequencing_runs WHERE sample_id = ?", (s["sample_id"],)).fetchall()
        run_export = []
        for r in runs:
            variants = conn.execute("SELECT * FROM variants WHERE run_id = ?", (r["run_id"],)).fetchall()
            variant_export = []
            for v in variants:
                annos = conn.execute(
                    "SELECT * FROM variant_annotations WHERE variant_id = ?", (v["variant_id"],)
                ).fetchall()
                vd = dict(v)
                vd["annotations"] = rows_to_list(annos)
                variant_export.append(vd)
            rd = dict(r)
            rd["variants"] = variant_export
            run_export.append(rd)
        sd = dict(s)
        sd["sequencing_runs"] = run_export
        sample_export.append(sd)

    reports = conn.execute("SELECT * FROM clinical_reports WHERE patient_id = ?", (id,)).fetchall()
    conn.close()

    result = dict(patient)
    result["samples"] = sample_export
    result["clinical_reports"] = rows_to_list(reports)
    return jsonify(result)


@app.route("/api/auth/login", methods=["POST"])
def login():
    """Auth stub: validates a username exists against the users table and
    returns a fake bearer token. No real password hashing/session mgmt --
    this demonstrates the endpoint shape, not a production auth system."""
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username")
    if not username:
        return jsonify({"error": "missing field: username"}), 400
    conn = get_connection()
    user = conn.execute("SELECT user_id, username, role FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if user is None:
        return jsonify({"error": "invalid credentials"}), 401
    return jsonify({"token": f"stub-token-for-{user['username']}", "role": user["role"]})


@app.route("/api/audit-log", methods=["GET"])
def audit_log():
    page, per_page = paginate_args()
    conn = get_connection()
    clauses, params = [], []
    if username := request.args.get("username"):
        clauses.append("username = ?")
        params.append(username)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = conn.execute(f"SELECT COUNT(*) AS c FROM access_log {where}", params).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM access_log {where} ORDER BY log_id DESC LIMIT ? OFFSET ?",
        (*params, per_page, (page - 1) * per_page),
    ).fetchall()
    conn.close()
    return jsonify({"page": page, "per_page": per_page, "total": total, "items": rows_to_list(rows)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
