import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.schema_detector import detect_schema_version

def test_v1_detection():
    cols = ["student_id","student_name","schoolId","credentialType","issueDate","status"]
    assert detect_schema_version(cols) == "v1"

def test_v2_detection():
    cols = ["studentId","first_name","last_name","school_id","cred_type","issue_date","credentialStatus"]
    assert detect_schema_version(cols) == "v2"

def test_v3_detection():
    cols = ["stu_id","firstName","lastName","school_code","credential_category","issued_on","status_code"]
    assert detect_schema_version(cols) == "v3"