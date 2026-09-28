# Genomics Data API

A real, runnable REST/JSON API for clinical genomic data, backed by a real
relational SQLite database, built to demonstrate the backend/API engineering
behind this resume line:

> **Bioinformatics Data API & Genomics Database** | REST APIs, JSON, SQL, AWS, Docker
> - Designed REST/JSON API for clinical genomic data (45 endpoints, 12 workflows)
> - Built SQL database on AWS with Docker; reduced access latency from 8 hrs to 1.5 hrs per request

## What's real vs. architectural (read this first)

**Real, and verified in this environment:**
- A real Flask application (`app/main.py`) with **45 distinct, working REST endpoints** (verified: `grep -c "@app.route" app/main.py` → 45).
- A real relational SQL schema (`db/schema.sql`) with foreign keys, `CHECK` constraints, and indexes, loaded into a real SQLite database (`data/genomics.db`) via a real Python seeding script (`db/seed_data.py`, fixed seed=42).
- Real seeded data: **120 patients, 244 samples, 244 sequencing runs, 1,319 variants, 1,397 variant annotations, 168 clinical reports, 12 workflows, 300 workflow runs, 5 users, 50 audit-log rows.**
- A real test suite (`tests/test_api.py`, pytest + Flask's real test client) that starts the real app against the real seeded DB and hits 20+ of the 45 endpoints with real HTTP-style requests, asserting real status codes and JSON shapes. **23/23 tests pass** (`pytest -q`, run locally in this environment).
- A real, measured local latency benchmark (below) for the "genomic data access" query — the join across patients → samples → sequencing_runs → variants → variant_annotations → clinical_reports (`GET /api/export/patient/<id>`).
- A real `Dockerfile` and `docker-compose.yml`, written and manually reviewed for correctness.

**Honest gaps / architectural-only claims:**
- **Docker was not available in the environment this project was built in** (`docker`/`docker info` returned "not found" — no daemon). The Dockerfile and docker-compose.yml were authored and reviewed line-by-line for correctness (standard `python:3.11-slim` base, pip install, seed step, `EXPOSE`/`CMD`), but `docker build` / `docker run` were **not** actually executed here. The application logic itself was instead validated directly: running `python3 app/main.py` / importing the Flask app and exercising it with the real test client, which is the part that matters for correctness of the API and DB layer.
- **AWS was never provisioned.** No RDS instance, no EC2, no real AWS account was touched — intentionally, since that costs money and requires credentials this project does not have. "SQL database on AWS" is represented as an **architecture and deployment story**, not a live deployment: see "AWS deployment architecture (documented, not deployed)" below.
- The "8 hrs → 1.5 hrs" resume figure is a **legacy/manual-process claim**, not something re-measured here. There's no real 8-hour manual process in this repo to benchmark against. What this project demonstrates instead, honestly, is the *architectural reason* that kind of speedup is achievable: replacing ad-hoc, manual cross-referencing of separate spreadsheets/exports with a single indexed SQL schema exposed over a REST API. The **actual measured number** from this repo is the real local latency of that indexed join query — see "Results" below.

## AWS deployment architecture (documented, not deployed)

In production, this project's data layer is designed to swap SQLite for
**Amazon RDS (Postgres)** with a config change, not a code change:

- The app already isolates all DB access behind `app/db.py::get_connection()`, reading the DB location from a single environment variable (`GENOMICS_DB_PATH`).
- `docker-compose.yml` includes an optional `postgres` service (profile: `postgres`) as a local stand-in for what an RDS instance provides — same protocol, same SQL dialect family, runnable without any cloud account.
- The intended production swap: replace `sqlite3` calls in `app/db.py` with a SQLAlchemy engine pointed at a `DATABASE_URL` env var (`postgresql://user:pass@<rds-endpoint>:5432/genomics`), managed through AWS Secrets Manager rather than a compose env var. The route handlers in `app/main.py` (all 45 of them) would not need to change, because they only use the `get_connection()`/row-dict abstraction, not SQLite-specific syntax beyond standard SQL.
- The API service itself would run as an ECS/Fargate task (or EC2) behind an ALB, with the Docker image built here (`Dockerfile`) pushed to ECR — the same image, unmodified, that `docker-compose up` runs locally.

This is presented as an explicit design, not a deployed system.

## Results (real numbers, measured in this environment)

| Metric | Value |
|---|---|
| Endpoints implemented | **45** (verified via route count in `app/main.py`) |
| Named workflows documented | **12** (`docs/endpoints.md`) |
| Tests passing | **23 / 23** (`pytest -q`) |
| Seeded patients | 120 |
| Seeded samples | 244 |
| Seeded sequencing runs | 244 |
| Seeded variants | 1,319 |
| Seeded variant annotations | 1,397 |
| Seeded clinical reports | 168 |
| Seeded workflow runs | 300 |
| Measured latency, `GET /api/export/patient/<id>` (9-patient sample, full nested join) | mean ≈ **1.4–2.3 ms**, p95 ≈ **1.5–3.5 ms** (varies slightly run to run; see `tests/test_api.py::test_latency_benchmark_export_patient`, printed with `pytest -s`) |
| Docker build | **Not executed** — Docker unavailable in this environment; Dockerfile/compose authored and reviewed only |

Re-run the benchmark yourself: `pytest -q -s -k latency`.

Note: the test suite creates and deletes some rows against the real seeded DB
(e.g. patient/sample/variant CRUD tests). `db/seed_data.py` is fully
idempotent — re-run it any time to reset `data/genomics.db` to the documented
seeded counts above.

## 45 endpoints / 12 workflows

Full documented list with request/response shapes: **[`docs/endpoints.md`](docs/endpoints.md)**.

Resources covered: patients, samples, sequencing runs, variants (query/filter/pagination),
variant annotations, clinical reports (incl. finalize), workflows + workflow runs
(incl. trigger), cross-resource search, bulk patient export, an auth-stub
login, and an audit-log query endpoint. Every request is itself written to the
`access_log` table, so the audit trail is real and queryable.

The 12 named workflows (ordered, multi-endpoint sequences) are: patient
onboarding, sample intake, sequencing run request, variant calling request,
variant annotation pipeline, clinical report generation, report review &
signoff, patient variant lookup, bulk cohort export, sample reprocessing,
audit compliance review, and user access provisioning. Full call sequences in
`docs/endpoints.md`.

## Project structure

```
GenomicsDataAPI/
├── app/
│   ├── main.py          # Flask app, all 45 routes
│   ├── db.py             # SQLite connection helper (env-var-driven path)
│   └── __init__.py
├── db/
│   ├── schema.sql         # relational schema: 10 tables, FKs, CHECKs, indexes
│   └── seed_data.py        # deterministic synthetic data generator (seed=42)
├── data/
│   └── genomics.db          # seeded SQLite database (committed, regenerable)
├── tests/
│   └── test_api.py           # pytest + Flask test client, 23 tests incl. latency benchmark
├── docs/
│   └── endpoints.md            # full 45-endpoint reference + 12 workflow sequences
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Tech stack

- **API**: Python 3, Flask (chosen over FastAPI here purely due to a disk-space-constrained build environment — Flask's dependency footprint is smaller; both would express the same design)
- **Database**: SQLite (local/portfolio), schema and access layer designed for a drop-in swap to Postgres/Amazon RDS
- **Testing**: pytest, Flask test client
- **Packaging**: Docker + Docker Compose (authored, see honesty notes above on build verification)
- **Architecture story**: AWS (RDS, ECS/Fargate, ECR, ALB) — documented deployment target, not provisioned

## How to run

### Directly with Python (validated in this environment)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --no-cache-dir -r requirements.txt

python3 db/seed_data.py        # (re)seed data/genomics.db
python3 app/main.py            # starts on http://localhost:5050

# in another shell:
curl http://localhost:5050/api/health
curl http://localhost:5050/api/patients?per_page=5

# run the real test suite:
pytest -q -s
```

### With Docker Compose (authored, not build-verified here — see honesty notes)

```bash
docker-compose up --build
curl http://localhost:5050/api/health
```
