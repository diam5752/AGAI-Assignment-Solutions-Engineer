"""Parser for email (.eml) sources."""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import timezone
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from automation.core.models import UnifiedRecord
from automation.ingestion.common import html_to_text

logger = logging.getLogger(__name__)


def _parse_email_date(date_header: str | None) -> str | None:
    """Return an ISO-formatted date string derived from an email header."""

    if not date_header:
        return None

    try:
        parsed = parsedate_to_datetime(date_header)
    except (TypeError, ValueError):
        return date_header.strip() or None

    if not parsed:
        return date_header.strip() or None

    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc)

    return parsed.date().isoformat()


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
        "προμηθευτής": "company",
        "supplier": "company",
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
        phone_match = re.search(
            r"(?i)(?:τηλ|τηλέφωνο|κινητό|phone|tel)\s*[:\-]?\s*(\+?\d[\d\s\-]{6,})",
            text,
        )
        if phone_match:
            cleaned_phone = re.sub(r"[^\d+]", "", phone_match.group(1))
            contact["phone"] = cleaned_phone
    return contact


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
                    return html_to_text(content)
                return content.strip()

        if message.get_content_type().startswith("text/"):
            content = message.get_content()
            if message.get_content_subtype() == "html":
                return html_to_text(content)
            return content.strip()

        payload = message.get_payload(decode=True)
        if payload:
            charset = message.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="ignore").strip()
        return ""

    text_body = _extract_text_body().replace("\r\n", "\n").replace("\r", "\n")

    structured_contact = _extract_structured_contact(text_body)
    header_name, header_email = parseaddr(from_header)
    submission_date = _parse_email_date(message.get("Date"))

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
        submission_date=submission_date,
        notes="parsed from email header and body",
    )
