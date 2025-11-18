# Developer Quickstart

A minimal guide to run the extraction pipeline, dashboard, and tests locally.

## Setup
1. Use Python 3.11+.
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies (includes Streamlit and test tools):
   ```bash
   pip install -r requirements.txt -r requirements-dev.txt
   ```

## Run the pipeline CLI
The CLI reads from `dummy_data` by default and writes a CSV with the unified records.
```bash
python -m automation.cli --data-dir dummy_data --output output/unified_records.csv
```

Choose an optional sink to mirror the same rows:
- Excel: `python -m automation.cli --sink=excel --excel-output output/unified_records.xlsx`
- Google Sheets: requires a service account JSON (download it to `credentials/service_account.json`) shared with the target sheet.
  ```bash
  python -m automation.cli \
    --sink=sheets \
    --spreadsheet-id <your_sheet_id> \
    --worksheet Sheet1 \
    --service-account credentials/service_account.json
  ```

## Launch the review dashboard
Use the same data directory to review/edit records, approve or reject them, and export a reviewed CSV.
```bash
streamlit run automation/dashboard.py
```

## Run tests
Execute the test suite to validate extractors, quality checks, and review helpers.
```bash
pytest
```

## Logging
The CLI and pipeline emit structured logs to stdout. Set `LOG_LEVEL=DEBUG` to see
per-file parsing errors without interrupting the run.
