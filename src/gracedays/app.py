from __future__ import annotations

import json
import re
from datetime import date
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from gracedays.clock import Clock
from gracedays.config import Settings
from gracedays.duplicates import find_duplicates
from gracedays.extraction import ExtractionError, ExtractionService
from gracedays.gateway import MCPGatewayError, McpGateway
from gracedays.models import EvidenceReview, ReviewPurchase, VerificationStatus
from gracedays.orchestrator import AgentOrchestrator
from gracedays.providers import create_provider


st.set_page_config(page_title="GraceDays", page_icon="◷", layout="wide", initial_sidebar_state="expanded")


@st.cache_resource
def get_settings() -> Settings:
    return Settings.from_env()


@st.cache_resource
def get_gateway(server_url: str) -> McpGateway:
    return McpGateway(server_url)


@st.cache_resource
def get_provider(provider_name: str, api_key: str | None, model: str, base_url: str, timeout: float):
    settings = Settings.from_env()
    # Use live environment config only after Settings has validated it.
    return create_provider(settings)


settings = get_settings()
gateway = get_gateway(settings.mcp_server_url)
provider = get_provider(settings.llm_provider, settings.llm_api_key, settings.llm_model, settings.llm_base_url, settings.llm_timeout_seconds)
clock = Clock(settings.timezone, settings.fake_today)

st.markdown("""
<style>
:root { --gd-ink: #172238; --gd-blue: #4f62d9; --gd-lilac: #eef0ff; --gd-line: #e4e8f1; }
.block-container { padding-top: 1.65rem; max-width: 1400px; }
[data-testid="stMetric"] { background: linear-gradient(145deg,#fff,#f7f8ff); border: 1px solid var(--gd-line); padding: 1rem 1.1rem; border-radius: 16px; }
.gd-subtitle { color: #65708a; margin-top: -10px; }
.gd-muted { color: #6e7890; font-size: .9rem; }
.gd-card { border: 1px solid var(--gd-line); border-radius: 14px; padding: 14px 16px; margin-bottom: 8px; }
.gd-evidence { border-left: 3px solid #8792ef; padding: 8px 12px; background: #f7f8ff; border-radius: 0 8px 8px 0; }
</style>
""", unsafe_allow_html=True)

st.title("GraceDays")
st.markdown('<p class="gd-subtitle">Keep the dates that start after checkout from slipping through the cracks.</p>', unsafe_allow_html=True)


def call_tool(name: str, args: dict[str, Any] | None = None) -> Any:
    return gateway.call_tool(name, args or {})


def show_error(prefix: str, exc: Exception) -> None:
    st.error(f"{prefix}: {exc}")


def get_purchases() -> list[dict[str, Any]]:
    result = call_tool("list_purchases", {"query": "", "limit": 100})
    return result.get("purchases", []) if isinstance(result, dict) else []


def show_deadline_card(row: dict[str, Any]) -> None:
    state = row.get("derived_state", "open")
    title = row.get("title", "Purchase")
    due = row.get("due_date", "Unknown")
    remain = row.get("days_remaining")
    remain_label = "date unavailable" if remain is None else "due today" if remain == 0 else f"{abs(remain)} days {'overdue' if remain < 0 else 'left'}"
    st.markdown(
        f"<div class='gd-card'><strong>{title}</strong> &nbsp; · &nbsp; {row.get('deadline_type','deadline').replace('_',' ').title()}<br>"
        f"<strong>{due}</strong> &nbsp; · &nbsp; <span>{remain_label}</span> &nbsp; · &nbsp; <strong>{state.replace('_',' ').title()}</strong><br>"
        f"<span class='gd-muted'>{row.get('merchant') or 'Merchant not recorded'}</span></div>",
        unsafe_allow_html=True,
    )
    if row.get("evidence_excerpt"):
        with st.expander("View source evidence"):
            st.code(row["evidence_excerpt"], language=None)


