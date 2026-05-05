"""
ingestion/schema_detector.py

Identifies the schema version of a source CSV by fingerprinting its column set.
Source files don't carry a schema_version header — the detector derives the version
from which columns are present.

This mirrors the pattern used in production where files arrive from legacy systems
without version metadata and must be classified before any mapping logic runs.
"""

import csv
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "data_generator"))
from schema_definitions import SCHEMA_FINGERPRINTS


class SchemaDetectionError(Exception):
    pass


def detect_schema_version(columns: list[str]) -> str:
    """
    Identify the schema version from a list of column names.

    Strategy: each schema version has a unique fingerprint — a frozenset of
    columns that appears in that version and no other. We check whether the
    fingerprint is a subset of the file's columns (allowing for extra columns
    in case the source system added fields not in our mapping).

    Args:
        columns: List of column names from the source CSV header row.

    Returns:
        Version string (e.g. "v1", "v2", ... "v8").

    Raises:
        SchemaDetectionError: If no fingerprint matches the column set.
    """
    column_set = frozenset(columns)

    matches = []
    for version, fingerprint in SCHEMA_FINGERPRINTS.items():
        if fingerprint.issubset(column_set):
            matches.append(version)

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        # Ambiguous match — pick the version whose fingerprint has the most overlap
        # (i.e. the most specific match). This handles cases where one schema is
        # a superset of another.
        best = max(matches, key=lambda v: len(SCHEMA_FINGERPRINTS[v]))
        return best

    # No match — the column set doesn't correspond to any known schema version
    raise SchemaDetectionError(
        f"Unknown schema version. Column set does not match any of the 8 known fingerprints.\n"
        f"Columns found: {sorted(columns)}\n"
        f"Known fingerprints:\n" +
        "\n".join(f"  {v}: {sorted(fp)}" for v, fp in SCHEMA_FINGERPRINTS.items())
    )


def detect_schema_version_from_file(filepath: Path) -> tuple[str, list[str]]:
    """
    Open a CSV file, read the header row, and detect the schema version.

    Returns:
        Tuple of (schema_version, column_names).
    """
    with open(filepath, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        headers = next(reader)

    version = detect_schema_version(headers)
    return version, headers


def detect_all_files(source_dir: Path) -> dict[str, str]:
    """
    Detect schema versions for all CSV files in a directory.

    Returns:
        Dict mapping filepath → schema_version.
    """
    results = {}
    csv_files = sorted(source_dir.glob("*.csv"))

    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {source_dir}")

    for filepath in csv_files:
        try:
            version, _ = detect_schema_version_from_file(filepath)
            results[str(filepath)] = version
        except SchemaDetectionError as e:
            results[str(filepath)] = f"UNKNOWN: {e}"

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Detect schema versions of source CSV files")
    parser.add_argument("--source-dir", type=str, default="data/source/")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    detections = detect_all_files(source_dir)

    print(f"\nSchema detection results for {source_dir}:\n")
    print(f"{'File':<40} {'Detected version'}")
    print("-" * 60)
    for filepath, version in detections.items():
        filename = Path(filepath).name
        print(f"{filename:<40} {version}")
