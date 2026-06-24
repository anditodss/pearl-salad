"""
utils/ui_components.py
======================
Shared UI components and styling for Streamlit.
"""
import streamlit as st

def inject_custom_css():
    """Injects modern dark theme CSS into Streamlit."""
    st.markdown("""
        <style>
        /* Base typography and background */
        html, body, [class*="css"] {
            font-family: 'Inter', 'Segoe UI', sans-serif;
            background-color: #0B0F19 !important;
        }

        /* Sidebar styling to mirror Veayra navigation */
        section[data-testid="stSidebar"] {
            background-color: #0B0F19 !important;
            border-right: 1px solid #1E293B !important;
        }
        
        /* Sidebar active link styling hack */
        .st-emotion-cache-17lntkn {
            color: #94A3B8;
        }
        .st-emotion-cache-17lntkn:hover {
            color: #00E5FF;
            background-color: transparent !important;
        }

        /* Modern metrics card styling */
        div[data-testid="metric-container"] {
            background-color: #111827 !important;
            border: 1px solid #1E293B !important;
            padding: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
        }
        
        div[data-testid="metric-container"]:hover {
            border-color: #00E5FF !important;
            box-shadow: 0 0 15px rgba(0, 229, 255, 0.1);
        }

        /* Value color for metrics (Cyan glowing) */
        div[data-testid="metric-container"] > div:nth-child(1) > div:nth-child(2) > div {
            color: #00E5FF !important;
            font-weight: 700;
            text-shadow: 0 0 10px rgba(0, 229, 255, 0.3);
        }
        
        /* Metric Label Color */
        div[data-testid="metric-container"] > div:nth-child(1) > div:nth-child(1) > div {
            color: #64748B !important;
            text-transform: uppercase;
            font-size: 0.8rem;
            letter-spacing: 0.05em;
        }

        /* Clean up table styling */
        div[data-testid="stDataFrame"] {
            border: 1px solid #1E293B;
            border-radius: 8px;
            overflow: hidden;
            background-color: #111827;
        }
        
        div[data-testid="stDataFrame"] table {
            background-color: #111827 !important;
        }

        /* Reduce top padding of main block */
        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 2rem !important;
        }

        /* Header styling */
        h1, h2, h3 {
            color: #F8FAFC !important;
            font-weight: 600 !important;
        }
        
        /* Buttons */
        button[kind="primary"] {
            background-color: transparent !important;
            border: 1px solid #00E5FF !important;
            color: #00E5FF !important;
            transition: all 0.2s;
        }
        button[kind="primary"]:hover {
            background-color: rgba(0, 229, 255, 0.1) !important;
            box-shadow: 0 0 10px rgba(0, 229, 255, 0.2);
        }
        </style>
    """, unsafe_allow_html=True)

def render_sync_button():
    """Renders a Force Sync button that triggers background jobs synchronously."""
    if st.button("🚀 Force Sync Now", type="primary", use_container_width=True, help="Force an immediate pull of all data from Salad API without waiting for the scheduler."):
        with st.spinner("Synchronizing data with Salad API..."):
            from scheduler.jobs import _sync_job, _log_job, _monitor_job
            import logging
            logger = logging.getLogger(__name__)
            try:
                _sync_job()
                _log_job()
                _monitor_job()
                st.success("✅ Synchronization complete!")
            except Exception as e:
                logger.error(f"Manual sync failed: {e}")
                st.error(f"Sync failed: {e}")
            st.rerun()
