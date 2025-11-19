"""Data models for unified records extracted from diverse sources."""
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


@dataclass
class UnifiedRecord:
    """Represents a single normalized record across forms, emails, or invoices."""

    source: str
    source_name: str
    customer_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    service: Optional[str] = None
    message: Optional[str] = None
    priority: Optional[str] = None
    submission_date: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    net_amount: Optional[float] = None
    vat_amount: Optional[float] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = "EUR"
    status: str = "pending_review"
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dictionary representation for CSV serialization."""

        return asdict(self)
