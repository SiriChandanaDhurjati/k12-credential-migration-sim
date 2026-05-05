"""
data_generator/generate_source_data.py

Generates synthetic student credential data across 8 schema versions.
Each version uses different column names, date formats, and name conventions —
simulating the real-world accumulation of schema changes across software upgrades
and regional implementations.

Usage:
    python data_generator/generate_source_data.py --total-records 500000 --output-dir data/source/
    python data_generator/generate_source_data.py --total-records 10000  --output-dir data/source/  # quick dev run
"""

import argparse
import csv
import os
import random
import string
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from schema_definitions import SCHEMA_DEFINITIONS
from name_pools import FIRST_NAMES, LAST_NAMES, SCHOOL_IDS, CREDENTIAL_TYPES, STATUS_VALUES


def generate_student_id(schema_version: str) -> str:
    """Generate a student ID in the format expected by each schema version."""
    base = f"{random.randint(100000, 999999)}"
    prefixes = {
        "v1": "STU", "v2": "S", "v3": "stu",
        "v4": "LRN", "v5": "STU", "v6": "",
        "v7": "SN", "v8": "UID"
    }
    prefix = prefixes.get(schema_version, "STU")
    return f"{prefix}{base}"


def generate_date(schema_version: str, base_date: datetime) -> str:
    """Return a date string in the format used by each schema version."""
    formats = {
        "v1": "%Y-%m-%dT%H:%M:%S",   # ISO 8601 with time
        "v2": "%m/%d/%Y",              # US format
        "v3": "%Y-%m-%d",             # ISO date only
        "v4": "%Y-%m-%d",             # ISO date only
        "v5": "%d-%b-%Y",             # e.g. 15-Nov-2021
        "v6": "%Y-%m-%dT%H:%M:%SZ",  # ISO 8601 with Z
        "v7": "%m-%d-%Y",             # US with dashes
        "v8": "%Y-%m-%d",             # ISO date only
    }
    fmt = formats.get(schema_version, "%Y-%m-%d")
    return base_date.strftime(fmt)


def generate_status(schema_version: str) -> str:
    """Return a status value using the vocabulary of each schema version."""
    status_maps = {
        "v1": ["ACTIVE", "EXPIRED", "REVOKED", "PENDING"],
        "v2": ["Active", "Expired", "Revoked", "Pending"],
        "v3": ["ACT", "EXP", "REV", "PND"],
        "v4": ["A", "E", "R", "P"],
        "v5": ["ACTIVE", "EXPIRED", "REVOKED", "PENDING"],
        "v6": ["active", "expired", "revoked", "pending"],
        "v7": ["Active", "Expired", "Revoked", "Pending"],
        "v8": ["ISSUED", "EXPIRED", "REVOKED", "DRAFT"],
    }
    return random.choice(status_maps.get(schema_version, ["ACTIVE", "EXPIRED"]))


def generate_missing_value(schema_version: str) -> str:
    """Each schema version has a different convention for missing optional data."""
    missing_conventions = {
        "v1": "",
        "v2": "N/A",
        "v3": "",
        "v4": "UNKNOWN",
        "v5": "",
        "v6": "null",
        "v7": "",
        "v8": "N/A",
    }
    return missing_conventions.get(schema_version, "")


def build_record_v1(student_id: str, first: str, last: str, school_id: str,
                     cred_type: str, issue_date: str, status: str,
                     updated_at: str, preferred_name: str) -> dict:
    """v1: single student_name field, camelCase columns, ISO 8601 dates."""
    return {
        "student_id":      student_id,
        "student_name":    f"{first} {last}",
        "schoolId":        school_id,
        "credentialType":  cred_type,
        "issueDate":       issue_date,
        "status":          status,
        "preferred_name":  preferred_name,
        "updated_at":      updated_at,
    }


def build_record_v2(student_id: str, first: str, last: str, school_id: str,
                     cred_type: str, issue_date: str, status: str,
                     updated_at: str, preferred_name: str) -> dict:
    """v2: split name, US date format MM/DD/YYYY, 'N/A' for missing."""
    return {
        "studentId":         student_id,
        "first_name":        first,
        "last_name":         last,
        "school_id":         school_id,
        "cred_type":         cred_type,
        "issue_date":        issue_date,
        "credentialStatus":  status,
        "preferredName":     preferred_name,
        "last_modified":     updated_at,
    }


def build_record_v3(student_id: str, first: str, last: str, school_id: str,
                     cred_type: str, issue_date: str, status: str,
                     updated_at: str, preferred_name: str) -> dict:
    """v3: lowercase snake_case, abbreviated status codes, no preferred_name."""
    return {
        "stu_id":               student_id,
        "firstName":            first,
        "lastName":             last,
        "school_code":          school_id,
        "credential_category":  cred_type,
        "issued_on":            issue_date,
        "status_code":          status,
        "modified_timestamp":   updated_at,
    }


def build_record_v4(student_id: str, first: str, last: str, school_id: str,
                     cred_type: str, issue_date: str, status: str,
                     updated_at: str, preferred_name: str) -> dict:
    """v4: given_name/family_name split, institution_id, single-char status."""
    return {
        "learner_id":       student_id,
        "given_name":       first,
        "family_name":      last,
        "institution_id":   school_id,
        "type_cd":          cred_type,
        "date_issued":      issue_date,
        "cred_status":      status,
        "pref_name":        preferred_name,
        "last_updated":     updated_at,
    }


def build_record_v5(student_id: str, first: str, last: str, school_id: str,
                     cred_type: str, issue_date: str, status: str,
                     updated_at: str, preferred_name: str) -> dict:
    """v5: single name field, DD-Mon-YYYY date, school_ref."""
    return {
        "student_id":       student_id,
        "student_name":     f"{first} {last}",
        "school_ref":       school_id,
        "credential_type":  cred_type,
        "issue_dt":         issue_date,
        "status":           status,
        "updated_at":       updated_at,
    }


