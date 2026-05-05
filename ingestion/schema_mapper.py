"""
ingestion/schema_mapper.py

Maps each of the 8 source schema versions to the canonical staging schema.

The canonical schema is:
    student_id          — normalised student identifier (prefix stripped)
    first_name          — separated from combined name fields where necessary
    last_name           — separated from combined name fields where necessary
    preferred_name      — nullable; empty string becomes NULL
    school_id           — normalised school identifier
    credential_type     — normalised to uppercase underscore format
    issue_date          — parsed and converted to ISO 8601 date (YYYY-MM-DD)
    status              — normalised to canonical status vocabulary
    source_schema_version — preserved for lineage tracing
    source_student_id   — original student_id value before normalisation
    staged_at           — timestamp when the record was written to staging
"""

import re
from datetime import datetime
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "data_generator"))
from schema_definitions import SCHEMA_DEFINITIONS


# ──────────────────────────────────────────────────────────────────────────────
# Date normalisation
# ──────────────────────────────────────────────────────────────────────────────

DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%SZ",  # v6: ISO with Z
    "%Y-%m-%dT%H:%M:%S",   # v1: ISO with time
    "%Y-%m-%d",            # v3, v4, v8: ISO date only
    "%m/%d/%Y",            # v2: US slash
    "%m-%d-%Y",            # v7: US dash
    "%d-%b-%Y",            # v5: DD-Mon-YYYY (e.g. 15-Nov-2021)
]


def parse_date(date_str: str) -> Optional[datetime]:
    """Try each known date format until one parses successfully."""
    if not date_str or date_str.strip() in ("", "null", "N/A", "UNKNOWN"):
        return None
    date_str = date_str.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def normalise_date(date_str: str) -> Optional[str]:
    """Return date as YYYY-MM-DD string, or None if unparseable."""
    dt = parse_date(date_str)
    return dt.strftime("%Y-%m-%d") if dt else None


# ──────────────────────────────────────────────────────────────────────────────
# Status normalisation
# ──────────────────────────────────────────────────────────────────────────────

STATUS_NORMALISATION = {
    # v1, v5: uppercase
    "ACTIVE": "ACTIVE", "EXPIRED": "EXPIRED", "REVOKED": "REVOKED", "PENDING": "PENDING",
    # v2, v7: title case
    "Active": "ACTIVE", "Expired": "EXPIRED", "Revoked": "REVOKED", "Pending": "PENDING",
    # v3: abbreviated
    "ACT": "ACTIVE", "EXP": "EXPIRED", "REV": "REVOKED", "PND": "PENDING",
    # v4: single char
    "A": "ACTIVE", "E": "EXPIRED", "R": "REVOKED", "P": "PENDING",
    # v6: lowercase
    "active": "ACTIVE", "expired": "EXPIRED", "revoked": "REVOKED", "pending": "PENDING",
    # v8: different vocabulary
    "ISSUED": "ACTIVE", "DRAFT": "PENDING",
}


def normalise_status(raw_status: str) -> str:
    """Map any source status value to the canonical set."""
    return STATUS_NORMALISATION.get(raw_status.strip(), "UNKNOWN")


# ──────────────────────────────────────────────────────────────────────────────
# Student ID normalisation
# ──────────────────────────────────────────────────────────────────────────────

STUDENT_ID_PREFIX_PATTERN = re.compile(r"^[A-Za-z]+-?([0-9]+)$")


def normalise_student_id(raw_id: str) -> str:
    """
    Strip schema-specific prefixes and return the numeric core.
    Examples:
        STU123456  → 123456
        S123456    → 123456
        LRN123456  → 123456
        UID123456  → 123456
        SN123456   → 123456
        123456     → 123456  (already numeric — v6 'id' field)
    """
    raw_id = raw_id.strip()
    match = STUDENT_ID_PREFIX_PATTERN.match(raw_id)
    if match:
        return match.group(1)
    # If no prefix pattern matches, return as-is (numeric IDs from v6)
    return re.sub(r"[^0-9]", "", raw_id) or raw_id


# ──────────────────────────────────────────────────────────────────────────────
# Name splitting
# ──────────────────────────────────────────────────────────────────────────────

