# Genomics Data API - container image
#
# NOTE ON THIS ENVIRONMENT: this Dockerfile was authored and manually
# reviewed for correctness, but `docker` was not installed in the sandbox
# used to build this project (no docker daemon available), so `docker build`
# could not actually be executed here. The application logic itself was
# validated directly with `python3` and the real pytest suite (see README).

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY db/ ./db/
COPY data/ ./data/

# Regenerate the seeded SQLite DB inside the image so the container is
# self-contained (fixed random seed -> deterministic, reproducible data).
RUN python3 db/seed_data.py

ENV GENOMICS_DB_PATH=/app/data/genomics.db
EXPOSE 5050

CMD ["python3", "-m", "app.main"]
