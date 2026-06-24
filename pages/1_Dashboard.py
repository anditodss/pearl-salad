"""
pages/1_Dashboard.py
=====================
Overview dashboard — summary metrics and status breakdown.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

from utils.ui_components import inject_custom_css, render_sync_button

st.set_page_config(
    page_title="Dashboard — Salad Fleet Manager",
    page_icon="📊",
    layout="wide",
)

# Inject custom CSS
inject_custom_css()

# Auto-refresh every 30 seconds
st_autorefresh(interval=30000, key="dashboard_autorefresh")

col_title, col_btn = st.columns([3, 1])
with col_title:
    st.title("📊 Dashboard")
with col_btn:
    st.write("") # spacer
    render_sync_button()

try:
    from utils.query_service import get_dashboard_stats, get_gpu_summary
    from utils.helpers import format_hashrate
    from utils.config import get_config
except Exception as exc:
    st.error(f"Initialisation error: {exc}")
    st.stop()

# ── Summary metrics ────────────────────────────────────────────────────────
try:
    stats = get_dashboard_stats()
except Exception as exc:
    st.warning(f"No data yet — {exc}")
    st.stop()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("💼 Accounts", stats.total_accounts)
col2.metric("🏢 Organizations", stats.total_organizations)
col3.metric("📦 Container Groups", stats.total_container_groups)
col4.metric("🖥️ Instances", stats.total_instances)
col5.metric("🎮 GPU Types", stats.total_gpu_types)

st.divider()

# ── Status & Performance Charts ──────────────────────────────────────────────
col_left, col_right = st.columns([1, 2])

with col_left:
    st.subheader("Instance Health")
    if stats.total_instances > 0:
        # Create a donut chart for health
        labels = ['GOOD', 'WARNING', 'BAD', 'UNKNOWN']
        values = [stats.good_count, stats.warning_count, stats.bad_count, stats.unknown_count]
        colors = ['#00E5FF', '#F59E0B', '#EF4444', '#334155']
        
        fig_health = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.6, marker_colors=colors)])
        fig_health.update_layout(
            showlegend=True,
            margin=dict(t=20, b=20, l=20, r=20),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#94A3B8')
        )
        st.plotly_chart(fig_health, use_container_width=True)
        
        good_pct = (stats.good_count / stats.total_instances) * 100
        st.progress(int(good_pct), text=f"Fleet health: {good_pct:.1f}% GOOD")
    else:
        st.info("No instances found.")
        
    if stats.last_check:
        st.caption(f"Last check: {stats.last_check.strftime('%Y-%m-%d %H:%M:%S')} UTC")

with col_right:
    st.subheader("GPU Performance Summary")
    try:
        cfg = get_config()
        unit = cfg.hashrate.unit
        gpu_data = get_gpu_summary()

        if gpu_data:
            # Create a bar chart for average hashrates
            df_gpu = pd.DataFrame([
                {"GPU": g.gpu_type, f"Avg ({unit})": g.avg_hashrate or 0, "Instances": g.instance_count}
                for g in gpu_data if g.avg_hashrate is not None
            ])
            if not df_gpu.empty:
                fig_bar = px.bar(
                    df_gpu, x="GPU", y=f"Avg ({unit})",
                    text_auto='.2f', hover_data=["Instances"]
                )
                fig_bar.update_traces(marker_color='#00E5FF', marker_line_color='#00E5FF',
                                      marker_line_width=1.5, opacity=0.8)
                fig_bar.update_layout(
                    margin=dict(t=20, b=20, l=20, r=20),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#94A3B8'),
                    showlegend=False,
                    xaxis=dict(showgrid=False, zeroline=False, linecolor='#1E293B'),
                    yaxis=dict(showgrid=True, gridcolor='#1E293B', zeroline=False)
                )
                st.plotly_chart(fig_bar, use_container_width=True)
            
            # Show the detailed table below
            rows = []
            for g in gpu_data:
                rows.append({
                    "GPU Type": g.gpu_type,
                    "Instances": g.instance_count,
                    f"Median ({unit})": round(g.median_hashrate, 2) if g.median_hashrate else None,
                    f"Average ({unit})": round(g.avg_hashrate, 2) if g.avg_hashrate else None,
                    f"Min ({unit})": round(g.min_hashrate, 2) if g.min_hashrate else None,
                    f"Max ({unit})": round(g.max_hashrate, 2) if g.max_hashrate else None,
                    "Bad": g.bad_count,
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No GPU data available yet — waiting for first monitoring cycle.", icon="⏳")
    except Exception as exc:
        st.error(f"Failed to load GPU summary: {exc}")
