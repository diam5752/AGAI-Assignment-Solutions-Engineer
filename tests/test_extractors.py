"""Minimal tests to verify data extraction from dummy assets."""
from email.message import EmailMessage
from pathlib import Path

from automation.ingestion import load_records, parse_email, parse_form, parse_invoice

DATA_DIR = Path("dummy_data")


def test_parse_form_basic_fields():
    """Ensure a contact form yields the expected name and priority."""

    form_path = DATA_DIR / "forms" / "contact_form_1.html"
    record = parse_form(form_path)
    assert record.customer_name == "Νίκος Παπαδόπουλος"
    assert record.priority == "Υψηλή"


def test_parse_invoice_amounts():
    """Extract amounts and invoice number from an invoice HTML file."""

    invoice_path = DATA_DIR / "invoices" / "invoice_TF-2024-001.html"
    record = parse_invoice(invoice_path)
    assert record.invoice_number == "TF-2024-001"
    assert record.total_amount == 1054.00
    assert record.vat_amount == 204.00
    assert record.company is None
    assert record.email is None
    assert record.phone is None


def test_parse_email_structured_contact_details():
    """Validate structured body details populate unified fields."""

    email_path = DATA_DIR / "emails" / "email_01.eml"
    record = parse_email(email_path)

    assert record.customer_name == "Σπύρος Μιχαήλ"
    assert record.email == "spyros.michail@techcorp.gr"
    assert record.phone == "210-3344556"
    assert record.company == "TechCorp AE"
    assert "CRM" in record.service
    assert "συνάντηση".casefold() in record.message.casefold()
    assert record.submission_date == "2024-01-20"


def test_parse_email_header_date_populates_submission_date(tmp_path):
    """The Date header should feed the record submission_date."""

    message = EmailMessage()
    message["From"] = "Header <header@example.com>"
    message["Date"] = "Mon, 20 Jan 2024 10:30:00 +0200"
    message.set_content("Body text")

    eml_path = tmp_path / "dated.eml"
    eml_path.write_bytes(message.as_bytes())

    record = parse_email(eml_path)
    assert record.submission_date == "2024-01-20"
    assert record.submission_date == "2024-01-20"


def test_parse_email_uses_header_when_body_missing_email(tmp_path):
    """Fallback to From header if body omits email field."""

    message = EmailMessage()
    message["From"] = "Header Name <header@example.com>"
    message["Subject"] = "Νέο αίτημα"
    message.set_content(
        "Στοιχεία:\n"
        "- Όνομα: Body Name\n"
        "- Τηλέφωνο: 6944000000\n"
        "- Εταιρεία: Body Co"
    )

    eml_path = tmp_path / "missing_email.eml"
    eml_path.write_bytes(message.as_bytes())

    record = parse_email(eml_path)

    assert record.customer_name == "Body Name"
    assert record.email == "header@example.com"
    assert record.phone == "6944000000"
    assert record.company == "Body Co"


def test_parse_email_without_headers(tmp_path):
    """Handle structured contact details even when headers are absent."""

    message = EmailMessage()
    message.set_content(
        "Στοιχεία Επικοινωνίας:\n"
        "- Όνομα: No Header Name\n"
        "- Email: body@example.com\n"
        "- Κινητό: 2100000000\n"
        "- Εταιρεία: Headerless Co"
    )

    eml_path = tmp_path / "no_headers.eml"
    eml_path.write_bytes(message.as_bytes())

    record = parse_email(eml_path)

    assert record.customer_name == "No Header Name"
    assert record.email == "body@example.com"
    assert record.phone == "2100000000"
    assert record.company == "Headerless Co"


def test_parse_email_html_only_body(tmp_path):
    """HTML-only emails should still yield contact and message content."""

    message = EmailMessage()
    message["From"] = "HTML Sender <html.sender@example.com>"
    message["Subject"] = "HTML Inquiry"
    message.add_alternative(
        """
        <html><body>
        <p>- Όνομα: HTML Name</p>
        <p>- Email: html@contact.gr</p>
        <p>- Τηλέφωνο: +30 210 5555555</p>
        <p>- Εταιρεία: HTML Co</p>
        <p>Θέλω πληροφορίες για custom εφαρμογή.</p>
        </body></html>
        """,
        subtype="html",
    )

    eml_path = tmp_path / "html_only.eml"
    eml_path.write_bytes(message.as_bytes())

    record = parse_email(eml_path)

    assert record.customer_name == "HTML Name"
    assert record.email == "html@contact.gr"
    assert record.phone == "+302105555555"
    assert "custom εφαρμογή" in (record.message or "")


def test_parse_email_invoice_summary_extracts_supplier():
    """Invoice summary emails should capture supplier details without fake phones."""

    email_path = DATA_DIR / "emails" / "email_03.eml"
    record = parse_email(email_path)

    assert record.company == "Office Solutions Ltd"
    assert record.phone is None


def test_parse_invoice_european_decimal_format(tmp_path):
    """Invoices with comma decimals should still parse numeric totals correctly."""

    html_invoice = """
    <html><body>
    <div><strong>Αριθμός:</strong> INV-002<br>
    <strong>Ημερομηνία:</strong> 02/02/2024<br></div>
    <div><strong>Πελάτης:</strong> Δοκιμαστική Εταιρεία</div>
    <table>
      <tr><td>Καθαρή Αξία:</td><td>€1.234,00</td></tr>
      <tr><td>ΦΠΑ 24%:</td><td>€296,16</td></tr>
      <tr><td>ΣΥΝΟΛΟ:</td><td>€1.530,16</td></tr>
    </table>
    </body></html>
    """

    invoice_path = tmp_path / "invoice_comma.html"
    invoice_path.write_text(html_invoice, encoding="utf-8")

    record = parse_invoice(invoice_path)

    assert record.invoice_number == "INV-002"
    assert record.customer_name == "Δοκιμαστική Εταιρεία"
    assert record.net_amount == 1234.00
    assert record.vat_amount == 296.16
    assert record.total_amount == 1530.16


def test_load_records_counts_all_assets():
    """Loading records should cover all files across dummy folders."""

    records = load_records(DATA_DIR)
    assert len(records) == 5 + 10 + 10
