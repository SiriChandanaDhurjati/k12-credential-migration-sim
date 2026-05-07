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

CREATE TABLE IF NOT EXISTS watermark_control (
    schema_version      TEXT PRIMARY KEY,
    last_processed_at   TEXT NOT NULL,
    last_run_row_count  INTEGER,
    last_run_timestamp  TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);