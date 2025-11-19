# Codebase Documentation

This repository is organized as a small Python package named `automation` that powers data ingestion, enrichment, review, and export flows. The layout keeps related concerns in focused subpackages so new contributors can find functionality quickly.

## Package layout

```
automation/
├── core/              # Fundamental models, pipeline orchestration, quality checks, and template mapping
├── enrichment/        # AI + heuristic enrichment engine
├── export/            # External sinks such as Excel and Google Sheets
├── ingestion/         # Parsers for forms, invoices, and emails plus the unified loader
└── review/            # Human-in-the-loop utilities and the Streamlit dashboard
```

### Core
- `core/models.py` defines the `UnifiedRecord` dataclass used end-to-end.
- `core/templates.py` maps records into the spreadsheet-ready schema and normalizes dates/amounts.
- `core/quality.py` performs lightweight validation and annotates statuses.
- `core/pipeline.py` orchestrates ingestion → quality → enrichment → export, handling CSV/Excel/Sheets sinks and auto-sync.
- `core/logging.py` exposes `configure_logging` for consistent log formatting across tools.

### Ingestion
- `ingestion/forms.py`, `ingestion/invoices.py`, and `ingestion/emails.py` parse individual asset types.
- `ingestion/loader.py` coordinates parsing across dummy folders and tracks ingestion alerts.

### Enrichment
- `enrichment/engine.py` implements deterministic enrichment plus optional OpenAI-backed summaries (`AI_ENRICHMENT_DISABLED=1` forces local heuristics).

### Export
- `export/sinks.py` contains helpers for pushing rows to Google Sheets or writing Excel files; it is used by the pipeline and dashboard.

### Review
- `review/workflow.py` wraps review-friendly operations (loading records, applying edits, setting statuses).
- `review/dashboard.py` hosts the Streamlit UI for approvals and exports.

## Execution paths
- **CLI**: `python -m automation.cli --data-dir dummy_data --output output/unified_records.csv` (optional `--sink excel|sheets`).
- **Dashboard**: `streamlit run automation/review/dashboard.py` to review, edit, and export approved rows.

## Adding new capabilities
- **New source type**: add a parser module under `ingestion/`, expose it via `ingestion/__init__.py`, and register it in `ingestion/loader.py`.
- **New sink**: implement it in `export/sinks.py` and wire it into `core/pipeline.py` (and optionally the dashboard export controls).
- **Additional quality rules**: extend `core/quality.validate_record`—the pipeline and dashboard will automatically pick up the new checks.
