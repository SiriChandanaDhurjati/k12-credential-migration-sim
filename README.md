# Pearson K12 Credential Migration Simulator

A simulation of the core data engineering challenges from a real-world credential data migration — normalising student records across 8 schema versions into a unified reporting layer, implementing watermark-based incremental extraction, and running zero-tolerance reconciliation to validate every record before it's declared migrated.

> **Why "simulator"?** The architecture and reconciliation patterns in this repo come from production experience on a K12 data migration at scale. Client data and proprietary pipeline configurations can't be shared. What can be shared is the engineering: the schema normalisation logic, the watermark incremental patterns, and the reconciliation scripts that caught 3 critical discrepancies before production release. This repo rebuilds those patterns from scratch using synthetic data so they can be examined, tested, and run end-to-end by anyone.

---

## The Problem

Student credential data doesn't arrive in a clean, consistent format. It accumulates across years of software upgrades, regional customisation, and different vendor implementations — the same underlying information spread across 8 different schema versions. A student's credential type might be in `credentialType`, `cred_type`, `credential_category`, or `type_cd` depending on which version of the source system recorded it. Dates might be ISO strings in one schema and MM/DD/YYYY in another. Some versions have a single `student_name` field; others split it into `first_name` and `last_name`; others add a `preferred_name`.

Migrating this data into a single unified reporting layer requires:

1. **Schema mapping** — a reliable translation from each of the 8 source schemas to a canonical target schema
2. **Incremental extraction** — processing only new and changed records on each pipeline run, not reloading the full dataset every night
3. **Zero-tolerance reconciliation** — verifying that every source row is accounted for in the target, with no data loss and no corruption across any schema version

This simulator implements all three patterns using synthetic student credential data generated to match the shape and complexity of the real migration.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Synthetic Data Generator                                            │
│  Produces 8 CSV files — one per schema version                      │
│  ~500K student credential records total, distributed across schemas  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Ingestion Layer (Python / ADF-pattern)                             │
│  Schema detection → version-specific mapping → canonical staging    │
│  Watermark table tracks last_processed_at per source schema         │
│  Only new/changed records extracted per pipeline run                │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Staging Layer (SQLite / SQL Server)                                │
│  Unified schema: all 8 versions normalised into single table        │
│  source_schema_version tracked on every row for lineage             │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Reconciliation Layer                                               │
│  Row-count reconciliation per source schema                         │
│  Null assertion checks on critical fields                           │
│  Referential integrity validation                                   │
│  Duplicate detection across schema versions                         │
│  Cross-version consistency checks                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## The 8 Schema Versions

This is the core challenge the simulator recreates. The same student credential, represented 8 different ways:

| Field (canonical) | v1 | v2 | v3 | v4 | v5 | v6 | v7 | v8 |
|---|---|---|---|---|---|---|---|---|
| student_id | `student_id` | `studentId` | `stu_id` | `learner_id` | `student_id` | `id` | `student_number` | `student_uid` |
| credential_type | `credentialType` | `cred_type` | `credential_category` | `type_cd` | `credential_type` | `credType` | `cert_type` | `qualification_type` |
| issue_date | `issueDate` | `issue_date` | `issued_on` | `date_issued` | `issue_dt` | `issuedDate` | `cert_date` | `issue_date` |
| student_name | `student_name` (single) | `first_name` + `last_name` | `firstName` + `lastName` | `given_name` + `family_name` | `student_name` (single) | `name_first` + `name_last` | `first_name` + `last_name` | `full_name` (single) |
| school_id | `schoolId` | `school_id` | `school_code` | `institution_id` | `school_ref` | `schl_id` | `school_number` | `school_id` |
| status | `status` | `credentialStatus` | `status_code` | `cred_status` | `status` | `state` | `cert_status` | `credential_state` |
| date format | ISO 8601 | `MM/DD/YYYY` | ISO 8601 | `YYYY-MM-DD` | `DD-Mon-YYYY` | ISO 8601 | `MM-DD-YYYY` | ISO 8601 |

Each schema version also has different nullable fields, different allowed values for status codes, and different conventions for representing missing data (empty string vs NULL vs `"N/A"` vs `"UNKNOWN"`).

---

## Getting Started

```bash
git clone https://github.com/SiriChandanaDhurjati/pearson-k12-migration-sim.git
cd pearson-k12-migration-sim

pip install -r requirements.txt

# Step 1: Generate synthetic source data (8 schema versions, ~500K records)
python data_generator/generate_source_data.py --total-records 500000 --output-dir data/source/

# Step 2: Run the ingestion pipeline (schema detection + normalisation + watermark)
python ingestion/run_pipeline.py --source-dir data/source/ --db data/staging.db

# Step 3: Run the reconciliation suite
python reconciliation/run_reconciliation.py --db data/staging.db --source-dir data/source/

# Step 4: View reconciliation report
cat reports/reconciliation_report.txt
```

---

## Repository Structure

