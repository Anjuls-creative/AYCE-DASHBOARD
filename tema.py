"""Tema & komponen tampilan bersama (CSS, brand, header, tiles)."""

from html import escape
from urllib.parse import quote

import streamlit as st

# Palet warna (mengikuti referensi: oranye + indigo di atas latar peach)
ORANYE = "#FF5B1F"
ORANYE_MUDA = "#FF9B73"
ORANYE_PUDAR = "#FFD3BF"
INDIGO = "#3B2FC9"
TEKS = "#1B2236"
ABU = "#8A94A6"


def _icon_uri(inner_svg: str) -> str:
    """Ubah path SVG (putih) menjadi data-URI untuk dipakai di CSS."""
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' "
        "fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
        + inner_svg
        + "</svg>"
    )
    return "data:image/svg+xml," + quote(svg, safe="")


ICON_WALLET = _icon_uri(
    "<path d='M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1'/>"
    "<path d='M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4'/>"
)
ICON_UTENSILS = _icon_uri(
    "<path d='M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2'/><path d='M7 2v20'/>"
    "<path d='M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7'/>"
)
ICON_USERS = _icon_uri(
    "<path d='M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2'/><circle cx='9' cy='7' r='4'/>"
    "<path d='M22 21v-2a4 4 0 0 0-3-3.87'/><path d='M16 3.13a4 4 0 0 1 0 7.75'/>"
)

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, .stApp, [data-testid="stSidebar"], .stMarkdown, .stMarkdown p, label,
[data-testid="stMetric"] *, [data-testid="stCaptionContainer"] {
    font-family: 'Plus Jakarta Sans', sans-serif;
}

