"""Data ingestion package for parsing forms, invoices, and emails."""
from automation.ingestion.emails import parse_email
from automation.ingestion.forms import parse_form
from automation.ingestion.invoices import parse_invoice
from automation.ingestion.loader import get_ingestion_alerts, load_records

__all__ = [
    "parse_email",
    "parse_form",
    "parse_invoice",
    "get_ingestion_alerts",
    "load_records",
]
