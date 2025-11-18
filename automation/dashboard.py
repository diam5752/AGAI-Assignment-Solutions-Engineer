"""Streamlit dashboard to review, edit, and approve extracted records."""
from pathlib import Path
from typing import List
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.pipeline import write_csv
from automation.review import (
    apply_edits,
    load_review_records,
    mark_status,
    records_to_rows,
)
from automation.models import UnifiedRecord


def _load_session_records(data_dir: Path) -> List[UnifiedRecord]:
    """Load records once per session to keep the app responsive."""

    if "records" not in st.session_state:
        st.session_state.records = load_review_records(data_dir)
    return st.session_state.records


def _persist_record(index: int, new_record: UnifiedRecord) -> None:
    """Replace the record at the given index in session state."""

    st.session_state.records[index] = new_record


def _edit_controls(record: UnifiedRecord) -> UnifiedRecord:
    """Render editable fields and return the updated record."""

    st.subheader("Edit fields")
    customer_name = st.text_input("Customer", value=record.customer_name or "")
    email = st.text_input("Email", value=record.email or "")
    phone = st.text_input("Phone", value=record.phone or "")
    total_amount = st.number_input(
        "Total Amount", value=record.total_amount or 0.0, step=0.01, format="%.2f"
    )
    notes = st.text_area("Notes", value=record.notes or "")

    updates = {
        "customer_name": customer_name or None,
        "email": email or None,
        "phone": phone or None,
        "total_amount": float(total_amount) if total_amount else None,
        "notes": notes or None,
    }
    return apply_edits(record, updates)


def main() -> None:
    """Launch a lightweight human-in-the-loop dashboard."""

    st.title("Human Review for Extracted Records")
    data_dir = Path(st.sidebar.text_input("Data directory", value="dummy_data"))
    output_path = Path(st.sidebar.text_input("Output CSV", value="output/reviewed_records.csv"))

    records = _load_session_records(data_dir)
    st.write("Records ready for review:")
    st.dataframe(records_to_rows(records))

    selected = st.number_input(
        "Select row to review", min_value=0, max_value=max(len(records) - 1, 0), step=1
    )
    record = records[selected]

    st.markdown(f"**Source:** {record.source} — {record.source_name}")
    edited = _edit_controls(record)

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Approve"):
            _persist_record(selected, mark_status(edited, "approved"))
            st.success("Record approved")
    with col2:
        if st.button("Reject"):
            _persist_record(selected, mark_status(edited, "rejected", note="rejected by reviewer"))
            st.warning("Record rejected")
    with col3:
        if st.button("Mark needs review"):
            _persist_record(selected, mark_status(edited, "needs_review", note="sent back for edits"))
            st.info("Record flagged for follow-up")

    if st.button("Save CSV"):
        write_csv(st.session_state.records, output_path)
        st.success(f"Saved to {output_path}")


if __name__ == "__main__":
    main()
