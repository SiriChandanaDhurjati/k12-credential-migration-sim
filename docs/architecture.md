# Pipeline Architecture

## Flow

Source CSVs (8 schema versions)
        ↓
Schema Detection (schema_detector.py)
        ↓
Schema Mapping → Canonical staging schema (schema_mapper.py)
        ↓
Watermark Extraction — incremental only (watermark.py)
        ↓
SQLite Staging Table
        ↓
Reconciliation Suite (run_reconciliation.py)
        ↓
Reconciliation Report → reports/

## Schema Versions Handled
v1 through v8 — each with different column names,
date formats, and missing value conventions.
All normalised to a single canonical staging schema.

## Key Patterns
- Watermark incremental extraction (no full reloads)
- Zero-tolerance row reconciliation per schema version
- Fail-fast quality gate before Gold layer