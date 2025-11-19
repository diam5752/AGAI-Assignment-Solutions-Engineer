"""Tests for AI/heuristic enrichment helpers."""
import os

import automation.processing.enrichment as enrichment
from automation.processing.enrichment import LLMEnricher, enrich_records
from automation.core.models import UnifiedRecord


def test_enrich_records_heuristics(monkeypatch):
    """Fallback heuristics should keep messages meaningful without LLM calls."""

    monkeypatch.setenv("AI_ENRICHMENT_DISABLED", "1")
    record = UnifiedRecord(
        source="email",
        source_name="email_urgent.eml",
        service=None,
        priority=None,
        message="Είναι επείγον να στηθεί CRM system και email marketing flow άμεσα.",
    )

    enriched = enrich_records([record])[0]

    assert enriched.priority is None
    assert enriched.service is None
    assert enriched.message.startswith("Είναι επείγον")
    assert len(enriched.message or "") <= 240


def test_enrich_records_preserves_existing_fields(monkeypatch):
    """Existing metadata should remain untouched if already populated."""

    monkeypatch.setenv("AI_ENRICHMENT_DISABLED", "1")
    record = UnifiedRecord(
        source="form",
        source_name="contact_form_1.html",
        service="Ανάπτυξη Website",
        priority="Υψηλή",
        message="Σύντομο μήνυμα",
    )

    enriched = enrich_records([record])[0]

    assert enriched.service == "Ανάπτυξη Website"
    assert enriched.priority == "high"  # translated to template-friendly terms
    assert enriched.message == "Σύντομο μήνυμα"


def test_enrichment_prefers_need_statement(monkeypatch):
    """Summaries should highlight the need-style lines from the original text."""

    monkeypatch.setenv("AI_ENRICHMENT_DISABLED", "1")
    record = UnifiedRecord(
        source="email",
        source_name="email_need.eml",
        service="CRM System",
        priority=None,
        message="Χρειαζόμαστε:\n- Διαχείριση πελατών (300+)\n- Παρακολούθηση πωλήσεων",
    )

    enriched = enrich_records([record])[0]

    assert enriched.message.startswith("Χρειαζόμαστε")
    assert "Διαχείριση πελατών" in enriched.message


def test_enrichment_limits_message_to_single_sentence(monkeypatch):
    """Messages should be truncated to the first sentence for consistency."""

    monkeypatch.setenv("AI_ENRICHMENT_DISABLED", "1")
    record = UnifiedRecord(
        source="form",
        source_name="contact_form_1.html",
        service="E-commerce Platform",
        priority="high",
        message="Χρειαζόμαστε ένα νέο e-commerce website για την εταιρεία μας. Έχουμε περίπου 200 προϊόντα και θέλουμε integration με το ERP μας.",
    )

    enriched = enrich_records([record])[0]

    assert enriched.message == "Χρειαζόμαστε ένα νέο e-commerce website"


def test_enrichment_handles_colon_followed_by_list(monkeypatch):
    """Need statements ending with ':' should ignore numbered reasons."""

    monkeypatch.setenv("AI_ENRICHMENT_DISABLED", "1")
    record = UnifiedRecord(
        source="email",
        source_name="email_02.eml",
        service="E-commerce Platform",
        priority=None,
        message=(
            "Θέλουμε να δημιουργήσουμε ένα e-commerce website γιατί:\n"
            "1. Έχουμε φυσικό κατάστημα 10 χρόνια\n"
            "2. Διαθέτουμε 500+ προϊόντα"
        ),
    )

    enriched = enrich_records([record])[0]

    assert enriched.message == "Θέλουμε να δημιουργήσουμε ένα e-commerce website"


