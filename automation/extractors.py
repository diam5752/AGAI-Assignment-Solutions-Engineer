"""Utilities for parsing forms, invoices, and emails into unified records."""
import html
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
import logging
import re
import unicodedata
from pathlib import Path
from typing import List

from automation.models import UnifiedRecord


logger = logging.getLogger(__name__)


def _read_file(path: Path) -> str:
    """Read file content as UTF-8 text."""

    return path.read_text(encoding="utf-8")


def _html_to_text(raw: str) -> str:
    """Strip HTML tags, condense whitespace, and unescape entities."""

    with_breaks = re.sub(r"(?i)<\s*br\s*/?>", "\n", raw)
    with_breaks = re.sub(r"(?i)</p>", "\n", with_breaks)
    with_breaks = re.sub(r"(?i)</div>", "\n", with_breaks)
    text = re.sub(r"<[^>]+>", " ", with_breaks)
    text = html.unescape(text)
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _clean_amount(raw: str) -> float:
    """Convert euro-formatted strings into floats (handles , or . decimals)."""

    normalized = re.sub(r"[€\s]", "", raw)

    # Detect European-style decimals (comma) vs. US-style (dot)
    if re.search(r",\d{2}$", normalized):
        normalized = normalized.replace(".", "")
        normalized = normalized.replace(",", ".")
    else:
        normalized = normalized.replace(",", "")

    return float(normalized)


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
    text = _html_to_text(content).replace("\r", "")
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

    def _extract_text_body() -> str:
        if message.is_multipart():
            part = message.get_body(preferencelist=("plain", "html"))
            if part:
                content = part.get_content()
                if part.get_content_subtype() == "html":
                    return _html_to_text(content)
                return content.strip()

        if message.get_content_type().startswith("text/"):
            content = message.get_content()
            if message.get_content_subtype() == "html":
                return _html_to_text(content)
            return content.strip()

        payload = message.get_payload(decode=True)
        if payload:
            charset = message.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="ignore").strip()
        return ""

    text_body = _extract_text_body().replace("\r\n", "\n").replace("\r", "\n")

    def _extract_structured_contact(text: str) -> dict:
        """Pull contact fields from bullet lists like '- Όνομα: Value'."""

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        contact: dict = {}
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

        def _normalized(value: str) -> str:
            decomposed = unicodedata.normalize("NFD", value.casefold())
            return "".join(ch for ch in decomposed if not unicodedata.combining(ch))

        normalized_tokens = {_normalized(token): field for token, field in label_to_field.items()}

        for raw_line in text.splitlines():
            if ":" not in raw_line:
                continue
            label, value = raw_line.split(":", 1)
            label = label.lstrip("-•*").strip()
            value = value.strip()
            normalized = _normalized(label)
            for token, field in normalized_tokens.items():
                if token in normalized:
                    cleaned = re.sub(r"\s+", "", value) if field == "phone" else value
                    contact.setdefault(field, cleaned)
                    break

        if "email" not in contact:
            email_match = re.search(r"[\w.+-]+@[\w.-]+", text)
            if email_match:
                contact["email"] = email_match.group(0)
        if "phone" not in contact:
            phone_match = re.search(r"(\+?\d[\d\s\-]{6,})", text)
            if phone_match:
                cleaned_phone = re.sub(r"\s+", "", phone_match.group(1))
                contact["phone"] = cleaned_phone
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
