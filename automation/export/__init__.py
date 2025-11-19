"""Export destinations for unified records."""
from automation.export.sinks import ensure_output_dir, push_to_google_sheets, write_excel

__all__ = ["ensure_output_dir", "push_to_google_sheets", "write_excel"]
