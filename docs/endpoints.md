# Genomics Data API — Endpoint Reference

This document is generated to match the real implementation in `app/main.py`.
All 45 endpoints below are real Flask routes, backed by the real SQLite
database at `data/genomics.db` (schema: `db/schema.sql`).

## Health / Status (2)

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness check. Returns `{"status": "ok"}`. |
| GET | `/api/status` | Service status: uptime + row counts per core table. |

## Patients (6)

| Method | Path | Description | Request | Response |
|---|---|---|---|---|
| GET | `/api/patients` | Paginated list. Query: `page`, `per_page`. | - | `{page, per_page, total, items:[patient]}` |
| POST | `/api/patients` | Create a patient. | `{mrn, first_name, last_name, date_of_birth, sex, ethnicity?, diagnosis?}` | `201` + patient object |
| GET | `/api/patients/<id>` | Fetch one patient. | - | patient object or `404` |
| PUT | `/api/patients/<id>` | Partial update. | any updatable field | updated patient object |
| DELETE | `/api/patients/<id>` | Delete patient (cascades samples). | - | `204` |
| GET | `/api/patients/<id>/samples` | All samples for a patient. | - | `[sample]` |

## Samples (6)

| Method | Path | Description |
|---|---|---|
| GET | `/api/samples` | Paginated list. |
| POST | `/api/samples` | Create sample (`patient_id`, `sample_type`, `collection_date` required). |
| GET | `/api/samples/<id>` | Fetch one sample. |
| PUT | `/api/samples/<id>` | Partial update. |
| DELETE | `/api/samples/<id>` | Delete sample (cascades sequencing runs). |
| GET | `/api/samples/<id>/sequencing_runs` | All sequencing runs for a sample. |

## Sequencing runs (6)

| Method | Path | Description |
|---|---|---|
| GET | `/api/sequencing_runs` | Paginated list. |
| POST | `/api/sequencing_runs` | Create run (`sample_id`, `platform`, `assay_type`, `run_date` required). |
| GET | `/api/sequencing_runs/<id>` | Fetch one run. |
| PUT | `/api/sequencing_runs/<id>` | Partial update. |
| DELETE | `/api/sequencing_runs/<id>` | Delete run (cascades variants). |
| GET | `/api/sequencing_runs/<id>/variants` | All variants called from a run. |

## Variants (5)

| Method | Path | Description |
|---|---|---|
| GET | `/api/variants` | Paginated, filterable list. Query: `gene_symbol`, `chromosome`, `variant_type`, `page`, `per_page`. |
| POST | `/api/variants` | Create variant record. |
| GET | `/api/variants/<id>` | Fetch one variant. |
| PUT | `/api/variants/<id>` | Partial update. |
| DELETE | `/api/variants/<id>` | Delete variant (cascades annotations). |

## Variant annotations (5)

| Method | Path | Description |
|---|---|---|
| GET | `/api/variants/<id>/annotations` | All annotations for a variant. |
| POST | `/api/variants/<id>/annotations` | Add an annotation (`clinical_significance` required). |
| GET | `/api/annotations/<id>` | Fetch one annotation. |
| PUT | `/api/annotations/<id>` | Partial update. |
| DELETE | `/api/annotations/<id>` | Delete annotation. |

## Clinical reports (6)

| Method | Path | Description |
|---|---|---|
| GET | `/api/reports` | Paginated list. |
| POST | `/api/reports` | Create draft report (`patient_id`, `sample_id` required). |
| GET | `/api/reports/<id>` | Fetch one report. |
| PUT | `/api/reports/<id>` | Partial update (summary, status, signer). |
| DELETE | `/api/reports/<id>` | Delete report. |
| POST | `/api/reports/<id>/finalize` | Sets `report_status='finalized'`, stamps `finalized_at`. |

## Workflows / workflow runs (5)

