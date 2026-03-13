# VitaCall Data Pipeline Design

**Version:** 1.0
**Date:** 2026-03-13
**Scope:** Week 6 deliverable — data pipeline only

## Overview

Monorepo MLOps platform for VitaCall — a healthcare call center that needs speech-to-text (edge) and sentiment analysis (cloud). This spec covers the **week 6 deliverable: data pipeline**.

The current repo has an Electron + React frontend at the root. This spec describes the **target** structure after restructuring.

## Architecture: Medallion (Bronze / Silver / Gold)

Industry-standard layered data architecture using PySpark. Each layer reads from the previous and writes Parquet to `data/{layer}/`.

**Ordering:** Layers must run sequentially — Bronze before Silver before Gold. The API enforces this: requesting Silver when Bronze has not produced output returns a 409 Conflict error.

## Target Monorepo Structure

> **Note:** Existing root-level Electron files (`main.js`, `package.json`, `src/`, etc.) will be moved into `frontend/`.

```
MLOPS/
├── frontend/                  # Electron + React (Vite) — moved from root
│   ├── main.js
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│
├── python/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── pipelines/
│   │   ├── bronze/
│   │   │   ├── ingest_common_voice.py
│   │   │   └── ingest_imdb.py
│   │   ├── silver/
│   │   │   ├── clean_audio_metadata.py
│   │   │   └── clean_reviews.py
│   │   └── gold/
│   │       ├── asr_features.py
│   │       └── sentiment_features.py
│   ├── api/
│   │   ├── main.py
│   │   └── routes/
│   │       ├── pipeline.py
│   │       └── data.py
│   └── tests/
│       ├── test_bronze.py
│       ├── test_silver.py
│       └── test_gold.py
│
├── data/                      # DVC-tracked, git-ignored
│   ├── bronze/
│   ├── silver/
│   └── gold/
│
├── docker-compose.yml
├── .dvc/
├── .dvcignore
└── .gitignore
```

## Data Schemas

### Bronze — Common Voice

| Column | Type | Description |
|--------|------|-------------|
| `client_id` | string | Anonymized speaker ID |
| `path` | string | Audio file path (relative) |
| `sentence` | string | Ground truth transcription |
| `up_votes` | int | Community upvotes |
| `down_votes` | int | Community downvotes |
| `age` | string | Speaker age bracket (nullable) |
| `gender` | string | Speaker gender (nullable) |
| `duration` | float | Audio duration in seconds |

### Bronze — IMDb Reviews

| Column | Type | Description |
|--------|------|-------------|
| `review_id` | string | Unique review identifier |
| `text` | string | Raw review text (may contain HTML) |
| `label` | int | 0 = negative, 1 = positive |
| `source_file` | string | Original filename |

### Silver — Common Voice (cleaned)

Same columns as Bronze, with additions:
- Rows with `duration < 1.0` or `duration > 30.0` removed
- Rows with null/empty `sentence` removed
- Duplicates on `client_id + sentence` removed
- Column names lowercased and snake_cased

### Silver — IMDb Reviews (cleaned)

Same columns as Bronze, with additions:
- `text_clean` (string): HTML stripped, whitespace normalized
- Rows with empty `text_clean` removed
- Duplicates on `text_clean` removed

### Gold — ASR Features

| Column | Type | Description |
|--------|------|-------------|
| All Silver columns | — | Inherited |
| `split` | string | "train" / "val" / "test" (80/10/10) |
| `duration_bucket` | string | "short" / "medium" / "long" |

### Gold — Sentiment Features

| Column | Type | Description |
|--------|------|-------------|
| All Silver columns | — | Inherited |
| `split` | string | "train" / "val" / "test" (80/10/10, stratified) |
| `token_count` | int | Word count of `text_clean` |

## Pipeline Layers

### Bronze (Raw Ingest)

