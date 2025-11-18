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

## Configure AI Enrichment
1. Copy `secrets/openai.env.example` to `secrets/openai.env`.
2. Fill in your actual credentials:
   ```bash
   OPENAI_API_KEY=sk-your-key
   OPENAI_MODEL=gpt-4o-mini
   OPENAI_BASE_URL=https://api.openai.com/v1
   AI_ENRICHMENT_DISABLED=0
   ```
3. The pipeline automatically loads this file; set `AI_SECRET_FILE=/path/to/file` if you prefer a custom location.
4. Leave `AI_ENRICHMENT_DISABLED=1` locally when you want to force the deterministic fallbacks.

## Configure Google Sheets Sync
1. Create a Google Cloud service account with Sheets API access and download the JSON key.
2. Copy `secrets/service_account.example.json` to `secrets/service_account.json` and replace the placeholder values with your key.
3. Share your Google Sheet with the service account `client_email` (Editor access).
4. Run the CLI with:
   ```bash
   python -m automation.cli \
     --sink=sheets \
     --spreadsheet-id <your_sheet_id> \
     --worksheet Sheet1 \
     --service-account secrets/service_account.json
   ```
   If the file lives at `secrets/service_account.json`, you can omit `--service-account`.
5. Optional: copy `secrets/sheets.env.example` to `secrets/sheets.env`, set `GOOGLE_SHEETS_AUTO_SYNC=1`, and fill in the IDs to push automatically every time the CLI runs (even when `--sink` stays `csv`).

## Run the pipeline CLI
The CLI reads from `dummy_data` by default and writes a CSV with the unified records.
```bash
python -m automation.cli --data-dir dummy_data --output output/unified_records.csv
```

Choose an optional sink to mirror the same rows:
- Excel: `python -m automation.cli --sink=excel --excel-output output/unified_records.xlsx`
- Google Sheets: requires a service account JSON (download it to `secrets/service_account.json`) shared with the target sheet.
  ```bash
  python -m automation.cli \
    --sink=sheets \
    --spreadsheet-id <your_sheet_id> \
    --worksheet Sheet1 \
    --service-account secrets/service_account.json
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
