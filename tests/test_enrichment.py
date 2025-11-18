"""Tests for AI/heuristic enrichment helpers."""
import os

import automation.enrichment as enrichment
from automation.enrichment import enrich_records
from automation.models import UnifiedRecord


def test_enrich_records_heuristics(monkeypatch):
    """Fallback heuristics should normalize service, priority, and summary."""

    monkeypatch.setenv("AI_ENRICHMENT_DISABLED", "1")
    record = UnifiedRecord(
        source="email",
        source_name="email_urgent.eml",
        service=None,
        priority=None,
        message="Είναι επείγον να στηθεί CRM system και email marketing flow άμεσα.",
    )

    enriched = enrich_records([record])[0]

    assert enriched.priority == "high"
    assert enriched.service == "CRM System"
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
