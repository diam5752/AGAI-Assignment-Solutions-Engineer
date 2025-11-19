"""Aggregate loaders that fetch records from all supported sources."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from automation.core.models import UnifiedRecord
from automation.ingestion.emails import parse_email
from automation.ingestion.forms import parse_form
from automation.ingestion.invoices import parse_invoice

logger = logging.getLogger(__name__)

_INGESTION_ALERTS: list[str] = []


def load_records(data_dir: Path) -> List[UnifiedRecord]:
    """Parse all supported files under a data directory into normalized records."""

    global _INGESTION_ALERTS
    _INGESTION_ALERTS = []

    records: List[UnifiedRecord] = []
    forms_dir = data_dir / "forms"
    invoices_dir = data_dir / "invoices"
    emails_dir = data_dir / "emails"

    logger.info("Loading records from %s", data_dir)

    for form_path in sorted(forms_dir.glob("*.html")):
        try:
            records.append(parse_form(form_path))
        except Exception:  # pragma: no cover - exercised via caplog
            logger.exception("Failed to parse form %s", form_path)
            _INGESTION_ALERTS.append(f"Failed to parse form {form_path.name}")

    for invoice_path in sorted(invoices_dir.glob("*.html")):
        try:
            records.append(parse_invoice(invoice_path))
        except Exception:  # pragma: no cover - exercised via caplog
            logger.exception("Failed to parse invoice %s", invoice_path)
            _INGESTION_ALERTS.append(f"Failed to parse invoice {invoice_path.name}")

    for email_path in sorted(emails_dir.glob("*.eml")):
        try:
            records.append(parse_email(email_path))
        except Exception:  # pragma: no cover - exercised via caplog
            logger.exception("Failed to parse email %s", email_path)
            _INGESTION_ALERTS.append(f"Failed to parse email {email_path.name}")

    logger.info("Loaded %d records", len(records))

    return records


def get_ingestion_alerts() -> List[str]:
    """Return a copy of the ingestion alerts recorded during ``load_records``."""

    return list(_INGESTION_ALERTS)
