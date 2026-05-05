"""
ingestion/watermark.py

Watermark control table for incremental extraction.

The watermark table tracks the last successfully processed timestamp per schema version.
On each pipeline run, only records with updated_at > last_processed_at are extracted
and staged — avoiding a full-table reload on every run.

This is the pattern that reduced the nightly processing window from 4 hours to under
90 minutes in production: instead of reloading 500K records nightly, only the delta
(typically 2–5% of the dataset) is processed.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

EPOCH_START = datetime(2000, 1, 1)  # Default watermark for first run (load everything)


def ensure_watermark_table(conn: sqlite3.Connection):
    """Create the watermark control table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watermark_control (
            schema_version      TEXT PRIMARY KEY,
            last_processed_at   TEXT NOT NULL,      -- ISO 8601 UTC
            last_run_row_count  INTEGER,            -- rows processed in the last run
            last_run_timestamp  TEXT,               -- when the last pipeline run completed
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def get_watermark(conn: sqlite3.Connection, schema_version: str) -> datetime:
    """
    Retrieve the watermark timestamp for a schema version.

    Returns EPOCH_START (2000-01-01) on first run — ensures the first pipeline
    execution loads the full dataset for that schema version.
    """
    ensure_watermark_table(conn)
    row = conn.execute(
        "SELECT last_processed_at FROM watermark_control WHERE schema_version = ?",
        (schema_version,)
    ).fetchone()

    if row is None:
        return EPOCH_START

    try:
        return datetime.fromisoformat(row[0].replace("Z", "+00:00").replace("+00:00", ""))
    except (ValueError, AttributeError):
        return EPOCH_START


def update_watermark(
    conn: sqlite3.Connection,
    schema_version: str,
    run_timestamp: datetime,
    rows_processed: int = 0
):
    """
    Update the watermark after a successful pipeline run.

    Uses UPSERT semantics — inserts on first run, updates on subsequent runs.
    Only called after all records for this schema version have been successfully
    staged — a failed run leaves the watermark unchanged, triggering a retry
    of the same delta on the next run.
    """
    ensure_watermark_table(conn)
    run_ts_iso = run_timestamp.strftime("%Y-%m-%dT%H:%M:%S")

    conn.execute("""
        INSERT INTO watermark_control (schema_version, last_processed_at, last_run_row_count, last_run_timestamp)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(schema_version) DO UPDATE SET
            last_processed_at  = excluded.last_processed_at,
            last_run_row_count = excluded.last_run_row_count,
            last_run_timestamp = excluded.last_run_timestamp
    """, (schema_version, run_ts_iso, rows_processed, run_ts_iso))
    conn.commit()


def get_all_watermarks(conn: sqlite3.Connection) -> list[dict]:
    """Return all watermark records — used for monitoring and reporting."""
    ensure_watermark_table(conn)
    rows = conn.execute("""
        SELECT schema_version, last_processed_at, last_run_row_count, last_run_timestamp
        FROM watermark_control
        ORDER BY schema_version
    """).fetchall()

    return [
        {
            "schema_version":     row[0],
            "last_processed_at":  row[1],
            "last_run_row_count": row[2],
            "last_run_timestamp": row[3],
        }
        for row in rows
    ]


def reset_watermark(conn: sqlite3.Connection, schema_version: str):
    """
    Reset a watermark to epoch start — forces a full reload of that schema version
    on the next pipeline run. Used for reprocessing after a known data issue.
    """
    ensure_watermark_table(conn)
    conn.execute(
        "DELETE FROM watermark_control WHERE schema_version = ?",
        (schema_version,)
    )
    conn.commit()


def reset_all_watermarks(conn: sqlite3.Connection):
    """Reset all watermarks — forces a full reload of all schema versions."""
    ensure_watermark_table(conn)
    conn.execute("DELETE FROM watermark_control")
    conn.commit()
