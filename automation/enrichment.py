"""AI and heuristic enrichment for parsed records."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests

from automation.models import UnifiedRecord

logger = logging.getLogger(__name__)
DEFAULT_SECRET_FILE = Path(__file__).resolve().parents[1] / "secrets" / "openai.env"
_AI_ENV_LOADED = False

PRIORITY_TRANSLATIONS = {
    "υψηλή": "high",
    "μεσαία": "medium",
    "μέτρια": "medium",
    "χαμηλή": "low",
}

PRIORITY_KEYWORDS = {
    "high": ["επείγον", "urgent", "άμεσα", "asap"],
    "medium": ["εντός", "soon", "βραχυπρόθεσμα"],
    "low": ["όταν", "μακροπρόθεσμα"],
}

SERVICE_KEYWORDS = [
    ("CRM", "CRM System"),
    ("crm", "CRM System"),
    ("e-commerce", "E-commerce Platform"),
    ("eshop", "E-commerce Platform"),
    ("e-shop", "E-commerce Platform"),
    ("τιμολόγιο", "Invoice Processing"),
    ("invoice", "Invoice Processing"),
    ("marketing", "Marketing Services"),
    ("hotel", "Hotel Management System"),
    ("booking", "Hotel Management System"),
]

NEED_KEYWORDS = (
    "χρειαζόμαστε",
    "χρειάζομαι",
    "θέλουμε",
    "θέλω",
    "ζητάμε",
    "ζητούμε",
    "αναζητούμε",
    "χρειαζόμαστε:",
    "θέλουμε:",
    "ζητάμε:",
    "we need",
    "we want",
)


def _load_ai_env_from_file() -> None:
    """Load AI credentials from a local secrets file once per process."""

    global _AI_ENV_LOADED
    if _AI_ENV_LOADED:
        return

    _AI_ENV_LOADED = True
    secret_location = os.getenv("AI_SECRET_FILE")
    path = Path(secret_location).expanduser() if secret_location else DEFAULT_SECRET_FILE
    if not path.exists():
        return

    try:
        with path.open(encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key or key in os.environ:
                    continue
                os.environ[key] = value.strip().strip('"').strip("'")
    except OSError as exc:  # pragma: no cover - best-effort secret loading
        logger.debug("Could not load AI secrets file %s: %s", path, exc)


def _clean_phrase(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" -•\n\t")
    if text.endswith((".", "!", "?")):
        text = text[:-1]
    return text.strip()


def enrich_records(records: Iterable[UnifiedRecord]) -> List[UnifiedRecord]:
    """Run AI/heuristic enrichment across all records."""

    enricher = LLMEnricher()
    enriched: List[UnifiedRecord] = []
    for record in records:
        try:
            enriched.append(enricher.enrich(record))
        except Exception:  # pragma: no cover - defensive to keep pipeline running
            logger.exception("Failed to enrich record %s", record.source_name)
            enriched.append(record)
    return enriched


class LLMEnricher:
    """Optional AI-backed enrichment with deterministic heuristics fallback."""

    def __init__(self) -> None:
        _load_ai_env_from_file()
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.disabled = os.getenv("AI_ENRICHMENT_DISABLED", "0") == "1"
        self.session = requests.Session() if self.api_key else None

    def enrich(self, record: UnifiedRecord) -> UnifiedRecord:
        """Return a new record with summarized fields."""

        if self.disabled:
            return self._apply_updates(record, self._fallback(record))

        needs_ai = self._needs_ai(record)
        if needs_ai and self.session:
            response = self._call_model(record)
            if response:
                return self._apply_updates(record, response)

        return self._apply_updates(record, self._fallback(record))

    def _needs_ai(self, record: UnifiedRecord) -> bool:
        if not record.service or not record.priority or (record.message and len(record.message) > 400):
            return True
        return False

    def _call_model(self, record: UnifiedRecord) -> Dict[str, str]:
        """Call OpenAI chat completions to derive structured insights."""

        prompt = self._prompt(record)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You extract business metadata. Respond ONLY with JSON object containing "
                        "'service_interest', 'priority', 'message_summary', and optionally 'missing_fields'. "
                        "Priority must be high, medium, or low."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as exc:  # pragma: no cover - network optional
            logger.debug("LLM enrichment failed: %s", exc)
            return {}

    def _prompt(self, record: UnifiedRecord) -> str:
        fields = {
            "customer": record.customer_name or "",
            "company": record.company or "",
            "service": record.service or "",
            "priority": record.priority or "",
            "message": (record.message or "")[:2000],
        }
        return json.dumps(fields, ensure_ascii=False)

    def _apply_updates(self, record: UnifiedRecord, data: Dict[str, Optional[str]]) -> UnifiedRecord:
        updates: Dict[str, Optional[str]] = {}

        priority = self._normalize_priority(data.get("priority") or record.priority)
        if priority:
            updates["priority"] = priority

        service = data.get("service_interest") or record.service
        service = self._normalize_service(service)
        if service:
            updates["service"] = service

        summary = data.get("message_summary")
        message_text = self._template_style_message(record, summary)
        if message_text:
            updates["message"] = message_text

        missing_fields = data.get("missing_fields") or {}
        if isinstance(missing_fields, dict):
            if not record.company and missing_fields.get("company"):
                updates["company"] = missing_fields["company"]

        if not updates:
            return record
        return replace(record, **updates)

    def _fallback(self, record: UnifiedRecord) -> Dict[str, Optional[str]]:
        """Deterministic heuristics when AI is unavailable."""

        priority = self._normalize_priority(record.priority) or self._priority_from_text(record.message or "")
        service = self._normalize_service(record.service) or self._service_from_text(record)
        summary = self._shorten(record.message or "")

        return {
            "priority": priority,
            "service_interest": service,
            "message_summary": summary,
        }

    def _template_style_message(self, record: UnifiedRecord, summary: Optional[str]) -> str:
        """Prefer concise 'needs' statements similar to the shared template."""

        for text in (summary, record.message):
            phrase = self._need_statement_from_text(text)
            if phrase:
                return phrase

        fallback = summary or record.message or ""
        if fallback:
            return self._shorten(fallback, max_chars=160)
        if record.service:
            return f"Χρειαζόμαστε λύση για {record.service}"
        return ""

    def _need_statement_from_text(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None

        lines = [line.rstrip() for line in text.splitlines()]
        pending_prefix: Optional[str] = None
        for raw in lines:
            stripped = raw.strip()
            if not stripped:
                continue
            normalized = stripped.lstrip("-• ").strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            matched_keyword = False
            for keyword in NEED_KEYWORDS:
                if lowered.startswith(keyword):
                    matched_keyword = True
                    phrase = normalized.rstrip(":")
                    if normalized.endswith(":"):
                        pending_prefix = phrase
                    else:
                        return _clean_phrase(phrase)
                    break
                if keyword in lowered:
                    matched_keyword = True
                    idx = lowered.find(keyword)
                    snippet = normalized[idx:]
                    snippet = re.split(r"[.!?\n]", snippet, maxsplit=1)[0]
                    return _clean_phrase(snippet)
            if pending_prefix and not matched_keyword:
                combined = f"{pending_prefix} {normalized}"
                pending_prefix = None
                return _clean_phrase(combined)

        flat = " ".join(line.strip() for line in lines if line.strip())
        lowered_flat = flat.lower()
        for keyword in NEED_KEYWORDS:
            idx = lowered_flat.find(keyword)
            if idx != -1:
                snippet = flat[idx:]
                snippet = re.split(r"[.!?\n]", snippet, maxsplit=1)[0]
                return _clean_phrase(snippet)
        return None

    def _normalize_priority(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        lowered = value.strip().lower()
        if lowered in {"high", "medium", "low"}:
            return lowered
        return PRIORITY_TRANSLATIONS.get(lowered)

    def _priority_from_text(self, text: str) -> Optional[str]:
        lowered = text.lower()
        for level, keywords in PRIORITY_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                return level
        return None

    def _normalize_service(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        cleaned = " ".join(value.split())
        for keyword, canonical in SERVICE_KEYWORDS:
            if keyword.lower() in cleaned.lower():
                return canonical
        return cleaned

    def _service_from_text(self, record: UnifiedRecord) -> Optional[str]:
        text = " ".join(filter(None, [record.service, record.message or ""]))
        for keyword, canonical in SERVICE_KEYWORDS:
            if keyword.lower() in text.lower():
                return canonical
        return None

    def _shorten(self, message: str, max_chars: int = 240) -> str:
        if not message:
            return ""
        message = " ".join(message.split())
        if len(message) <= max_chars:
            return message
        sentences = re.split(r"(?<=[.!?])\s+", message)
        summary = ""
        for sentence in sentences:
            if len(summary) + len(sentence) + 1 > max_chars:
                break
            summary = f"{summary} {sentence}".strip()
        return summary or message[:max_chars].rstrip() + "…"
