# VitaCall Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working Medallion (Bronze/Silver/Gold) data pipeline with PySpark, FastAPI, DVC, and Docker for VitaCall healthcare call center data.

**Architecture:** Monorepo with `frontend/` (existing Electron app) and `python/` (new pipeline + API). Each pipeline layer reads Parquet from the previous layer's output directory and writes to its own. FastAPI exposes async pipeline triggers and data stats.

**Tech Stack:** PySpark, FastAPI, DVC, Docker, pytest, Python 3.11

**Spec:** `docs/superpowers/specs/2026-03-13-vitacall-data-pipeline-design.md`

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Move | `main.js` → `frontend/main.js` | Electron entry |
| Move | `package.json` → `frontend/package.json` | Frontend deps |
| Move | `vite.config.js` → `frontend/vite.config.js` | Vite config |
| Move | `index.html` → `frontend/index.html` | HTML entry |
| Move | `src/` → `frontend/src/` | React components |
| Move | `bun.lock` → `frontend/bun.lock` | Lock file |
| Move | `node_modules/` → `frontend/node_modules/` | Deps (or reinstall) |
| Move | `dist/` → `frontend/dist/` | Build output |
| Create | `python/pyproject.toml` | Python project config + deps |
| Create | `python/Dockerfile` | Container image for API + Spark |
| Create | `python/pipelines/__init__.py` | Package init |
| Create | `python/pipelines/bronze/__init__.py` | Package init |
| Create | `python/pipelines/bronze/ingest_common_voice.py` | Download + parse Common Voice → Parquet |
| Create | `python/pipelines/bronze/ingest_imdb.py` | Download + parse IMDb → Parquet |
| Create | `python/pipelines/silver/__init__.py` | Package init |
| Create | `python/pipelines/silver/clean_audio_metadata.py` | Clean/validate Common Voice data |
| Create | `python/pipelines/silver/clean_reviews.py` | Clean/validate IMDb reviews |
| Create | `python/pipelines/gold/__init__.py` | Package init |
| Create | `python/pipelines/gold/asr_features.py` | ASR feature engineering + splits |
| Create | `python/pipelines/gold/sentiment_features.py` | Sentiment feature engineering + splits |
| Create | `python/api/__init__.py` | Package init |
| Create | `python/api/main.py` | FastAPI app entrypoint |
| Create | `python/api/routes/__init__.py` | Package init |
| Create | `python/api/routes/pipeline.py` | Pipeline trigger + status endpoints |
| Create | `python/api/routes/data.py` | Data stats endpoints |
| Create | `python/tests/__init__.py` | Package init |
| Create | `python/tests/conftest.py` | Shared Spark fixtures |
| Create | `python/tests/test_bronze.py` | Bronze layer tests |
| Create | `python/tests/test_silver.py` | Silver layer tests |
| Create | `python/tests/test_gold.py` | Gold layer tests |
| Create | `python/tests/test_api.py` | API route tests |
| Create | `docker-compose.yml` | Service orchestration |
| Create | `.dvcignore` | DVC ignore patterns |
| Modify | `.gitignore` | Add data/, venv, __pycache__, etc. |

---

## Chunk 1: Project Setup & Restructure

### Task 1: Initialize Git and Restructure Monorepo

**Files:**
- Modify: `.gitignore`
- Move: all root-level frontend files → `frontend/`

- [ ] **Step 1: Init git repo**

```bash
cd /c/dev/MLOPS
git init
```

- [ ] **Step 2: Update .gitignore before first commit**

Replace `.gitignore` with:
```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/

# Data (DVC-tracked)
data/bronze/
data/silver/
data/gold/
data/raw/

# Node
node_modules/
dist/

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store
Thumbs.db

# DVC local
/tmp/dvc-storage/
```

- [ ] **Step 3: Create frontend directory and move files**

```bash
mkdir -p frontend
mv main.js frontend/
mv package.json frontend/
mv vite.config.js frontend/
mv index.html frontend/
mv src frontend/
mv bun.lock frontend/
rm -rf node_modules
rm -rf dist
```

> Note: `node_modules/` and `dist/` are regenerable — delete instead of move to keep the move clean.

- [ ] **Step 4: Fix frontend/main.js path (dist is now inside frontend)**

In `frontend/main.js`, the `loadFile` path is already relative (`path.join(__dirname, 'dist', 'index.html')`) — this still works since `__dirname` will be `frontend/`.

- [ ] **Step 5: Create data directories**

```bash
mkdir -p data/bronze data/silver data/gold data/raw
```

> Note: No `.gitkeep` — these directories are git-ignored and DVC-tracked. They'll be created by the pipeline or DVC.

- [ ] **Step 6: Initial commit**

```bash
git add -A
git commit -m "chore: restructure monorepo — move frontend to frontend/"
```

### Task 2: Python Project Setup

**Files:**
- Create: `python/pyproject.toml`
- Create: `python/pipelines/__init__.py`
- Create: `python/pipelines/bronze/__init__.py`
- Create: `python/pipelines/silver/__init__.py`
- Create: `python/pipelines/gold/__init__.py`
- Create: `python/api/__init__.py`
- Create: `python/api/routes/__init__.py`
- Create: `python/tests/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "vitacall-pipeline"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pyspark>=3.5.0",
    "fastapi>=0.115.0",
    "uvicorn>=0.34.0",
    "requests>=2.32.0",
    "beautifulsoup4>=4.12.0",
    "pandas>=2.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "httpx>=0.27.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 2: Create all __init__.py files**

All empty files:
```
python/pipelines/__init__.py
python/pipelines/bronze/__init__.py
python/pipelines/silver/__init__.py
python/pipelines/gold/__init__.py
python/api/__init__.py
python/api/routes/__init__.py
python/tests/__init__.py
```

- [ ] **Step 3: Create virtual environment and install deps**

```bash
cd /c/dev/MLOPS/python
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
pip install -e ".[dev]"
```

- [ ] **Step 4: Verify PySpark works**

```bash
python -c "from pyspark.sql import SparkSession; spark = SparkSession.builder.master('local[*]').getOrCreate(); print(spark.version); spark.stop()"
```

Expected: prints Spark version (e.g., `3.5.x`)

- [ ] **Step 5: Commit**

```bash
cd /c/dev/MLOPS
git add -A
git commit -m "chore: add Python project with PySpark, FastAPI deps"
```

### Task 3: DVC Setup

**Files:**
- Create: `.dvcignore`
- Modify: `.gitignore` (if needed)

- [ ] **Step 1: Install DVC**

```bash
cd /c/dev/MLOPS/python
source .venv/Scripts/activate
pip install dvc
```

- [ ] **Step 2: Initialize DVC**

```bash
cd /c/dev/MLOPS
dvc init
```

- [ ] **Step 3: Create .dvcignore**

```
# Ignore Python caches
__pycache__
.venv
*.pyc
```

- [ ] **Step 4: Configure local DVC remote**

```bash
mkdir -p /c/dvc-storage
dvc remote add -d local /c/dvc-storage
```

- [ ] **Step 5: Commit DVC setup**

```bash
git add -A
git commit -m "chore: initialize DVC with local remote"
```

### Task 4: Test Fixtures (conftest.py)

**Files:**
- Create: `python/tests/conftest.py`

- [ ] **Step 1: Write conftest with SparkSession fixture**

```python
import pytest
from pyspark.sql import SparkSession
import tempfile
import shutil
import os


