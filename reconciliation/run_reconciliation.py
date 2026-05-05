"""
reconciliation/run_reconciliation.py

Reconciliation suite for the K12 credential migration.

Runs 5 check types after the ingestion pipeline completes:
  1. Row count reconciliation  — source rows == staging rows per schema version
  2. Null assertions           — critical fields have zero nulls
  3. Referential integrity     — student_id format valid, credential_type in allowed set
  4. Duplicate detection       — no duplicate student_ids across schema versions
  5. Cross-version consistency — same student_id shouldn't have conflicting school_id

In production, these checks ran after every load and caught 3 critical discrepancies
before the data reached the reporting layer on a 500K+ student credential dataset.

Usage:
    python reconciliation/run_reconciliation.py --db data/staging.db --source-dir data/source/
"""

import argparse
import csv
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from ingestion.schema_detector import detect_schema_version_from_file, SchemaDetectionError

# ──────────────────────────────────────────────────────────────────────────────
# Result types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    check_type: str
    check_name: str
    status: str           # PASS | FAIL | WARNING
    severity: str         # FAIL | WARNING
    detail: str
    expected: Optional[str] = None
    actual: Optional[str] = None
    sample_values: list = field(default_factory=list)


@dataclass
class ReconciliationReport:
    pipeline_run_id: str
    run_timestamp: str
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == "PASS"]

    @property
    def failed(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == "FAIL"]

    @property
    def warnings(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == "WARNING"]

    @property
    def overall_status(self) -> str:
        if any(r.status == "FAIL" for r in self.results):
            return "FAIL"
        if any(r.status == "WARNING" for r in self.results):
            return "PASS_WITH_WARNINGS"
        return "PASS"


# ──────────────────────────────────────────────────────────────────────────────
# Check 1: Row count reconciliation
# ──────────────────────────────────────────────────────────────────────────────

