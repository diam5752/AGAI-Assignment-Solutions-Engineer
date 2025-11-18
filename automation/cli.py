"""Simple CLI to run the extraction pipeline against the dummy data."""
import argparse
from pathlib import Path

from .pipeline import run_pipeline
from .logging_utils import configure_logging


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
    return parser


def main() -> None:
    """Entrypoint for running the pipeline from the command line."""

    configure_logging()
    args = build_parser().parse_args()
    output_path = run_pipeline(args.data_dir, args.output)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
