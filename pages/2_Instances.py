"""
pages/2_Instances.py
=====================
Full instance table with performance metrics and status badges.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh
from utils.ui_components import inject_custom_css, render_sync_button

st.set_page_config(
    page_title="Instances — Salad Fleet Manager",
    page_icon="🖥️",
    layout="wide",
)

inject_custom_css()
st_autorefresh(interval=30000, key="instances_autorefresh")

col_title, col_btn = st.columns([3, 1])
with col_title:
    st.title("🖥️ Instances")
with col_btn:
    st.write("")
    render_sync_button()

try:
    from utils.query_service import get_all_instances, get_bad_instances
    from utils.helpers import format_hashrate, format_efficiency
    from utils.config import get_config
except Exception as exc:
    st.error(f"Initialisation error: {exc}")
    st.stop()

# ── Controls ───────────────────────────────────────────────────────────────
col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([2, 2, 1])
with col_ctrl1:
    filter_status = st.selectbox(
        "Filter by status",
        options=["ALL", "GOOD", "WARNING", "BAD", "UNKNOWN"],
        key="inst_filter_status",
    )
with col_ctrl2:
    filter_gpu = st.text_input("Filter by GPU type", placeholder="e.g. rtx-3090", key="inst_filter_gpu")
with col_ctrl3:
    st.write("")

# ── Data ───────────────────────────────────────────────────────────────────
try:
    cfg = get_config()
    unit = cfg.hashrate.unit
    all_instances = get_all_instances()
except Exception as exc:
    st.warning(f"No data yet: {exc}", icon="⏳")
    st.stop()

# Apply filters
filtered = all_instances
if filter_status != "ALL":
    filtered = [i for i in filtered if i.status == filter_status]
if filter_gpu:
    filtered = [i for i in filtered if i.gpu_type and filter_gpu.lower() in i.gpu_type.lower()]

st.caption(f"Showing {len(filtered)} of {len(all_instances)} instances")

# ── Status badge helper ────────────────────────────────────────────────────
STATUS_EMOJI = {
    "GOOD": "✅ GOOD",
    "WARNING": "⚠️ WARNING",
    "BAD": "🔴 BAD",
    "UNKNOWN": "❓ UNKNOWN",
}

if not filtered:
    st.info("No instances match the current filters.", icon="🔍")
else:
    rows = []
    for i in filtered:
        eff_str = format_efficiency(i.efficiency)
        hr_str = f"{i.latest_hashrate:.2f}" if i.latest_hashrate else "N/A"
        median_str = f"{i.gpu_median_hashrate:.2f}" if i.gpu_median_hashrate else "N/A"

        rows.append({
            "Status": STATUS_EMOJI.get(i.status, i.status),
            "Account": i.account_name,
            "Organization": i.org_name,
            "Group": i.group_name,
            "Machine ID": i.machine_id or "—",
            "Instance ID": i.instance_id,
            "GPU Type": i.gpu_type or "—",
            "State": i.state or "—",
            f"Hashrate ({unit})": hr_str,
            f"Median ({unit})": median_str,
            "Efficiency": eff_str,
            "Bad Checks": i.consecutive_bad_checks,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=600)

    # ── Manual Action Panel ────────────────────────────────────────────────────
    bad_instances = [i for i in filtered if i.status == "BAD"]
    if bad_instances:
        st.markdown("---")
        st.subheader("🛠️ Manual Remediation")
        st.caption("Manually trigger a reallocation for bad instances.")
        
        bad_options = { f"{i.instance_id[:8]}... (Group: {i.group_name}) - Hashrate: {i.latest_hashrate}": i for i in bad_instances }
        
        col_act1, col_act2 = st.columns([3, 1])
        with col_act1:
            selected_bad = st.selectbox("Select instance to reallocate", options=list(bad_options.keys()))
        with col_act2:
            st.write("") # Padding to align with selectbox
            st.write("")
            if st.button("🚀 Reallocate Now", type="primary", use_container_width=True):
                inst = bad_options[selected_bad]
                
                from api.salad_client import SaladClient
                if "/" in inst.org_name:
                    actual_org, actual_proj = inst.org_name.split("/", 1)
                else:
                    actual_org = inst.org_name
                    actual_proj = ""
                    
                try:
                    api_key = next((a.api_key for a in cfg.accounts if a.name == inst.account_name), None)
                    if not api_key:
                        st.error(f"API Key not found for account: {inst.account_name}")
                    else:
                        client = SaladClient(api_key=api_key, account_name=inst.account_name)
                        with st.spinner("Sending reallocation request..."):
                            client.reallocate_instance(actual_org, actual_proj, inst.group_name, inst.instance_id)
                        st.success(f"Successfully reallocated `{inst.instance_id}`!")
                except Exception as e:
                    st.error(f"Reallocation failed: {e}")