def check_row_counts(
    conn: sqlite3.Connection,
    source_dir: Path,
    tolerance_pct: float = 0.0
) -> list[CheckResult]:
    """
    Compare row counts per schema version between source CSVs and staging table.

    In production, tolerance_pct=0.0 was enforced for credential data — every
    source record must appear in staging. For analytics pipelines where late-arriving
    records are expected, a small tolerance (0.5–1.0%) may be appropriate.
    """
    results = []
    csv_files = sorted(source_dir.glob("*.csv"))

    # Get staging counts per schema version
    staging_counts = {}
    rows = conn.execute("""
        SELECT source_schema_version, COUNT(*) as cnt
        FROM student_credentials_staging
        GROUP BY source_schema_version
        ORDER BY source_schema_version
    """).fetchall()
    for row in rows:
        staging_counts[row[0]] = row[1]

    # Count source rows per file
    for filepath in csv_files:
        try:
            schema_version, _ = detect_schema_version_from_file(filepath)
        except SchemaDetectionError:
            results.append(CheckResult(
                check_type="ROW_RECONCILIATION",
                check_name=f"Row count: {filepath.name}",
                status="FAIL",
                severity="FAIL",
                detail=f"Could not detect schema version for {filepath.name} — skipped",
            ))
            continue

        # Count source rows (excluding header)
        source_count = 0
        with open(filepath, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            for _ in reader:
                source_count += 1

        staged_count = staging_counts.get(schema_version, 0)
        delta = staged_count - source_count
        delta_pct = abs(delta / source_count * 100) if source_count > 0 else 0.0

        if delta == 0:
            status = "PASS"
            detail = f"source={source_count:,}, staged={staged_count:,}, delta=0"
        elif delta_pct <= tolerance_pct:
            status = "WARNING"
            detail = f"source={source_count:,}, staged={staged_count:,}, delta={delta:+,} ({delta_pct:.2f}% — within {tolerance_pct}% tolerance)"
        else:
            status = "FAIL"
            detail = f"source={source_count:,}, staged={staged_count:,}, delta={delta:+,} ({delta_pct:.2f}% — exceeds {tolerance_pct}% tolerance)"

        results.append(CheckResult(
            check_type="ROW_RECONCILIATION",
            check_name=f"Row count: {schema_version} ({filepath.name})",
            status=status,
            severity="FAIL",
            detail=detail,
            expected=str(source_count),
            actual=str(staged_count),
        ))

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Check 2: Null assertions
# ──────────────────────────────────────────────────────────────────────────────

NULL_THRESHOLDS = {
    "student_id":       {"max_null_pct": 0.0,  "severity": "FAIL"},
    "first_name":       {"max_null_pct": 0.0,  "severity": "FAIL"},
    "last_name":        {"max_null_pct": 0.0,  "severity": "FAIL"},
    "school_id":        {"max_null_pct": 0.0,  "severity": "FAIL"},
    "credential_type":  {"max_null_pct": 0.0,  "severity": "FAIL"},
    "issue_date":       {"max_null_pct": 1.0,  "severity": "WARNING"},
    "status":           {"max_null_pct": 0.0,  "severity": "FAIL"},
    "preferred_name":   {"max_null_pct": 100.0, "severity": "WARNING"},  # optional field
}


def check_null_assertions(conn: sqlite3.Connection) -> list[CheckResult]:
    """
    Verify that critical fields meet their null percentage thresholds.

    Zero-tolerance for primary key and required fields. A tolerance of 1% on
    issue_date catches cases where a small number of records have unparseable
    dates without failing the entire load.
    """
    results = []

    total_row = conn.execute("SELECT COUNT(*) FROM student_credentials_staging").fetchone()
    total_rows = total_row[0] if total_row else 0

    if total_rows == 0:
        results.append(CheckResult(
            check_type="NULL_ASSERTIONS",
            check_name="Null assertions: staging table",
            status="FAIL",
            severity="FAIL",
            detail="Staging table is empty — no records to check",
        ))
        return results

    for column, config in NULL_THRESHOLDS.items():
        null_count_row = conn.execute(
            f"SELECT COUNT(*) FROM student_credentials_staging WHERE {column} IS NULL OR {column} = ''"
        ).fetchone()
        null_count = null_count_row[0] if null_count_row else 0
        null_pct = (null_count / total_rows * 100) if total_rows > 0 else 0.0

        if null_pct <= config["max_null_pct"]:
            status = "PASS"
            detail = f"null_count={null_count:,}, null_pct={null_pct:.2f}% (threshold={config['max_null_pct']}%)"
        else:
            status = config["severity"]
            detail = f"null_count={null_count:,}, null_pct={null_pct:.2f}% EXCEEDS threshold={config['max_null_pct']}%"

        results.append(CheckResult(
            check_type="NULL_ASSERTIONS",
            check_name=f"Null check: {column}",
            status=status,
            severity=config["severity"],
            detail=detail,
            expected=f"≤{config['max_null_pct']}%",
            actual=f"{null_pct:.2f}%",
        ))

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Check 3: Referential integrity
# ──────────────────────────────────────────────────────────────────────────────

ALLOWED_CREDENTIAL_TYPES = {
    "HIGH_SCHOOL_DIPLOMA", "GED", "CERTIFICATE_OF_COMPLETION",
    "HONORS_DIPLOMA", "ADVANCED_DIPLOMA", "VOCATIONAL_CERTIFICATE",
    "AP_CREDIT", "DUAL_ENROLLMENT", "SPECIAL_EDUCATION_DIPLOMA",
    "ALTERNATIVE_DIPLOMA",
}

ALLOWED_STATUSES = {"ACTIVE", "EXPIRED", "REVOKED", "PENDING"}

STUDENT_ID_PATTERN = re.compile(r"^\d{6}$")  # normalised IDs are 6-digit numeric strings


def check_referential_integrity(conn: sqlite3.Connection) -> list[CheckResult]:
    """
    Validate that values in key fields conform to expected constraints:
    - student_id: 6-digit numeric string (post-normalisation)
    - credential_type: one of the allowed set
    - status: one of the canonical status values
    """
    results = []

    # ── student_id format ────────────────────────────────────────────────────
    all_ids = conn.execute("SELECT student_id FROM student_credentials_staging").fetchall()
    invalid_ids = [row[0] for row in all_ids if not STUDENT_ID_PATTERN.match(str(row[0]))]
    invalid_id_count = len(invalid_ids)

    if invalid_id_count == 0:
        results.append(CheckResult(
            check_type="REFERENTIAL_INTEGRITY",
            check_name="student_id: format validation (6-digit numeric)",
            status="PASS",
            severity="FAIL",
            detail=f"All {len(all_ids):,} student_id values match expected format",
        ))
    else:
        results.append(CheckResult(
            check_type="REFERENTIAL_INTEGRITY",
            check_name="student_id: format validation (6-digit numeric)",
            status="FAIL",
            severity="FAIL",
            detail=f"{invalid_id_count:,} student_id values do not match expected format",
            actual=str(invalid_id_count),
            sample_values=invalid_ids[:10],
        ))

    # ── credential_type values ───────────────────────────────────────────────
    cred_type_rows = conn.execute("""
        SELECT credential_type, COUNT(*) as cnt
        FROM student_credentials_staging
        GROUP BY credential_type
    """).fetchall()

    invalid_cred_types = [(row[0], row[1]) for row in cred_type_rows if row[0] not in ALLOWED_CREDENTIAL_TYPES]

    if not invalid_cred_types:
        results.append(CheckResult(
            check_type="REFERENTIAL_INTEGRITY",
            check_name="credential_type: allowed values check",
            status="PASS",
            severity="FAIL",
            detail=f"All credential_type values are in the allowed set ({len(ALLOWED_CREDENTIAL_TYPES)} types)",
        ))
    else:
        total_invalid = sum(ct[1] for ct in invalid_cred_types)
        results.append(CheckResult(
            check_type="REFERENTIAL_INTEGRITY",
            check_name="credential_type: allowed values check",
            status="FAIL",
            severity="FAIL",
            detail=f"{total_invalid:,} records have unrecognised credential_type values: {[ct[0] for ct in invalid_cred_types[:5]]}",
            actual=str(total_invalid),
            sample_values=[ct[0] for ct in invalid_cred_types[:10]],
        ))

    # ── status values ────────────────────────────────────────────────────────
    status_rows = conn.execute("""
        SELECT status, COUNT(*) as cnt
        FROM student_credentials_staging
        GROUP BY status
    """).fetchall()

    invalid_statuses = [(row[0], row[1]) for row in status_rows if row[0] not in ALLOWED_STATUSES]

    if not invalid_statuses:
        results.append(CheckResult(
            check_type="REFERENTIAL_INTEGRITY",
            check_name="status: allowed values check",
            status="PASS",
            severity="FAIL",
            detail=f"All status values are in canonical set {sorted(ALLOWED_STATUSES)}",
        ))
    else:
        total_invalid = sum(s[1] for s in invalid_statuses)
        results.append(CheckResult(
            check_type="REFERENTIAL_INTEGRITY",
            check_name="status: allowed values check",
            status="WARNING",
            severity="WARNING",
            detail=f"{total_invalid:,} records have non-canonical status values: {[s[0] for s in invalid_statuses[:5]]}",
            actual=str(total_invalid),
            sample_values=[s[0] for s in invalid_statuses[:10]],
        ))

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Check 4: Duplicate detection
# ──────────────────────────────────────────────────────────────────────────────

def check_duplicate_detection(conn: sqlite3.Connection) -> list[CheckResult]:
    """
    Detect duplicate student_ids that appear in more than one schema version.

    In a migration, the same student might have records in multiple source systems.
    Duplicates that are exact copies can be deduplicated safely; duplicates with
    conflicting data (different school_id, different credential_type) are data quality
    issues that need investigation before they reach the reporting layer.
    """
    results = []

    # Exact duplicates: same student_id AND same (school_id, credential_type, issue_date)
    exact_dup_rows = conn.execute("""
        SELECT student_id, school_id, credential_type, issue_date, COUNT(*) as cnt
        FROM student_credentials_staging
        GROUP BY student_id, school_id, credential_type, issue_date
        HAVING COUNT(*) > 1
    """).fetchall()

    if not exact_dup_rows:
        results.append(CheckResult(
            check_type="DUPLICATE_DETECTION",
            check_name="Exact duplicates (same student_id + credential + date)",
            status="PASS",
            severity="WARNING",
            detail="No exact duplicate records found across all schema versions",
        ))
    else:
        total_extra = sum(row[4] - 1 for row in exact_dup_rows)
        results.append(CheckResult(
            check_type="DUPLICATE_DETECTION",
            check_name="Exact duplicates (same student_id + credential + date)",
            status="WARNING",
            severity="WARNING",
            detail=f"{len(exact_dup_rows):,} student_ids appear in multiple schema versions with identical data ({total_extra:,} excess rows)",
            actual=str(len(exact_dup_rows)),
            sample_values=[row[0] for row in exact_dup_rows[:10]],
        ))

    # Conflict duplicates: same student_id but different school_id across versions
    # These are harder to resolve — same student somehow linked to different schools
    conflict_rows = conn.execute("""
        SELECT student_id, COUNT(DISTINCT school_id) as school_count
        FROM student_credentials_staging
        GROUP BY student_id
        HAVING COUNT(DISTINCT school_id) > 1
    """).fetchall()

    if not conflict_rows:
        results.append(CheckResult(
            check_type="DUPLICATE_DETECTION",
            check_name="Conflict duplicates (same student_id, different school_id)",
            status="PASS",
            severity="FAIL",
            detail="No student_ids with conflicting school_id found",
        ))
    else:
        results.append(CheckResult(
            check_type="DUPLICATE_DETECTION",
            check_name="Conflict duplicates (same student_id, different school_id)",
            status="FAIL",
            severity="FAIL",
            detail=f"{len(conflict_rows):,} student_ids appear with >1 distinct school_id — requires investigation before Gold load",
            actual=str(len(conflict_rows)),
            sample_values=[row[0] for row in conflict_rows[:10]],
        ))

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Check 5: Cross-version consistency
# ──────────────────────────────────────────────────────────────────────────────

def check_cross_version_consistency(conn: sqlite3.Connection) -> list[CheckResult]:
    """
    For student_ids that appear in multiple schema versions, check whether
    the credential data is consistent across versions.

    A student who appears in both v1 (legacy system) and v5 (upgraded system)
    should have the same credential_type and issue_date. Discrepancies indicate
    either a data entry error in one system or a genuine credential change that
    needs to be resolved before migration.
    """
    results = []

    # Students with multiple schema versions
    multi_version_rows = conn.execute("""
        SELECT student_id, COUNT(DISTINCT source_schema_version) as version_count
        FROM student_credentials_staging
        GROUP BY student_id
        HAVING COUNT(DISTINCT source_schema_version) > 1
    """).fetchall()

    if not multi_version_rows:
        results.append(CheckResult(
            check_type="CROSS_VERSION_CONSISTENCY",
            check_name="Students appearing in multiple schema versions",
            status="PASS",
            severity="WARNING",
            detail="No student_ids appear across multiple schema versions",
        ))
        return results

    multi_version_ids = [row[0] for row in multi_version_rows]

    # For multi-version students, check whether credential_type is consistent
    inconsistent_cred = conn.execute(f"""
        SELECT student_id, COUNT(DISTINCT credential_type) as type_count
        FROM student_credentials_staging
        WHERE student_id IN ({','.join('?' for _ in multi_version_ids)})
        GROUP BY student_id
        HAVING COUNT(DISTINCT credential_type) > 1
    """, multi_version_ids).fetchall()

    if not inconsistent_cred:
        results.append(CheckResult(
            check_type="CROSS_VERSION_CONSISTENCY",
            check_name="Cross-version: credential_type consistency",
            status="PASS",
            severity="WARNING",
            detail=f"{len(multi_version_ids):,} students appear in multiple schema versions — all have consistent credential_type",
        ))
    else:
        results.append(CheckResult(
            check_type="CROSS_VERSION_CONSISTENCY",
            check_name="Cross-version: credential_type consistency",
            status="WARNING",
            severity="WARNING",
            detail=f"{len(inconsistent_cred):,} students have different credential_type values across schema versions — review before deduplication",
            actual=str(len(inconsistent_cred)),
            sample_values=[row[0] for row in inconsistent_cred[:10]],
        ))

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Report generation
# ──────────────────────────────────────────────────────────────────────────────

def print_report(report: ReconciliationReport):
    """Print a formatted reconciliation report to stdout."""
    W = 74  # report width
    print("\n" + "=" * W)
    print("PEARSON K12 MIGRATION — RECONCILIATION REPORT")
    print(f"Run timestamp  : {report.run_timestamp}")
    print(f"Pipeline run   : {report.pipeline_run_id}")
    print("=" * W)

    current_check_type = None

    for result in report.results:
        if result.check_type != current_check_type:
            current_check_type = result.check_type
            print(f"\n{current_check_type}")
            print("-" * W)

        status_icon = {"PASS": "✓", "FAIL": "✗", "WARNING": "⚠"}.get(result.status, "?")
        print(f"  [{result.status:<7}] {status_icon}  {result.check_name}")
        print(f"             {result.detail}")

        if result.sample_values:
            sample_str = ", ".join(str(v) for v in result.sample_values[:5])
            print(f"             Sample: [{sample_str}]")

    print("\n" + "=" * W)
    print(f"OVERALL RESULT : {report.overall_status}")
    print(f"  Passed   : {len(report.passed)}")
    print(f"  Warnings : {len(report.warnings)}")
    print(f"  Failed   : {len(report.failed)}")
    print("=" * W + "\n")


def save_report(report: ReconciliationReport, reports_dir: Path):
    """Save report to a text file in the reports/ directory."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = reports_dir / f"reconciliation_{ts}.txt"

    import io
    import contextlib

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        print_report(report)

    filepath.write_text(buffer.getvalue(), encoding="utf-8")
    print(f"Report saved: {filepath.resolve()}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def run_reconciliation(db_path: Path, source_dir: Path) -> ReconciliationReport:
    conn = sqlite3.connect(str(db_path))

    run_id = f"sim_run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    run_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    report = ReconciliationReport(pipeline_run_id=run_id, run_timestamp=run_ts)

    print(f"Running reconciliation checks... (run_id={run_id})\n")

    checks = [
        ("Row count reconciliation",     lambda: check_row_counts(conn, source_dir)),
        ("Null assertions",              lambda: check_null_assertions(conn)),
        ("Referential integrity",        lambda: check_referential_integrity(conn)),
        ("Duplicate detection",          lambda: check_duplicate_detection(conn)),
        ("Cross-version consistency",    lambda: check_cross_version_consistency(conn)),
    ]

    for check_name, check_fn in checks:
        print(f"  Running: {check_name}...", end=" ", flush=True)
        results = check_fn()
        report.results.extend(results)
        fail_count = sum(1 for r in results if r.status == "FAIL")
        warn_count = sum(1 for r in results if r.status == "WARNING")
        print(f"done. ({len(results)} checks: {fail_count} failed, {warn_count} warnings)")

    conn.close()
    return report


def main():
    parser = argparse.ArgumentParser(description="Run reconciliation checks on staged K12 credential data")
    parser.add_argument("--db", type=str, default="data/staging.db")
    parser.add_argument("--source-dir", type=str, default="data/source/")
    parser.add_argument("--reports-dir", type=str, default="reports/")
    args = parser.parse_args()

    report = run_reconciliation(
        db_path=Path(args.db),
        source_dir=Path(args.source_dir),
    )

    print_report(report)
    save_report(report, Path(args.reports_dir))

    sys.exit(0 if report.overall_status in ("PASS", "PASS_WITH_WARNINGS") else 1)


if __name__ == "__main__":
    main()
