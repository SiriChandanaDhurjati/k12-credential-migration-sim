"""
ingestion/run_pipeline.py

Main ingestion pipeline entry point.

Orchestrates:
1. Schema detection — identify the schema version of each source CSV
2. Watermark extraction — determine which records are new since the last run
3. Schema mapping — normalise each record to the canonical staging schema
4. Staging write — insert normalised records into the SQLite staging table
5. Watermark update — advance the watermark after a successful run

Usage:
    python ingestion/run_pipeline.py --source-dir data/source/ --db data/staging.db
    python ingestion/run_pipeline.py --source-dir data/source/ --db data/staging.db --full-reload
"""

import argparse
import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.schema_detector import detect_schema_version_from_file, SchemaDetectionError
from ingestion.schema_mapper import map_record, MappingError
from ingestion.watermark import (
    get_watermark, update_watermark, get_all_watermarks,
    reset_all_watermarks, ensure_watermark_table
)

# ──────────────────────────────────────────────────────────────────────────────
# Staging schema
# ──────────────────────────────────────────────────────────────────────────────

CREATE_STAGING_TABLE = """
CREATE TABLE IF NOT EXISTS staging.student_credentials (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id              TEXT NOT NULL,
    first_name              TEXT NOT NULL,
    last_name               TEXT NOT NULL,
    preferred_name          TEXT,
    school_id               TEXT NOT NULL,
    credential_type         TEXT NOT NULL,
    issue_date              TEXT NOT NULL,       -- YYYY-MM-DD
    status                  TEXT NOT NULL,
    source_schema_version   TEXT NOT NULL,       -- v1 .. v8 (lineage)
    source_student_id       TEXT NOT NULL,       -- original value before normalisation
    staged_at               TEXT NOT NULL        -- ISO 8601 UTC
);
"""

