"""AI and heuristic enrichment for parsed records."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests

from automation.core.models import UnifiedRecord

from automation.core.utils import load_env_file, get_config_value

logger = logging.getLogger(__name__)
DEFAULT_SECRET_FILE = Path(__file__).resolve().parents[1] / "secrets" / "openai.env"
_AI_ENV_LOADED = False

PRIORITY_TRANSLATIONS = {
    "υψηλή": "high",
    "μεσαία": "medium",
    "μέτρια": "medium",
    "χαμηλή": "low",
}

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

TRAILING_CONNECTORS = [
    "γιατί",
    "διότι",
    "επειδή",
    "because",
    "since",
    "ώστε",
    "so that",
    "για να",
]

TRAILING_CLAUSE_PATTERNS = [
    re.compile(r"\s+για\s+(?:τον|την|το|τη|τους)\s+[^.?!]*?\b(?:μας|μου)\b.*$", re.IGNORECASE),
    re.compile(r"\s+for\s+our\b.*$", re.IGNORECASE),
]


def _ensure_ai_env() -> None:
    """Load AI credentials from a local secrets file once per process."""

    global _AI_ENV_LOADED
    if _AI_ENV_LOADED:
        return

    _AI_ENV_LOADED = True
    secret_location = os.getenv("AI_SECRET_FILE")
    path = Path(secret_location).expanduser() if secret_location else DEFAULT_SECRET_FILE
    load_env_file(path)


def _strip_trailing_connectors(text: str) -> str:
    lowered = text.lower().rstrip(".!?…").rstrip()
    for connector in TRAILING_CONNECTORS:
        c = connector.lower()
        if lowered.endswith(c):
            cutoff = len(text) - len(connector)
            return text[:cutoff].rstrip(" ,:;-")
    return text


def _clean_phrase(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" -•\n\t")
    text = text.strip()
    return _strip_trailing_connectors(text).strip()


def _trim_trailing_clause(text: str) -> str:
    for pattern in TRAILING_CLAUSE_PATTERNS:
        match = pattern.search(text)
        if match:
            trimmed = text[: match.start()].strip()
            if trimmed:
                return trimmed
    return text


def _single_sentence(text: str) -> str:
    """Return only the first sentence-like fragment without trailing punctuation."""

    if not text:
        return ""
    compact = " ".join(text.split()).strip()
    if not compact:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", compact, maxsplit=1)
    first = parts[0] if parts else compact
    trimmed = _trim_trailing_clause(first)
    return trimmed.rstrip(".!?…").strip()


def _indicates_missing_info(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return True
    placeholders = [
        "not specified",
        "not provided",
        "no service",
        "no priority",
        "no specific service",
        "no specific priority",
        "unknown",
        "n/a",
        "none",
        "χωρίς πληροφορίες",
        "χωρίς υπηρεσία",
        "χωρίς προτεραιότητα",
        "δεν παρείχε",
        "δεν αναφέρ",
    ]
    return any(token in lowered for token in placeholders)


def enrich_records(
    records: Iterable[UnifiedRecord], progress_callback: Optional[callable] = None
) -> List[UnifiedRecord]:
    """Run AI/heuristic enrichment across all records."""

    enricher = LLMEnricher()
    enriched: List[UnifiedRecord] = []
    record_list = list(records)
    total = len(record_list)

    for i, record in enumerate(record_list):
        try:
            enriched.append(enricher.enrich(record))
        except Exception:  # pragma: no cover - defensive to keep pipeline running
            logger.exception("Failed to enrich record %s", record.source_name)
            enriched.append(record)
        if progress_callback:
            progress_callback((i + 1) / total)

    return enriched


class LLMEnricher:
    """Optional AI-backed enrichment with deterministic heuristics fallback."""

    def __init__(self) -> None:
        _ensure_ai_env()
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-5-nano")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.disabled = get_config_value("AI_ENRICHMENT_DISABLED", "0") == "1"
        self.session = requests.Session() if self.api_key else None
        self._cache: dict[str, Dict[str, Optional[str]]] = {}

    def enrich(self, record: UnifiedRecord) -> UnifiedRecord:
        """Return a new record with summarized fields."""

        if self.disabled:
            return self._apply_updates(record, self._fallback(record))

        needs_ai = self._needs_ai(record)
        if needs_ai and self.session:
            cache_key = self._fingerprint(record)
            if cache_key in self._cache:
                response = self._cache[cache_key]
            else:
                response = self._call_model(record)
                if response:
                    self._cache[cache_key] = response
            if response:
                return self._apply_updates(record, response)

        return self._apply_updates(record, self._fallback(record))

    def _needs_ai(self, record: UnifiedRecord) -> bool:
        if (record.source or "").lower() == "invoice":
            return False

        priority = self._normalize_priority(record.priority)
        service = self._normalize_service(record.service)
        message = (record.message or "").strip()

        message_missing = not message or _indicates_missing_info(message)
        message_long = len(message) > 360
        missing_core_fields = not priority or not service

        return missing_core_fields or message_missing or message_long

    def _call_model(self, record: UnifiedRecord) -> Dict[str, str]:
        """Call OpenAI chat completions to derive structured insights."""

        prompt = self._prompt(record)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You extract business metadata. Respond ONLY with a minimal JSON object containing "
                        "'service_interest', 'priority', 'message_summary', and optionally 'missing_fields'. "
                        "Priority must be exactly high, medium, or low. message_summary must be a single, complete "
                        "sentence (same language as the user) that reflects the core need expressed in the content, "
                        "without lists, numbering, or trailing conjunctions."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 200,
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
            payload = json.loads(content)
            payload["_source"] = "ai"
            return payload
        except Exception as exc:  # pragma: no cover - network optional
            logger.debug("LLM enrichment failed: %s", exc)
            return {}

    def _prompt(self, record: UnifiedRecord) -> str:
        fields = {
            "customer": record.customer_name or "",
            "company": record.company or "",
            "service": record.service or "",
            "priority": record.priority or "",
            "message": (record.message or "")[:1200],
        }
        return json.dumps(fields, ensure_ascii=False)

    def _fingerprint(self, record: UnifiedRecord) -> str:
        """Create a stable hash so repeated inputs reuse cached AI responses."""

        canonical = json.dumps(
            {
                "service": record.service,
                "priority": record.priority,
                "message": (record.message or "")[:500],
                "company": record.company,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _apply_updates(self, record: UnifiedRecord, data: Dict[str, Optional[str]]) -> UnifiedRecord:
        updates: Dict[str, Optional[str]] = {}

        priority = self._normalize_priority(data.get("priority") or record.priority)
        if priority:
            updates["priority"] = priority

        service = data.get("service_interest") or record.service
        service = self._normalize_service(service)
        if service:
            updates["service"] = service

        summary_source = data.pop("_source", None)
        summary = data.get("message_summary")
        message_text = self._template_style_message(record, summary, summary_source)
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

        priority = self._normalize_priority(record.priority)
        service = self._normalize_service(record.service)
        summary = self._smart_shorten(record.message or "")

        return {
            "priority": priority,
            "service_interest": service,
            "message_summary": summary,
            "_source": "fallback",
        }

    def _template_style_message(
        self, record: UnifiedRecord, summary: Optional[str], summary_source: Optional[str]
    ) -> str:
        """Prefer concise 'needs' statements similar to the shared template."""

        if summary_source == "ai" and summary:
            candidate = self._need_statement_from_text(summary) or summary
            candidate = _clean_phrase(candidate)
            if candidate and not _indicates_missing_info(candidate):
                return candidate

        texts = [record.message, summary]
        for text in texts:
            if not text:
                continue
            phrase = self._need_statement_from_text(text)
            if phrase:
                cleaned = _clean_phrase(phrase)
                if cleaned and not _indicates_missing_info(cleaned):
                    if summary_source == "ai" and text is summary:
                        return cleaned
                    return _single_sentence(cleaned)

        fallback = summary or record.message or ""
        if fallback and not _indicates_missing_info(fallback):
            if summary_source == "ai" and summary:
                return _clean_phrase(summary)
            return _single_sentence(self._smart_shorten(fallback, max_chars=200))
        if record.service:
            return _single_sentence(f"Χρειαζόμαστε λύση για {record.service}")
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
                if re.match(r"^(\d+[\.\)]\s*|[-•]\s*)", normalized):
                    phrase = _clean_phrase(pending_prefix)
                    pending_prefix = None
                    if phrase:
                        return phrase
                    continue
                combined = f"{pending_prefix} {normalized}"
                pending_prefix = None
                return _clean_phrase(combined)

        if pending_prefix:
            phrase = _clean_phrase(pending_prefix)
            if phrase:
                return phrase

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

    def _normalize_service(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        cleaned = " ".join(value.split()).strip()
        lowered = cleaned.lower()
        placeholders = {
            "not specified",
            "unknown",
            "n/a",
            "na",
            "none",
            "no service",
            "χωρίς υπηρεσία",
        }
        if lowered in placeholders:
            return None
        return cleaned

    def _smart_shorten(self, message: str, max_chars: int = 240) -> str:
        """Preserve meaning by keeping full sentences within the limit."""

        if not message:
            return ""

        normalized = " ".join(message.split()).strip()
        if len(normalized) <= max_chars:
            return normalized

        sentences = re.split(r"(?<=[.!?])\s+", normalized)
        summary_parts: list[str] = []
        total = 0
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            projected = total + len(sentence) + (1 if summary_parts else 0)
            if projected > max_chars:
                break
            summary_parts.append(sentence)
            total = projected

        if summary_parts:
            return " ".join(summary_parts)

        return normalized[: max_chars - 1].rstrip() + "…"
