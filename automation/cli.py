"""Simple CLI to run the extraction pipeline against the dummy data."""
import argparse
from pathlib import Path

from automation.logging_utils import configure_logging
from automation.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    """Create a small argument parser for the CLI entry point."""

    parser = argparse.ArgumentParser(description="Run the data extraction pipeline")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("dummy_data"),
        help="Path to the root dummy data directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/unified_records.csv"),
        help="CSV file to write extracted records to",
    )
    parser.add_argument(
        "--sink",
        choices=["csv", "sheets", "excel"],
        default="csv",
        help="Where to forward extracted rows after writing the CSV",
    )
    parser.add_argument(
        "--spreadsheet-id",
        help="Google Sheets spreadsheet ID for the sheets sink",
    )
    parser.add_argument(
        "--worksheet",
        default="Sheet1",
        help="Worksheet title inside the Google Sheets document",
    )
    parser.add_argument(
        "--service-account",
        type=Path,
        help="Path to a Google service account JSON key used for Sheets pushes",
    )
    parser.add_argument(
        "--excel-output",
        type=Path,
        default=Path("output/unified_records.xlsx"),
        help="Excel file to write when --sink=excel",
    )
    return parser


def main() -> None:
    """Entrypoint for running the pipeline from the command line."""

    configure_logging()
    args = build_parser().parse_args()
    output_path = run_pipeline(
        args.data_dir,
        args.output,
        sink=args.sink,
        spreadsheet_id=args.spreadsheet_id,
        worksheet_title=args.worksheet,
        service_account_path=args.service_account,
        excel_path=args.excel_output,
    )
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