with st.sidebar:
    st.subheader("Connection status")
    if st.button("Check MCP + Turso", use_container_width=True):
        try:
            status = gateway.health_check()
            st.session_state["last_health"] = status
        except Exception as exc:
            st.session_state["last_health"] = {"status": "error", "detail": str(exc)}
    health = st.session_state.get("last_health")
    if health is None:
        try:
            health = gateway.health_check()
            st.session_state["last_health"] = health
        except Exception as exc:
            health = {"status": "unavailable", "detail": str(exc)}
            st.session_state["last_health"] = health
    if health.get("status") == "healthy":
        st.success("MCP server reachable")
    else:
        st.warning("MCP server unavailable")
    database_health = health.get("database", {}) if isinstance(health, dict) else {}
    database_status = database_health.get("status", "not checked")
    st.caption(f"Turso database: {database_status}")
    if database_status != "healthy":
        detail = database_health.get("detail")
        if detail:
            st.caption(str(detail)[:240])
    if settings.llm_provider == "mock":
        st.info("Offline demo mode: scripted extraction and assistant responses; no LLM API key required.")
    else:
        st.caption(f"Live extraction/assistant provider: {settings.llm_provider}")
    st.divider()
    st.subheader("Demo data")
    st.caption("These controls only seed or remove records marked as demo data.")
    if st.button("Seed / refresh demo data", use_container_width=True):
        try:
            result = call_tool("seed_demo_data", {})
            st.success(f"Seeded {result.get('seeded', result.get('count', 'fresh'))} synthetic records.")
            st.session_state.pop("dashboard_data", None)
        except Exception as exc:
            show_error("Demo seed failed", exc)
    reset_phrase = st.text_input("Type RESET DEMO DATA to reset", key="reset_phrase")
    if st.button("Reset demo records", use_container_width=True, type="secondary"):
        if reset_phrase != "RESET DEMO DATA":
            st.warning("Type the full confirmation phrase first.")
        else:
            try:
                result = call_tool("reset_demo_data", {"confirm_phrase": reset_phrase})
                st.success(f"Deleted {result.get('deleted_demo_records', 0)} demo record(s). Non-demo records were preserved.")
                st.session_state.pop("dashboard_data", None)
            except Exception as exc:
                show_error("Demo reset failed", exc)


tab_dashboard, tab_capture, tab_assistant, tab_purchases = st.tabs(["Dashboard", "Capture & review", "Assistant", "Purchases"])

with tab_dashboard:
    st.subheader("Your deadlines at a glance")
    try:
        purchases = get_purchases()
        deadline_result = call_tool("list_deadlines", {"within_days": 7, "include_closed": False})
        deadlines = deadline_result.get("deadlines", []) if isinstance(deadline_result, dict) else []
        overdue = [row for row in deadlines if row.get("derived_state") == "overdue"]
        due_soon = [row for row in deadlines if row.get("derived_state") in {"due_today", "upcoming"}]
        active = [row for row in purchases if row.get("status") == "active"]
        col1, col2, col3 = st.columns(3)
        col1.metric("Overdue", len(overdue))
        col2.metric("Due today or soon", len(due_soon))
        col3.metric("Active purchases", len(active))
        left, right = st.columns([1.2, 1])
        with left:
            st.markdown("#### Needs attention")
            if deadlines:
                for row in deadlines:
                    show_deadline_card(row)
            else:
                st.info("No saved deadlines need attention. Unknown dates remain separate from confirmed deadlines.")
        with right:
            st.markdown("#### Recently added")
            if purchases:
                for item in purchases[:6]:
                    st.markdown(f"**{item.get('title','Untitled')}**  \n{item.get('merchant') or 'Merchant not recorded'} · {item.get('status','active').title()}")
                    st.divider()
            else:
                st.info("No purchases saved yet. Paste an order confirmation in Capture & review.")
    except Exception as exc:
        show_error("Dashboard could not load persisted data. Check the MCP server and Turso database connection", exc)

