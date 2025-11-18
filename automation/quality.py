"""Lightweight quality checks to keep extracted records trustworthy."""
import logging
from typing import Iterable, List

from automation.models import UnifiedRecord


logger = logging.getLogger(__name__)


def validate_record(record: UnifiedRecord) -> List[str]:
    """Return a list of quality issues for a single record."""

    issues: List[str] = []

    # Basic identity fields should exist for traceability.
    if not record.customer_name:
        issues.append("missing customer name")

    # Source-specific checks keep the validation focused and minimal.
    if record.source == "invoice":
        if not record.invoice_number:
            issues.append("missing invoice number")
        if record.total_amount is None or record.total_amount <= 0:
            issues.append("invalid total amount")
        if record.net_amount is not None and record.vat_amount is not None:
            expected_total = round(record.net_amount + record.vat_amount, 2)
            if record.total_amount is not None and abs(expected_total - record.total_amount) > 0.01:
                issues.append("net + vat does not match total")

    if record.source == "form":
        if not (record.email or record.phone):
            issues.append("contact info missing")

    if record.source == "email":
        if not record.message:
            issues.append("empty email body")

    return issues


def apply_quality_checks(records: Iterable[UnifiedRecord]) -> List[UnifiedRecord]:
    """Annotate each record with a status and notes based on validation results."""

    updated: List[UnifiedRecord] = []

    for record in records:
        issues = validate_record(record)
        record.status = "auto_valid" if not issues else "needs_review"
        if issues:
            note = "; ".join(issues)
            record.notes = f"{record.notes or ''} quality: {note}".strip()
            logger.warning("Quality issues for %s: %s", record.source_name, note)
        updated.append(record)

    return updated
