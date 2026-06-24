"""
pages/3_GPU_Summary.py
=======================
Per-GPU-type performance breakdown.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="GPU Summary — Salad Fleet Manager",
    page_icon="🎮",
    layout="wide",
)

st.title("🎮 GPU Summary")

try:
    from utils.query_service import get_gpu_summary, get_all_instances
    from utils.config import get_config
except Exception as exc:
    st.error(f"Initialisation error: {exc}")
    st.stop()

if st.button("🔄 Refresh", key="gpu_refresh"):
    st.rerun()

try:
    cfg = get_config()
    unit = cfg.hashrate.unit
    gpu_data = get_gpu_summary()
    all_instances = get_all_instances()
except Exception as exc:
    st.warning(f"No data yet: {exc}", icon="⏳")
    st.stop()

if not gpu_data:
    st.info("No GPU data available yet.", icon="⏳")
    st.stop()

# ── Summary table ──────────────────────────────────────────────────────────
st.subheader("Aggregated Stats per GPU Type")

rows = []
for g in gpu_data:
    health_pct = ((g.instance_count - g.bad_count) / g.instance_count * 100) if g.instance_count else 0
    rows.append({
        "GPU Type": g.gpu_type,
        "Total Instances": g.instance_count,
        "Bad Instances": g.bad_count,
        "Health %": f"{health_pct:.1f}%",
        f"Median {unit}": f"{g.median_hashrate:.2f}" if g.median_hashrate else "N/A",
        f"Avg {unit}": f"{g.avg_hashrate:.2f}" if g.avg_hashrate else "N/A",
        f"Min {unit}": f"{g.min_hashrate:.2f}" if g.min_hashrate else "N/A",
        f"Max {unit}": f"{g.max_hashrate:.2f}" if g.max_hashrate else "N/A",
    })

df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True, hide_index=True)

st.divider()

# ── Per-GPU instance drilldown ─────────────────────────────────────────────
st.subheader("Drilldown by GPU Type")

selected_gpu = st.selectbox(
    "Select GPU Type",
    options=[g.gpu_type for g in gpu_data],
    key="gpu_drilldown",
)

if selected_gpu:
    gpu_instances = [i for i in all_instances if i.gpu_type == selected_gpu]
    if gpu_instances:
        drilldown_rows = []
        for i in gpu_instances:
            drilldown_rows.append({
                "Instance ID": i.instance_id,
                "Machine ID": i.machine_id or "—",
                "Account": i.account_name,
                "Group": i.group_name,
                "State": i.state or "—",
                f"Hashrate ({unit})": f"{i.latest_hashrate:.2f}" if i.latest_hashrate else "N/A",
                "Efficiency": f"{i.efficiency*100:.1f}%" if i.efficiency else "N/A",
                "Status": i.status,
            })
        st.dataframe(pd.DataFrame(drilldown_rows), use_container_width=True, hide_index=True)