with tab_capture:
    st.subheader("Capture a purchase")
    st.caption("Paste only the order or policy text you want GraceDays to analyze. Card-like numbers are masked before a provider is called.")
    st.warning("Privacy: pasted text is sent to the configured extraction provider. GraceDays does not connect to your inbox or retailer accounts.")
    sample_options = {
        "Choose a sample…": "",
        "Return window": "Order confirmation for Aurora Wireless Headphones.\nMerchant: Northstar Market.\nOrder date: October 10, 2026. Order number: DEMO-AU2345.\nYour Aurora Wireless Headphones were delivered on October 12, 2026.\nItems may be returned within 30 days of delivery.",
        "Trial cancellation": "Product: CloudNotes Monthly Plan.\nMerchant: Paperplane Digital.\nOrder date: October 2, 2026.\nTrial started on October 2, 2026.\nCancel the trial within 7 days of trial start. The subscription renews on November 2, 2026 for $8.00/month.",
        "No deadline in source": "Order confirmation for a ceramic mug.\nMerchant: Small Planet Goods.\nOrder date: October 20, 2026.\nThank you for your purchase. Keep this email for your records.",
    }
    chosen_sample = st.selectbox("Load synthetic example", list(sample_options.keys()), key="sample_choice")
    capture_text = st.text_area("Order email or policy text", value=sample_options[chosen_sample], height=200, max_chars=settings.max_source_text_chars + 1, key="capture_source")
    if st.button("Extract fields for review", type="primary", use_container_width=False):
        try:
            with st.spinner("Extracting candidate facts and checking source evidence…"):
                service = ExtractionService(provider, settings)
                proposed, diagnostics = service.extract(capture_text)
                try:
                    existing = get_purchases()
                    proposed.duplicate_candidates = find_duplicates(proposed.model_dump(mode="json"), existing)
                except Exception as exc:
                    diagnostics["duplicate_check_warning"] = str(exc)
                st.session_state["review_purchase"] = proposed.model_dump(mode="json")
                st.session_state["review_diagnostics"] = diagnostics
                st.session_state["review_form_nonce"] = st.session_state.get("review_form_nonce", 0) + 1
        except ExtractionError as exc:
            st.error(str(exc))
        except Exception as exc:
            show_error("Extraction failed", exc)

    raw_review = st.session_state.get("review_purchase")
    if raw_review:
        try:
            review = ReviewPurchase.model_validate(raw_review)
            diagnostics = st.session_state.get("review_diagnostics", {})
            st.divider()
            st.markdown("### Review before saving")
            if diagnostics.get("offline_mode"):
                st.info("Offline demo mode — candidate fields are generated with deterministic heuristics, not live AI.")
            if diagnostics.get("redacted_card_count"):
                st.success(f"Masked {diagnostics['redacted_card_count']} card-like number(s) before provider processing.")
            if review.duplicate_candidates:
                st.warning("Possible duplicate detected. Check the existing record before saving.")
                st.dataframe(pd.DataFrame(review.duplicate_candidates), use_container_width=True, hide_index=True)
            if review.unknown_fields:
                st.warning("Fields requiring attention: " + ", ".join(review.unknown_fields))

            with st.form("review_purchase_form"):
                col1, col2 = st.columns(2)
                with col1:
                    title = st.text_input("Product / plan name", value=review.title, max_chars=160)
                    merchant = st.text_input("Merchant", value=review.merchant or "", max_chars=120)
                    purchase_type = st.selectbox("Purchase type", ["physical_product", "subscription", "digital_purchase", "other"], index=["physical_product", "subscription", "digital_purchase", "other"].index(review.purchase_type.value))
                    order_reference = st.text_input("Order reference", value=review.order_reference or "", max_chars=80)
                with col2:
                    order_date_text = st.text_input("Order date (YYYY-MM-DD; leave blank if unknown)", value=review.order_date or "")
                    delivery_date_text = st.text_input("Delivery date (YYYY-MM-DD; leave blank if unknown)", value=review.delivery_date or "")
                    trial_date_text = st.text_input("Trial start date (YYYY-MM-DD; leave blank if unknown)", value=review.trial_start_date or "")
                    price_text = st.text_input("Price / renewal price as written", value=review.price_text or "", max_chars=60)
                policy_summary = st.text_input("Policy summary", value=review.policy_summary or "", max_chars=400)
                st.markdown("#### Proposed deadlines")
                deadline_rows = []
                original_deadline_dates = {item.id: item.due_date for item in review.deadlines}
                for item in review.deadlines:
                    deadline_rows.append({
                        "deadline_id": item.id,
                        "deadline_type": item.deadline_type.value,
                        "due_date": item.due_date or "",
                        "rule_text": item.rule_text[:300],
                        "evidence_excerpt": item.evidence_excerpt[:500],
                        "verification": item.verification.value if item.verification else "unverified",
                        "needs_review": item.needs_review,
                        "review_reason": item.review_reason or "",
                        "derivation_note": item.derivation_note or "",
                    })
                if deadline_rows:
                    editable_deadlines = st.data_editor(
                        pd.DataFrame(deadline_rows),
                        key=f"deadline_editor_{st.session_state.get('review_form_nonce', 0)}",
                        num_rows="dynamic",
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "deadline_id": st.column_config.TextColumn("Internal ID", disabled=True),
                            "deadline_type": st.column_config.SelectboxColumn("Deadline type", options=["return_by", "trial_cancel_by", "renewal_on", "warranty_expires", "other"], required=True),
                            "due_date": st.column_config.TextColumn("Due date YYYY-MM-DD", help="A missing or ambiguous date must be corrected here or the deadline row removed."),
                            "rule_text": st.column_config.TextColumn("Policy rule", width="large"),
                            "evidence_excerpt": st.column_config.TextColumn("Source evidence", width="large"),
                            "verification": st.column_config.SelectboxColumn("Verification", options=["explicit", "derived", "user_entered", "unverified"], required=True),
                            "needs_review": st.column_config.CheckboxColumn("Needs review"),
                            "review_reason": st.column_config.TextColumn("Review reason", width="large"),
                            "derivation_note": st.column_config.TextColumn("Calculation note", width="large"),
                        },
                    )
                    edited_deadline_rows = editable_deadlines.to_dict(orient="records")
                else:
                    st.info("No dated deadlines were extracted. You can still save the purchase with unknown fields preserved.")
                    edited_deadline_rows = []
                st.markdown("#### Extracted field evidence")
                evidence_rows = [{
                    "evidence_id": item.id,
                    "field_name": item.field_name,
                    "source_excerpt": item.source_excerpt,
                    "verification_status": item.verification_status.value,
                } for item in review.evidence]
                evidence_df = st.data_editor(
                    pd.DataFrame(evidence_rows, columns=["evidence_id", "field_name", "source_excerpt", "verification_status"]),
                    key=f"evidence_editor_{st.session_state.get('review_form_nonce', 0)}",
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "evidence_id": st.column_config.TextColumn("Internal ID", disabled=True),
                        "field_name": st.column_config.TextColumn("Field name", required=True),
                        "source_excerpt": st.column_config.TextColumn("Exact excerpt or manual-entry note", width="large", required=True),
                        "verification_status": st.column_config.SelectboxColumn("Evidence type", options=["explicit", "derived", "user_entered", "unverified"], required=True),
                    },
                )
                edited_evidence_rows = evidence_df.to_dict(orient="records")
                unknown_options = sorted(set(review.unknown_fields))
                unknown_fields_selection = st.multiselect(
                    "Unknown fields — resolve them or remove fields you do not want to track before saving",
                    options=unknown_options,
                    default=unknown_options,
                    key=f"unknown_fields_{st.session_state.get('review_form_nonce', 0)}",
                )
                st.checkbox("I reviewed these fields and authorize saving this record to my GraceDays database.", key="confirm_purchase_save")
                save_col, cancel_col = st.columns([1, 1])
                with save_col:
                    confirm_save = st.form_submit_button("Confirm and save", type="primary", use_container_width=True)
                with cancel_col:
                    cancel_review = st.form_submit_button("Discard review", use_container_width=True)

            if cancel_review:
                st.session_state.pop("review_purchase", None)
                st.session_state.pop("review_diagnostics", None)
                st.session_state["confirm_purchase_save"] = False
                st.rerun()
            if confirm_save:
                if not st.session_state.get("confirm_purchase_save", False):
                    st.error("Check the confirmation box before saving.")
                elif not title.strip():
                    st.error("Enter a product or plan name before saving.")
                else:
                    try:
                        edited = review.model_copy(deep=True)
                        original_values = {
                            "title": review.title,
                            "merchant": review.merchant,
                            "price_text": review.price_text,
                            "policy_summary": review.policy_summary,
                            "policy_excerpt": review.policy_excerpt,
                            "order_date": review.order_date,
                            "delivery_date": review.delivery_date,
                            "trial_start_date": review.trial_start_date,
                        }
                        edited.title = title.strip()
                        edited.merchant = merchant.strip() or None
                        edited.purchase_type = purchase_type
                        edited.order_reference = order_reference.strip() or None
                        for field_name, raw in (("order_date", order_date_text), ("delivery_date", delivery_date_text), ("trial_start_date", trial_date_text)):
                            value = raw.strip()
                            if value:
                                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                                    raise ValueError(f"{field_name} must use YYYY-MM-DD")
                                date.fromisoformat(value)
                                setattr(edited, field_name, value)
                            else:
                                setattr(edited, field_name, None)
                        edited.price_text = price_text.strip() or None
                        edited.policy_summary = policy_summary.strip() or None
                        updated_deadlines = []
                        errors = []
                        for row in edited_deadline_rows:
                            try:
                                row_type = str(row.get("deadline_type", "other"))
                                due_raw = str(row.get("due_date", "") or "").strip()
                                if not due_raw:
                                    errors.append(f"{row_type}: set a due date or remove this deadline row")
                                    continue
                                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_raw):
                                    errors.append(f"{row_type}: due date must use YYYY-MM-DD")
                                    continue
                                date.fromisoformat(due_raw)
                                excerpt = str(row.get("evidence_excerpt", "") or "").strip()
                                verification = str(row.get("verification", "unverified"))
                                old_id = str(row.get("deadline_id", "") or "")
                                changed_date = old_id not in original_deadline_dates or original_deadline_dates.get(old_id) != due_raw
                                manually_entered = bool(row.get("needs_review", False)) or verification == "unverified" or changed_date
                                row_id = old_id if old_id and old_id not in {"nan", "None"} else str(uuid4())
                                if manually_entered:
                                    verification = "user_entered"
                                    excerpt = f"Entered manually by you on {clock.today().isoformat()}"
                                elif excerpt not in edited.source_text:
                                    errors.append(f"{row_type}: evidence must be a literal substring of the captured source")
                                    continue
                                updated_deadlines.append({
                                    "id": row_id,
                                    "deadline_type": row_type,
                                    "due_date": due_raw,
                                    "rule_text": str(row.get("rule_text", "Manual user-entered date") or "Manual user-entered date")[:300],
                                    "evidence_excerpt": excerpt,
                                    "verification": verification,
                                    "needs_review": False,
                                    "review_reason": None,
                                    "derivation_note": str(row.get("derivation_note", "") or "")[:300] or (f"Date entered manually by the user on {clock.today().isoformat()}." if verification == "user_entered" else None),
                                })
                            except (ValueError, TypeError) as exc:
                                errors.append(str(exc))

                        # Rebuild field evidence after edits. Any changed field receives a clearly
                        # labelled user-entered provenance note rather than a misleading old quote.
                        current_values = {
                            "title": edited.title,
                            "merchant": edited.merchant,
                            "price_text": edited.price_text,
                            "policy_summary": edited.policy_summary,
                            "policy_excerpt": edited.policy_excerpt,
                            "order_date": edited.order_date,
                            "delivery_date": edited.delivery_date,
                            "trial_start_date": edited.trial_start_date,
                        }
                        evidence_rows_to_save = []
                        changed_fields = {name for name, value in current_values.items() if value != original_values.get(name)}
                        original_evidence_by_id = {item.id: item for item in review.evidence}
                        validated_evidence_fields = set()
                        for row in edited_evidence_rows:
                            field_name = str(row.get("field_name", "") or "").strip()
                            excerpt = str(row.get("source_excerpt", "") or "").strip()
                            if not field_name or not excerpt:
                                errors.append("Evidence rows need both a field name and an excerpt.")
                                continue
                            if field_name in changed_fields:
                                continue
                            evidence_type = str(row.get("verification_status", "unverified"))
                            row_id = str(row.get("evidence_id", "") or "")
                            if row_id in {"", "nan", "None"}:
                                row_id = str(uuid4())
                            if evidence_type == "user_entered":
                                if not re.fullmatch(r"Entered manually by you on \d{4}-\d{2}-\d{2}", excerpt):
                                    errors.append(f"{field_name}: user-entered evidence must use the manual-entry note format.")
                                    continue
                            elif evidence_type == "unverified":
                                errors.append(f"{field_name}: unverified evidence cannot be promoted to verified without manual entry.")
                                continue
                            elif excerpt in edited.source_text:
                                if field_name in {"title", "merchant", "price_text", "policy_summary", "policy_excerpt"}:
                                    field_value = current_values.get(field_name)
                                    if field_value and str(field_value).casefold() not in excerpt.casefold():
                                        errors.append(f"{field_name}: the excerpt does not contain the value it is supposed to support.")
                                        continue
                                elif field_name in {"order_date", "delivery_date", "trial_start_date"}:
                                    original_item = original_evidence_by_id.get(row_id)
                                    if field_name in changed_fields or not original_item or original_item.verification_status == VerificationStatus.UNVERIFIED or original_item.source_excerpt != excerpt:
                                        errors.append(f"{field_name}: keep verified original evidence or enter the date manually.")
                                        continue
                                evidence_type = "explicit"
                            else:
                                errors.append(f"{field_name}: evidence must be an exact excerpt in the captured source or a valid manual-entry note.")
                                continue
                            validated_evidence_fields.add(field_name)
                            evidence_rows_to_save.append({
                                "id": row_id,
                                "deadline_id": None,
                                "field_name": field_name,
                                "source_excerpt": excerpt,
                                "verification_status": evidence_type,
                                "source_hash": edited.source_hash,
                            })
                        for field_name in changed_fields:
                            if current_values.get(field_name) is not None and current_values.get(field_name) != "":
                                evidence_rows_to_save.append({
                                    "id": str(uuid4()),
                                    "deadline_id": None,
                                    "field_name": field_name,
                                    "source_excerpt": f"Entered manually by you on {clock.today().isoformat()}",
                                    "verification_status": "user_entered",
                                    "source_hash": edited.source_hash,
                                })
                        for field_name, field_value in current_values.items():
                            if field_value is not None and field_value != "" and not any(item["field_name"] == field_name for item in evidence_rows_to_save):
                                errors.append(f"{field_name}: provide verified source evidence or a manual-entry note before saving.")
                        for row in updated_deadlines:
                            evidence_rows_to_save.append({
                                "id": str(uuid4()),
                                "deadline_id": row["id"],
                                "field_name": f"deadline:{row['deadline_type']}",
                                "source_excerpt": row["evidence_excerpt"],
                                "verification_status": row["verification"],
                                "source_hash": edited.source_hash,
                            })

                        for key, value in current_values.items():
                            if value is not None and value != "" and (key in changed_fields or key in validated_evidence_fields):
                                unknown_fields_selection = [field for field in unknown_fields_selection if field != key]
                        unknown = set(unknown_fields_selection)
                        for item in updated_deadlines:
                            unknown.discard(item["deadline_type"])
                        edited.unknown_fields = sorted(unknown)
                        if edited.unknown_fields:
                            errors.append("Resolve or remove unknown fields before saving: " + ", ".join(edited.unknown_fields))
                        if edited.title == "Unknown purchase":
                            errors.append("Enter the actual product or plan name before saving.")
                        if any(item["verification_status"] == "unverified" for item in evidence_rows_to_save):
                            errors.append("Unverified evidence cannot be saved.")
                        if errors:
                            st.error("Resolve these review items before saving: " + "; ".join(errors))
                        else:
                            edited.evidence = [EvidenceReview.model_validate({
                                "id": row["id"],
                                "deadline_id": row["deadline_id"],
                                "field_name": row["field_name"],
                                "source_excerpt": row["source_excerpt"],
                                "verification_status": row["verification_status"],
                                "source_hash": row["source_hash"],
                            }) for row in evidence_rows_to_save]
                            payload = edited.model_dump(mode="json")
                            payload["deadlines"] = [{k: v for k, v in row.items() if k in {"id", "deadline_type", "due_date", "rule_text", "status", "evidence_excerpt", "verification", "derivation_note"}} for row in updated_deadlines]
                            payload["evidence"] = evidence_rows_to_save
                            # MCP UI-only write; chat orchestrator never receives save_purchase.
                            saved = call_tool("save_purchase", {"purchase_json": json.dumps(payload), "confirmed": True})
                            st.success(f"Saved {edited.title}. This record will be retrieved from Turso on refresh.")
                            st.session_state.pop("review_purchase", None)
                            st.session_state.pop("review_diagnostics", None)
                            st.session_state["confirm_purchase_save"] = False
                            st.session_state.pop("dashboard_data", None)
                    except (ValueError, ValidationError, MCPGatewayError) as exc:
                        show_error("The record was not saved", exc)
        except ValidationError as exc:
            st.error(f"The review state is invalid; please extract again. {exc}")

