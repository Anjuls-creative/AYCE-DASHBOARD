"""
AYCE Dashboard — titik masuk aplikasi (login + navigasi per peran).

Peran & halaman:
  pegawai : Input Data, Dashboard
  bos     : Dashboard, Data Masuk & Unduh

Ubah AKSES di bawah untuk mengatur halaman tiap peran.
Jalankan:  streamlit run app.py
"""

import streamlit as st

# set_page_config harus menjadi perintah Streamlit pertama
st.set_page_config(
    page_title="AYCE Dashboard",
    page_icon="🍖",
    layout="wide",
    initial_sidebar_state="expanded",
)

import auth  # noqa: E402
import tema  # noqa: E402
from dashboard import halaman_dashboard  # noqa: E402
from data_masuk import halaman_data_masuk  # noqa: E402
from input_data import halaman_input  # noqa: E402

tema.terapkan()

# ---------------------------------------------------------------------------
# Gerbang login
# ---------------------------------------------------------------------------
user = st.session_state.get("auth")
if not user:
    tema.sembunyikan_sidebar()
    auth.tampil_login()
    st.stop()

# ---------------------------------------------------------------------------
# Halaman & hak akses
# ---------------------------------------------------------------------------
HALAMAN = {
    "dashboard": dict(fn=halaman_dashboard, title="Dashboard", icon="📊", path="dashboard"),
    "input": dict(fn=halaman_input, title="Input Data", icon="📝", path="input-data"),
    "data_masuk": dict(fn=halaman_data_masuk, title="Data Masuk & Unduh", icon="📥", path="data-masuk"),
}
AKSES = {
    "pegawai": ["input", "dashboard"],
    "bos": ["dashboard", "data_masuk"],
}

kunci = AKSES.get(user["role"], [])
if not kunci:
    st.error("Peran akun ini tidak dikenali.")
    st.stop()

pages = [
    st.Page(HALAMAN[k]["fn"], title=HALAMAN[k]["title"], icon=HALAMAN[k]["icon"],
            url_path=HALAMAN[k]["path"], default=(i == 0))
    for i, k in enumerate(kunci)
]

# Navigasi disembunyikan lalu digambar ulang dengan gaya referensi (st.page_link).
# Jika versi Streamlit belum mendukung position="hidden", dipakai navigasi bawaan.
try:
    pg = st.navigation(pages, position="hidden")
    nav_kustom = True
except Exception:
    pg = st.navigation(pages)
    nav_kustom = False

with st.sidebar:
    st.markdown(tema.brand_html(), unsafe_allow_html=True)
    if nav_kustom:
        for p in pages:
            st.page_link(p, label=p.title, icon=p.icon)
    st.markdown(tema.user_chip(user), unsafe_allow_html=True)
    if st.button("Keluar", key="btn_logout"):
        auth.logout()

pg.run()