| Script | Dataset | Action |
|--------|---------|--------|
| `ingest_common_voice.py` | Mozilla Common Voice NL (~2.5 GB, CC-0 license) | Download, convert TSV + audio paths to Parquet |
| `ingest_imdb.py` | IMDb Reviews (~80 MB, academic use) | Download tar.gz, parse text files, store as Parquet |

No transformations. 1:1 storage of source data.

### Silver (Clean & Validate)

| Script | Action |
|--------|--------|
| `clean_audio_metadata.py` | Filter invalid samples, normalize columns, deduplicate (see schema above) |
| `clean_reviews.py` | Strip HTML, normalize text, remove duplicates, filter empty reviews |

Data quality assertions per schema: non-null on required columns, duration range checks, label value checks.

### Gold (Feature-Ready)

| Script | Action |
|--------|--------|
| `asr_features.py` | Train/val/test splits (80/10/10), duration buckets |
| `sentiment_features.py` | Stratified splits (80/10/10), label encoding, token counts |

## Infrastructure

### Docker

- `docker-compose.yml` with service `api` (FastAPI + PySpark)
- `python/Dockerfile` based on `python:3.11-slim` with Java 17 (Spark dependency)
- All Python deps installed via pip from `pyproject.toml`

### FastAPI Endpoints

Pipeline runs are **asynchronous**. `POST` returns a run ID immediately; poll `GET /pipeline/status/{run_id}` for progress.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/pipeline/run/{layer}` | Trigger pipeline. Returns `{"run_id": "...", "status": "started"}`. Returns 409 if prerequisite layer has no output. |
| GET | `/pipeline/status/{run_id}` | Returns `{"run_id": "...", "status": "running|completed|failed", "error": null}` |
| GET | `/data/stats/{layer}` | Row count, column names, sample rows (5) per layer. Returns 404 if layer has no data. |

### DVC

- `data/` directory in `.gitignore`, tracked by DVC
- Initial remote: local folder (`/tmp/dvc-storage` or `C:\dvc-storage`)
- After each successful pipeline run, `dvc add data/{layer}` is called automatically
- `.dvc` files committed to git for reproducibility
- Teammates clone repo, then `dvc pull` to get data

## Testing Strategy

| Test file | What it tests | Approach |
|-----------|--------------|----------|
| `test_bronze.py` | Ingest functions produce valid Parquet with expected schema | Unit tests with small synthetic data (5-10 rows), no real downloads |
| `test_silver.py` | Cleaning functions correctly filter, deduplicate, strip HTML | Unit tests with crafted dirty data, assert output matches expected |
| `test_gold.py` | Splits are correct ratios, feature columns present | Unit tests with synthetic silver data, check split proportions |

All tests use a local SparkSession (no cluster needed). Test fixtures in `tests/conftest.py`.

## Out of Scope (Week 6)

- Frontend-to-API integration (Electron calling FastAPI) — comes later
- Model training — week 12
- Deployment — week 17
- Monitoring and drift detection — week 17

## Technology Stack

| Tool | Purpose |
|------|---------|
| PySpark | Data processing (all pipeline layers) |
| FastAPI | Python backend API |
| DVC | Data version control |
| Docker + docker-compose | Containerization |
| pytest | Testing |
| Electron + React + Vite | Frontend (existing, untouched this sprint) |

## Datasets

| Dataset | Size | License | URL |
|---------|------|---------|-----|
| Mozilla Common Voice (NL) | ~2.5 GB | CC-0 | commonvoice.mozilla.org |
| IMDb Reviews | ~80 MB | Academic | ai.stanford.edu/~amaas/data/sentiment/ |

## Decisions

- Parquet for storage (simple, Spark-native)
- Medallion architecture (Bronze/Silver/Gold)
- FastAPI for Python-Electron communication
- DVC for data versioning
- Docker for reproducible environment
- Monorepo with `frontend/` and `python/` top-level directories
- Async pipeline runs via FastAPI
- Sequential layer ordering enforced by API