```
pearson-k12-migration-sim/
│
├── data_generator/
│   ├── generate_source_data.py       # Generates 8 CSV files with schema variations
│   ├── schema_definitions.py         # The 8 schema mappings
│   └── name_pools.py                 # Synthetic name/school data pools
│
├── ingestion/
│   ├── run_pipeline.py               # Main pipeline entry point
│   ├── schema_detector.py            # Detects schema version from column fingerprint
│   ├── schema_mapper.py              # Maps each version to canonical schema
│   ├── watermark.py                  # Watermark control table management
│   ├── date_normaliser.py            # Handles 5 date formats across schemas
│   └── staging_writer.py             # Writes normalised records to SQLite
│
├── reconciliation/
│   ├── run_reconciliation.py         # Orchestrates all reconciliation checks
│   ├── row_count_reconciliation.py   # Source vs staging count per schema version
│   ├── null_assertions.py            # Critical field null checks
│   ├── referential_integrity.py      # student_id and school_id validity checks
│   ├── duplicate_detection.py        # Cross-schema duplicate identification
│   └── cross_version_consistency.py  # Same student_id, conflicting values across versions
│
├── sql/
│   ├── create_staging_schema.sql     # Canonical staging table DDL
│   ├── create_watermark_table.sql    # Watermark control table DDL
│   └── reconciliation_queries.sql    # Reusable SQL for manual spot-checking
│
├── tests/
│   ├── test_schema_detector.py
│   ├── test_schema_mapper.py
│   ├── test_watermark.py
│   └── test_reconciliation.py
│
├── requirements.txt
└── reports/                          # Generated reconciliation reports (gitignored except samples)
    └── sample_reconciliation_report.txt
```

---

## Key Engineering Patterns

### Schema detection without hardcoding version numbers

Source files don't carry a `schema_version` header. The detector identifies which of the 8 versions a file belongs to by fingerprinting the column set:

```python
# From ingestion/schema_detector.py
SCHEMA_FINGERPRINTS = {
    "v1": frozenset(["student_id", "credentialType", "issueDate", "student_name", "schoolId", "status"]),
    "v2": frozenset(["studentId", "cred_type", "issue_date", "first_name", "last_name", "school_id", "credentialStatus"]),
    # ... all 8 versions
}

def detect_schema_version(df_columns: list[str]) -> str:
    column_set = frozenset(df_columns)
    for version, fingerprint in SCHEMA_FINGERPRINTS.items():
        if fingerprint.issubset(column_set):
            return version
    raise ValueError(f"Unknown schema version. Columns: {sorted(df_columns)}")
```

### Watermark incremental extraction

The watermark table tracks the last processed timestamp per schema version. On each run, only records updated after the watermark are extracted and processed. This mirrors the pattern used in production to reduce a 4-hour nightly full-table refresh to under 90 minutes.

```python
# From ingestion/watermark.py
def get_watermark(conn, schema_version: str) -> datetime:
    row = conn.execute(
        "SELECT last_processed_at FROM watermark_control WHERE schema_version = ?",
        (schema_version,)
    ).fetchone()
    return row[0] if row else datetime(2000, 1, 1)  # epoch start for first run

def update_watermark(conn, schema_version: str, run_timestamp: datetime):
    conn.execute("""
        INSERT INTO watermark_control (schema_version, last_processed_at)
        VALUES (?, ?)
        ON CONFLICT(schema_version) DO UPDATE SET last_processed_at = excluded.last_processed_at
    """, (schema_version, run_timestamp))
    conn.commit()
```

### Zero-tolerance row reconciliation

Every source record must arrive in the staging table. The reconciliation script counts rows per schema version in the source CSVs, counts staging rows with that `source_schema_version` value, and flags any delta as a FAIL — not a warning, not a tolerance band. For credential data, every row matters.

See `reconciliation/row_count_reconciliation.py` for the full implementation.

---

## Sample Reconciliation Report

```
==========================================================================
PEARSON K12 MIGRATION — RECONCILIATION REPORT
Run timestamp : 2024-11-15 02:14:33 UTC
Pipeline run  : sim_run_20241115_001
==========================================================================

ROW COUNT RECONCILIATION
----------------------------------------------------------------------------------
Schema  | Source rows | Staged rows | Delta | Status
----------------------------------------------------------------------------------
v1      |      62,441 |      62,441 |     0 | PASS
v2      |      78,203 |      78,203 |     0 | PASS
v3      |      55,019 |      55,019 |     0 | PASS
v4      |      67,834 |      67,834 |     0 | PASS
v5      |      72,108 |      72,108 |     0 | PASS
v6      |      48,991 |      48,991 |     0 | PASS
v7      |      63,217 |      63,217 |     0 | PASS
v8      |      52,187 |      52,187 |     0 | PASS
----------------------------------------------------------------------------------
TOTAL   |     500,000 |     500,000 |     0 | PASS ✓

NULL ASSERTIONS
----------------------------------------------------------------------------------
Column            | Null count | Null % | Threshold | Status
----------------------------------------------------------------------------------
student_id        |          0 |  0.00% |     0.00% | PASS
credential_type   |          0 |  0.00% |     0.00% | PASS
issue_date        |        312 |  0.06% |     1.00% | PASS
school_id         |          0 |  0.00% |     0.00% | PASS
status            |          0 |  0.00% |     0.00% | PASS
preferred_name    |    187,443 | 37.49% |    50.00% | PASS

REFERENTIAL INTEGRITY
----------------------------------------------------------------------------------
Check                              | Orphans | Status
----------------------------------------------------------------------------------
student_id → valid format (regex) |       0 | PASS
school_id  → known school list     |       0 | PASS
credential_type → allowed values   |       0 | PASS

DUPLICATE DETECTION
----------------------------------------------------------------------------------
Duplicate student_id across all versions : 0       | PASS
Same student_id, conflicting school_id   : 0       | PASS

==========================================================================
OVERALL RESULT: PASS — 500,000 records migrated with zero data loss
==========================================================================
```

---

*Built to demonstrate production migration engineering patterns: multi-version schema normalisation, watermark-based incremental extraction, and zero-tolerance reconciliation on credential data at scale.*
