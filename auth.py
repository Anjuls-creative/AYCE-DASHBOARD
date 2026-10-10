"""
Login sederhana (EKSPERIMEN) dengan dua peran: `pegawai` dan `bos`.

Akun dibaca dari Streamlit Secrets (bagian [users.*]); jika tidak ada, dipakai akun demo di bawah.
Lihat .streamlit/secrets.toml.example untuk format Secrets.
"""

import hashlib
import hmac
import time

import streamlit as st

import tema

ROLE_VALID = ("pegawai", "bos")

# AKUN DEMO — hanya untuk percobaan. Ganti lewat Secrets sebelum dipakai serius / jika repo publik.
AKUN_DEMO = {
    "pegawai": {"password": "pegawai123", "role": "pegawai", "nama": "Pegawai"},
    "bos": {"password": "bos123", "role": "bos", "nama": "Bos"},
}

MAKS_GAGAL = 5
KUNCI_DETIK = 30


def _muat_akun() -> dict:
    try:
        sec = st.secrets.get("users")
        if sec:
            return {str(k).strip().lower(): dict(v) for k, v in sec.items()}
    except Exception:
        pass  # tidak ada secrets -> pakai akun demo
    return AKUN_DEMO


def pakai_akun_demo() -> bool:
    return _muat_akun() is AKUN_DEMO


def cek_login(username: str, password: str):
    """Kembalikan dict sesi jika valid, selain itu None."""
    akun = _muat_akun().get((username or "").strip().lower())
    sandi = (password or "").encode("utf-8")
    ok = False
    if akun:
        if "password_sha256" in akun:
            ok = hmac.compare_digest(hashlib.sha256(sandi).hexdigest(), str(akun["password_sha256"]).strip().lower())
        else:
            ok = hmac.compare_digest(sandi, str(akun.get("password", "")).encode("utf-8"))
    else:
        hmac.compare_digest(b"dummy", b"dummy2")  # samakan waktu proses
    if ok and akun.get("role") in ROLE_VALID:
        return {
            "username": username.strip().lower(),
            "role": akun["role"],
            "nama": akun.get("nama") or username.strip().title(),
        }
    return None


def tampil_login():
    """Form login di tengah halaman. Jika berhasil: simpan sesi lalu rerun."""
    _, tengah, _ = st.columns([1, 1.15, 1])
    with tengah:
        with st.container(key="login_card"):
            st.markdown(
                tema.brand_html()
                + '<div class="login-title">Masuk ke dashboard</div>'
                + '<div class="login-sub">Gunakan akun pegawai atau bos.</div>',
                unsafe_allow_html=True,
            )
            terkunci = st.session_state.get("kunci_sampai", 0) - time.time()
            with st.form("form_login"):
                username = st.text_input("Username", key="login_user")
                password = st.text_input("Password", type="password", key="login_pass")
                kirim = st.form_submit_button("Masuk", type="primary")

            if kirim:
                if terkunci > 0:
                    st.error(f"Terlalu banyak percobaan. Coba lagi dalam {int(terkunci) + 1} detik.")
                    return
                sesi = cek_login(username, password)
                if sesi:
                    st.session_state.pop("gagal", None)
                    st.session_state["auth"] = sesi
                    st.rerun()
                gagal = st.session_state.get("gagal", 0) + 1
                st.session_state["gagal"] = gagal
                if gagal >= MAKS_GAGAL:
                    st.session_state["kunci_sampai"] = time.time() + KUNCI_DETIK
                    st.session_state["gagal"] = 0
                st.error("Username atau password salah.")


def logout():
    st.session_state.clear()
    st.rerun()


def wajib(*roles):
    """Pastikan pengguna login dan berperan salah satu dari `roles`; jika tidak, hentikan halaman."""
    user = st.session_state.get("auth")
    if not user or user.get("role") not in roles:
        st.error("Anda tidak memiliki akses ke halaman ini.")
        st.stop()
    return user