/* ---------- Kerangka halaman ---------- */
.stApp { background: linear-gradient(160deg, #FDE6DB 0%, #FCD6C5 100%); }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }

.block-container {
    max-width: calc(100% - 2.4rem);
    margin: 0.8rem auto 1.6rem auto;
    padding: 2rem 2.4rem 2.4rem 2.4rem;
    background: #F5F7FB;
    border-radius: 28px;
    box-shadow: 0 24px 60px rgba(160, 80, 40, 0.16);
}

/* ---------- Tombol ---------- */
.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {
    border-radius: 12px; font-weight: 700;
}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] { background: #F5F7FB; border-right: 1px solid #ECEFF5; }
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    font-weight: 700; font-size: 0.82rem; color: __TEKS__;
}
.brand { display: flex; align-items: center; gap: 12px; margin: 0.4rem 0 1.2rem 0; }
.brand-ico {
    width: 40px; height: 40px; border-radius: 13px;
    background-image: url("__UTENSILS__"), linear-gradient(135deg, #FF7A45, #FF4D1C);
    background-size: 21px, cover; background-repeat: no-repeat; background-position: center;
    box-shadow: 0 6px 14px rgba(255, 91, 31, 0.28);
}
.brand-name { font-size: 1.55rem; font-weight: 800; color: __TEKS__; letter-spacing: -0.02em; }
.brand-name span { color: __ORANYE__; }

/* Navigasi kustom (st.page_link) */
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {
    border-radius: 14px; padding: 0.62rem 0.85rem; margin-bottom: 0.15rem;
}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p { font-weight: 700; font-size: 0.92rem; color: __TEKS__; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover { background: rgba(255, 91, 31, 0.08); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] {
    background: #fff; box-shadow: 0 2px 10px rgba(30, 41, 59, 0.06);
}

.user-chip {
    display: flex; align-items: center; gap: 10px; margin: 1rem 0 0.4rem 0; padding: 10px 12px;
    background: #fff; border-radius: 14px; box-shadow: 0 2px 10px rgba(30, 41, 59, 0.05);
}
.uc-avatar {
    width: 34px; height: 34px; border-radius: 50%; flex: none; color: #fff; font-weight: 800;
    background: linear-gradient(135deg, #FF7A45, #FF4D1C); display: flex; align-items: center; justify-content: center;
}
.uc-name { font-weight: 700; font-size: 0.86rem; color: __TEKS__; line-height: 1.2; }
.uc-role { font-size: 0.7rem; color: __ABU__; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }

.side-title {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
    color: __ABU__; margin: 1.5rem 0 0.4rem 0;
}
.side-card {
    margin-top: 1.8rem; padding: 18px 18px 16px 18px; border-radius: 18px; color: #fff;
    background:
        radial-gradient(circle at 108% -8%, rgba(255,255,255,0.22) 0 22%, transparent 23%),
        radial-gradient(circle at -8% 118%, rgba(255,255,255,0.16) 0 28%, transparent 29%),
        linear-gradient(135deg, #FF7A45, #FF4D1C);
}
.sc-title { font-weight: 800; font-size: 0.95rem; margin-bottom: 0.35rem; }
.sc-text { font-size: 0.76rem; line-height: 1.55; opacity: 0.96; }

/* ---------- Header halaman ---------- */
.page-head { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 1.2rem; gap: 1rem; flex-wrap: wrap; }
.crumb { font-size: 0.74rem; color: #9AA3B2; }
.crumb b { color: __TEKS__; font-weight: 600; }
.page-title { font-size: 1.45rem; font-weight: 800; color: __TEKS__; line-height: 1.25; }
.pill {
    background: #fff; border-radius: 12px; padding: 0.55rem 0.95rem; font-size: 0.78rem;
    color: #5B6475; font-weight: 600; box-shadow: 0 2px 10px rgba(30, 41, 59, 0.05);
}

/* ---------- Kartu KPI (dashboard) ---------- */
.st-key-kpi_rev, .st-key-kpi_meja, .st-key-kpi_cust {
    position: relative; background: #fff; border-radius: 18px; padding: 18px 20px 12px 20px;
    box-shadow: 0 2px 12px rgba(30, 41, 59, 0.05);
}
.st-key-kpi_rev::after, .st-key-kpi_meja::after, .st-key-kpi_cust::after {
    content: ""; position: absolute; top: 18px; right: 18px; width: 42px; height: 42px; border-radius: 13px;
    background-size: 21px, cover; background-repeat: no-repeat; background-position: center;
    box-shadow: 0 6px 14px rgba(255, 91, 31, 0.28);
}
.st-key-kpi_rev::after  { background-image: url("__WALLET__"),   linear-gradient(135deg, #FF7A45, #FF4D1C); }
.st-key-kpi_meja::after { background-image: url("__UTENSILS__"), linear-gradient(135deg, #FF7A45, #FF4D1C); }
.st-key-kpi_cust::after { background-image: url("__USERS__"),    linear-gradient(135deg, #FF7A45, #FF4D1C); }

[data-testid="stMetricLabel"] p { font-size: 0.78rem; font-weight: 600; color: __ABU__; }
[data-testid="stMetricValue"] { font-size: 1.45rem; font-weight: 800; color: __TEKS__; }
[data-testid="stMetricDelta"] { font-size: 0.78rem; font-weight: 700; }
.st-key-kpi_rev [data-testid="stCaptionContainer"],
.st-key-kpi_meja [data-testid="stCaptionContainer"],
.st-key-kpi_cust [data-testid="stCaptionContainer"] { font-size: 0.74rem; color: #9AA3B2; }

/* ---------- Kartu putih umum: container ber-key "card_*" ---------- */
[class*="st-key-card_"] {
    background: #fff; border-radius: 20px; padding: 22px 24px 14px 24px;
    box-shadow: 0 2px 12px rgba(30, 41, 59, 0.05);
}
.card-title { font-weight: 800; font-size: 1.02rem; color: __TEKS__; }
.card-sub { font-size: 0.78rem; color: __ABU__; margin-bottom: 0.6rem; }
.card-sub b { color: #16A34A; font-weight: 700; }

/* ---------- Tiles ringkasan ---------- */
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 0.4rem 0 1.1rem 0; }
.tile { background: #fff; border-radius: 16px; padding: 14px 16px; box-shadow: 0 2px 12px rgba(30, 41, 59, 0.05); }
.t-l { font-size: 0.72rem; color: __ABU__; font-weight: 600; }
.t-v { font-size: 1.35rem; font-weight: 800; color: __TEKS__; line-height: 1.3; }
.t-s { font-size: 0.72rem; color: #9AA3B2; }

/* ---------- Login ---------- */
.st-key-login_card {
    background: #fff; border-radius: 24px; padding: 30px 32px 22px 32px;
    box-shadow: 0 10px 40px rgba(160, 80, 40, 0.14); margin-top: 8vh;
}
.login-title { font-size: 1.35rem; font-weight: 800; color: __TEKS__; margin: 0.2rem 0 0.2rem 0; }
.login-sub { font-size: 0.8rem; color: __ABU__; margin-bottom: 0.8rem; }
"""

for _token, _value in {
    "__TEKS__": TEKS,
    "__ABU__": ABU,
    "__ORANYE__": ORANYE,
    "__WALLET__": ICON_WALLET,
    "__UTENSILS__": ICON_UTENSILS,
    "__USERS__": ICON_USERS,
}.items():
    _CSS = _CSS.replace(_token, _value)

# Rapatkan CSS (hapus baris kosong) supaya aman diparse sebagai satu blok HTML
_CSS_MIN = "\n".join(line for line in _CSS.splitlines() if line.strip())


def terapkan():
    """Suntik CSS tema ke halaman."""
    st.markdown(f"<style>{_CSS_MIN}</style>", unsafe_allow_html=True)


def sembunyikan_sidebar():
    """Dipakai pada halaman login (sebelum ada sesi)."""
    st.markdown(
        "<style>[data-testid='stSidebar'], [data-testid='stSidebarCollapsedControl'], "
        "[data-testid='collapsedControl'] { display: none !important; }</style>",
        unsafe_allow_html=True,
    )


def brand_html() -> str:
    return (
        '<div class="brand"><div class="brand-ico"></div>'
        '<div class="brand-name">AYCE<span>Dash</span></div></div>'
    )


def user_chip(user: dict) -> str:
    nama = escape(str(user.get("nama") or user.get("username") or "?"))
    role = "Bos" if user.get("role") == "bos" else "Pegawai"
    return (
        '<div class="user-chip">'
        f'<div class="uc-avatar">{nama[:1].upper()}</div>'
        f'<div><div class="uc-name">{nama}</div><div class="uc-role">{role}</div></div></div>'
    )


def header(crumb: str, judul: str, pill: str = ""):
    kanan = f'<div class="pill">{pill}</div>' if pill else ""
    st.markdown(
        '<div class="page-head"><div>'
        f'<div class="crumb">Pages / <b>{crumb}</b></div>'
        f'<div class="page-title">{judul}</div></div>{kanan}</div>',
        unsafe_allow_html=True,
    )


def judul_kartu(judul: str, sub: str = ""):
    st.markdown(
        f'<div class="card-title">{judul}</div><div class="card-sub">{sub}</div>',
        unsafe_allow_html=True,
    )


def tiles(items):
    """items: list of (label, nilai, keterangan)."""
    html = "".join(
        f'<div class="tile"><div class="t-l">{l}</div><div class="t-v">{v}</div><div class="t-s">{s}</div></div>'
        for l, v, s in items
    )
    st.markdown(f'<div class="tiles">{html}</div>', unsafe_allow_html=True)
