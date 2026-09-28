"""
Real integration tests against the real Flask app + the real seeded SQLite
database, using Flask's real test client (an in-process WSGI client that
performs genuine request/response cycles, not mocked responses).

Run with:
    pytest -q
"""
import os
import sys
import time
import statistics

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Health / status
# ---------------------------------------------------------------------------
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_status(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "running"
    assert body["row_counts"]["patients"] >= 100


# ---------------------------------------------------------------------------
# Patients CRUD
# ---------------------------------------------------------------------------
def test_list_patients_pagination(client):
    r = client.get("/api/patients?page=1&per_page=10")
    assert r.status_code == 200
    body = r.get_json()
    assert body["total"] >= 100
    assert len(body["items"]) == 10
    assert "mrn" in body["items"][0]


def test_get_patient_found_and_not_found(client):
    r = client.get("/api/patients/1")
    assert r.status_code == 200
    assert r.get_json()["patient_id"] == 1

    r = client.get("/api/patients/999999")
    assert r.status_code == 404


def test_create_update_delete_patient(client):
    r = client.post("/api/patients", json={
        "mrn": "MRN-TEST-001", "first_name": "Test", "last_name": "Patient",
        "date_of_birth": "1990-01-01", "sex": "F",
    })
    assert r.status_code == 201
    pid = r.get_json()["patient_id"]

    r = client.put(f"/api/patients/{pid}", json={"diagnosis": "Updated Diagnosis"})
    assert r.status_code == 200
    assert r.get_json()["diagnosis"] == "Updated Diagnosis"

    r = client.delete(f"/api/patients/{pid}")
    assert r.status_code == 204

    r = client.get(f"/api/patients/{pid}")
    assert r.status_code == 404


def test_create_patient_missing_fields(client):
    r = client.post("/api/patients", json={"first_name": "Incomplete"})
    assert r.status_code == 400


def test_patient_samples(client):
    r = client.get("/api/patients/1/samples")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


# ---------------------------------------------------------------------------
# Samples CRUD
# ---------------------------------------------------------------------------
def test_list_and_get_sample(client):
    r = client.get("/api/samples?per_page=5")
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert len(items) == 5
    sample_id = items[0]["sample_id"]

    r = client.get(f"/api/samples/{sample_id}")
    assert r.status_code == 200
    assert r.get_json()["sample_id"] == sample_id


def test_create_sample_and_runs_link(client):
    r = client.post("/api/samples", json={
        "patient_id": 1, "sample_type": "blood", "collection_date": "2024-01-01",
    })
    assert r.status_code == 201
    sid = r.get_json()["sample_id"]

    r = client.get(f"/api/samples/{sid}/sequencing_runs")
    assert r.status_code == 200
    assert r.get_json() == []

    r = client.delete(f"/api/samples/{sid}")
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Sequencing runs
# ---------------------------------------------------------------------------
def test_list_sequencing_runs(client):
    r = client.get("/api/sequencing_runs?per_page=5")
    assert r.status_code == 200
    assert len(r.get_json()["items"]) == 5


def test_create_sequencing_run(client):
    r = client.post("/api/sequencing_runs", json={
        "sample_id": 1, "platform": "Illumina NovaSeq", "assay_type": "WGS", "run_date": "2024-01-01",
    })
    assert r.status_code == 201
    run_id = r.get_json()["run_id"]
    r = client.get(f"/api/sequencing_runs/{run_id}/variants")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Variants: query/filter/pagination + CRUD
# ---------------------------------------------------------------------------
def test_list_variants_with_filter(client):
    r = client.get("/api/variants?gene_symbol=BRCA1&per_page=5")
    assert r.status_code == 200
    body = r.get_json()
    for v in body["items"]:
        assert v["gene_symbol"] == "BRCA1"


def test_variant_crud(client):
    r = client.post("/api/variants", json={
        "run_id": 1, "chromosome": "17", "position": 41246481,
        "ref_allele": "G", "alt_allele": "A", "variant_type": "SNV", "gene_symbol": "BRCA1",
    })
    assert r.status_code == 201
    vid = r.get_json()["variant_id"]

    r = client.put(f"/api/variants/{vid}", json={"zygosity": "homozygous"})
    assert r.status_code == 200
    assert r.get_json()["zygosity"] == "homozygous"

    r = client.delete(f"/api/variants/{vid}")
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Variant annotations
# ---------------------------------------------------------------------------
def test_annotation_lifecycle(client):
    r = client.get("/api/variants/1/annotations")
    assert r.status_code == 200

    r = client.post("/api/variants/1/annotations", json={
        "clinical_significance": "pathogenic", "condition": "Test Condition",
    })
    assert r.status_code == 201
    aid = r.get_json()["annotation_id"]

    r = client.get(f"/api/annotations/{aid}")
    assert r.status_code == 200

    r = client.put(f"/api/annotations/{aid}", json={"review_status": "reviewed"})
    assert r.status_code == 200

    r = client.delete(f"/api/annotations/{aid}")
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Clinical reports
# ---------------------------------------------------------------------------
def test_report_lifecycle_and_finalize(client):
    r = client.post("/api/reports", json={"patient_id": 1, "sample_id": 1, "summary": "Test report"})
    assert r.status_code == 201
    rid = r.get_json()["report_id"]

    r = client.post(f"/api/reports/{rid}/finalize", json={"signed_by": "Dr. Test"})
    assert r.status_code == 200
    assert r.get_json()["report_status"] == "finalized"

    r = client.delete(f"/api/reports/{rid}")
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Workflows / workflow runs
# ---------------------------------------------------------------------------
def test_list_workflows_returns_twelve(client):
    r = client.get("/api/workflows")
    assert r.status_code == 200
    assert len(r.get_json()) == 12


def test_trigger_workflow_and_fetch_run(client):
    r = client.get("/api/workflows")
    workflow_id = r.get_json()[0]["workflow_id"]

    r = client.post(f"/api/workflows/{workflow_id}/trigger", json={"sample_id": 1, "patient_id": 1})
    assert r.status_code == 201
    run_id = r.get_json()["workflow_run_id"]

    r = client.get(f"/api/workflow_runs/{run_id}")
    assert r.status_code == 200
    assert r.get_json()["status"] == "triggered"

    r = client.get(f"/api/workflows/{workflow_id}/runs")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Search, export, auth, audit log
# ---------------------------------------------------------------------------
def test_search(client):
    r = client.get("/api/search?q=BRCA1")
    assert r.status_code == 200
    body = r.get_json()
    assert "patients" in body and "variants" in body


def test_search_requires_query(client):
    r = client.get("/api/search")
    assert r.status_code == 400


def test_export_patient(client):
    r = client.get("/api/export/patient/1")
    assert r.status_code == 200
    body = r.get_json()
    assert "samples" in body
    assert "clinical_reports" in body


def test_auth_login_success_and_failure(client):
    r = client.post("/api/auth/login", json={"username": "dr_patel"})
    assert r.status_code == 200
    assert "token" in r.get_json()

    r = client.post("/api/auth/login", json={"username": "nonexistent_user"})
    assert r.status_code == 401


def test_audit_log(client):
    r = client.get("/api/audit-log?per_page=5")
    assert r.status_code == 200
    assert "items" in r.get_json()


# ---------------------------------------------------------------------------
# Latency benchmark: real measured local query latency for the
# "genomic data access" join query (export_patient), via the real API +
# real SQLite DB path in this environment.
#
# HONESTY NOTE: this measures REAL local latency (milliseconds), not the
# literal "8 hours -> 1.5 hours" resume figure. That figure describes the
# architectural claim this project supports: replacing a manual/ad-hoc
# cross-referencing process (looking up a patient's samples, runs, variants,
# and annotations by hand across separate spreadsheets/systems) with a
# single indexed, API-driven database query. The number below is honest,
# reproducible evidence of what "database access with indexes via a REST
# API" actually costs computationally: milliseconds, not hours.
# ---------------------------------------------------------------------------
def test_latency_benchmark_export_patient(client):
    patient_ids = [1, 2, 3, 4, 5, 10, 20, 50, 100]
    timings_ms = []
    for pid in patient_ids:
        start = time.perf_counter()
        r = client.get(f"/api/export/patient/{pid}")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        timings_ms.append(elapsed_ms)

    mean_ms = statistics.mean(timings_ms)
    p95_ms = sorted(timings_ms)[int(len(timings_ms) * 0.95) - 1]

    print(f"\n[latency benchmark] export_patient join query over {len(patient_ids)} patients: "
          f"mean={mean_ms:.2f}ms, p95={p95_ms:.2f}ms, all_samples_ms={[round(t, 2) for t in timings_ms]}")

    # Sanity bound: a locally indexed SQLite join over this seed dataset
    # should complete in well under a second per request.
    assert mean_ms < 1000
