import json
import os
import streamlit as st
from pathlib import Path

from utils.config import reload_config, _CONFIG_PATH

st.set_page_config(page_title="Settings - Salad Fleet", layout="wide")
st.title("⚙️ Settings")

# Check if .env is overriding settings
has_env_override = bool(os.getenv("SALAD_API_KEY") or os.getenv("SALAD_ACCOUNT_1_API_KEY"))
if has_env_override:
    st.warning(
        "⚠️ **Environment Variables Detected**\n\n"
        "You have configuration defined in your `.env` file. "
        "The `.env` file takes priority over the settings here. "
        "To manage accounts through this UI, please delete or clear your `.env` file."
    )

st.markdown("### Manage Salad Accounts")
st.write("Tambahkan atau hapus akun Salad Cloud yang ingin Anda monitor. Format Project Name: `organization_name/project_name`")

# Load existing config
def load_raw_config():
    if not _CONFIG_PATH.exists():
        return {"accounts": [], "monitoring": {}}
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_raw_config(data):
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    reload_config()

config_data = load_raw_config()
accounts = config_data.get("accounts", [])

# Display existing accounts
if not accounts:
    st.info("Belum ada akun yang dikonfigurasi.")
else:
    for idx, acc in enumerate(accounts):
        with st.expander(f"👤 {acc.get('name', 'Unknown')}"):
            st.write(f"**API Key:** `{(acc.get('api_key', '')[:6])}••••••••`")
            st.write(f"**Projects:** `{', '.join(acc.get('organizations', []))}`")
            
            if st.button(f"Hapus Akun", key=f"del_{idx}"):
                accounts.pop(idx)
                config_data["accounts"] = accounts
                save_raw_config(config_data)
                st.success("Akun dihapus!")
                st.rerun()

st.divider()

# Add new account form
st.markdown("#### Tambah Akun Baru")
with st.form("add_account_form", clear_on_submit=True):
    new_name = st.text_input("Nama Akun", placeholder="Misal: AkunUtama")
    new_api_key = st.text_input("API Key", type="password", placeholder="Salad API Key Anda")
    new_projects = st.text_input("Projects", placeholder="Format: my-org/my-project, my-org/project-2")
    
    submitted = st.form_submit_button("Simpan Akun")
    if submitted:
        if not new_name or not new_api_key or not new_projects:
            st.error("Semua kolom wajib diisi!")
        else:
            proj_list = [p.strip() for p in new_projects.split(",") if p.strip()]
            new_acc = {
                "name": new_name,
                "api_key": new_api_key,
                "organizations": proj_list
            }
            accounts.append(new_acc)
            config_data["accounts"] = accounts
            save_raw_config(config_data)
            st.success(f"Akun '{new_name}' berhasil ditambahkan!")
            st.rerun()
