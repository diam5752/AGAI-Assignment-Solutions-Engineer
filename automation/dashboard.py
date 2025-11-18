"""Streamlit dashboard to review, edit, and approve extracted records."""
from pathlib import Path
from typing import List

import streamlit as st

# Allow running via "streamlit run automation/dashboard.py" without installing the package
# by ensuring the repository root is on ``sys.path``.
if __package__ in {None, ""}:
    import sys

    sys.path.append(str(Path(__file__).resolve().parent.parent))

from automation.models import UnifiedRecord
from automation.pipeline import write_csv
from automation.review import (
    apply_edits,
    load_review_records,
    mark_status,
    records_to_rows,
)


def _load_session_records(data_dir: Path) -> List[UnifiedRecord]:
    """Load records once per session to keep the app responsive."""

    if "records" not in st.session_state:
        st.session_state.records = load_review_records(data_dir)
    return st.session_state.records


def _persist_record(index: int, new_record: UnifiedRecord) -> None:
    """Replace the record at the given index in session state."""

    st.session_state.records[index] = new_record


def _save_records(records: List[UnifiedRecord], output_path: Path) -> None:
    """Write the in-memory records to disk."""

    write_csv(records_to_rows(records), output_path)


def _rerun_app() -> None:
    """Trigger a Streamlit rerun, compatible with newer and older APIs."""

    rerun = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if not rerun:
        raise RuntimeError("Streamlit does not expose a rerun helper.")
    rerun()


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
    last_action = st.session_state.get("last_action")
    if last_action and last_action.get("message"):
        level = last_action.get("level", "info")
        renderer = {
            "success": st.success,
            "warning": st.warning,
            "info": st.info,
            "error": st.error,
        }.get(level, st.info)
        renderer(last_action["message"])
    data_dir = Path(st.sidebar.text_input("Data directory", value="dummy_data"))
    output_path = Path(st.sidebar.text_input("Output CSV", value="output/reviewed_records.csv"))

    if st.sidebar.button("Reload data"):
        st.session_state.pop("records", None)
        st.session_state.pop("selected_row", None)
        _rerun_app()

    records = _load_session_records(data_dir)

    sources = sorted({record.source for record in records})
    statuses = sorted({record.status for record in records})
    selected_sources = st.sidebar.multiselect("Filter by source", sources, default=sources)
    selected_statuses = st.sidebar.multiselect("Filter by status", statuses, default=statuses)
    search_term = st.sidebar.text_input("Search customer or service").lower()

    def _matches_search(record: UnifiedRecord) -> bool:
        haystacks = [record.customer_name or "", record.service or ""]
        return any(search_term in value.lower() for value in haystacks) if search_term else True

    filtered_records = [
        (index, record)
        for index, record in enumerate(records)
        if (not selected_sources or record.source in selected_sources)
        and (not selected_statuses or record.status in selected_statuses)
        and _matches_search(record)
    ]

    st.write("Records ready for review:")
    if filtered_records:
        st.dataframe(records_to_rows(record for _, record in filtered_records))
    else:
        st.info("No records match the current filters.")

    st.subheader("Alerts")
    alerts = [
        record
        for record in records
        if record.status == "needs_review" or (record.notes and "quality" in record.notes.lower())
    ]
    if alerts:
        for alert in alerts:
            alert_message = f"{alert.source_name} — status: {alert.status}"
            if alert.notes:
                alert_message = f"{alert_message} — notes: {alert.notes}"
            if alert.status == "needs_review":
                st.warning(alert_message)
            else:
                st.info(alert_message)
    else:
        st.success("No alerts found for the current selection.")

    if not filtered_records:
        st.session_state.pop("selected_row", None)
        return

    max_index = max(len(filtered_records) - 1, 0)
    selected_row = st.session_state.get("selected_row", 0)
    selected_row = min(selected_row, max_index)
    selected = st.number_input(
        "Select row to review",
        min_value=0,
        max_value=max_index,
        step=1,
        value=selected_row,
        format="%d",
    )
    selected = int(selected)
    st.session_state["selected_row"] = selected
    record_index, record = filtered_records[selected]

    st.markdown(f"**Source:** {record.source} — {record.source_name}")
    st.caption(f"Current status: {record.status} | Notes: {record.notes or 'No reviewer notes yet.'}")
    edited = _edit_controls(record)

    def _commit_action(index: int, updated: UnifiedRecord, message: str, level: str) -> None:
        """Persist record updates, sync to disk, and log a toast message."""

        _persist_record(index, updated)
        _save_records(st.session_state.records, output_path)
        st.session_state["last_action"] = {"message": message, "level": level}

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Approve"):
            updated = mark_status(edited, "approved")
            message = f"Record '{record.source_name}' approved. Notes: {edited.notes or 'No quality issues noted.'}"
            _commit_action(record_index, updated, message, "success")
            st.success(message)
    with col2:
        if st.button("Reject"):
            updated = mark_status(edited, "rejected", note="rejected by reviewer")
            message = (
                f"Record '{record.source_name}' rejected. "
                f"Review notes: {edited.notes or 'no notes provided.'}"
            )
            _commit_action(record_index, updated, message, "warning")
            st.warning(message)
    with col3:
        if st.button("Mark needs review"):
            updated = mark_status(edited, "needs_review", note="sent back for edits")
            message = (
                f"Record '{record.source_name}' flagged for follow-up. "
                f"Quality findings: {edited.notes or 'none recorded.'}"
            )
            _commit_action(record_index, updated, message, "info")
            st.info(message)

    if st.button("Save CSV"):
        _save_records(st.session_state.records, output_path)
        message = f"Saved {len(st.session_state.records)} records to {output_path}"
        st.session_state["last_action"] = {"message": message, "level": "success"}
        st.success(message)


if __name__ == "__main__":
    main()