| Method | Path | Description |
|---|---|---|
| GET | `/api/workflows` | List all 12 defined workflows. |
| GET | `/api/workflows/<id>` | Fetch one workflow definition. |
| POST | `/api/workflows/<id>/trigger` | Trigger a new run of a workflow (creates a `workflow_runs` row). |
| GET | `/api/workflows/<id>/runs` | All runs of a given workflow. |
| GET | `/api/workflow_runs/<id>` | Fetch one workflow run's status. |

## Search, export, auth, audit (4)

| Method | Path | Description |
|---|---|---|
| GET | `/api/search` | Cross-resource search. Query: `q` (matches patient name/MRN and gene symbol). |
| GET | `/api/export/patient/<id>` | Bulk export: full nested genomic record for a patient (samples → sequencing runs → variants → annotations → reports). This is the query used in the latency benchmark. |
| POST | `/api/auth/login` | Auth stub. `{username}` → `{token, role}` if the username exists in `users`, else `401`. |
| GET | `/api/audit-log` | Paginated query over `access_log` (every API request is logged here). Query: `username`, `page`, `per_page`. |

**Total: 45 endpoints.** Verified by `grep -c "@app.route" app/main.py` and exercised by `tests/test_api.py`.

---

## The 12 workflows

Each "workflow" is a named, multi-step sequence of API calls representing a
real clinical-genomics operational process. The `workflows` table stores the
definition; `workflow_runs` records each execution (created via the trigger
endpoint or implicitly by the natural sequence of calls below).

1. **patient_onboarding** — Register a new patient and their first sample.
   `POST /api/patients` → `POST /api/samples` → `GET /api/patients/<id>/samples`

2. **sample_intake** — Log a new sample and put it into processing.
   `POST /api/samples` → `PUT /api/samples/<id>` (`status=processing`) → `GET /api/samples/<id>`

3. **sequencing_run_request** — Queue sequencing for a received sample.
   `GET /api/samples/<id>` → `POST /api/sequencing_runs` → `GET /api/samples/<id>/sequencing_runs`

4. **variant_calling_request** — Trigger variant calling once a run completes.
   `PUT /api/sequencing_runs/<id>` (`status=complete`) → `POST /api/variants` (×N) → `GET /api/sequencing_runs/<id>/variants`

5. **variant_annotation_pipeline** — Annotate called variants with clinical significance.
   `GET /api/sequencing_runs/<id>/variants` → `POST /api/variants/<id>/annotations` (×N) → `GET /api/variants/<id>/annotations`

6. **clinical_report_generation** — Draft a report from annotated variants.
   `GET /api/export/patient/<id>` → `POST /api/reports`

7. **report_review_and_signoff** — Review a draft report and finalize it.
   `GET /api/reports/<id>` → `PUT /api/reports/<id>` (`report_status=pending_review`) → `POST /api/reports/<id>/finalize`

8. **patient_variant_lookup** — Clinician looks up all variants for a patient.
   `GET /api/patients/<id>` → `GET /api/patients/<id>/samples` → `GET /api/samples/<id>/sequencing_runs` → `GET /api/sequencing_runs/<id>/variants`

9. **bulk_cohort_export** — Export full genomic records for a set of patients (e.g. for a research cohort).
   `GET /api/patients?per_page=200` → `GET /api/export/patient/<id>` (×N)

10. **sample_reprocessing** — Re-queue a failed sample/run.
    `GET /api/samples/<id>` (`status=failed`) → `PUT /api/samples/<id>` (`status=processing`) → `POST /api/sequencing_runs` → `POST /api/workflows/<id>/trigger`

11. **audit_compliance_review** — Compliance officer reviews access history for a user.
    `POST /api/auth/login` → `GET /api/audit-log?username=<name>`

12. **user_access_provisioning** — Provision a new user/role (represented via the auth stub + audit trail).
    `POST /api/auth/login` (verify requester) → `GET /api/audit-log` (confirm logged) — in a full system this would pair with a `POST /api/users` endpoint; here it is modeled as an auditable workflow over the existing `users`/`access_log` tables seeded at setup time.

Workflow definitions and their `workflow_runs` history are queryable live via
`GET /api/workflows` and `GET /api/workflows/<id>/runs`.