def split_full_name(full_name: str) -> tuple[str, str]:
    """
    Split a 'First Last' combined name field into first and last components.
    Handles: single word, two words, three+ words (last word = family name).
    """
    parts = full_name.strip().split()
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return (parts[0], "")
    return (" ".join(parts[:-1]), parts[-1])


# ──────────────────────────────────────────────────────────────────────────────
# Credential type normalisation
# ──────────────────────────────────────────────────────────────────────────────

def normalise_credential_type(raw_type: str) -> str:
    """Normalise credential type to uppercase underscore format."""
    return raw_type.strip().upper().replace(" ", "_").replace("-", "_")


# ──────────────────────────────────────────────────────────────────────────────
# Missing value handling
# ──────────────────────────────────────────────────────────────────────────────

MISSING_VALUES = {"", "n/a", "null", "unknown", "none", "na"}


def clean_optional(value: Optional[str], schema_version: str) -> Optional[str]:
    """
    Return None for any value that represents 'missing' in this schema version.
    Preserves legitimate empty-string-as-missing conventions.
    """
    if value is None:
        return None
    if value.strip().lower() in MISSING_VALUES:
        return None
    return value.strip() or None


# ──────────────────────────────────────────────────────────────────────────────
# Main mapper
# ──────────────────────────────────────────────────────────────────────────────

class MappingError(Exception):
    pass


def map_record(raw_record: dict, schema_version: str) -> dict:
    """
    Map a raw source record to the canonical staging schema.

    Args:
        raw_record: Dict of field_name → value from the source CSV row.
        schema_version: One of "v1" .. "v8".

    Returns:
        Dict conforming to the canonical staging schema.

    Raises:
        MappingError: If a required field cannot be extracted.
    """
    defn = SCHEMA_DEFINITIONS[schema_version]
    now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── student_id ──────────────────────────────────────────────────────────
    raw_student_id = raw_record.get(defn["student_id"], "")
    if not raw_student_id:
        raise MappingError(f"Missing student_id field '{defn['student_id']}' in {schema_version} record")
    source_student_id = raw_student_id.strip()
    student_id = normalise_student_id(source_student_id)

    # ── name ─────────────────────────────────────────────────────────────────
    if defn["full_name_field"]:
        # Combined name field (v1, v5, v8)
        full_name = raw_record.get(defn["full_name_field"], "")
        first_name, last_name = split_full_name(full_name)
    else:
        # Split name fields
        first_name = raw_record.get(defn["first_name"], "").strip()
        last_name = raw_record.get(defn["last_name"], "").strip()

    # ── preferred_name ───────────────────────────────────────────────────────
    if defn["has_preferred_name"] and defn["preferred_name"]:
        preferred_name = clean_optional(
            raw_record.get(defn["preferred_name"], ""), schema_version
        )
    else:
        preferred_name = None

    # ── school_id ────────────────────────────────────────────────────────────
    school_id_field = defn["school_id"]
    raw_school_id = raw_record.get(school_id_field, "")
    if not raw_school_id:
        raise MappingError(f"Missing school_id field '{school_id_field}' in {schema_version} record")
    school_id = raw_school_id.strip()

    # ── credential_type ──────────────────────────────────────────────────────
    raw_cred_type = raw_record.get(defn["credential_type"], "")
    credential_type = normalise_credential_type(raw_cred_type)

    # ── issue_date ───────────────────────────────────────────────────────────
    raw_issue_date = raw_record.get(defn["issue_date"], "")
    issue_date = normalise_date(raw_issue_date)
    if issue_date is None:
        raise MappingError(
            f"Unparseable issue_date '{raw_issue_date}' in {schema_version} record "
            f"(student_id={source_student_id})"
        )

    # ── status ───────────────────────────────────────────────────────────────
    raw_status = raw_record.get(defn["status"], "")
    status = normalise_status(raw_status)

    return {
        "student_id":             student_id,
        "first_name":             first_name,
        "last_name":              last_name,
        "preferred_name":         preferred_name,
        "school_id":              school_id,
        "credential_type":        credential_type,
        "issue_date":             issue_date,
        "status":                 status,
        "source_schema_version":  schema_version,
        "source_student_id":      source_student_id,
        "staged_at":              now_iso,
    }