# SQLite doesn't support schemas, so we use a flat table name
CREATE_STAGING_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS student_credentials_staging (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id              TEXT NOT NULL,
    first_name              TEXT NOT NULL,
    last_name               TEXT NOT NULL,
    preferred_name          TEXT,
    school_id               TEXT NOT NULL,
    credential_type         TEXT NOT NULL,
    issue_date              TEXT NOT NULL,
    status                  TEXT NOT NULL,
    source_schema_version   TEXT NOT NULL,
    source_student_id       TEXT NOT NULL,
    staged_at               TEXT NOT NULL
);
"""

INSERT_STAGED_RECORD = """
INSERT INTO student_credentials_staging (
    student_id, first_name, last_name, preferred_name,
    school_id, credential_type, issue_date, status,
    source_schema_version, source_student_id, staged_at
) VALUES (
    :student_id, :first_name, :last_name, :preferred_name,
    :school_id, :credential_type, :issue_date, :status,
    :source_schema_version, :source_student_id, :staged_at
)
"""

UPDATED_AT_FIELDS = {
    "v1": "updated_at",
    "v2": "last_modified",
    "v3": "modified_timestamp",
    "v4": "last_updated",
    "v5": "updated_at",
    "v6": "modified",
    "v7": "record_updated",
    "v8": "updated_at",
}


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline logic
# ──────────────────────────────────────────────────────────────────────────────

def setup_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(CREATE_STAGING_TABLE_SQLITE)
    ensure_watermark_table(conn)
    conn.commit()
    return conn


def process_file(
    filepath: Path,
    schema_version: str,
    conn: sqlite3.Connection,
    watermark: datetime,
    run_timestamp: datetime,
    batch_size: int = 1000,
) -> dict:
    """
    Read a source CSV, filter to records updated after the watermark,
    map to canonical schema, and write to the staging table in batches.

    Returns a summary dict with counts for reporting.
    """
    updated_at_field = UPDATED_AT_FIELDS[schema_version]

    total_rows = 0
    extracted_rows = 0
    mapped_rows = 0
    mapping_errors = 0
    batch = []

    with open(filepath, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for raw_record in reader:
            total_rows += 1

            # Watermark filter — only process records updated since last run
            updated_at_str = raw_record.get(updated_at_field, "")
            if updated_at_str:
                try:
                    updated_at = datetime.fromisoformat(
                        updated_at_str.replace("Z", "").replace("T", " ").split(".")[0]
                    )
                    if updated_at <= watermark:
                        continue  # skip — already processed in a previous run
                except ValueError:
                    pass  # if we can't parse updated_at, include the record

            extracted_rows += 1

            # Map to canonical schema
            try:
                canonical = map_record(raw_record, schema_version)
                batch.append(canonical)
                mapped_rows += 1
            except MappingError as e:
                mapping_errors += 1
                print(f"    [WARN] Mapping error in {filepath.name}: {e}", file=sys.stderr)
                continue

            # Write batch to staging
            if len(batch) >= batch_size:
                conn.executemany(INSERT_STAGED_RECORD, batch)
                conn.commit()
                batch = []

    # Write remaining records
    if batch:
        conn.executemany(INSERT_STAGED_RECORD, batch)
        conn.commit()

    return {
        "schema_version":  schema_version,
        "file":            filepath.name,
        "total_rows":      total_rows,
        "extracted_rows":  extracted_rows,
        "mapped_rows":     mapped_rows,
        "mapping_errors":  mapping_errors,
        "skipped_rows":    total_rows - extracted_rows,
    }


def run_pipeline(source_dir: Path, db_path: Path, full_reload: bool = False):
    """Main pipeline entry point."""
    run_timestamp = datetime.utcnow()
    print(f"\n{'='*70}")
    print(f"K12 MIGRATION PIPELINE")
    print(f"Run timestamp : {run_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Source dir    : {source_dir.resolve()}")
    print(f"Database      : {db_path.resolve()}")
    print(f"Mode          : {'FULL RELOAD' if full_reload else 'INCREMENTAL (watermark)'}")
    print(f"{'='*70}\n")

    conn = setup_db(db_path)

    if full_reload:
        print("Full reload requested — resetting all watermarks and truncating staging table.\n")
        reset_all_watermarks(conn)
        conn.execute("DELETE FROM student_credentials_staging")
        conn.commit()

    csv_files = sorted(source_dir.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {source_dir}")
        return

    print(f"Found {len(csv_files)} source file(s).\n")

    summaries = []
    total_errors = 0

    for filepath in csv_files:
        print(f"Processing: {filepath.name}")

        # Detect schema version
        try:
            schema_version, _ = detect_schema_version_from_file(filepath)
            print(f"  Schema version detected: {schema_version}")
        except SchemaDetectionError as e:
            print(f"  [ERROR] {e}", file=sys.stderr)
            total_errors += 1
            continue

        # Get watermark
        watermark = get_watermark(conn, schema_version)
        print(f"  Watermark (last processed): {watermark.strftime('%Y-%m-%d %H:%M:%S') if watermark.year > 2000 else 'EPOCH (first run)'}")

        # Process file
        summary = process_file(
            filepath=filepath,
            schema_version=schema_version,
            conn=conn,
            watermark=watermark,
            run_timestamp=run_timestamp,
        )
        summaries.append(summary)

        print(f"  Total rows in file : {summary['total_rows']:,}")
        print(f"  Rows after watermark: {summary['extracted_rows']:,}")
        print(f"  Successfully staged : {summary['mapped_rows']:,}")
        if summary['mapping_errors']:
            print(f"  Mapping errors     : {summary['mapping_errors']:,}  ← review stderr log")
            total_errors += summary['mapping_errors']

        # Advance watermark only if the run succeeded for this file
        if summary['mapping_errors'] == 0 or summary['mapped_rows'] > 0:
            update_watermark(conn, schema_version, run_timestamp, summary['mapped_rows'])
            print(f"  Watermark advanced to: {run_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        print()

    # Summary
    print(f"\n{'='*70}")
    print("RUN SUMMARY")
    print(f"{'='*70}")
    print(f"{'Schema':<10} {'File':<40} {'Staged':>10} {'Skipped':>10}")
    print("-" * 70)
    for s in summaries:
        print(f"{s['schema_version']:<10} {s['file']:<40} {s['mapped_rows']:>10,} {s['skipped_rows']:>10,}")

    total_staged = sum(s['mapped_rows'] for s in summaries)
    total_skipped = sum(s['skipped_rows'] for s in summaries)
    print("-" * 70)
    print(f"{'TOTAL':<51} {total_staged:>10,} {total_skipped:>10,}")

    print(f"\nPipeline {'COMPLETED' if total_errors == 0 else 'COMPLETED WITH WARNINGS'}.")
    if total_errors:
        print(f"⚠  {total_errors} error(s) encountered — review stderr output above.")
    print(f"{'='*70}\n")

    conn.close()
    return summaries


def main():
    parser = argparse.ArgumentParser(description="Run K12 credential migration ingestion pipeline")
    parser.add_argument("--source-dir", type=str, default="data/source/")
    parser.add_argument("--db", type=str, default="data/staging.db")
    parser.add_argument("--full-reload", action="store_true",
                        help="Reset watermarks and reload all records from all schema versions")
    args = parser.parse_args()

    run_pipeline(
        source_dir=Path(args.source_dir),
        db_path=Path(args.db),
        full_reload=args.full_reload,
    )


if __name__ == "__main__":
    main()
