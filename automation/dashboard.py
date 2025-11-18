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
from automation.sinks import push_to_google_sheets, write_excel
from automation.review import apply_edits, load_review_records, mark_status
from automation.templates import records_to_template_rows


def _load_session_records(data_dir: Path) -> List[UnifiedRecord]:
    """Load records once per session to keep the app responsive."""

    if "records" not in st.session_state:
        st.session_state.records = load_review_records(data_dir)
    return st.session_state.records


def _persist_record(index: int, new_record: UnifiedRecord) -> None:
    """Replace the record at the given index in session state."""

    st.session_state.records[index] = new_record


def _save_records(records: List[UnifiedRecord], output_path: Path) -> List[dict]:
    """Write the in-memory records to disk and return template-aligned rows."""

    template_rows = records_to_template_rows(records)
    write_csv(template_rows, output_path)
    return template_rows


def _export_sink(
    records: List[UnifiedRecord],
    template_rows: List[dict],
    sink: str,
    output_path: Path,
    excel_path: Path | None,
    spreadsheet_id: str,
    worksheet_title: str,
    service_account_path: Path | None,
) -> tuple[str | None, str | None]:
    """Run the configured export sink and return a status message."""

    if sink == "csv":
        return None, None

    if sink == "excel":
        target = excel_path or output_path.with_suffix(".xlsx")
        try:
            write_excel(template_rows, target)
            return f"Excel export saved to {target}", "success"
        except Exception as exc:  # pragma: no cover - defensive UI feedback
            return f"Excel export failed: {exc}", "error"

    if sink == "sheets":
        if not spreadsheet_id or not worksheet_title or not service_account_path:
            return (
                "Provide spreadsheet ID, worksheet title, and a service account file to sync with Google Sheets.",
                "warning",
            )
        if not service_account_path.exists():
            return (
                f"Service account file not found at {service_account_path}.",
                "warning",
            )

        approved_rows = [
            template_rows[index] for index, record in enumerate(records) if record.status == "approved"
        ]
        if not approved_rows:
            return ("No approved records to push to Google Sheets yet.", "info")
        try:
            push_to_google_sheets(
                approved_rows,
                spreadsheet_id=spreadsheet_id,
                worksheet_title=worksheet_title,
                service_account_path=service_account_path,
            )
            return (
                f"Pushed {len(approved_rows)} approved records to Google Sheets worksheet '{worksheet_title}'.",
                "success",
            )
        except Exception as exc:  # pragma: no cover - defensive UI feedback
            return (f"Google Sheets sync failed: {exc}", "error")

    return None, None


def _combined_feedback(
    primary_message: str, primary_level: str, export_feedback: tuple[str | None, str | None]
) -> tuple[str, str]:
    """Merge action and export messages while keeping the highest-severity level."""

    export_message, export_level = export_feedback
    if not export_message:
        return primary_message, primary_level

    combined_message = f"{primary_message} | {export_message}"
    severity = {"success": 0, "info": 1, "warning": 2, "error": 3}
    combined_level = (
        export_level
        if severity.get(export_level or "info", 0) > severity.get(primary_level, 0)
        else primary_level
    )
    return combined_message, combined_level


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


def _status_counters(records: List[UnifiedRecord]) -> None:
    """Summarize review progress so reviewers see real-time queue health."""

    if not records:
        return

    status_counts: dict[str, int] = {}
    for record in records:
        status_counts[record.status] = status_counts.get(record.status, 0) + 1

    top_statuses = sorted(status_counts.items(), key=lambda item: item[0])
    columns = st.columns(len(top_statuses))
    for column, (status, count) in zip(columns, top_statuses):
        column.metric(label=status.replace("_", " ").title(), value=count)


def _source_overview(records: List[UnifiedRecord]) -> None:
    """Surface how many records originate from each capture channel."""

    if not records:
        return

    source_counts: dict[str, int] = {}
    for record in records:
        source_counts[record.source] = source_counts.get(record.source, 0) + 1

    st.caption("Mix of sources (forms, emails, invoices) currently loaded")
    st.bar_chart(source_counts)


