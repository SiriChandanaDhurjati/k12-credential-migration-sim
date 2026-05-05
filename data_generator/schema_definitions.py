"""
data_generator/schema_definitions.py

Defines the 8 source schema versions used in the K12 credential migration simulation.
Each entry maps the canonical field name to the column name used in that schema version,
along with the date format and missing-value convention.
"""

SCHEMA_DEFINITIONS = {
    "v1": {
        "student_id":       "student_id",
        "first_name":       None,               # combined in student_name
        "last_name":        None,
        "full_name_field":  "student_name",     # single-field name
        "school_id":        "schoolId",
        "credential_type":  "credentialType",
        "issue_date":       "issueDate",
        "status":           "status",
        "preferred_name":   "preferred_name",
        "updated_at":       "updated_at",
        "date_format":      "%Y-%m-%dT%H:%M:%S",
        "missing_value":    "",
        "has_preferred_name": True,
    },
    "v2": {
        "student_id":       "studentId",
        "first_name":       "first_name",
        "last_name":        "last_name",
        "full_name_field":  None,
        "school_id":        "school_id",
        "credential_type":  "cred_type",
        "issue_date":       "issue_date",
        "status":           "credentialStatus",
        "preferred_name":   "preferredName",
        "updated_at":       "last_modified",
        "date_format":      "%m/%d/%Y",
        "missing_value":    "N/A",
        "has_preferred_name": True,
    },
    "v3": {
        "student_id":       "stu_id",
        "first_name":       "firstName",
        "last_name":        "lastName",
        "full_name_field":  None,
        "school_id":        "school_code",
        "credential_type":  "credential_category",
        "issue_date":       "issued_on",
        "status":           "status_code",
        "preferred_name":   None,               # not present in v3
        "updated_at":       "modified_timestamp",
        "date_format":      "%Y-%m-%d",
        "missing_value":    "",
        "has_preferred_name": False,
    },
    "v4": {
        "student_id":       "learner_id",
        "first_name":       "given_name",
        "last_name":        "family_name",
        "full_name_field":  None,
        "school_id":        "institution_id",
        "credential_type":  "type_cd",
        "issue_date":       "date_issued",
        "status":           "cred_status",
        "preferred_name":   "pref_name",
        "updated_at":       "last_updated",
        "date_format":      "%Y-%m-%d",
        "missing_value":    "UNKNOWN",
        "has_preferred_name": True,
    },
    "v5": {
        "student_id":       "student_id",
        "first_name":       None,
        "last_name":        None,
        "full_name_field":  "student_name",
        "school_id":        "school_ref",
        "credential_type":  "credential_type",
        "issue_date":       "issue_dt",
        "status":           "status",
        "preferred_name":   None,               # not present in v5
        "updated_at":       "updated_at",
        "date_format":      "%d-%b-%Y",
        "missing_value":    "",
        "has_preferred_name": False,
    },
    "v6": {
        "student_id":       "id",
        "first_name":       "name_first",
        "last_name":        "name_last",
        "full_name_field":  None,
        "school_id":        "schl_id",
        "credential_type":  "credType",
        "issue_date":       "issuedDate",
        "status":           "state",
        "preferred_name":   None,               # not present in v6
        "updated_at":       "modified",
        "date_format":      "%Y-%m-%dT%H:%M:%SZ",
        "missing_value":    "null",
        "has_preferred_name": False,
    },
    "v7": {
        "student_id":       "student_number",
        "first_name":       "first_name",
        "last_name":        "last_name",
        "full_name_field":  None,
        "school_id":        "school_number",
        "credential_type":  "cert_type",
        "issue_date":       "cert_date",
        "status":           "cert_status",
        "preferred_name":   "preferred_name",
        "updated_at":       "record_updated",
        "date_format":      "%m-%d-%Y",
        "missing_value":    "",
        "has_preferred_name": True,
    },
    "v8": {
        "student_id":       "student_uid",
        "first_name":       None,
        "last_name":        None,
        "full_name_field":  "full_name",
        "school_id":        "school_id",
        "credential_type":  "qualification_type",
        "issue_date":       "issue_date",
        "status":           "credential_state",
        "preferred_name":   "preferred_name",
        "updated_at":       "updated_at",
        "date_format":      "%Y-%m-%d",
        "missing_value":    "N/A",
        "has_preferred_name": True,
    },
}


# Fingerprint: the set of columns that uniquely identifies each schema version.
# Used by schema_detector.py for version identification without relying on file metadata.
SCHEMA_FINGERPRINTS = {
    "v1": frozenset(["student_id", "student_name", "schoolId", "credentialType", "issueDate", "status"]),
    "v2": frozenset(["studentId", "first_name", "last_name", "school_id", "cred_type", "issue_date", "credentialStatus"]),
    "v3": frozenset(["stu_id", "firstName", "lastName", "school_code", "credential_category", "issued_on", "status_code"]),
    "v4": frozenset(["learner_id", "given_name", "family_name", "institution_id", "type_cd", "date_issued", "cred_status"]),
    "v5": frozenset(["student_id", "student_name", "school_ref", "credential_type", "issue_dt", "status"]),
    "v6": frozenset(["id", "name_first", "name_last", "schl_id", "credType", "issuedDate", "state"]),
    "v7": frozenset(["student_number", "first_name", "last_name", "school_number", "cert_type", "cert_date", "cert_status"]),
    "v8": frozenset(["student_uid", "full_name", "school_id", "qualification_type", "issue_date", "credential_state"]),
}
