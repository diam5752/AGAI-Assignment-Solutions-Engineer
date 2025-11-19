# AGAI Assignment Solutions Engineer

This repository contains the automation pipeline for processing forms, emails, and invoices.

## Online Resources

- **Online Excel Spreadsheet**: [View the shared spreadsheet](https://docs.google.com/spreadsheets/d/13OUC-GsJS5B2bszl_eaPxSBC3YiB2-_p0XWSL2X8rl8/edit?gid=0#gid=0)
- **Live Application**: [View the app online](https://diam5752-agai-assignment-solutions-automationuidashboard-t7rgll.streamlit.app/)

**Note**: AI enrichment is **enabled** in the online app. Please be mindful of usage as it consumes API credits. For local development, you can control AI enrichment by configuring the appropriate environment variable (see Secrets Configuration below).

## Secrets Configuration

The application requires configuration files that will be provided via email. After receiving them, place them in the `secrets/` directory as follows:

1. **`service_account.json`** (Required for Google Sheets access)
   - Place at: `secrets/service_account.json`

2. **`openai.env`** (Optional for AI enrichment features)
   - Place at: `secrets/openai.env`

**Note**: AI enrichment is **disabled by default**. To enable it, set the environment variable `AI_ENRICHMENT_DISABLED=0` before running the application.

## Prerequisites

- **Python 3.8** or higher
- **macOS** or **Linux** environment

## Quick Start

Follow these steps to set up and run the application:

1.  **Create a virtual environment:**
    ```bash
    python3 -m venv venv
    ```

2.  **Activate the virtual environment:**
    ```bash
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the dashboard:**
    ```bash
    streamlit run automation/ui/dashboard.py
    ```

The application will open in your default web browser (usually at `http://localhost:8501`).
