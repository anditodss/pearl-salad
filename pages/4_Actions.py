"""
pages/4_Actions.py
===================
Remediation action log — all REALLOCATE / RECREATE / RESTART events.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Actions — Salad Fleet Manager",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ Remediation Actions")
st.caption("Automated actions taken when instances fall below the efficiency threshold.")

try:
    from utils.query_service import get_recent_actions
except Exception as exc:
    st.error(f"Initialisation error: {exc}")
    st.stop()

# ── Controls ───────────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    filter_type = st.selectbox(
        "Filter by action type",
        options=["ALL", "REALLOCATE", "RECREATE", "RESTART"],
        key="action_filter",
    )
with col2:
    st.write("")
    st.write("")
    if st.button("🔄 Refresh", key="actions_refresh"):
        st.rerun()

# ── Data ───────────────────────────────────────────────────────────────────
try:
    actions = get_recent_actions(limit=200)
except Exception as exc:
    st.warning(f"No actions yet: {exc}", icon="⏳")
    st.stop()

if filter_type != "ALL":
    actions = [a for a in actions if a.action_type == filter_type]

if not actions:
    st.info("No remediation actions recorded yet.", icon="📭")
else:
    st.caption(f"Showing {len(actions)} action(s)")
    rows = []
    for a in actions:
        rows.append({
            "Timestamp (UTC)": a.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "Result": "✅ Success" if a.success else "❌ Failed",
            "Action": a.action_type,
            "Account": a.account_name,
            "Organization": a.org_name,
            "Group": a.group_name,
            "Instance ID": a.instance_id,
            "Machine ID": a.machine_id or "—",
            "Reason": a.reason or "—",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=600)

    # ── Summary counters ───────────────────────────────────────────────────
    st.divider()
    total = len(actions)
    succeeded = sum(1 for a in actions if a.success)
    failed = total - succeeded

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Total Actions", total)
    mc2.metric("✅ Succeeded", succeeded)
    mc3.metric("❌ Failed", failed)