def _step_selected_row(delta: int, max_index: int) -> int:
    """Adjust the selected row index with bounds checking for navigation buttons."""

    current = int(st.session_state.get("selected_row", 0))
    updated = min(max(current + delta, 0), max_index)
    st.session_state["selected_row"] = updated
    st.session_state["selected_row_input"] = updated
    return updated


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

    sink = st.sidebar.selectbox(
        "Export sink (CSV always saved)",
        options=["csv", "excel", "sheets"],
        format_func=lambda value: value.upper(),
    )
    excel_default = output_path.with_suffix(".xlsx")
    excel_path_value = st.sidebar.text_input("Excel output", value=str(excel_default))
    excel_path = Path(excel_path_value) if excel_path_value else None

    st.sidebar.markdown("**Google Sheets settings**")
    spreadsheet_id = st.sidebar.text_input("Spreadsheet ID")
    worksheet_title = st.sidebar.text_input("Worksheet title", value="Sheet1")
    service_account_file = st.sidebar.text_input("Service account JSON", value="service_account.json")
    service_account_path = Path(service_account_file) if service_account_file else None

    if sink == "sheets":
        sheets_ready = bool(spreadsheet_id and worksheet_title and service_account_file)
        if sheets_ready and service_account_path and service_account_path.exists():
            st.sidebar.success("Google Sheets settings look valid.")
        elif sheets_ready:
            st.sidebar.warning(f"Service account file not found at {service_account_path}.")
        else:
            st.sidebar.warning(
                "Enter a Spreadsheet ID, worksheet title, and a service account JSON file to enable sync."
            )

    st.sidebar.info(
        "Workflow: filter by source/status, navigate records with the arrows, edit fields, and approve/reject. "
        "Approved rows will always be written to CSV and optionally to Excel or Sheets as configured."
    )

    if st.sidebar.button("Reload data"):
        st.session_state.pop("records", None)
        st.session_state.pop("selected_row", None)
        _rerun_app()

    records = _load_session_records(data_dir)

    st.subheader("Review progress snapshot")
    _status_counters(records)
    _source_overview(records)

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
        table_rows = records_to_template_rows(record for _, record in filtered_records)
        st.dataframe(table_rows)
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
    selected_row = int(st.session_state.get("selected_row", 0))
    selected_row = min(selected_row, max_index)

    nav_prev, nav_label, nav_next, nav_jump = st.columns([1, 2, 1, 1])
    with nav_prev:
        if st.button("⬅️ Previous", disabled=selected_row <= 0):
            selected_row = _step_selected_row(-1, max_index)
    with nav_label:
        st.markdown(
            f"**Select row to review**  "+
            f"Row {selected_row + 1} of {max_index + 1} (filtered view)",
        )
    with nav_next:
        if st.button("Next ➡️", disabled=selected_row >= max_index):
            selected_row = _step_selected_row(1, max_index)
    with nav_jump:
        if st.button("Skip to issue"):
            ahead = [
                idx for idx, (_, rec) in enumerate(filtered_records)
                if rec.status == "needs_review" and idx > selected_row
            ]
            target = ahead[0] if ahead else selected_row
            selected_row = _step_selected_row(target - selected_row, max_index)

    def _sync_row_input() -> None:
        st.session_state["selected_row"] = int(st.session_state["selected_row_input"])

    selected = st.number_input(
        "Manual row selection",
        min_value=0,
        max_value=max_index,
        step=1,
        value=selected_row,
        format="%d",
        key="selected_row_input",
        on_change=_sync_row_input,
    )

    selected_row = int(st.session_state.get("selected_row", selected))
    st.session_state["selected_row"] = selected_row
    record_index, record = filtered_records[selected_row]

    st.markdown(f"**Source:** {record.source} — {record.source_name}")
    st.caption(f"Current status: {record.status} | Notes: {record.notes or 'No reviewer notes yet.'}")
    with st.expander("Quality & readiness", expanded=True):
        if record.status == "needs_review":
            st.warning(
                "This record was flagged during automated checks. Prioritize reviewing the highlighted fields before exporting."
            )
        else:
            st.info("Automated checks passed; confirm the values below before approving.")
        st.markdown(
            "- **Customer:** "
            f"{record.customer_name or 'Unknown'}  \n"
            f"- **Contact:** {record.email or record.phone or 'Not captured'}  \n"
            f"- **Amounts:** Net {record.net_amount or 'n/a'}, VAT {record.vat_amount or 'n/a'}, Total {record.total_amount or 'n/a'}"
        )

    edited = _edit_controls(record)

    renderers = {
        "success": st.success,
        "warning": st.warning,
        "info": st.info,
        "error": st.error,
    }

    def _commit_action(index: int, updated: UnifiedRecord, message: str, level: str) -> None:
        """Persist record updates, sync to disk, trigger exports, and log a toast."""

        _persist_record(index, updated)
        rows = _save_records(st.session_state.records, output_path)
        export_feedback = _export_sink(
            st.session_state.records,
            rows,
            sink=sink,
            output_path=output_path,
            excel_path=excel_path,
            spreadsheet_id=spreadsheet_id.strip(),
            worksheet_title=worksheet_title.strip(),
            service_account_path=service_account_path,
        )
        combined_message, combined_level = _combined_feedback(message, level, export_feedback)
        st.session_state["last_action"] = {"message": combined_message, "level": combined_level}
        renderers.get(combined_level, st.info)(combined_message)

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Approve"):
            updated = mark_status(edited, "approved")
            message = f"Record '{record.source_name}' approved. Notes: {edited.notes or 'No quality issues noted.'}"
            _commit_action(record_index, updated, message, "success")
    with col2:
        if st.button("Reject"):
            updated = mark_status(edited, "rejected", note="rejected by reviewer")
            message = (
                f"Record '{record.source_name}' rejected. "
                f"Review notes: {edited.notes or 'no notes provided.'}"
            )
            _commit_action(record_index, updated, message, "warning")
    with col3:
        if st.button("Mark needs review"):
            updated = mark_status(edited, "needs_review", note="sent back for edits")
            message = (
                f"Record '{record.source_name}' flagged for follow-up. "
                f"Quality findings: {edited.notes or 'none recorded.'}"
            )
            _commit_action(record_index, updated, message, "info")

    if st.button("Save"):
        rows = _save_records(st.session_state.records, output_path)
        export_feedback = _export_sink(
            st.session_state.records,
            rows,
            sink=sink,
            output_path=output_path,
            excel_path=excel_path,
            spreadsheet_id=spreadsheet_id.strip(),
            worksheet_title=worksheet_title.strip(),
            service_account_path=service_account_path,
        )
        message = f"Saved {len(st.session_state.records)} records to {output_path}"
        combined_message, combined_level = _combined_feedback(message, "success", export_feedback)
        st.session_state["last_action"] = {"message": combined_message, "level": combined_level}
        renderers.get(combined_level, st.info)(combined_message)


if __name__ == "__main__":
    main()
