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
from automation.pipeline import write_csv, auto_sheets_target
from automation.sinks import push_to_google_sheets, write_excel
from automation.quality import validate_record
from automation.review import apply_edits, load_review_records, mark_status
from automation.templates import records_to_template_rows


def _load_session_records(data_dir: Path) -> List[UnifiedRecord]:
    """Load records once per session to keep the app responsive."""

    if "records" not in st.session_state:
        loaded_records, ingestion_alerts = load_review_records(data_dir)
        st.session_state.records = loaded_records
        st.session_state.original_records = copy.deepcopy(loaded_records)
        st.session_state.ingestion_alerts = ingestion_alerts
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
    auto_config: dict | None = None,
) -> tuple[str | None, str | None]:
    """Run the configured export sink and return a status message."""

    if sink == "excel":
        target = excel_path or output_path.with_suffix(".xlsx")
        try:
            write_excel(template_rows, target)
            return f"Excel export saved to {target}", "success"
        except Exception as exc:  # pragma: no cover - defensive UI feedback
            return f"Excel export failed: {exc}", "error"

    if sink == "sheets":
        if not (spreadsheet_id and worksheet_title and service_account_path) and auto_config:
            spreadsheet_id = auto_config.get("spreadsheet_id", spreadsheet_id)
            worksheet_title = auto_config.get("worksheet_title", worksheet_title or "Sheet1")
            service_account_path = auto_config.get("service_account_path", service_account_path)
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

        if not template_rows:
            return ("No approved records to push to Google Sheets yet.", "info")
        try:
            push_to_google_sheets(
                template_rows,
                spreadsheet_id=spreadsheet_id,
                worksheet_title=worksheet_title,
                service_account_path=service_account_path,
            )
            return (
                f"Pushed {len(template_rows)} approved records to Google Sheets worksheet '{worksheet_title}'.",
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


def _edit_controls(record: UnifiedRecord, editor_key: str) -> UnifiedRecord:
    """Render inline editable fields and return the updated record."""

    st.subheader("Edit fields (double-click to update)")
    editable_fields = {
        "Customer": "customer_name",
        "Email": "email",
        "Phone": "phone",
        "Total Amount": "total_amount",
        "Notes": "notes",
    }
    row = {
        "Customer": record.customer_name or "",
        "Email": record.email or "",
        "Phone": record.phone or "",
        "Total Amount": record.total_amount if record.total_amount is not None else "",
        "Notes": record.notes or "",
    }

    edited_rows = st.data_editor(
        [row],
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        key=f"editor_{editor_key}",
        column_config={
            "Total Amount": st.column_config.NumberColumn("Total Amount", format="%.2f")
        },
    )
    edited_row = edited_rows[0] if edited_rows else row

    updates = {}
    for label, field in editable_fields.items():
        value = edited_row.get(label)
        if field == "total_amount":
            if value in ("", None):
                updates[field] = None
            else:
                try:
                    updates[field] = float(value)
                except (ValueError, TypeError):
                    updates[field] = None
        else:
            updates[field] = value or None
    return apply_edits(record, updates)


def _queue_dashboard(records: List[UnifiedRecord]) -> None:
    """Render a real-time dashboard summarizing queue health."""

    total = len(records)
    approved = len([record for record in records if record.status == "approved"])
    needs_review = len([record for record in records if record.status == "needs_review"])
    rejected = len([record for record in records if record.status == "rejected"])

    top_cols = st.columns(4)
    top_cols[0].metric("Total records", total)
    top_cols[1].metric("Approved", approved)
    top_cols[2].metric("Needs review", needs_review)
    top_cols[3].metric("Rejected", rejected)

    completion_ratio = approved / total if total else 0
    st.progress(completion_ratio)
    st.caption(f"{approved} of {total} ready for export")

def _source_overview(records: List[UnifiedRecord]) -> None:
    """Surface how many records originate from each capture channel."""

    if not records:
        return

    source_counts: dict[str, int] = {}
    for record in records:
        source_counts[record.source] = source_counts.get(record.source, 0) + 1

    st.caption("Mix of sources (forms, emails, invoices) currently loaded")
    st.bar_chart(source_counts)


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
                --primary-color-dark: #0c5b52;
                --accent-color: #f97316;
                --card-color: #eef2ff;
                --text-strong: #0f172a;
            }
            body, button, input, textarea, select, label {
                font-family: "Inter","Noto Sans","Segoe UI",sans-serif !important;
                letter-spacing: 0.01em;
                color: var(--text-strong);
            }
            h1, h2, h3, h4, h5, h6 {
                font-weight: 600;
                color: var(--text-strong);
            }
            div[data-testid="stSidebar"] {
                background: #f8fafc;
                color: var(--text-strong);
                border-right: 1px solid #e2e8f0;
            } 
            div[data-testid="stSidebar"] h1, div[data-testid="stSidebar"] h2, div[data-testid="stSidebar"] label {
                color: var(--text-strong);
            }
            .stButton>button {
                width: 100%;
                padding: 0.75rem;
                font-weight: 600;
                border-radius: 0.55rem;
                border: 1px solid transparent;
                transition: all 0.2s ease;
            }
            .stButton>button[kind="primary"],
            .stButton>button[data-testid="baseButton-primary"] {
                background: #16a34a;
                color: #fff;
                border-color: #15803d;
            }
            .stButton>button[kind="secondary"],
            .stButton>button[data-testid="baseButton-secondary"] {
                background: #eef2ff;
                color: #0f172a;
                border-color: #c7d2fe;
            }
            .stButton>button:hover {
                filter: brightness(0.92);
            }
            .stButton>button:focus-visible {
                outline: 2px solid var(--accent-color);
                outline-offset: 1px;
            }
            .stTextInput input,
            .stNumberInput input,
            textarea {
                background: #f8fafc;
                border-radius: 0.55rem;
                border: 1px solid #cbd5f5;
                color: var(--text-strong);
            }
            .stNumberInput button {
                color: var(--text-strong);
            }
            div[data-testid="stMultiSelect"] div[data-baseweb="tag"] {
                background: rgba(15,118,110,0.16);
                color: #0f4c45;
                border: none;
                font-weight: 600;
            }
            div[data-testid="stMetricLabel"] {
                color: #475569;
                text-transform: none;
            }
            div[data-testid="stMetricValue"] {
                color: var(--text-strong);
                font-weight: 600;
            }
            .dashboard-card {background: var(--card-color); padding: 1rem; border-radius: 0.75rem; border: 1px solid #cbd5f5;}
            .alert-card {border-left: 6px solid var(--accent-color); padding: 0.75rem; background: rgba(249,115,22,0.08); border-radius: 0.6rem; margin-bottom: 0.5rem;}
            .section-title {font-size: 1.05rem; font-weight: 700; color: var(--text-strong); margin-top: 0.5rem;}
            .sticky-panel {position: sticky; top: 1rem; background: rgba(15,118,110,0.05); padding: 1rem; border-radius: 0.8rem; border: 1px solid #cbd5f5;}
            .sticky-panel .stExpander {background: transparent;}
            .metrics-card, .alerts-card {padding: 0.5rem 0.75rem; border-radius: 0.75rem; border: 1px solid rgba(15,118,110,0.15); margin-bottom: 0.8rem;}
            .metrics-card {background: rgba(15,118,110,0.08);}
            .alerts-card {background: rgba(244,114,182,0.12); border-color: rgba(244,114,182,0.35);}
            .human-loop-controls div[data-testid="column"] {flex: 1;}
            .human-loop-controls .stButton>button {width: 100%; font-weight: 600;}
            .human-loop-controls div[data-testid="column"]:nth-of-type(2) .stButton>button {background: #dc2626; color: white; border-color: #b91c1c;}
            .human-loop-controls div[data-testid="column"]:nth-of-type(3) .stButton>button {background: #f97316; color: white; border-color: #ea580c;}
            section[data-testid="stSidebar"], div[data-testid="collapsedControl"] {
                display: none;
            }
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


def _attention_payload(record: UnifiedRecord) -> tuple[bool, List[str]]:
    """Return whether a record needs attention and the messages to show."""

    issues = _detected_issues(record)
    flagged = record.status in {"needs_review", "rejected"}
    if issues or flagged:
        return True, issues or ["Awaiting human decision"]
    return False, []


def _status_badge(status: str) -> str:
    """Return a color-coded label for queue preview."""

    mapping = {
        "approved": "🟢 Approved",
        "pending": "🟡 Pending",
        "needs_review": "🟠 Needs review",
        "rejected": "🔴 Rejected",
    }
    return mapping.get(status, "⚪ Pending")


def main() -> None:
    """Launch a lightweight human-in-the-loop dashboard."""

    st.set_page_config(
        page_title="Review Console", layout="wide", initial_sidebar_state="collapsed"
    )
    _inject_theme()

    st.title("Human Review for Extracted Records")
    st.caption("Keep exports under human control with quick approvals and edits.")
    auto_sheets_config = auto_sheets_target()

    st.session_state.setdefault("data_dir_input", "dummy_data")
    st.session_state.setdefault("output_path_input", "output/reviewed_records.csv")
    st.session_state.setdefault("override_paths_checkbox", False)

    review_tab, config_tab = st.tabs(["Review queue", "Data configuration"])

    with config_tab:
        st.markdown("Adjust the data source and destination settings below.")
        override_paths = st.checkbox(
            "Enable path overrides",
            key="override_paths_checkbox",
            help="Turn on only if you need to load data outside the default dummy_data folder.",
        )
        if not override_paths:
            st.session_state["data_dir_input"] = "dummy_data"
            st.session_state["output_path_input"] = "output/reviewed_records.csv"

        if override_paths:
            config_cols = st.columns(2)
            with config_cols[0]:
                st.text_input(
                    "Data directory",
                    key="data_dir_input",
                    help="Folder with forms, emails, and invoices.",
                )
            with config_cols[1]:
                st.text_input(
                    "Review autosave CSV",
                    key="output_path_input",
                    help="Where reviewed rows are stored.",
                )
        else:
            st.caption(f"Data directory: `{st.session_state['data_dir_input']}`")
            st.caption(f"Review autosave CSV: `{st.session_state['output_path_input']}`")

        derived_excel_path = Path(st.session_state["output_path_input"]).with_suffix(".xlsx")
        st.text_input(
            "Excel output (auto derived)",
            value=str(derived_excel_path),
            key="excel_output_display",
            disabled=True,
        )

        if st.button("Reload data", type="secondary"):
            st.session_state.pop("records", None)
            st.session_state.pop("selected_row", None)
            st.session_state.pop("ingestion_alerts", None)
            _rerun_app()

    data_dir = Path(st.session_state["data_dir_input"])
    output_path = Path(st.session_state["output_path_input"])
    excel_path = output_path.with_suffix(".xlsx")

    def _render_review_tab() -> None:
        records = _load_session_records(data_dir)

        queue_col, metrics_col = st.columns([3, 1.1])
        alert_rows: List[dict[str, str]] = []

        with queue_col:
            sources = sorted({record.source for record in records})
            statuses = sorted({record.status for record in records})

            st.markdown("### Queue filters")
            filter_cols = st.columns([1.3, 1.3, 1])
            with filter_cols[0]:
                selected_sources = st.multiselect(
                    "Filter by source", options=sources, default=sources
                )
            with filter_cols[1]:
                selected_statuses = st.multiselect(
                    "Filter by status", options=statuses, default=statuses
                )
            with filter_cols[2]:
                search_term = st.text_input("Search customer or service").lower()

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

            ingestion_alerts = st.session_state.get("ingestion_alerts", [])
            for alert in ingestion_alerts:
                alert_rows.append(
                    {
                        "Record": "Ingestion",
                        "Source": "SYSTEM",
                        "Status": "error",
                        "Issue": alert,
                    }
                )

            st.markdown("#### Records ready for review")
            if filtered_records:
                st.markdown("<div class='section-title'>Queue preview</div>", unsafe_allow_html=True)
                template_rows = records_to_template_rows(record for _, record in filtered_records)
                preview_rows: List[dict[str, str]] = []
                for (row_index, record), template in zip(filtered_records, template_rows):
                    issues = _detected_issues(record)
                    warning_text = f"⚠️ {'; '.join(issues)}" if issues else ""
                    action_needed = bool(issues or record.status in {"needs_review", "rejected"})
                    ordered_row = {
                        "Row": row_index + 1,
                        "Status": _status_badge(record.status),
                        "Warnings": warning_text,
                        "Type": template["Type"],
                        "Source": template["Source"],
                        "Date": template["Date"],
                        "Client_Name": template["Client_Name"],
                        "Email": template["Email"],
                        "Phone": template["Phone"],
                        "Company": template["Company"],
                        "Service_Interest": template["Service_Interest"],
                        "Total_Amount": template["Total_Amount"],
                        "Amount": template["Amount"],
                        "VAT": template["VAT"],
                        "Invoice_Number": template["Invoice_Number"],
                        "Priority": template["Priority"],
                        "Message": template["Message"],
                    }
                    preview_rows.append(ordered_row)
                    if action_needed:
                        alert_rows.append(
                            {
                                "Record": template["Source"],
                                "Source": record.source.upper(),
                                "Status": record.status,
                                "Issue": warning_text or "Manually flagged",
                            }
                        )
                st.dataframe(preview_rows, use_container_width=True, height=320, hide_index=True)
            else:
                st.info("No records match the current filters.")
            with st.expander("Source mix chart", expanded=False):
                st.caption("Live breakdown of loaded sources.")
                _source_overview(records)

            if filtered_records:
                max_index = len(filtered_records) - 1
                selected_row = min(int(st.session_state.get("selected_row", 0)), max_index)
                st.session_state["selected_row"] = selected_row
                def _advance_row(delta: int = 1) -> None:
                    """Move the selection forward/backward before rerendering."""

                    next_index = min(max(st.session_state["selected_row"] + delta, 0), max_index)
                    st.session_state["selected_row"] = next_index

                nav_cols = st.columns([1, 2, 1])
                with nav_cols[0]:
                    st.markdown("### ")
                    if st.button("⬅️", disabled=selected_row <= 0, type="secondary", help="Previous record"):
                        _advance_row(-1)
                        selected_row = st.session_state["selected_row"]
                with nav_cols[1]:
                    st.markdown(
                        f"**Select row to review**  "
                        f"Row {selected_row + 1} of {max_index + 1} (filtered view)",
                    )
                with nav_cols[2]:
                    st.markdown("### ")
                    if st.button("➡️", disabled=selected_row >= max_index, type="secondary", help="Next record"):
                        _advance_row(1)
                        selected_row = st.session_state["selected_row"]

                selected_display = st.number_input(
                    "Manual row selection",
                    min_value=1,
                    max_value=max_index + 1,
                    step=1,
                    format="%d",
                    value=selected_row + 1,
                )

                if selected_display - 1 != selected_row:
                    st.session_state["selected_row"] = int(selected_display - 1)
                    selected_row = st.session_state["selected_row"]
                st.session_state["selected_row"] = selected_row
                record_index, record = filtered_records[selected_row]

                st.markdown(f"**Source:** {record.source} — {record.source_name}")
                st.caption(f"Current status: {record.status} | Notes: {record.notes or 'No reviewer notes yet.'}")

                editor_key = f"{record_index}_{record.source_name}"
                edited = _edit_controls(record, editor_key)

                def _commit_action(index: int, updated: UnifiedRecord, message: str, level: str, renderer_col) -> None:
                    """Persist record updates, sync to disk, and render feedback next to the button."""

                    _persist_record(index, updated)
                    _save_records(st.session_state.records, output_path)
                    st.session_state["last_action"] = {"message": message, "level": level}
                    renderer = {
                        "success": renderer_col.success,
                        "warning": renderer_col.warning,
                        "info": renderer_col.info,
                        "error": renderer_col.error,
                    }.get(level, renderer_col.info)
                    renderer(message)
                    _rerun_app()

                st.markdown('<div class="human-loop-controls">', unsafe_allow_html=True)
                action_cols = st.columns(3)
                with action_cols[0]:
                    if st.button("👍 Approve", type="primary"):
                        updated = mark_status(edited, "approved")
                        message = f"Record '{record.source_name}' approved."
                        _advance_row(1)
                        _commit_action(record_index, updated, message, "success", action_cols[0])
                with action_cols[1]:
                    if st.button("🛑 Reject", type="secondary"):
                        updated = mark_status(edited, "rejected")
                        message = (
                            f"Record '{record.source_name}' rejected. "
                            f"Review notes: {edited.notes or 'no notes provided.'}"
                        )
                        _advance_row(1)
                        _commit_action(record_index, updated, message, "warning", action_cols[1])
                with action_cols[2]:
                    if st.button("📝 Needs review", type="secondary"):
                        updated = mark_status(edited, "needs_review")
                        message = (
                            f"Record '{record.source_name}' flagged for follow-up. "
                            f"Quality findings: {edited.notes or 'none recorded.'}"
                        )
                        _advance_row(1)
                        _commit_action(record_index, updated, message, "info", action_cols[2])
                st.markdown("</div>", unsafe_allow_html=True)

                st.markdown("### Finalize & export")
                sink_options = ["csv", "excel", "sheets"]
                export_sink = st.radio(
                    "Choose destination",
                    options=sink_options,
                    format_func=lambda value: value.upper(),
                    horizontal=True,
                    key="export_sink_choice",
                )
                st.session_state.setdefault("csv_export_path", "output/approved_records.csv")
                st.session_state.setdefault("excel_export_path", str(excel_path))
                st.session_state.setdefault(
                    "sheets_spreadsheet_id",
                    auto_sheets_config.get("spreadsheet_id", "") if auto_sheets_config else "",
                )
                st.session_state.setdefault(
                    "sheets_worksheet",
                    auto_sheets_config.get("worksheet_title", "Sheet1") if auto_sheets_config else "Sheet1",
                )
                st.session_state.setdefault(
                    "sheets_service_account",
                    str(auto_sheets_config.get("service_account_path", "service_account.json"))
                    if auto_sheets_config
                    else "service_account.json",
                )

                csv_input_value = st.text_input(
                    "CSV file path",
                    value=st.session_state["csv_export_path"],
                    key="csv_export_path",
                    disabled=export_sink != "csv",
                )
                excel_input_value = st.text_input(
                    "Excel file path",
                    value=st.session_state["excel_export_path"],
                    key="excel_export_path",
                    disabled=export_sink != "excel",
                )
                csv_export_path = Path(csv_input_value or "output/approved_records.csv")
                export_excel_path = Path(excel_input_value or str(excel_path))

                sheets_enabled = False
                if export_sink == "sheets":
                    toggle_default = st.session_state.get("sheets_settings_enabled", False)
                    sheets_enabled = st.checkbox(
                        "Enable Google Sheets settings",
                        value=toggle_default,
                        key="sheets_settings_enabled",
                        help="Turn on to review or override the target Sheet details.",
                    )
                    if sheets_enabled:
                        sheet_cols = st.columns(3)
                        with sheet_cols[0]:
                            st.text_input(
                                "Spreadsheet ID",
                                key="sheets_spreadsheet_id",
                                help="Copied from the Google Sheet URL.",
                            )
                        with sheet_cols[1]:
                            st.text_input(
                                "Worksheet title",
                                key="sheets_worksheet",
                            )
                        with sheet_cols[2]:
                            st.text_input(
                                "Service account JSON",
                                key="sheets_service_account",
                            )
                    else:
                        st.caption("Using stored Google Sheets defaults. Enable the toggle above to edit.")

                if st.button("Export approved rows", type="primary"):
                    approved_records = [record for record in st.session_state.records if record.status == "approved"]
                    if not approved_records:
                        st.info("No approved records available for export.")
                    else:
                        approved_rows = records_to_template_rows(approved_records)
                        if export_sink == "csv":
                            write_csv(approved_rows, csv_export_path)
                            st.success(
                                f"Saved {len(approved_rows)} approved rows to {csv_export_path.resolve()}"
                            )
                        elif export_sink == "excel":
                            message, level = _export_sink(
                                approved_records,
                                approved_rows,
                                sink="excel",
                                output_path=output_path,
                                excel_path=export_excel_path,
                                spreadsheet_id="",
                                worksheet_title="",
                                service_account_path=None,
                                auto_config=auto_sheets_config,
                            )
                            renderer = {"success": st.success, "warning": st.warning, "error": st.error}.get(
                                level or "success", st.info
                            )
                            renderer(message or "Excel export completed.")
                        else:
                            service_account_value = st.session_state.get("sheets_service_account", "").strip()
                            service_account_path = (
                                Path(service_account_value) if service_account_value else None
                            )
                            message, level = _export_sink(
                                approved_records,
                                approved_rows,
                                sink="sheets",
                                output_path=output_path,
                                excel_path=None,
                                spreadsheet_id=st.session_state.get("sheets_spreadsheet_id", "").strip(),
                                worksheet_title=st.session_state.get("sheets_worksheet", "").strip(),
                                service_account_path=service_account_path,
                                auto_config=auto_sheets_config,
                            )
                            renderer = {"success": st.success, "warning": st.warning, "error": st.error}.get(
                                level or "success", st.info
                            )
                            renderer(message or "Google Sheets sync completed.")
            else:
                st.session_state.pop("selected_row", None)
        with metrics_col:
            st.markdown('<div class="sticky-panel">', unsafe_allow_html=True)
            st.markdown('<div class="metrics-card">', unsafe_allow_html=True)
            st.subheader("Live dashboard")
            _queue_dashboard(records)
            st.markdown("</div>", unsafe_allow_html=True)
            st.markdown('<div class="alerts-card">', unsafe_allow_html=True)
            st.subheader("Alerts")
            if alert_rows:
                st.caption(f"{len(alert_rows)} record(s) flagged.")
                st.dataframe(alert_rows, use_container_width=True, hide_index=True, height=280)
            else:
                st.success("No alerts found for the current filters.")
            st.markdown("</div></div>", unsafe_allow_html=True)


    with review_tab:
        _render_review_tab()


if __name__ == "__main__":
    main()