with tab_assistant:
    st.subheader("Ask GraceDays")
    if "assistant_messages" not in st.session_state:
        st.session_state["assistant_messages"] = []
    if "briefing_loaded" not in st.session_state:
        try:
            brief = call_tool("list_deadlines", {"within_days": 7, "include_closed": False})
            st.session_state["briefing"] = brief
        except Exception as exc:
            st.session_state["briefing"] = {"error": str(exc)}
        st.session_state["briefing_loaded"] = True
    briefing = st.session_state.get("briefing", {})
    if "error" in briefing:
        st.warning(f"The proactive briefing is unavailable: {briefing['error']}")
    else:
        rows = briefing.get("deadlines", [])
        if rows:
            st.info(f"Briefing: {len(rows)} saved deadline(s) need attention. Overdue items are listed first.")
            with st.expander("View briefing items"):
                for row in rows[:6]:
                    st.write(f"{row.get('title')} — {row.get('deadline_type')} — {row.get('due_date')} ({row.get('derived_state')})")
        else:
            st.info("Briefing: no saved deadline needs attention in the next seven days.")
    for message in st.session_state["assistant_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("tool_activity"):
                with st.expander("Tools used"):
                    st.json(message["tool_activity"])
    question = st.chat_input("Ask about a saved purchase or request a message draft…")
    if question:
        st.session_state["assistant_messages"].append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            try:
                orchestrator = AgentOrchestrator(gateway, provider, clock)
                prior = [{"role": m["role"], "content": m["content"]} for m in st.session_state["assistant_messages"][:-1]]
                result = orchestrator.ask(question, prior)
                st.markdown(result["answer"])
                if result.get("offline_mode"):
                    st.caption("Offline demo mode — scripted tool routing, not live AI.")
                if result.get("tool_activity"):
                    with st.expander("Tools used", expanded=True):
                        st.json(result["tool_activity"])
                st.session_state["assistant_messages"].append({
                    "role": "assistant", "content": result["answer"], "tool_activity": result.get("tool_activity", []),
                })
            except Exception as exc:
                st.error(f"I couldn't answer from saved records: {exc}")
                st.session_state["assistant_messages"].append({"role": "assistant", "content": f"I couldn't answer from saved records: {exc}"})

with tab_purchases:
    st.subheader("Saved purchases")
    try:
        purchases = get_purchases()
        if not purchases:
            st.info("No purchases have been saved. Use Capture & review or seed synthetic demo data.")
        else:
            options = {f"{item.get('title','Untitled')} — {str(item.get('id',''))[:8]}": item.get("id") for item in purchases}
            chosen_label = st.selectbox("Choose a purchase", list(options.keys()))
            purchase_id = options[chosen_label]
            details = call_tool("get_purchase_details", {"purchase_id": purchase_id})
            purchase = details.get("purchase", {})
            detail_col, status_col = st.columns([1.3, 1])
            with detail_col:
                st.markdown(f"### {purchase.get('title', 'Purchase')}")
                st.write(f"Merchant: {purchase.get('merchant') or 'Not recorded'}")
                st.write(f"Status: {purchase.get('status', 'active').title()}")
                st.write(f"Order reference: {purchase.get('order_reference') or 'Not recorded'}")
                st.write(f"Order date: {purchase.get('order_date') or 'Unknown'} · Delivery date: {purchase.get('delivery_date') or 'Unknown'}")
                unknown_fields = purchase.get("unknown_fields", [])
                if unknown_fields:
                    st.warning("Unknown fields: " + ", ".join(unknown_fields))
                if purchase.get("policy_excerpt"):
                    st.markdown("**Policy excerpt**")
                    st.code(purchase["policy_excerpt"], language=None)
            with status_col:
                new_status = st.selectbox("Update purchase status", ["active", "returned", "cancelled", "resolved"], index=["active", "returned", "cancelled", "resolved"].index(purchase.get("status", "active")))
                if st.button("Save status", type="primary"):
                    result = call_tool("update_purchase_status", {"purchase_id": purchase_id, "status": new_status})
                    st.success(f"Purchase status updated to {result.get('status', new_status)}. No external return/cancellation was performed.")
                with st.expander("Delete purchase", expanded=False):
                    st.warning("Deletion is permanent and only removes the selected purchase and its attached records.")
                    delete_confirmation = st.text_input("Type DELETE", key=f"delete_confirm_{purchase_id}")
                    if st.button("Delete this purchase", key=f"delete_button_{purchase_id}"):
                        if delete_confirmation != "DELETE":
                            st.error("Type DELETE to confirm.")
                        else:
                            call_tool("delete_purchase", {"purchase_id": purchase_id, "confirm_phrase": delete_confirmation})
                            st.success("Purchase deleted.")
                            st.rerun()
            st.markdown("#### Deadlines")
            for deadline in details.get("deadlines", []):
                row = dict(deadline)
                row["title"] = purchase.get("title")
                row["purchase_status"] = purchase.get("status", "active")
                row["derived_state"] = row.get("derived_state", "open")
                if row.get("due_date"):
                    row["days_remaining"] = (date.fromisoformat(row["due_date"]) - clock.today()).days
                show_deadline_card(row)
            st.markdown("#### Evidence records")
            for evidence in details.get("evidence", []):
                st.markdown(f"**{evidence.get('field_name')}** — {evidence.get('verification_status')}")
                st.code(evidence.get("source_excerpt", ""), language=None)
    except Exception as exc:
        show_error("Could not load purchase details", exc)