def build_record_v6(student_id: str, first: str, last: str, school_id: str,
                     cred_type: str, issue_date: str, status: str,
                     updated_at: str, preferred_name: str) -> dict:
    """v6: minimal field names, lowercase status, 'null' string for missing."""
    return {
        "id":           student_id,
        "name_first":   first,
        "name_last":    last,
        "schl_id":      school_id,
        "credType":     cred_type,
        "issuedDate":   issue_date,
        "state":        status,
        "modified":     updated_at,
    }


def build_record_v7(student_id: str, first: str, last: str, school_id: str,
                     cred_type: str, issue_date: str, status: str,
                     updated_at: str, preferred_name: str) -> dict:
    """v7: student_number, MM-DD-YYYY dates, cert_ prefix naming."""
    return {
        "student_number":   student_id,
        "first_name":       first,
        "last_name":        last,
        "school_number":    school_id,
        "cert_type":        cred_type,
        "cert_date":        issue_date,
        "cert_status":      status,
        "preferred_name":   preferred_name,
        "record_updated":   updated_at,
    }


def build_record_v8(student_id: str, first: str, last: str, school_id: str,
                     cred_type: str, issue_date: str, status: str,
                     updated_at: str, preferred_name: str) -> dict:
    """v8: uid naming, full_name single field, ISSUED/REVOKED/EXPIRED vocabulary."""
    return {
        "student_uid":          student_id,
        "full_name":            f"{first} {last}",
        "school_id":            school_id,
        "qualification_type":   cred_type,
        "issue_date":           issue_date,
        "credential_state":     status,
        "preferred_name":       preferred_name,
        "updated_at":           updated_at,
    }


RECORD_BUILDERS: dict[str, Callable] = {
    "v1": build_record_v1,
    "v2": build_record_v2,
    "v3": build_record_v3,
    "v4": build_record_v4,
    "v5": build_record_v5,
    "v6": build_record_v6,
    "v7": build_record_v7,
    "v8": build_record_v8,
}


def generate_base_date() -> datetime:
    """Random issue date between 2015 and 2023."""
    start = datetime(2015, 1, 1)
    end = datetime(2023, 12, 31)
    delta = end - start
    return start + timedelta(days=random.randint(0, delta.days))


def generate_updated_at(issue_date: datetime) -> datetime:
    """updated_at is always >= issue_date, within 90 days after."""
    days_after = random.randint(0, 90)
    return issue_date + timedelta(days=days_after)


def should_include_optional_field(field: str, schema_version: str) -> bool:
    """
    Some schema versions don't have preferred_name at all.
    Others have it but it's often empty.
    """
    no_preferred_name_versions = {"v3", "v5", "v6"}
    if schema_version in no_preferred_name_versions:
        return False
    return random.random() > 0.60  # 40% of records have a preferred name


def generate_records_for_version(schema_version: str, count: int) -> list[dict]:
    records = []
    builder = RECORD_BUILDERS[schema_version]

    for _ in range(count):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        school_id = random.choice(SCHOOL_IDS)
        cred_type = random.choice(CREDENTIAL_TYPES)
        student_id = generate_student_id(schema_version)

        issue_dt = generate_base_date()
        updated_dt = generate_updated_at(issue_dt)

        issue_date_str = generate_date(schema_version, issue_dt)
        updated_at_str = generate_date("v1", updated_dt)  # updated_at always ISO

        status = generate_status(schema_version)

        has_preferred = should_include_optional_field("preferred_name", schema_version)
        preferred_name = (
            random.choice(FIRST_NAMES) if has_preferred
            else generate_missing_value(schema_version)
        )

        record = builder(
            student_id=student_id,
            first=first,
            last=last,
            school_id=school_id,
            cred_type=cred_type,
            issue_date=issue_date_str,
            status=status,
            updated_at=updated_at_str,
            preferred_name=preferred_name,
        )
        records.append(record)

    return records


def distribute_records(total: int, num_versions: int = 8) -> list[int]:
    """Distribute total records across 8 versions with some variance."""
    base = total // num_versions
    counts = [base] * num_versions
    remainder = total - sum(counts)
    for i in range(remainder):
        counts[i] += 1
    # Add ±10% variance to make distribution realistic
    for i in range(num_versions):
        variance = int(counts[i] * 0.10)
        counts[i] += random.randint(-variance, variance)
    # Normalise back to total
    delta = total - sum(counts)
    counts[0] += delta
    return counts


def write_csv(records: list[dict], filepath: Path):
    if not records:
        return
    fieldnames = list(records[0].keys())
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic K12 credential data")
    parser.add_argument("--total-records", type=int, default=500_000,
                        help="Total records to generate across all schema versions")
    parser.add_argument("--output-dir", type=str, default="data/source/",
                        help="Directory to write output CSV files")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility")
    args = parser.parse_args()

    random.seed(args.seed)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    versions = ["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8"]
    counts = distribute_records(args.total_records, len(versions))

    print(f"Generating {args.total_records:,} student credential records across {len(versions)} schema versions...")
    print(f"Output directory: {output_dir.resolve()}\n")

    total_written = 0
    for version, count in zip(versions, counts):
        filepath = output_dir / f"credentials_{version}.csv"
        records = generate_records_for_version(version, count)
        write_csv(records, filepath)
        total_written += len(records)
        print(f"  {version}: {len(records):>8,} records → {filepath.name}")

    print(f"\nDone. {total_written:,} total records written to {output_dir.resolve()}/")


if __name__ == "__main__":
    main()
