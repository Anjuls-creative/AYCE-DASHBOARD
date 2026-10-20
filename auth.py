"""
auth.py — LOGIN (EKSPERIMEN) dengan dua peran: `pegawai` dan `bos`.

╔══════════════════════ PETA UBAH CEPAT ═══════════════════════╗
║ Mau ubah ...                       → cari bagian ...          ║
║ • Username / password / nama       → AKUN_DEMO (atau Secrets) ║
║ • Tambah akun pegawai baru         → Secrets: [users.namaakun]║
║ • Batas salah password & lama kunci→ MAKS_GAGAL, KUNCI_DETIK  ║
║ • Teks di form login               → tampil_login()           ║
║ • Siapa boleh buka halaman         → auth.wajib(...) di halaman║
║                                      (daftar halaman per peran ║
║                                      ada di AKSES pada app.py) ║
╚═══════════════════════════════════════════════════════════════╝

Akun dibaca dari Streamlit Secrets (bagian [users.*]); jika tidak ada, dipakai AKUN_DEMO.
Format Secrets: lihat .streamlit/secrets.toml.example
"""

import hashlib
import hmac
import time

import streamlit as st

import tema

ROLE_VALID = ("pegawai", "bos")  # UBAH: kalau menambah peran baru (mis. "kasir"), tambahkan di sini dan di AKSES (app.py)

# ===== AKUN DEMO =====
# UBAH: ganti username/password di bawah. Hanya dipakai bila Secrets belum diisi.
# PERINGATAN: jika repo GitHub Anda publik, password di file ini bisa dibaca siapa saja.
#             Untuk pemakaian serius, isi Secrets dan JANGAN simpan password asli di kode.
AKUN_DEMO = {
    "pegawai": {"password": "pegawai123", "role": "pegawai", "nama": "Pegawai"},
    "bos": {"password": "bos123", "role": "bos", "nama": "Bos"},
}

MAKS_GAGAL = 5     # UBAH: berapa kali salah password sebelum dikunci sementara
KUNCI_DETIK = 30   # UBAH: lama penguncian (detik)


def _muat_akun() -> dict:
    """Ambil akun dari Secrets bila ada, jika tidak pakai AKUN_DEMO."""
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
    """Kembalikan data sesi (dict) jika username & password benar, selain itu None."""
    akun = _muat_akun().get((username or "").strip().lower())
    sandi = (password or "").encode("utf-8")
    ok = False
    if akun:
        if "password_sha256" in akun:  # alternatif: simpan hash SHA-256, bukan password asli
            ok = hmac.compare_digest(hashlib.sha256(sandi).hexdigest(), str(akun["password_sha256"]).strip().lower())
        else:
            ok = hmac.compare_digest(sandi, str(akun.get("password", "")).encode("utf-8"))
    else:
        hmac.compare_digest(b"dummy", b"dummy2")  # samakan waktu proses agar username tidak bisa ditebak
    if ok and akun.get("role") in ROLE_VALID:
        return {
            "username": username.strip().lower(),
            "role": akun["role"],
            "nama": akun.get("nama") or username.strip().title(),
        }
    return None


def tampil_login():
    """Form login di tengah halaman. Jika berhasil: simpan sesi lalu rerun halaman."""
    _, tengah, _ = st.columns([1, 1.15, 1])
    with tengah:
        with st.container(key="login_card"):
            # UBAH: judul & keterangan form login
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
                    st.session_state["auth"] = sesi  # <- inilah 'tanda sudah login'
                    st.rerun()
                gagal = st.session_state.get("gagal", 0) + 1
                st.session_state["gagal"] = gagal
                if gagal >= MAKS_GAGAL:
                    st.session_state["kunci_sampai"] = time.time() + KUNCI_DETIK
                    st.session_state["gagal"] = 0
                st.error("Username atau password salah.")


def logout():
    """Hapus sesi lalu kembali ke halaman login."""
    st.session_state.clear()
    st.rerun()


def wajib(*roles):
    """
    Dipanggil di awal halaman: pastikan sudah login DAN perannya salah satu dari `roles`.
    Contoh: auth.wajib("bos") → halaman hanya untuk bos. Jika tidak cocok, halaman dihentikan.
    """
    user = st.session_state.get("auth")
    if not user or user.get("role") not in roles:
        st.error("Anda tidak memiliki akses ke halaman ini.")
        st.stop()
    return user
