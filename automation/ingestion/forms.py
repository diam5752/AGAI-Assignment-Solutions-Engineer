"""Parser for HTML contact forms."""
from __future__ import annotations

import re
from pathlib import Path

from automation.core.models import UnifiedRecord
from automation.ingestion.common import read_text


def parse_form(path: Path) -> UnifiedRecord:
    """Extract customer data from an HTML contact form."""

    content = read_text(path)

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
