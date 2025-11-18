# Dev README – How to Run Everything Locally

This guide walks you step by step through setting up the project, running the tests, and executing the full extraction pipeline on your laptop.

## 1. Prerequisites

- Python 3.9+ installed (`python3 --version` to check)
- `pip` available for installing Python packages
- A terminal (macOS Terminal, iTerm, Windows Terminal, etc.)

> Tip (Σημείωση): All commands below assume you are in the repository root (the folder that contains `README.md`, `automation/`, and `dummy_data/`).

---

## 2. Initial setup

1. **Clone or open the repo**
   - If you have not cloned it yet:
     - `git clone <this-repo-url>`
     - `cd AGAI-Assignment-Solutions-Engineer`
   - If the repo is already on your machine, just `cd` into it.

2. **Create and activate a virtual environment (recommended)**

   On macOS / Linux:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   On Windows (PowerShell):

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install development dependencies**

   The runtime code uses only the Python standard library; the only extra dependency is `pytest` for running tests:

   ```bash
   pip install -r requirements-dev.txt
   ```

---

## 3. Run the automated tests

From the repository root (with the virtual environment activated, if you created one):

```bash
pytest
```

or, for a quieter output:

```bash
pytest -q
```

You should see all tests in `tests/` pass. These verify that:

- HTML forms are parsed correctly
- HTML invoices amounts and numbers are extracted correctly
- E‑mails are parsed into sender, subject, and body
- All dummy assets are counted and turned into unified records

---

## 4. Run the extraction pipeline end‑to‑end

The main entry point for running the pipeline is the CLI defined in `automation/cli.py`. It reads from the `dummy_data` folders and writes a unified CSV file.

### 4.1 Run with default settings (dummy data)

From the repo root:

```bash
python3 -m automation.cli
```

What this does:

- Uses `dummy_data/` as the data source (forms, invoices, emails)
- Normalizes everything into a single list of records
- Writes the output to `output/unified_records.csv`
- Prints a confirmation message like:
  - `Wrote output/unified_records.csv`

You can now open `output/unified_records.csv` with:

- Excel
- Google Sheets
- Any CSV viewer

Each row represents one `UnifiedRecord` (see `automation/models.py`), with consistent columns across forms, invoices, and emails.

### 4.2 Run with a custom data directory or output file

The CLI accepts two optional arguments:

- `--data-dir` – root folder that contains `forms/`, `invoices/`, `emails/`
- `--output` – path of the CSV file to write

Examples:

```bash
# Use custom input data folder
python3 -m automation.cli --data-dir path/to/my_data

# Use a different output file
python3 -m automation.cli --output output/my_custom_file.csv

# Both at once
python3 -m automation.cli \
  --data-dir path/to/my_data \
  --output output/my_custom_file.csv
```

The pipeline will automatically create the parent folders for the output file if they do not exist.

---

## 5. Understanding the code structure

High‑level structure:

- `automation/cli.py`
  - Small command‑line interface.
  - Parses arguments and calls `run_pipeline`.
- `automation/pipeline.py`
  - Orchestrates the data loading and CSV writing.
  - Functions:
    - `run_pipeline(data_dir, output_path)` – main entry used by the CLI.
    - `write_csv(records, output_path)` – writes the unified CSV file.
- `automation/extractors.py`
  - Contains the parsing logic for each data type:
    - `parse_form(path)` – reads HTML forms.
    - `parse_invoice(path)` – reads HTML invoices.
    - `parse_email(path)` – reads `.eml` files.
    - `load_records(data_dir)` – walks the `forms/`, `invoices/`, `emails/` folders and returns a list of unified records.
- `automation/models.py`
  - Defines the `UnifiedRecord` dataclass used to represent a single normalized record across all sources.

If you want to experiment interactively, you can open a Python shell from the repo root:

```bash
python
```

Then:

```python
from pathlib import Path
from automation.extractors import parse_form, parse_invoice, parse_email, load_records

data_dir = Path("dummy_data")
records = load_records(data_dir)
len(records)  # should equal total number of dummy files
first = records[0]
first
```

This lets you see individual `UnifiedRecord` objects and inspect their fields directly.

---

## 6. Typical “from zero to results” workflow

If you want a concrete checklist (Βήμα‑βήμα) to verify everything works on your laptop:

1. Open a terminal and `cd` into the project folder:
   - `cd /path/to/AGAI-Assignment-Solutions-Engineer`
2. (Optional but recommended) Create and activate the virtual environment:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
3. Install dev dependencies:
   - `pip install -r requirements-dev.txt`
4. Run tests:
   - `pytest -q`
   - Confirm all tests pass.
5. Run the pipeline on the dummy data:
   - `python3 -m automation.cli`
   - Wait for the `Wrote output/unified_records.csv` message.
6. Open `output/unified_records.csv` in Excel / Sheets:
   - Confirm that:
     - There are rows for forms, invoices, and emails.
     - Important fields (customer name, email, invoice totals, etc.) look correct.

After these steps you have fully exercised the existing backend: parsing all dummy assets and producing a unified CSV you can use as a basis for further UI, approval workflows, or integrations.
