"""Utilities for parsing forms, invoices, and emails into unified records."""
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
import logging
import re
from pathlib import Path
from typing import List

from automation.models import UnifiedRecord


logger = logging.getLogger(__name__)


def _read_file(path: Path) -> str:
    """Read file content as UTF-8 text."""

    return path.read_text(encoding="utf-8")


def _clean_amount(raw: str) -> float:
    """Convert euro-formatted strings into floats (drops thousand separators)."""

    normalized = re.sub(r"[€\s]", "", raw)
    numeric = normalized.replace(",", "")
    return float(numeric)


def parse_form(path: Path) -> UnifiedRecord:
    """Extract customer data from an HTML contact form."""

    content = _read_file(path)

    def value_for(field: str) -> str:
        """Pull the value attribute for a given input name."""

        match = re.search(rf'name="{field}"[^>]*value="([^"]+)"', content)
        return match.group(1) if match else ""

    def selected_option(select_name: str) -> str:
        """Return the visible text of the selected option in a select field."""

        pattern = rf'<select[^>]*name="{select_name}"[^>]*>.*?<option[^>]*selected[^>]*>([^<]+)</option>'
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1).strip() if match else ""

    message_match = re.search(
        r'<textarea[^>]*name="message"[^>]*>(.*?)</textarea>', content, re.DOTALL
    )
    message = message_match.group(1).strip() if message_match else ""

    return UnifiedRecord(
        source="form",
        source_name=path.name,
        customer_name=value_for("full_name") or None,
        email=value_for("email") or None,
        phone=value_for("phone") or None,
        company=value_for("company") or None,
        service=selected_option("service") or None,
        message=message or None,
        priority=selected_option("priority") or None,
        submission_date=value_for("submission_date") or None,
        notes="extracted from HTML form",
    )


def parse_invoice(path: Path) -> UnifiedRecord:
    """Extract key fields from an HTML invoice file."""

    content = _read_file(path)
    text = re.sub(r"<[^>]+>", " ", content)

    def after(label: str) -> str:
        """Pull the text that follows a label like 'Αριθμός:' within the document."""

        match = re.search(label + r"\s*:?\s*([^\n]+)", text)
        return match.group(1).strip() if match else ""

    net_raw = after("Καθαρή Αξία")
    vat_raw = after("ΦΠΑ 24%")
    total_raw = after("ΣΥΝΟΛΟ")

    return UnifiedRecord(
        source="invoice",
        source_name=path.name,
        customer_name=after("Πελάτης"),
        invoice_number=after("Αριθμός"),
        invoice_date=after("Ημερομηνία"),
        net_amount=_clean_amount(net_raw) if net_raw else None,
        vat_amount=_clean_amount(vat_raw) if vat_raw else None,
        total_amount=_clean_amount(total_raw) if total_raw else None,
        notes="extracted from HTML invoice",
    )


def parse_email(path: Path) -> UnifiedRecord:
    """Extract sender, subject, and body from an EML file."""

    with path.open("rb") as eml_file:
        message = BytesParser(policy=policy.default).parse(eml_file)

    from_header = message["From"] or ""
    subject = message["Subject"] or ""
    body = message.get_body(preferencelist=("plain",))
    text_body = body.get_content().strip() if body else ""

    def _extract_structured_contact(text: str) -> dict:
        """Pull contact fields from bullet lists like '- Όνομα: Value'."""

        contact: dict = {}
        pattern = re.compile(r"^-\s*([^:]+):\s*(.+)$", re.MULTILINE)
        label_to_field = {
            "όνομα": "customer_name",
            "name": "customer_name",
            "email": "email",
            "e-mail": "email",
            "τηλέφωνο": "phone",
            "κινητό": "phone",
            "τηλ": "phone",
            "phone": "phone",
            "εταιρεία": "company",
            "company": "company",
        }

        for match in pattern.finditer(text):
            label, value = match.group(1).strip(), match.group(2).strip()
            normalized = label.casefold()
            for token, field in label_to_field.items():
                if token in normalized:
                    contact.setdefault(field, value)
                    break
        return contact

    structured_contact = _extract_structured_contact(text_body)
    header_name, header_email = parseaddr(from_header)

    customer_name = structured_contact.get("customer_name") or header_name or None
    email = structured_contact.get("email") or header_email or None

    return UnifiedRecord(
        source="email",
        source_name=path.name,
        customer_name=customer_name,
        email=email,
        phone=structured_contact.get("phone"),
        company=structured_contact.get("company"),
        message=text_body or None,
        service=subject or None,
        notes="parsed from email header and body",
    )


def load_records(data_dir: Path) -> List[UnifiedRecord]:
    """Parse all supported files under dummy_data into normalized records."""

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

    for invoice_path in sorted(invoices_dir.glob("*.html")):
        try:
            records.append(parse_invoice(invoice_path))
        except Exception:  # pragma: no cover - exercised via caplog
            logger.exception("Failed to parse invoice %s", invoice_path)

    for email_path in sorted(emails_dir.glob("*.eml")):
        try:
            records.append(parse_email(email_path))
        except Exception:  # pragma: no cover - exercised via caplog
            logger.exception("Failed to parse email %s", email_path)

    logger.info("Loaded %d records", len(records))

    return records