def test_ai_summary_is_preserved(monkeypatch):
    """AI-generated summaries should remain intact without code truncation."""

    monkeypatch.setenv("AI_ENRICHMENT_DISABLED", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_call(self, record):
        return {
            "priority": "high",
            "service_interest": "CRM System",
            "message_summary": "Θέλουμε σύστημα που οργανώνει όλο το συνεργείο χωρίς κοψίματα.",
            "_source": "ai",
        }

    monkeypatch.setattr(enrichment.LLMEnricher, "_call_model", fake_call)
    enrichment._AI_ENV_LOADED = False

    record = UnifiedRecord(
        source="email",
        source_name="email_ai.eml",
        service=None,
        priority=None,
        message="Περιγραφή με ελλιπή στοιχεία που απαιτεί AI.",
    )

    enriched = enrich_records([record])[0]

    assert enriched.message == "Θέλουμε σύστημα που οργανώνει όλο το συνεργείο χωρίς κοψίματα."
    assert enriched.priority == "high"
    assert enriched.service == "CRM System"


def test_llm_runs_only_for_uncertain_records(monkeypatch):
    """LLM should be invoked when fields are missing or text is long."""

    monkeypatch.setenv("AI_ENRICHMENT_DISABLED", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    calls: dict[str, int] = {"count": 0}

    def fake_call(self, record):
        calls["count"] += 1
        return {
            "priority": "medium",
            "service_interest": "CRM System",
            "message_summary": "Need a CRM with email automations",
            "_source": "ai",
        }

    monkeypatch.setattr(enrichment.LLMEnricher, "_call_model", fake_call)
    enrichment._AI_ENV_LOADED = False

    long_message = "Σκεφτόμαστε να οργανώσουμε καλύτερα τις πωλήσεις μας " * 30
    record = UnifiedRecord(
        source="email",
        source_name="email_ai.eml",
        service=None,
        priority=None,
        message=long_message,
    )

    enriched = enrich_records([record])[0]

    assert calls["count"] == 1
    assert enriched.priority == "medium"
    assert enriched.service == "CRM System"
    assert "CRM" in (enriched.message or "")


def test_llm_skips_when_metadata_confident(monkeypatch):
    """Confident records should rely on local normalization only."""

    monkeypatch.setenv("AI_ENRICHMENT_DISABLED", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fail_call(self, record):  # pragma: no cover - guardrail
        raise AssertionError("LLM should not run for confident records")

    monkeypatch.setattr(enrichment.LLMEnricher, "_call_model", fail_call)
    enrichment._AI_ENV_LOADED = False

    record = UnifiedRecord(
        source="email",
        source_name="email_ok.eml",
        service="CRM System",
        priority="high",
        message="Χρειαζόμαστε CRM με υποστήριξη ticketing.",
    )

    enriched = enrich_records([record])[0]

    assert enriched.service == "CRM System"
    assert enriched.priority == "high"
    assert "ticketing" in (enriched.message or "")


def test_invoice_records_skip_ai(monkeypatch):
    """Invoices should not trigger AI calls or placeholder metadata."""

    class DummySession:
        def post(self, *_args, **_kwargs):
            raise AssertionError("Invoices should not invoke the LLM")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(enrichment.requests, "Session", lambda: DummySession())
    enrichment._AI_ENV_LOADED = False

    record = UnifiedRecord(source="invoice", source_name="invoice.html")
    enriched = enrich_records([record])[0]

    assert enriched.priority is None
    assert enriched.service is None
    assert (enriched.message or "") == ""


def test_llm_enricher_reads_secret_file(tmp_path, monkeypatch):
    """LLMEnricher should load secrets from a dedicated env file."""

    secret_file = tmp_path / "openai.env"
    secret_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=from-file",
                "OPENAI_MODEL=gpt-mini",
                "OPENAI_BASE_URL=https://example.com/v1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_SECRET_FILE", str(secret_file))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    enrichment._AI_ENV_LOADED = False

    enricher = enrichment.LLMEnricher()

    assert enricher.api_key == "from-file"
    assert enricher.model == "gpt-mini"
    assert enricher.base_url == "https://example.com/v1"


def teardown_module():
    os.environ.pop("AI_ENRICHMENT_DISABLED", None)
    os.environ.pop("AI_SECRET_FILE", None)
    enrichment._AI_ENV_LOADED = False