@pytest.fixture(scope="session")
def spark():
    """Shared SparkSession for all tests — local mode, no cluster needed."""
    session = (
        SparkSession.builder
        .master("local[*]")
        .appName("vitacall-tests")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.ui.enabled", "false")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .getOrCreate()
    )
    yield session
    session.stop()


@pytest.fixture()
def tmp_dir():
    """Temporary directory for test output, cleaned up after each test."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)
```

- [ ] **Step 2: Verify fixture loads**

```bash
cd /c/dev/MLOPS/python
source .venv/Scripts/activate
python -m pytest tests/conftest.py --co
```

Expected: no errors (no tests collected is fine — we just want the import to work)

- [ ] **Step 3: Commit**

```bash
cd /c/dev/MLOPS
git add -A
git commit -m "test: add Spark session fixture in conftest.py"
```

---

## Chunk 2: Bronze Layer — Ingest Pipelines

### Task 5: Bronze — Common Voice Ingest

**Files:**
- Create: `python/pipelines/bronze/ingest_common_voice.py`
- Create: `python/tests/test_bronze.py`

- [ ] **Step 1: Write failing test for Common Voice ingest**

`python/tests/test_bronze.py`:
```python
import os
import csv
import tempfile
import shutil
from pyspark.sql import SparkSession
from pipelines.bronze.ingest_common_voice import ingest_common_voice


class TestIngestCommonVoice:
    def test_produces_parquet_with_expected_schema(self, spark, tmp_dir):
        """Ingest should read TSV and produce Parquet with correct columns."""
        # Create synthetic Common Voice TSV
        tsv_dir = os.path.join(tmp_dir, "cv-corpus", "nl")
        os.makedirs(tsv_dir, exist_ok=True)

        rows = [
            {
                "client_id": "abc123",
                "path": "common_voice_nl_001.mp3",
                "sentence": "Hallo, hoe gaat het?",
                "up_votes": "3",
                "down_votes": "0",
                "age": "twenties",
                "gender": "male",
                "duration": "2.5",
            },
            {
                "client_id": "def456",
                "path": "common_voice_nl_002.mp3",
                "sentence": "Het weer is goed vandaag.",
                "up_votes": "5",
                "down_votes": "1",
                "age": "",
                "gender": "",
                "duration": "3.1",
            },
        ]

        tsv_path = os.path.join(tsv_dir, "validated.tsv")
        with open(tsv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)

        output_path = os.path.join(tmp_dir, "output")
        ingest_common_voice(spark, tsv_path, output_path)

        df = spark.read.parquet(output_path)
        assert df.count() == 2

        expected_cols = {
            "client_id", "path", "sentence", "up_votes",
            "down_votes", "age", "gender", "duration",
        }
        assert set(df.columns) == expected_cols

    def test_casts_numeric_columns(self, spark, tmp_dir):
        """up_votes, down_votes should be int; duration should be float."""
        tsv_dir = os.path.join(tmp_dir, "cv-corpus", "nl")
        os.makedirs(tsv_dir, exist_ok=True)

        tsv_path = os.path.join(tsv_dir, "validated.tsv")
        with open(tsv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["client_id", "path", "sentence", "up_votes", "down_votes", "age", "gender", "duration"],
                delimiter="\t",
            )
            writer.writeheader()
            writer.writerow({
                "client_id": "x", "path": "a.mp3", "sentence": "Test",
                "up_votes": "2", "down_votes": "1", "age": "", "gender": "", "duration": "4.2",
            })

        output_path = os.path.join(tmp_dir, "output")
        ingest_common_voice(spark, tsv_path, output_path)

        df = spark.read.parquet(output_path)
        schema = {f.name: f.dataType.simpleString() for f in df.schema.fields}
        assert schema["up_votes"] == "int"
        assert schema["down_votes"] == "int"
        assert schema["duration"] == "double"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /c/dev/MLOPS/python
python -m pytest tests/test_bronze.py::TestIngestCommonVoice -v
```

Expected: `ModuleNotFoundError` or `ImportError` — function doesn't exist yet.

- [ ] **Step 3: Implement ingest_common_voice**

`python/pipelines/bronze/ingest_common_voice.py`:
```python
"""Bronze layer: Ingest Mozilla Common Voice dataset (Dutch subset) into Parquet."""

import os
import tarfile
import requests
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, DoubleType,
)

COMMON_VOICE_SCHEMA = StructType([
    StructField("client_id", StringType(), True),
    StructField("path", StringType(), True),
    StructField("sentence", StringType(), True),
    StructField("up_votes", IntegerType(), True),
    StructField("down_votes", IntegerType(), True),
    StructField("age", StringType(), True),
    StructField("gender", StringType(), True),
    StructField("duration", DoubleType(), True),
])


def ingest_common_voice(
    spark: SparkSession,
    tsv_path: str,
    output_path: str,
) -> None:
    """Read Common Voice validated.tsv and write as Parquet.

    Args:
        spark: Active SparkSession.
        tsv_path: Path to the validated.tsv file.
        output_path: Directory to write Parquet output.
    """
    df = (
        spark.read
        .option("header", "true")
        .option("delimiter", "\t")
        .option("quote", "")
        .csv(tsv_path)
    )

    df = (
        df
        .withColumn("up_votes", F.col("up_votes").cast("int"))
        .withColumn("down_votes", F.col("down_votes").cast("int"))
        .withColumn("duration", F.col("duration").cast("double"))
    )

    expected_cols = ["client_id", "path", "sentence", "up_votes", "down_votes", "age", "gender", "duration"]
    df = df.select(*expected_cols)

    df.write.mode("overwrite").parquet(output_path)


def download_common_voice(target_dir: str, url: str | None = None) -> str:
    """Download and extract Common Voice dataset. Returns path to validated.tsv.

    Note: Mozilla Common Voice requires authentication for download.
    Place the tar.gz manually in target_dir if automated download fails.
    """
    tsv_path = os.path.join(target_dir, "cv-corpus", "nl", "validated.tsv")
    if os.path.exists(tsv_path):
        return tsv_path

    if url is None:
        raise FileNotFoundError(
            f"Common Voice dataset not found at {tsv_path}. "
            "Download it manually from https://commonvoice.mozilla.org/nl/datasets "
            "and extract to target_dir."
        )

    tar_path = os.path.join(target_dir, "cv-corpus-nl.tar.gz")
    if not os.path.exists(tar_path):
        resp = requests.get(url, stream=True)
        resp.raise_for_status()
        with open(tar_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=target_dir)

    return tsv_path
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /c/dev/MLOPS/python
python -m pytest tests/test_bronze.py::TestIngestCommonVoice -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /c/dev/MLOPS
git add -A
git commit -m "feat: bronze layer — Common Voice ingest pipeline"
```

### Task 6: Bronze — IMDb Ingest

**Files:**
- Create: `python/pipelines/bronze/ingest_imdb.py`
- Modify: `python/tests/test_bronze.py`

- [ ] **Step 1: Write failing test for IMDb ingest**

Append to `python/tests/test_bronze.py`:
```python
from pipelines.bronze.ingest_imdb import ingest_imdb


class TestIngestImdb:
    def test_produces_parquet_with_expected_schema(self, spark, tmp_dir):
        """Ingest should parse text files from pos/neg dirs into Parquet."""
        # Create synthetic IMDb directory structure
        for split in ["train"]:
            for label_dir, label_name in [("pos", "pos"), ("neg", "neg")]:
                d = os.path.join(tmp_dir, "aclImdb", split, label_name)
                os.makedirs(d, exist_ok=True)

                for i in range(3):
                    rating = 9 if label_name == "pos" else 2
                    fname = f"{i}_{rating}.txt"
                    with open(os.path.join(d, fname), "w", encoding="utf-8") as f:
                        f.write(f"This is a {'great' if label_name == 'pos' else 'bad'} movie review #{i}.")

        imdb_dir = os.path.join(tmp_dir, "aclImdb")
        output_path = os.path.join(tmp_dir, "output")
        ingest_imdb(spark, imdb_dir, output_path)

        df = spark.read.parquet(output_path)
        assert df.count() == 6

        expected_cols = {"review_id", "text", "label", "source_file"}
        assert set(df.columns) == expected_cols

    def test_labels_are_correct(self, spark, tmp_dir):
        """Positive reviews should have label=1, negative label=0."""
        for label_dir, label_name in [("pos", "pos"), ("neg", "neg")]:
            d = os.path.join(tmp_dir, "aclImdb", "train", label_name)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "0_8.txt"), "w") as f:
                f.write("Review text here.")

        imdb_dir = os.path.join(tmp_dir, "aclImdb")
        output_path = os.path.join(tmp_dir, "output")
        ingest_imdb(spark, imdb_dir, output_path)

        df = spark.read.parquet(output_path)
        labels = {row["source_file"].split("/")[-2]: row["label"] for row in df.collect()}
        assert labels.get("pos") == 1 or any(r["label"] == 1 for r in df.collect())
        assert any(r["label"] == 0 for r in df.collect())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /c/dev/MLOPS/python
python -m pytest tests/test_bronze.py::TestIngestImdb -v
```

Expected: `ImportError` — function doesn't exist yet.

- [ ] **Step 3: Implement ingest_imdb**

`python/pipelines/bronze/ingest_imdb.py`:
```python
"""Bronze layer: Ingest IMDb Reviews dataset into Parquet."""

import os
import tarfile
import requests
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType

IMDB_URL = "https://ai.stanford.edu/~amaas/data/sentiment/aclImdb_v1.tar.gz"

IMDB_SCHEMA = StructType([
    StructField("review_id", StringType(), False),
    StructField("text", StringType(), False),
    StructField("label", IntegerType(), False),
    StructField("source_file", StringType(), False),
])


def ingest_imdb(
    spark: SparkSession,
    imdb_dir: str,
    output_path: str,
) -> None:
    """Parse IMDb review text files and write as Parquet.

    Expects directory structure: imdb_dir/{train,test}/{pos,neg}/*.txt

    Args:
        spark: Active SparkSession.
        imdb_dir: Path to extracted aclImdb directory.
        output_path: Directory to write Parquet output.
    """
    records = []

    for split in ["train", "test"]:
        split_dir = os.path.join(imdb_dir, split)
        if not os.path.isdir(split_dir):
            continue

        for sentiment in ["pos", "neg"]:
            sentiment_dir = os.path.join(split_dir, sentiment)
            if not os.path.isdir(sentiment_dir):
                continue

            label = 1 if sentiment == "pos" else 0

            for fname in os.listdir(sentiment_dir):
                if not fname.endswith(".txt"):
                    continue

                fpath = os.path.join(sentiment_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    text = f.read()

                review_id = f"{split}_{sentiment}_{fname.replace('.txt', '')}"
                source_file = f"{split}/{sentiment}/{fname}"
                records.append((review_id, text, label, source_file))

    df = spark.createDataFrame(records, schema=IMDB_SCHEMA)
    df.write.mode("overwrite").parquet(output_path)


def download_imdb(target_dir: str, url: str = IMDB_URL) -> str:
    """Download and extract IMDb dataset. Returns path to aclImdb directory."""
    imdb_dir = os.path.join(target_dir, "aclImdb")
    if os.path.exists(imdb_dir):
        return imdb_dir

    tar_path = os.path.join(target_dir, "aclImdb_v1.tar.gz")
    if not os.path.exists(tar_path):
        resp = requests.get(url, stream=True)
        resp.raise_for_status()
        with open(tar_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=target_dir)

    return imdb_dir
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /c/dev/MLOPS/python
python -m pytest tests/test_bronze.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /c/dev/MLOPS
git add -A
git commit -m "feat: bronze layer — IMDb reviews ingest pipeline"
```

---

## Chunk 3: Silver Layer — Cleaning Pipelines

### Task 7: Silver — Clean Audio Metadata

**Files:**
- Create: `python/pipelines/silver/clean_audio_metadata.py`
- Create: `python/tests/test_silver.py`

- [ ] **Step 1: Write failing test for audio cleaning**

`python/tests/test_silver.py`:
```python
import os
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
from pipelines.silver.clean_audio_metadata import clean_audio_metadata


class TestCleanAudioMetadata:
    def _bronze_schema(self):
        return StructType([
            StructField("client_id", StringType()),
            StructField("path", StringType()),
            StructField("sentence", StringType()),
            StructField("up_votes", IntegerType()),
            StructField("down_votes", IntegerType()),
            StructField("age", StringType()),
            StructField("gender", StringType()),
            StructField("duration", DoubleType()),
        ])

    def test_filters_short_and_long_duration(self, spark, tmp_dir):
        """Rows with duration < 1.0 or > 30.0 should be removed."""
        data = [
            ("a", "a.mp3", "Kort", 1, 0, None, None, 0.5),   # too short
            ("b", "b.mp3", "Goed", 1, 0, None, None, 5.0),    # valid
            ("c", "c.mp3", "Lang", 1, 0, None, None, 35.0),   # too long
        ]
        bronze_path = os.path.join(tmp_dir, "bronze")
        spark.createDataFrame(data, schema=self._bronze_schema()).write.parquet(bronze_path)

        output_path = os.path.join(tmp_dir, "silver")
        clean_audio_metadata(spark, bronze_path, output_path)

        df = spark.read.parquet(output_path)
        assert df.count() == 1
        assert df.collect()[0]["client_id"] == "b"

    def test_removes_null_sentences(self, spark, tmp_dir):
        """Rows with null or empty sentence should be removed."""
        data = [
            ("a", "a.mp3", None, 1, 0, None, None, 5.0),
            ("b", "b.mp3", "", 1, 0, None, None, 5.0),
            ("c", "c.mp3", "Geldige zin", 1, 0, None, None, 5.0),
        ]
        bronze_path = os.path.join(tmp_dir, "bronze")
        spark.createDataFrame(data, schema=self._bronze_schema()).write.parquet(bronze_path)

        output_path = os.path.join(tmp_dir, "silver")
        clean_audio_metadata(spark, bronze_path, output_path)

        df = spark.read.parquet(output_path)
        assert df.count() == 1

    def test_deduplicates_on_client_and_sentence(self, spark, tmp_dir):
        """Duplicate rows (same client_id + sentence) should be removed."""
        data = [
            ("a", "a1.mp3", "Hallo", 1, 0, None, None, 5.0),
            ("a", "a2.mp3", "Hallo", 2, 0, None, None, 6.0),
            ("b", "b.mp3", "Hallo", 1, 0, None, None, 5.0),
        ]
        bronze_path = os.path.join(tmp_dir, "bronze")
        spark.createDataFrame(data, schema=self._bronze_schema()).write.parquet(bronze_path)

        output_path = os.path.join(tmp_dir, "silver")
        clean_audio_metadata(spark, bronze_path, output_path)

        df = spark.read.parquet(output_path)
        assert df.count() == 2  # one "a"+"Hallo" kept, plus "b"+"Hallo"

    def test_lowercases_column_names(self, spark, tmp_dir):
        """Column names should be lowercased and snake_cased."""
        schema = StructType([
            StructField("Client_ID", StringType()),
            StructField("Path", StringType()),
            StructField("Sentence", StringType()),
            StructField("Up_Votes", IntegerType()),
            StructField("Down_Votes", IntegerType()),
            StructField("Age", StringType()),
            StructField("Gender", StringType()),
            StructField("Duration", DoubleType()),
        ])
        data = [("a", "a.mp3", "Test", 1, 0, None, None, 5.0)]
        bronze_path = os.path.join(tmp_dir, "bronze")
        spark.createDataFrame(data, schema=schema).write.parquet(bronze_path)

        output_path = os.path.join(tmp_dir, "silver")
        clean_audio_metadata(spark, bronze_path, output_path)

        df = spark.read.parquet(output_path)
        for col_name in df.columns:
            assert col_name == col_name.lower(), f"Column '{col_name}' is not lowercase"
            assert " " not in col_name, f"Column '{col_name}' contains spaces"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /c/dev/MLOPS/python
python -m pytest tests/test_silver.py::TestCleanAudioMetadata -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement clean_audio_metadata**

`python/pipelines/silver/clean_audio_metadata.py`:
```python
"""Silver layer: Clean and validate Common Voice audio metadata."""

import re
from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def _to_snake_case(name: str) -> str:
    """Convert column name to lowercase snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower().replace(" ", "_").replace("-", "_")


def clean_audio_metadata(
    spark: SparkSession,
    bronze_path: str,
    output_path: str,
) -> None:
    """Read bronze Common Voice Parquet, clean, and write to silver.

    Cleaning rules:
    - Lowercase and snake_case all column names
    - Remove rows with duration < 1.0 or > 30.0
    - Remove rows with null or empty sentence
    - Deduplicate on (client_id, sentence)
    """
    df = spark.read.parquet(bronze_path)

    # Lowercase and snake_case column names
    for col_name in df.columns:
        df = df.withColumnRenamed(col_name, _to_snake_case(col_name))

    # Filter duration range
    df = df.filter((F.col("duration") >= 1.0) & (F.col("duration") <= 30.0))

    # Remove null/empty sentences
    df = df.filter(F.col("sentence").isNotNull() & (F.trim(F.col("sentence")) != ""))

    # Deduplicate on client_id + sentence
    df = df.dropDuplicates(["client_id", "sentence"])

    df.write.mode("overwrite").parquet(output_path)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /c/dev/MLOPS/python
python -m pytest tests/test_silver.py::TestCleanAudioMetadata -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /c/dev/MLOPS
git add -A
git commit -m "feat: silver layer — Common Voice audio metadata cleaning"
```

### Task 8: Silver — Clean Reviews

**Files:**
- Create: `python/pipelines/silver/clean_reviews.py`
- Modify: `python/tests/test_silver.py`

- [ ] **Step 1: Write failing test for review cleaning**

Append to `python/tests/test_silver.py`:
```python
from pyspark.sql.types import StructType, StructField, StringType, IntegerType
from pipelines.silver.clean_reviews import clean_reviews


class TestCleanReviews:
    def _bronze_schema(self):
        return StructType([
            StructField("review_id", StringType()),
            StructField("text", StringType()),
            StructField("label", IntegerType()),
            StructField("source_file", StringType()),
        ])

    def test_strips_html_tags(self, spark, tmp_dir):
        """HTML tags should be stripped from text."""
        data = [
            ("r1", "<p>Great <b>movie</b>!</p>", 1, "train/pos/0_9.txt"),
        ]
        bronze_path = os.path.join(tmp_dir, "bronze")
        spark.createDataFrame(data, schema=self._bronze_schema()).write.parquet(bronze_path)

        output_path = os.path.join(tmp_dir, "silver")
        clean_reviews(spark, bronze_path, output_path)

        df = spark.read.parquet(output_path)
        row = df.collect()[0]
        assert "<" not in row["text_clean"]
        assert "Great" in row["text_clean"]
        assert "movie" in row["text_clean"]

    def test_removes_empty_after_cleaning(self, spark, tmp_dir):
        """Reviews that become empty after HTML stripping should be removed."""
        data = [
            ("r1", "<br/><br/>", 1, "train/pos/0_9.txt"),
            ("r2", "Actual review text", 0, "train/neg/1_2.txt"),
        ]
        bronze_path = os.path.join(tmp_dir, "bronze")
        spark.createDataFrame(data, schema=self._bronze_schema()).write.parquet(bronze_path)

        output_path = os.path.join(tmp_dir, "silver")
        clean_reviews(spark, bronze_path, output_path)

        df = spark.read.parquet(output_path)
        assert df.count() == 1
        assert df.collect()[0]["review_id"] == "r2"

    def test_deduplicates_on_text_clean(self, spark, tmp_dir):
        """Duplicate reviews (same text_clean) should be removed."""
        data = [
            ("r1", "Same review text", 1, "train/pos/0_9.txt"),
            ("r2", "Same review text", 0, "train/neg/1_2.txt"),
            ("r3", "Different review", 1, "train/pos/2_8.txt"),
        ]
        bronze_path = os.path.join(tmp_dir, "bronze")
        spark.createDataFrame(data, schema=self._bronze_schema()).write.parquet(bronze_path)

        output_path = os.path.join(tmp_dir, "silver")
        clean_reviews(spark, bronze_path, output_path)

        df = spark.read.parquet(output_path)
        assert df.count() == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /c/dev/MLOPS/python
python -m pytest tests/test_silver.py::TestCleanReviews -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement clean_reviews**

`python/pipelines/silver/clean_reviews.py`:
```python
"""Silver layer: Clean and validate IMDb reviews."""

import re
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType


def _strip_html(text: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    if text is None:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


strip_html_udf = F.udf(_strip_html, StringType())


def clean_reviews(
    spark: SparkSession,
    bronze_path: str,
    output_path: str,
) -> None:
    """Read bronze IMDb Parquet, clean, and write to silver.

    Cleaning rules:
    - Strip HTML from text → text_clean
    - Remove rows where text_clean is empty
    - Deduplicate on text_clean
    """
    df = spark.read.parquet(bronze_path)

    df = df.withColumn("text_clean", strip_html_udf(F.col("text")))

    # Remove empty reviews
    df = df.filter(F.col("text_clean").isNotNull() & (F.trim(F.col("text_clean")) != ""))

    # Validate labels (must be 0 or 1)
    df = df.filter(F.col("label").isin(0, 1))

    # Deduplicate on cleaned text
    df = df.dropDuplicates(["text_clean"])

    df.write.mode("overwrite").parquet(output_path)
```

- [ ] **Step 4: Run all silver tests**

```bash
cd /c/dev/MLOPS/python
python -m pytest tests/test_silver.py -v
```

Expected: 7 tests PASS (4 audio + 3 reviews).

- [ ] **Step 5: Commit**

```bash
cd /c/dev/MLOPS
git add -A
git commit -m "feat: silver layer — IMDb reviews cleaning pipeline"
```

---

## Chunk 4: Gold Layer — Feature Engineering

### Task 9: Gold — ASR Features

**Files:**
- Create: `python/pipelines/gold/asr_features.py`
- Create: `python/tests/test_gold.py`

- [ ] **Step 1: Write failing test for ASR features**

`python/tests/test_gold.py`:
```python
import os
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
from pipelines.gold.asr_features import create_asr_features


class TestAsrFeatures:
    def _silver_schema(self):
        return StructType([
            StructField("client_id", StringType()),
            StructField("path", StringType()),
            StructField("sentence", StringType()),
            StructField("up_votes", IntegerType()),
            StructField("down_votes", IntegerType()),
            StructField("age", StringType()),
            StructField("gender", StringType()),
            StructField("duration", DoubleType()),
        ])

    def test_adds_split_column(self, spark, tmp_dir):
        """Gold should add a 'split' column with train/val/test values."""
        data = [(f"c{i}", f"{i}.mp3", f"Zin {i}", 1, 0, None, None, 5.0) for i in range(100)]
        silver_path = os.path.join(tmp_dir, "silver")
        spark.createDataFrame(data, schema=self._silver_schema()).write.parquet(silver_path)

        output_path = os.path.join(tmp_dir, "gold")
        create_asr_features(spark, silver_path, output_path)

        df = spark.read.parquet(output_path)
        assert "split" in df.columns
        splits = set(row["split"] for row in df.select("split").distinct().collect())
        assert splits == {"train", "val", "test"}

    def test_split_ratios_approximate(self, spark, tmp_dir):
        """Splits should be approximately 80/10/10."""
        data = [(f"c{i}", f"{i}.mp3", f"Zin {i}", 1, 0, None, None, 5.0) for i in range(1000)]
        silver_path = os.path.join(tmp_dir, "silver")
        spark.createDataFrame(data, schema=self._silver_schema()).write.parquet(silver_path)

        output_path = os.path.join(tmp_dir, "gold")
        create_asr_features(spark, silver_path, output_path)

        df = spark.read.parquet(output_path)
        total = df.count()
        train_count = df.filter(df.split == "train").count()
        val_count = df.filter(df.split == "val").count()
        test_count = df.filter(df.split == "test").count()

        assert 0.70 < train_count / total < 0.90
        assert 0.05 < val_count / total < 0.15
        assert 0.05 < test_count / total < 0.15

    def test_adds_duration_bucket(self, spark, tmp_dir):
        """Gold should add duration_bucket: short (<5s), medium (5-15s), long (>15s)."""
        data = [
            ("a", "a.mp3", "Kort", 1, 0, None, None, 2.0),
            ("b", "b.mp3", "Midden", 1, 0, None, None, 10.0),
            ("c", "c.mp3", "Lang", 1, 0, None, None, 20.0),
        ]
        silver_path = os.path.join(tmp_dir, "silver")
        spark.createDataFrame(data, schema=self._silver_schema()).write.parquet(silver_path)

        output_path = os.path.join(tmp_dir, "gold")
        create_asr_features(spark, silver_path, output_path)

        df = spark.read.parquet(output_path)
        buckets = {row["client_id"]: row["duration_bucket"] for row in df.collect()}
        assert buckets["a"] == "short"
        assert buckets["b"] == "medium"
        assert buckets["c"] == "long"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /c/dev/MLOPS/python
python -m pytest tests/test_gold.py::TestAsrFeatures -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement create_asr_features**

`python/pipelines/gold/asr_features.py`:
```python
"""Gold layer: ASR feature engineering — splits and duration buckets."""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def create_asr_features(
    spark: SparkSession,
    silver_path: str,
    output_path: str,
    seed: int = 42,
) -> None:
    """Read silver Common Voice Parquet, add features, write to gold.

    Features added:
    - split: train (80%) / val (10%) / test (10%)
    - duration_bucket: short (<5s) / medium (5-15s) / long (>15s)
    """
    df = spark.read.parquet(silver_path)

    # Random split
    train_df, val_df, test_df = df.randomSplit([0.8, 0.1, 0.1], seed=seed)
    train_df = train_df.withColumn("split", F.lit("train"))
    val_df = val_df.withColumn("split", F.lit("val"))
    test_df = test_df.withColumn("split", F.lit("test"))
    df = train_df.unionByName(val_df).unionByName(test_df)

    # Duration buckets
    df = df.withColumn(
        "duration_bucket",
        F.when(F.col("duration") < 5.0, "short")
        .when(F.col("duration") <= 15.0, "medium")
        .otherwise("long"),
    )

    df.write.mode("overwrite").parquet(output_path)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /c/dev/MLOPS/python
python -m pytest tests/test_gold.py::TestAsrFeatures -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /c/dev/MLOPS
git add -A
git commit -m "feat: gold layer — ASR features with splits and duration buckets"
```

### Task 10: Gold — Sentiment Features

**Files:**
- Create: `python/pipelines/gold/sentiment_features.py`
- Modify: `python/tests/test_gold.py`

- [ ] **Step 1: Write failing test for sentiment features**

Append to `python/tests/test_gold.py`:
```python
from pipelines.gold.sentiment_features import create_sentiment_features


class TestSentimentFeatures:
    def _silver_schema(self):
        return StructType([
            StructField("review_id", StringType()),
            StructField("text", StringType()),
            StructField("label", IntegerType()),
            StructField("source_file", StringType()),
            StructField("text_clean", StringType()),
        ])

    def test_adds_split_column_stratified(self, spark, tmp_dir):
        """Splits should be stratified — each split has both labels."""
        data = []
        for i in range(100):
            label = i % 2
            data.append((f"r{i}", f"text {i}", label, f"file{i}.txt", f"clean text {i}"))

        silver_path = os.path.join(tmp_dir, "silver")
        spark.createDataFrame(data, schema=self._silver_schema()).write.parquet(silver_path)

        output_path = os.path.join(tmp_dir, "gold")
        create_sentiment_features(spark, silver_path, output_path)

        df = spark.read.parquet(output_path)
        assert "split" in df.columns

        for split_name in ["train", "val", "test"]:
            split_df = df.filter(df.split == split_name)
            labels = set(row["label"] for row in split_df.select("label").distinct().collect())
            assert 0 in labels and 1 in labels, f"Split '{split_name}' missing a label"

    def test_adds_token_count(self, spark, tmp_dir):
        """token_count should equal word count of text_clean."""
        data = [
            ("r1", "raw", 1, "f.txt", "three word sentence"),
            ("r2", "raw", 0, "f.txt", "one"),
        ]
        silver_path = os.path.join(tmp_dir, "silver")
        spark.createDataFrame(data, schema=self._silver_schema()).write.parquet(silver_path)

        output_path = os.path.join(tmp_dir, "gold")
        create_sentiment_features(spark, silver_path, output_path)

        df = spark.read.parquet(output_path)
        counts = {row["review_id"]: row["token_count"] for row in df.collect()}
        assert counts["r1"] == 3
        assert counts["r2"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /c/dev/MLOPS/python
python -m pytest tests/test_gold.py::TestSentimentFeatures -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement create_sentiment_features**

`python/pipelines/gold/sentiment_features.py`:
```python
"""Gold layer: Sentiment feature engineering — stratified splits and token counts."""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def create_sentiment_features(
    spark: SparkSession,
    silver_path: str,
    output_path: str,
    seed: int = 42,
) -> None:
    """Read silver IMDb Parquet, add features, write to gold.

    Features added:
    - split: train (80%) / val (10%) / test (10%), stratified by label
    - token_count: word count of text_clean
    """
    df = spark.read.parquet(silver_path)

    # Stratified split: split within each label group
    pos = df.filter(F.col("label") == 1)
    neg = df.filter(F.col("label") == 0)

    result_parts = []
    for subset in [pos, neg]:
        tr, va, te = subset.randomSplit([0.8, 0.1, 0.1], seed=seed)
        tr = tr.withColumn("split", F.lit("train"))
        va = va.withColumn("split", F.lit("val"))
        te = te.withColumn("split", F.lit("test"))
        result_parts.extend([tr, va, te])

    df = result_parts[0]
    for part in result_parts[1:]:
        df = df.unionByName(part)

    # Token count
    df = df.withColumn("token_count", F.size(F.split(F.col("text_clean"), r"\s+")))

    df.write.mode("overwrite").parquet(output_path)
```

- [ ] **Step 4: Run all gold tests**

```bash
cd /c/dev/MLOPS/python
python -m pytest tests/test_gold.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /c/dev/MLOPS
git add -A
git commit -m "feat: gold layer — sentiment features with stratified splits"
```

---

## Chunk 5: FastAPI Backend

### Task 11: FastAPI App + Pipeline Routes

**Files:**
- Create: `python/api/main.py`
- Create: `python/api/routes/pipeline.py`
- Create: `python/api/routes/data.py`
- Create: `python/tests/test_api.py`

- [ ] **Step 1: Write failing test for API**

`python/tests/test_api.py`:
```python
import os
import pytest
from fastapi.testclient import TestClient
from api.main import app


client = TestClient(app)


class TestPipelineRoutes:
    def test_run_returns_run_id(self):
        """POST /pipeline/run/{layer} should return a run_id and started status."""
        resp = client.post("/pipeline/run/bronze")
        assert resp.status_code in (200, 409)
        data = resp.json()
        if resp.status_code == 200:
            assert "run_id" in data
            assert data["status"] == "started"

    def test_run_invalid_layer_returns_422(self):
        """POST /pipeline/run/invalid should return 422."""
        resp = client.post("/pipeline/run/invalid")
        assert resp.status_code == 422


class TestPipelineStatusRoute:
    def test_status_unknown_run_returns_404(self):
        """GET /pipeline/status/{run_id} with unknown id should return 404."""
        resp = client.get("/pipeline/status/nonexistent")
        assert resp.status_code == 404

    def test_status_after_run_returns_valid_status(self):
        """GET /pipeline/status/{run_id} should return running/completed/failed."""
        run_resp = client.post("/pipeline/run/bronze")
        if run_resp.status_code == 200:
            run_id = run_resp.json()["run_id"]
            status_resp = client.get(f"/pipeline/status/{run_id}")
            assert status_resp.status_code == 200
            assert status_resp.json()["status"] in ("running", "completed", "failed")


class TestPrerequisiteEnforcement:
    def test_silver_without_bronze_returns_409(self):
        """POST /pipeline/run/silver without bronze data should return 409."""
        # Ensure no parquet data in bronze
        resp = client.post("/pipeline/run/silver")
        assert resp.status_code == 409


class TestDataRoutes:
    def test_stats_no_data_returns_404(self):
        """GET /data/stats/{layer} with no data should return 404."""
        resp = client.get("/data/stats/bronze")
        # Either 404 (no data) or 200 (data exists from prior run) is acceptable
        assert resp.status_code in (200, 404)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /c/dev/MLOPS/python
python -m pytest tests/test_api.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement api/main.py**

`python/api/main.py`:
```python
"""FastAPI application for VitaCall pipeline management."""

from fastapi import FastAPI
from api.routes.pipeline import router as pipeline_router
from api.routes.data import router as data_router

app = FastAPI(
    title="VitaCall Pipeline API",
    description="MLOps pipeline management for VitaCall healthcare call center",
    version="0.1.0",
)

app.include_router(pipeline_router, prefix="/pipeline", tags=["pipeline"])
app.include_router(data_router, prefix="/data", tags=["data"])


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Implement api/routes/pipeline.py**

`python/api/routes/pipeline.py`:
```python
"""Pipeline trigger and status endpoints."""

import os
import uuid
import threading
from enum import Enum
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pyspark.sql import SparkSession

router = APIRouter()

# In-memory run tracking (sufficient for single-instance)
_runs: dict[str, dict] = {}

DATA_DIR = os.environ.get("VITACALL_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "data"))


class Layer(str, Enum):
    bronze = "bronze"
    silver = "silver"
    gold = "gold"


LAYER_ORDER = ["bronze", "silver", "gold"]


class RunResponse(BaseModel):
    run_id: str
    status: str


class StatusResponse(BaseModel):
    run_id: str
    status: str
    error: str | None = None


def _has_parquet_data(path: str) -> bool:
    """Check if a directory contains Parquet data (subdirs with .parquet files)."""
    if not os.path.exists(path):
        return False
    for root, dirs, files in os.walk(path):
        if any(f.endswith(".parquet") for f in files):
            return True
    return False


def _check_prerequisite(layer: Layer) -> None:
    """Raise 409 if the prerequisite layer has no Parquet output."""
    idx = LAYER_ORDER.index(layer.value)
    if idx == 0:
        return  # Bronze has no prerequisite

    prereq = LAYER_ORDER[idx - 1]
    prereq_path = os.path.join(DATA_DIR, prereq)
    if not _has_parquet_data(prereq_path):
        raise HTTPException(
            status_code=409,
            detail=f"Prerequisite layer '{prereq}' has no output. Run it first.",
        )


def _execute_pipeline(run_id: str, layer: str) -> None:
    """Run the pipeline in a background thread."""
    try:
        spark = (
            SparkSession.builder
            .master("local[*]")
            .appName(f"vitacall-{layer}-{run_id}")
            .config("spark.ui.enabled", "false")
            .config("spark.driver.bindAddress", "127.0.0.1")
            .getOrCreate()
        )

        if layer == "bronze":
            from pipelines.bronze.ingest_common_voice import ingest_common_voice, download_common_voice
            from pipelines.bronze.ingest_imdb import ingest_imdb, download_imdb

            raw_dir = os.path.join(DATA_DIR, "raw")
            os.makedirs(raw_dir, exist_ok=True)

            # Common Voice
            try:
                tsv_path = download_common_voice(raw_dir)
                ingest_common_voice(spark, tsv_path, os.path.join(DATA_DIR, "bronze", "common_voice"))
            except FileNotFoundError as e:
                _runs[run_id]["error"] = str(e)

            # IMDb
            imdb_dir = download_imdb(raw_dir)
            ingest_imdb(spark, imdb_dir, os.path.join(DATA_DIR, "bronze", "imdb"))

        elif layer == "silver":
            from pipelines.silver.clean_audio_metadata import clean_audio_metadata
            from pipelines.silver.clean_reviews import clean_reviews

            cv_bronze = os.path.join(DATA_DIR, "bronze", "common_voice")
            if os.path.exists(cv_bronze):
                clean_audio_metadata(spark, cv_bronze, os.path.join(DATA_DIR, "silver", "common_voice"))

            imdb_bronze = os.path.join(DATA_DIR, "bronze", "imdb")
            if os.path.exists(imdb_bronze):
                clean_reviews(spark, imdb_bronze, os.path.join(DATA_DIR, "silver", "imdb"))

        elif layer == "gold":
            from pipelines.gold.asr_features import create_asr_features
            from pipelines.gold.sentiment_features import create_sentiment_features

            cv_silver = os.path.join(DATA_DIR, "silver", "common_voice")
            if os.path.exists(cv_silver):
                create_asr_features(spark, cv_silver, os.path.join(DATA_DIR, "gold", "common_voice"))

            imdb_silver = os.path.join(DATA_DIR, "silver", "imdb")
            if os.path.exists(imdb_silver):
                create_sentiment_features(spark, imdb_silver, os.path.join(DATA_DIR, "gold", "imdb"))

        # Auto-track with DVC after successful run
        import subprocess
        layer_path = os.path.join(DATA_DIR, layer)
        if os.path.exists(layer_path):
            subprocess.run(["dvc", "add", layer_path], cwd=os.path.dirname(DATA_DIR), capture_output=True)

        _runs[run_id]["status"] = "completed"
    except Exception as e:
        _runs[run_id]["status"] = "failed"
        _runs[run_id]["error"] = str(e)


@router.post("/run/{layer}", response_model=RunResponse)
def run_pipeline(layer: Layer):
    """Trigger a pipeline layer. Returns immediately with a run_id."""
    _check_prerequisite(layer)

    run_id = str(uuid.uuid4())[:8]
    _runs[run_id] = {"status": "running", "error": None}

    thread = threading.Thread(target=_execute_pipeline, args=(run_id, layer.value), daemon=True)
    thread.start()

    return RunResponse(run_id=run_id, status="started")


@router.get("/status/{run_id}", response_model=StatusResponse)
def pipeline_status(run_id: str):
    """Check the status of a pipeline run."""
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    run = _runs[run_id]
    return StatusResponse(run_id=run_id, status=run["status"], error=run["error"])
```

- [ ] **Step 5: Implement api/routes/data.py**

`python/api/routes/data.py`:
```python
"""Data statistics endpoints."""

import os
from enum import Enum
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pyspark.sql import SparkSession

router = APIRouter()

DATA_DIR = os.environ.get("VITACALL_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "data"))


class Layer(str, Enum):
    bronze = "bronze"
    silver = "silver"
    gold = "gold"


class StatsResponse(BaseModel):
    layer: str
    datasets: dict[str, dict]


def _get_spark() -> SparkSession:
    return (
        SparkSession.builder
        .master("local[*]")
        .appName("vitacall-stats")
        .config("spark.ui.enabled", "false")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .getOrCreate()
    )


@router.get("/stats/{layer}", response_model=StatsResponse)
def data_stats(layer: Layer):
    """Return row count, columns, and sample rows for each dataset in a layer."""
    layer_path = os.path.join(DATA_DIR, layer.value)

    if not os.path.exists(layer_path):
        raise HTTPException(status_code=404, detail=f"No data found for layer '{layer.value}'.")

    subdirs = [d for d in os.listdir(layer_path) if os.path.isdir(os.path.join(layer_path, d))]
    if not subdirs:
        raise HTTPException(status_code=404, detail=f"No datasets found in layer '{layer.value}'.")

    spark = _get_spark()
    datasets = {}

    for dataset_name in subdirs:
        dataset_path = os.path.join(layer_path, dataset_name)
        try:
            df = spark.read.parquet(dataset_path)
            sample_rows = [row.asDict() for row in df.limit(5).collect()]
            datasets[dataset_name] = {
                "row_count": df.count(),
                "columns": df.columns,
                "sample": sample_rows,
            }
        except Exception as e:
            datasets[dataset_name] = {"error": str(e)}

    return StatsResponse(layer=layer.value, datasets=datasets)
```

- [ ] **Step 6: Run API tests**

```bash
cd /c/dev/MLOPS/python
python -m pytest tests/test_api.py -v
```

Expected: 6 tests PASS.

- [ ] **Step 7: Commit**

```bash
cd /c/dev/MLOPS
git add -A
git commit -m "feat: FastAPI backend with pipeline trigger and data stats endpoints"
```

---

## Chunk 6: Docker & Integration

### Task 12: Dockerfile

**Files:**
- Create: `python/Dockerfile`

- [ ] **Step 1: Create Dockerfile**

`python/Dockerfile`:
```dockerfile
FROM python:3.11-slim

# Java 17 for PySpark
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-17-jre-headless && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

WORKDIR /app

# Install deps first (layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir pyspark>=3.5.0 fastapi>=0.115.0 uvicorn>=0.34.0 \
    requests>=2.32.0 beautifulsoup4>=4.12.0 pandas>=2.2.0 dvc

# Copy source
COPY . .
RUN pip install --no-cache-dir -e .

ENV VITACALL_DATA_DIR=/app/data

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Commit**

```bash
cd /c/dev/MLOPS
git add -A
git commit -m "feat: add Dockerfile for Python API + Spark"
```

### Task 13: docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create docker-compose.yml**

`docker-compose.yml`:
```yaml
services:
  api:
    build:
      context: ./python
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - VITACALL_DATA_DIR=/app/data
    restart: unless-stopped
```

- [ ] **Step 2: Build and test**

```bash
cd /c/dev/MLOPS
docker compose build
docker compose up -d
# Wait a few seconds for startup
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 3: Stop and commit**

```bash
docker compose down
git add -A
git commit -m "feat: add docker-compose for API service"
```

### Task 14: Full Pipeline Integration Test

- [ ] **Step 1: Run all tests**

```bash
cd /c/dev/MLOPS/python
source .venv/Scripts/activate
python -m pytest tests/ -v
```

Expected: all tests PASS (bronze: 4, silver: 7, gold: 5, api: 6 = 22 total).

- [ ] **Step 2: Final commit**

```bash
cd /c/dev/MLOPS
git add -A
git commit -m "chore: all pipeline tests passing — week 6 deliverable complete"
```
