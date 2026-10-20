"""
app.py — TITIK MASUK APLIKASI (login + menu per peran).

Jalankan:  streamlit run app.py

╔══════════════════════ PETA UBAH CEPAT ═══════════════════════╗
║ Mau ubah ...                       → cari bagian ...          ║
║ • Halaman apa yang dilihat tiap    → AKSES (di bawah)         ║
║   peran (pegawai / bos)                                       ║
║ • Nama menu, ikon, alamat URL      → HALAMAN (di bawah)       ║
║ • Menambah halaman baru            → tambah di HALAMAN +      ║
║                                      tambah kuncinya ke AKSES ║
║ • Judul tab browser & ikon         → st.set_page_config       ║
║ • Isi menu kiri (logo, tombol      → blok "with st.sidebar"   ║
║   Keluar)                                                     ║
╚═══════════════════════════════════════════════════════════════╝

Daftar file:
  auth.py        login          | store.py     baca/tulis CSV & hitung harga
  input_data.py  halaman Input  | data_masuk.py halaman Bos (data baru & unduh)
  dashboard.py   halaman grafik | tema.py      warna & CSS
"""

import streamlit as st

# set_page_config harus menjadi perintah Streamlit PERTAMA.
st.set_page_config(
    page_title="AYCE Dashboard",   # UBAH: judul tab browser
    page_icon="🍖",                # UBAH: ikon tab browser
    layout="wide",
    initial_sidebar_state="expanded",
)

import auth  # noqa: E402
import tema  # noqa: E402
from dashboard import halaman_dashboard  # noqa: E402
from data_masuk import halaman_data_masuk  # noqa: E402
from input_data import halaman_input  # noqa: E402

tema.terapkan()  # pasang CSS tema (warna, kartu, dll)

# ===========================================================================
# 1) GERBANG LOGIN — belum login = hanya form login yang tampil
# ===========================================================================
user = st.session_state.get("auth")
if not user:
    tema.sembunyikan_sidebar()
    auth.tampil_login()
    st.stop()

# ===========================================================================
# 2) DAFTAR HALAMAN & HAK AKSES
# ===========================================================================
# UBAH: title = nama di menu, icon = emoji menu, path = alamat URL (tanpa spasi).
HALAMAN = {
    "dashboard": dict(fn=halaman_dashboard, title="Dashboard", icon="📊", path="dashboard"),
    "input": dict(fn=halaman_input, title="Input Pesanan", icon="📝", path="input-pesanan"),
    "data_masuk": dict(fn=halaman_data_masuk, title="Data Masuk & Unduh", icon="📥", path="data-masuk"),
}
# UBAH: halaman apa saja yang boleh dibuka tiap peran. Halaman PERTAMA = halaman awal setelah login.
#   Contoh: agar bos juga bisa input → "bos": ["dashboard", "data_masuk", "input"]
#   (auth.wajib("pegawai") di input_data.py juga perlu diubah menjadi auth.wajib("pegawai", "bos"))
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

# ===========================================================================
# 3) MENU KIRI (sidebar)
# ===========================================================================
# Menu bawaan Streamlit disembunyikan lalu digambar ulang (st.page_link) dengan gaya referensi.
# Jika versi Streamlit belum mendukung position="hidden", dipakai menu bawaan.
try:
    pg = st.navigation(pages, position="hidden")
    nav_kustom = True
except Exception:
    pg = st.navigation(pages)
    nav_kustom = False

with st.sidebar:
    st.markdown(tema.brand_html(), unsafe_allow_html=True)          # logo & nama brand
    if nav_kustom:
        for p in pages:
            st.page_link(p, label=p.title, icon=p.icon)             # item menu
    st.markdown(tema.user_chip(user), unsafe_allow_html=True)       # siapa yang login
    if st.button("Keluar", key="btn_logout"):                       # UBAH: teks tombol keluar
        auth.logout()

pg.run()  # jalankan halaman yang sedang dipilih
