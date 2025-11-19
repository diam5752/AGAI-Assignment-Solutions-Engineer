"""Parser for HTML invoices."""
from __future__ import annotations

import re
from pathlib import Path

from automation.core.models import UnifiedRecord
from automation.ingestion.common import clean_amount, html_to_text, read_text


def parse_invoice(path: Path) -> UnifiedRecord:
    """Extract key fields from an HTML invoice file."""

    content = read_text(path)
    text = html_to_text(content).replace("\r", "")
    lines = [line for line in text.splitlines() if line.strip()]

    def after(labels: str | list[str]) -> str:
        """Pull the text that follows a label like 'Αριθμός:' within the document."""

        label_options = [labels] if isinstance(labels, str) else labels
        for label in label_options:
            for index, line in enumerate(lines):
                lowered = line.lower()
                if label.lower() in lowered:
                    start = lowered.find(label.lower()) + len(label)
                    value_part = line[start:]
                    value_part = value_part.lstrip(": ")
                    if not value_part and index + 1 < len(lines):
                        candidate = lines[index + 1].strip()
                        if candidate and all(lab.lower() not in candidate.lower() for lab in label_options):
                            value_part = candidate
                    return value_part.strip(" -")
        return ""

    def fallback_amount(raw: str, amounts: list[str]) -> str:
        """Return a parsed amount or best-effort fallback from detected euro values."""

        if raw:
            return raw
        return amounts[-1] if amounts else ""

    euro_amounts = re.findall(r"€\s*[\d\.,]+", text)

    net_raw = after(["Καθαρή Αξία", "Καθ. Αξία", "Net"])
    vat_raw = after(["ΦΠΑ 24%", "VAT"])
    total_raw = after(["ΣΥΝΟΛΟ", "Total"])
    total_raw = fallback_amount(total_raw, euro_amounts)

    return UnifiedRecord(
        source="invoice",
        source_name=path.name,
        customer_name=after(["Πελάτης", "Customer"]),
        invoice_number=after(["Αριθμός", "Invoice"]),
        invoice_date=after(["Ημερομηνία", "Date"]),
        company=None,
        email=None,
        phone=None,
        net_amount=clean_amount(net_raw) if net_raw else None,
        vat_amount=clean_amount(vat_raw) if vat_raw else None,
        total_amount=clean_amount(total_raw) if total_raw else None,
        notes="extracted from HTML invoice",
    )
