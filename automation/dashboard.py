"""Streamlit dashboard to review, edit, and approve extracted records."""
import copy
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
from automation.quality import validate_record
from automation.review import apply_edits, load_review_records, mark_status
from automation.templates import records_to_template_rows


def _load_session_records(data_dir: Path) -> List[UnifiedRecord]:
    """Load records once per session to keep the app responsive."""

    if "records" not in st.session_state:
        loaded = load_review_records(data_dir)
        st.session_state.records = loaded
        st.session_state.original_records = [copy.deepcopy(record) for record in loaded]
    return st.session_state.records


def _persist_record(index: int, new_record: UnifiedRecord) -> None:
    """Replace the record at the given index in session state."""

    st.session_state.records[index] = new_record


def _save_records(records: List[UnifiedRecord], output_path: Path) -> None:
    """Write the in-memory records to disk."""

    template_rows = records_to_template_rows(records)
    write_csv(template_rows, output_path)


def _detected_issues(record: UnifiedRecord) -> List[str]:
    """Return validation findings to populate the alerts panel."""

    findings = validate_record(record)
    if record.notes and "quality" in record.notes.lower():
        findings.append(record.notes)
    return findings


def _inject_theme() -> None:
    """Increase contrast and spacing for better readability."""

    st.markdown(
        """
        <style>
            :root {
                --primary-color: #0f766e;
                --accent-color: #f97316;
                --surface-color: #0b1220;
                --card-color: #111827;
                --text-strong: #f8fafc;
            }
            body {background-color: var(--surface-color);}
            [data-testid="stAppViewContainer"] {background-color: var(--surface-color); color: var(--text-strong);}
            section.main h1, section.main h2, section.main h3, section.main label {color: var(--text-strong);}
            .stButton>button {width: 100%; padding: 0.9rem; font-weight: 700; border-radius: 0.6rem; font-size: 1rem;}
            .stButton>button[data-baseweb="button"] {background: var(--primary-color); color: white; border: none;}
            .stButton>button[kind="secondary"] {background: #1f2937; color: var(--text-strong);}
            .dashboard-card {background: var(--card-color); padding: 1rem; border-radius: 0.75rem; border: 1px solid #1f2937;}
            .alert-card {border-left: 6px solid var(--accent-color); padding: 0.75rem; background: rgba(249,115,22,0.12); border-radius: 0.6rem; margin-bottom: 0.5rem;}
            .section-title {font-size: 1.05rem; font-weight: 700; color: var(--text-strong); margin-top: 0.5rem;}
            .record-panel {background: #0c1a2c; border: 1px solid #1f2937; border-radius: 0.75rem; padding: 1rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _step_selected_row(delta: int, max_index: int) -> int:
    """Adjust the selected row index with bounds checking for navigation buttons."""

    current = int(st.session_state.get("selected_row", 0))
    updated = min(max(current + delta, 0), max_index)
    st.session_state["selected_row"] = updated
    return updated


def _summary_panel(records: List[UnifiedRecord]) -> None:
    """Display real-time counts of review statuses."""

    status_labels = {
        "approved": "Approved",
        "needs_review": "Pending",
        "rejected": "Rejected",
        "auto_valid": "Ready",
        "pending_review": "Pending",
        "pending": "Pending",
    }
    counts: dict[str, int] = {"total": len(records)}
    for record in records:
        label = status_labels.get(record.status, record.status)
        counts[label] = counts.get(label, 0) + 1

    st.markdown("<div class='section-title'>Review overview</div>", unsafe_allow_html=True)
    cols = st.columns(4)
    cols[0].metric("Total", counts.get("total", 0))
    cols[1].metric("Pending", counts.get("Pending", 0))
    cols[2].metric("Approved", counts.get("Approved", 0))
    cols[3].metric("Rejected", counts.get("Rejected", 0))


def _issues_panel(records: List[UnifiedRecord]) -> None:
    """List validation issues for each record in a dedicated panel."""

    st.markdown("<div class='section-title'>Validation alerts</div>", unsafe_allow_html=True)
    alerts = []
    for index, record in enumerate(records):
        issues = _detected_issues(record)
        if issues:
            alerts.append((index, record, issues))

    if not alerts:
        st.success("No validation issues detected across the queue.")
        return

    for index, record, issues in alerts:
        st.markdown(
            f"<div class='alert-card'><strong>Row {index + 1}:</strong> {record.source_name}</div>",
            unsafe_allow_html=True,
        )
        for issue in issues:
            st.warning(issue)


def _record_table(records: List[UnifiedRecord]) -> None:
    """Show a quick table of records and their statuses."""

    preview_rows = []
    for idx, record in enumerate(records):
        preview_rows.append(
            {
                "#": idx + 1,
                "Customer": record.customer_name,
                "Email": record.email,
                "Total": record.total_amount,
                "Status": record.status,
            }
        )
    st.dataframe(preview_rows, use_container_width=True, height=320)


def _selected_record_details(record: UnifiedRecord) -> None:
    """Present key facts for the current record."""

    st.markdown(
        f"**Source:** {record.source_name or record.source} &nbsp;|&nbsp; **Status:** {record.status}",
        unsafe_allow_html=True,
    )
    detail_cols = st.columns(2)
    with detail_cols[0]:
        st.write(
            f"**Customer:** {record.customer_name or 'Unknown'}\n"
            f"**Email:** {record.email or 'Not provided'}\n"
            f"**Phone:** {record.phone or 'Not provided'}"
        )
    with detail_cols[1]:
        st.write(
            f"**Service:** {record.service or 'Not captured'}\n"
            f"**Total:** {record.total_amount or 'n/a'}\n"
            f"**Notes:** {record.notes or 'No notes yet.'}"
        )


def main() -> None:
    """Launch a streamlined human-in-the-loop dashboard."""

    st.set_page_config(page_title="Review Console", layout="wide")
    _inject_theme()

    st.title("Review Console")
    st.caption("Approve, correct, or reject captured customer records with full control.")

    data_dir = Path("dummy_data")
    output_path = Path("output/reviewed_records.csv")

    records = _load_session_records(data_dir)
    if not records:
        st.info("No records are available for review. Data ingestion runs automatically.")
        return

    with st.container():
        _summary_panel(records)
        st.markdown("<div class='section-title'>All records</div>", unsafe_allow_html=True)
        _record_table(records)

    st.markdown("<div class='section-title'>Validation for current record</div>", unsafe_allow_html=True)

    max_index = len(records) - 1
    selected_row = int(st.session_state.get("selected_row", 0))
    selected_row = min(max(selected_row, 0), max_index)

    nav_prev, nav_label, nav_next, nav_skip = st.columns([1, 2, 1, 1])
    with nav_prev:
        if st.button("⬅️ Previous", disabled=selected_row <= 0, type="secondary"):
            selected_row = _step_selected_row(-1, max_index)
    with nav_label:
        st.markdown(f"**Row {selected_row + 1} of {max_index + 1}**")
    with nav_next:
        if st.button("Next ➡️", disabled=selected_row >= max_index, type="primary"):
            selected_row = _step_selected_row(1, max_index)
    with nav_skip:
        if st.button("Skip to issue", type="secondary"):
            ahead = [idx for idx, rec in enumerate(records) if _detected_issues(rec) and idx > selected_row]
            target = ahead[0] if ahead else selected_row
            selected_row = _step_selected_row(target - selected_row, max_index)

    st.session_state["selected_row"] = selected_row
    record = records[selected_row]

    issue_list = _detected_issues(record)
    if issue_list:
        for issue in issue_list:
            st.warning(issue)
    else:
        st.success("No validation issues for this record.")

    st.markdown("<div class='section-title'>Record details</div>", unsafe_allow_html=True)
    with st.container():
        _selected_record_details(record)

    st.markdown("<div class='section-title'>Edit fields</div>", unsafe_allow_html=True)
    with st.form("edit_form", clear_on_submit=False):
        customer_name = st.text_input("Customer", value=record.customer_name or "")
        email = st.text_input("Email", value=record.email or "")
        phone = st.text_input("Phone", value=record.phone or "")
        total_amount = st.number_input(
            "Total Amount", value=record.total_amount or 0.0, step=0.01, format="%.2f"
        )
        notes = st.text_area("Notes", value=record.notes or "")
        save_edits = st.form_submit_button("Save changes", type="primary")

    def _current_edits(base: UnifiedRecord) -> UnifiedRecord:
        updates = {
            "customer_name": customer_name or None,
            "email": email or None,
            "phone": phone or None,
            "total_amount": float(total_amount) if total_amount else None,
            "notes": notes or None,
        }
        return apply_edits(base, updates)

    if save_edits:
        updated = _current_edits(record)
        _persist_record(selected_row, updated)
        _save_records(st.session_state.records, output_path)
        st.success("Edits saved for this record.")
        record = updated

    st.markdown("<div class='section-title'>Human-in-the-loop controls</div>", unsafe_allow_html=True)
    action_cols = st.columns(3)
    with action_cols[0]:
        if st.button("Approve", type="primary"):
            updated = mark_status(_current_edits(record), "approved")
            _persist_record(selected_row, updated)
            _save_records(st.session_state.records, output_path)
            st.success(f"Record '{updated.source_name}' approved.")
    with action_cols[1]:
        if st.button("Reject", type="secondary"):
            updated = mark_status(_current_edits(record), "rejected", note="rejected by reviewer")
            _persist_record(selected_row, updated)
            _save_records(st.session_state.records, output_path)
            st.warning(f"Record '{updated.source_name}' rejected.")
    with action_cols[2]:
        if st.button("Reset changes", type="secondary"):
            original = st.session_state.original_records[selected_row]
            _persist_record(selected_row, original)
            st.info("Reverted to the original captured values.")

    st.divider()
    _issues_panel(records)


if __name__ == "__main__":
    main()
