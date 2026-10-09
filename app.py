"""
AYCE Dashboard — Streamlit + Plotly
-----------------------------------
Dashboard interaktif untuk restoran All You Can Eat (AYCE).

Sumber data (dicari berurutan):
  1. data/<nama>.csv        (struktur repo: AYCE-DASHBOARD/data/*.csv)
  2. <nama>.csv             (kalau CSV ditaruh sejajar dengan app.py)
  3. tabel <nama> di ayce.db (SQLite, cadangan jika CSV tidak ditemukan)

Tabel yang dipakai: transaksi, reservasi, paket, (opsional) meja.
"""

import sqlite3
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# KONFIGURASI HALAMAN (harus menjadi perintah Streamlit pertama)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AYCE Dashboard",
    page_icon="🍖",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).parent
BATAS_SHIFT_JAM = 15  # Pagi: mulai sebelum 15:00 | Malam: mulai 15:00 ke atas

# Palet warna (mengikuti referensi: oranye + indigo di atas latar peach)
ORANYE = "#FF5B1F"
ORANYE_MUDA = "#FF9B73"
ORANYE_PUDAR = "#FFD3BF"
INDIGO = "#3B2FC9"
TEKS = "#1B2236"
ABU = "#8A94A6"

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


# ---------------------------------------------------------------------------
# STYLING (CSS)
# ---------------------------------------------------------------------------
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
ICON_CHART = _icon_uri(
    "<path d='M3 3v16a2 2 0 0 0 2 2h16'/><path d='M18 17V9'/><path d='M13 17V5'/><path d='M8 17v-3'/>"
)

CSS = """
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

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] { background: #F5F7FB; border-right: 1px solid #ECEFF5; }
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    font-weight: 700; font-size: 0.82rem; color: __TEKS__;
}
.brand { display: flex; align-items: center; gap: 12px; margin: 0.4rem 0 1.4rem 0; }
.brand-ico {
    width: 40px; height: 40px; border-radius: 13px;
    background-image: url("__UTENSILS__"), linear-gradient(135deg, #FF7A45, #FF4D1C);
    background-size: 21px, cover; background-repeat: no-repeat; background-position: center;
    box-shadow: 0 6px 14px rgba(255, 91, 31, 0.28);
}
.brand-name { font-size: 1.55rem; font-weight: 800; color: __TEKS__; letter-spacing: -0.02em; }
.brand-name span { color: __ORANYE__; }
.nav-active {
    display: flex; align-items: center; gap: 12px; padding: 11px 14px; border-radius: 14px;
    background: #fff; box-shadow: 0 2px 10px rgba(30, 41, 59, 0.06);
    font-weight: 700; font-size: 0.92rem; color: __TEKS__;
}
.nav-ico {
    width: 30px; height: 30px; border-radius: 10px; flex: none;
    background-image: url("__CHART__"), linear-gradient(135deg, #FF7A45, #FF4D1C);
    background-size: 16px, cover; background-repeat: no-repeat; background-position: center;
}
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

/* ---------- Kartu KPI ---------- */
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

/* ---------- Kartu grafik ---------- */
.st-key-card_bar, .st-key-card_line {
    background: #fff; border-radius: 20px; padding: 22px 24px 10px 24px;
    box-shadow: 0 2px 12px rgba(30, 41, 59, 0.05);
}
.card-title { font-weight: 800; font-size: 1.02rem; color: __TEKS__; }
.card-sub { font-size: 0.78rem; color: __ABU__; margin-bottom: 0.2rem; }
.card-sub b { color: #16A34A; font-weight: 700; }
"""

for token, value in {
    "__TEKS__": TEKS,
    "__ABU__": ABU,
    "__ORANYE__": ORANYE,
    "__WALLET__": ICON_WALLET,
    "__UTENSILS__": ICON_UTENSILS,
    "__USERS__": ICON_USERS,
    "__CHART__": ICON_CHART,
}.items():
    CSS = CSS.replace(token, value)

# Rapatkan CSS (hapus baris kosong) supaya aman diparse sebagai satu blok HTML
_css_min = "\n".join(line for line in CSS.splitlines() if line.strip())
st.markdown(f"<style>{_css_min}</style>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# HELPER FORMAT
# ---------------------------------------------------------------------------
def angka(v) -> str:
    """12345 -> '12.345' (format Indonesia)."""
    return f"{v:,.0f}".replace(",", ".")


def rupiah(v) -> str:
    return "Rp " + angka(v)


def fmt_tgl(d, tahun: bool = False) -> str:
    s = f"{d.day:02d} {BULAN[d.month - 1]}"
    return f"{s} {d.year}" if tahun else s


def persen_perubahan(sekarang, sebelumnya):
    """String delta '+12.3%' untuk st.metric, atau None jika tidak bisa dibandingkan."""
    if sebelumnya is None or sebelumnya == 0:
        return None
    return f"{(sekarang - sebelumnya) / sebelumnya * 100:+.1f}%"


# ---------------------------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------------------------
def _baca_tabel(nama: str):
    """Baca tabel dari CSV (data/ atau root) lalu cadangan dari ayce.db. None jika tidak ada."""
    for p in (BASE_DIR / "data" / f"{nama}.csv", BASE_DIR / f"{nama}.csv"):
        if p.exists():
            return pd.read_csv(p)
    db = BASE_DIR / "ayce.db"
    if db.exists():
        try:
            with sqlite3.connect(db) as con:
                return pd.read_sql(f"SELECT * FROM {nama}", con)
        except Exception:
            return None
    return None


@st.cache_data(show_spinner="Memuat data...")
def muat_data():
    trx = _baca_tabel("transaksi")
    res = _baca_tabel("reservasi")
    pak = _baca_tabel("paket")
    meja = _baca_tabel("meja")

    hilang = [n for n, d in (("transaksi", trx), ("reservasi", res), ("paket", pak)) if d is None]
    if hilang:
        raise FileNotFoundError(", ".join(hilang))

    trx = trx.copy()
    trx["tanggal"] = pd.to_datetime(trx["tanggal"])

    # Shift berdasarkan jam mulai makan: Pagi < 15:00 <= Malam
    jam = trx["waktu_mulai"].astype(str).str.split(":").str[0].astype(int)
    trx["shift"] = ["Pagi" if j < BATAS_SHIFT_JAM else "Malam" for j in jam]

    # Tipe kedatangan dari tabel reservasi (Booking ditampilkan sebagai "Reservasi")
    tipe = res[["id_reservasi", "tipe_kedatangan"]].copy()
    tipe["tipe"] = tipe["tipe_kedatangan"].replace({"Booking": "Reservasi"})
    trx = trx.merge(tipe[["id_reservasi", "tipe"]], on="id_reservasi", how="left")

    # Nama paket dari tabel paket
    trx = trx.merge(pak[["id_paket", "nama_paket"]], on="id_paket", how="left")
    trx["nama_paket"] = trx["nama_paket"].fillna(trx["id_paket"])

    total_meja = int(meja["id_meja"].nunique()) if meja is not None else None
    return trx, pak, total_meja


try:
    trx, paket, total_meja = muat_data()
except FileNotFoundError as e:
    st.error(
        f"Tabel yang diperlukan tidak ditemukan: **{e}**. "
        "Pastikan folder `data/` (berisi file CSV) atau `ayce.db` berada di repo yang sama dengan `app.py`."
    )
    st.stop()

DMIN = trx["tanggal"].min().date()
DMAX = trx["tanggal"].max().date()

# ---------------------------------------------------------------------------
# SIDEBAR — BRAND + FILTER
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="brand-ico"></div>'
        '<div class="brand-name">AYCE<span>Dash</span></div></div>'
        '<div class="nav-active"><div class="nav-ico"></div>Dashboard</div>'
        '<div class="side-title">Filter</div>',
        unsafe_allow_html=True,
    )

    rentang = st.date_input(
        "Rentang Tanggal",
        value=(DMIN, DMAX),
        min_value=DMIN,
        max_value=DMAX,
        format="DD/MM/YYYY",
    )
    agregasi = st.radio("Agregasi Waktu", ["Per Hari", "Per Minggu"], index=0, horizontal=True)
    tipe_pilihan = st.multiselect(
        "Tipe Kedatangan",
        ["Walk-in", "Reservasi"],
        default=["Walk-in", "Reservasi"],
    )

    st.markdown(
        '<div class="side-card"><div class="sc-title">Catatan Data</div>'
        '<div class="sc-text">Shift <b>Pagi</b>: mulai makan sebelum 15:00.<br>'
        "Shift <b>Malam</b>: mulai makan 15:00 ke atas.<br>"
        f"Data fiktif {fmt_tgl(DMIN, True)} – {fmt_tgl(DMAX, True)}.</div></div>",
        unsafe_allow_html=True,
    )

# date_input range bisa mengembalikan 1 tanggal saat pengguna belum memilih tanggal akhir
if isinstance(rentang, (tuple, list)):
    if len(rentang) == 2:
        mulai, akhir = rentang
    elif len(rentang) == 1:
        mulai = akhir = rentang[0]
    else:
        mulai, akhir = DMIN, DMAX
else:
    mulai = akhir = rentang

# ---------------------------------------------------------------------------
# FILTER DATA
# ---------------------------------------------------------------------------
dasar = trx[trx["tipe"].isin(tipe_pilihan)]  # sudah terfilter tipe kedatangan (belum tanggal)
cur = dasar[(dasar["tanggal"] >= pd.Timestamp(mulai)) & (dasar["tanggal"] <= pd.Timestamp(akhir))]

label_tipe = " + ".join(tipe_pilihan) if tipe_pilihan else "—"
st.markdown(
    '<div class="page-head"><div>'
    '<div class="crumb">Pages / <b>Dashboard</b></div>'
    '<div class="page-title">Dashboard Restoran AYCE</div></div>'
    f'<div class="pill">📅 {fmt_tgl(mulai, True)} – {fmt_tgl(akhir, True)} &nbsp;·&nbsp; {label_tipe}</div></div>',
    unsafe_allow_html=True,
)

if cur.empty:
    st.warning(
        "Tidak ada transaksi untuk filter yang dipilih. "
        "Coba ubah rentang tanggal atau pilih minimal satu Tipe Kedatangan."
    )
    st.stop()

# ---------------------------------------------------------------------------
# KPI (3 kolom st.metric) + perbandingan dengan periode sebelumnya
# ---------------------------------------------------------------------------
jumlah_hari = (akhir - mulai).days + 1
prev_akhir = mulai - timedelta(days=1)
prev_mulai = prev_akhir - timedelta(days=jumlah_hari - 1)
prev = None
if prev_mulai >= DMIN:  # bandingkan hanya jika periode sebelumnya masih dalam jangkauan data
    prev = dasar[(dasar["tanggal"] >= pd.Timestamp(prev_mulai)) & (dasar["tanggal"] <= pd.Timestamp(prev_akhir))]
    if prev.empty:
        prev = None

total_pendapatan = int(cur["total_bayar"].sum())
meja_unik = int(cur["id_meja"].nunique())
total_pelanggan = int(cur["jumlah_orang"].sum())
sesi = len(cur)

if prev is not None:
    d_rev = persen_perubahan(total_pendapatan, int(prev["total_bayar"].sum()))
    d_meja = persen_perubahan(meja_unik, int(prev["id_meja"].nunique()))
    d_cust = persen_perubahan(total_pelanggan, int(prev["jumlah_orang"].sum()))
    ket_delta = f"Dibandingkan periode sebelumnya ({fmt_tgl(prev_mulai)} – {fmt_tgl(prev_akhir)})"
else:
    d_rev = d_meja = d_cust = None
    ket_delta = "Perbandingan muncul jika ada periode sebelumnya dengan panjang hari yang sama dalam data."

k1, k2, k3 = st.columns(3, gap="medium")
with k1:
    with st.container(key="kpi_rev"):
        st.metric("Total Pendapatan", rupiah(total_pendapatan), delta=d_rev, help=ket_delta)
        st.caption(f"Rata-rata {rupiah(total_pendapatan / sesi)} per transaksi")
with k2:
    with st.container(key="kpi_meja"):
        st.metric("Total Meja Terisi", angka(meja_unik), delta=d_meja, help=ket_delta)
        dari = f"dari {total_meja} meja · " if total_meja else ""
        st.caption(f"{dari}{angka(sesi)} sesi meja")
with k3:
    with st.container(key="kpi_cust"):
        st.metric("Total Pelanggan", angka(total_pelanggan), delta=d_cust, help=ket_delta)
        st.caption(f"Rata-rata {total_pelanggan / sesi:.1f} orang per meja")

st.write("")  # jarak antar baris

# ---------------------------------------------------------------------------
# GRAFIK
# ---------------------------------------------------------------------------
FONT = dict(family="Plus Jakarta Sans, sans-serif", color="#5B6475", size=12)


def rapikan(fig, tinggi=350):
    fig.update_layout(
        height=tinggi,
        margin=dict(l=0, r=0, t=8, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=FONT,
        separators=",.",  # desimal koma, ribuan titik
    )
    return fig


col_bar, col_line = st.columns([2, 3], gap="medium")

# ---- Bar chart: Paket Paling Favorit --------------------------------------
with col_bar:
    with st.container(key="card_bar"):
        urut = (
            cur.groupby("nama_paket").size()
            .reindex(paket["nama_paket"].tolist(), fill_value=0)
            .sort_values(ascending=False)
        )
        total_trx = int(urut.sum())
        pangsa = urut / total_trx * 100
        favorit = urut.index[0]

        st.markdown(
            '<div class="card-title">Paket Paling Favorit</div>'
            f'<div class="card-sub"><b>{favorit}</b> terlaris · {pangsa.iloc[0]:.0f}% dari {angka(total_trx)} transaksi</div>',
            unsafe_allow_html=True,
        )

        palet = [ORANYE, ORANYE_MUDA, ORANYE_PUDAR]
        warna = [palet[min(i, len(palet) - 1)] for i in range(len(urut))]
        puncak = max(int(urut.max()), 1)

        fig_bar = go.Figure()
        fig_bar.add_bar(  # "track" abu-peach di belakang batang (gaya referensi)
            x=urut.index.tolist(),
            y=[puncak * 1.15] * len(urut),
            marker_color="#FFF1EA",
            hoverinfo="skip",
            showlegend=False,
        )
        fig_bar.add_bar(
            x=urut.index.tolist(),
            y=urut.values.tolist(),
            marker_color=warna,
            text=[f"{angka(v)}<br>({p:.0f}%)" for v, p in zip(urut.values, pangsa.values)],
            textposition="outside",
            cliponaxis=False,
            customdata=pangsa.round(1).values.tolist(),
            hovertemplate="<b>%{x}</b><br>%{y:,.0f} transaksi (%{customdata}%)<extra></extra>",
            showlegend=False,
        )
        fig_bar.update_layout(barmode="overlay", bargap=0.45)
        try:  # sudut batang membulat (butuh plotly >= 5.24, diabaikan jika tidak didukung)
            fig_bar.update_traces(marker=dict(cornerradius=12))
        except ValueError:
            pass
        fig_bar.update_xaxes(type="category", showgrid=False, linecolor="#E6EAF2", tickfont=dict(size=13, color=TEKS))
        fig_bar.update_yaxes(
            range=[0, puncak * 1.35], gridcolor="#EEF1F6", griddash="dot", zeroline=False,
            tickformat=",.0f", title=None,
        )
        rapikan(fig_bar, 360)
        st.plotly_chart(fig_bar, config={"displayModeBar": False}, key="chart_paket")

# ---- Line chart: omzet per shift -------------------------------------------
with col_line:
    with st.container(key="card_line"):
        mingguan = agregasi == "Per Minggu"
        ts_mulai, ts_akhir = pd.Timestamp(mulai), pd.Timestamp(akhir)

        if mingguan:
            periode = cur["tanggal"] - pd.to_timedelta(cur["tanggal"].dt.weekday, unit="D")  # Senin
            awal = ts_mulai - pd.Timedelta(days=ts_mulai.weekday())
            idx = pd.date_range(awal, ts_akhir, freq="7D")
            label = [f"{fmt_tgl(d)} – {fmt_tgl(d + pd.Timedelta(days=6))}" for d in idx]
            ket_agregasi = "per minggu (Senin–Minggu)"
        else:
            periode = cur["tanggal"]
            idx = pd.date_range(ts_mulai, ts_akhir, freq="D")
            label = [fmt_tgl(d) for d in idx]
            ket_agregasi = "per hari"

        omzet = (
            cur.assign(periode=periode)
            .groupby(["periode", "shift"])["total_bayar"].sum()
            .unstack("shift")
            .reindex(index=idx, columns=["Pagi", "Malam"])
            .fillna(0)
        )
        tot_pagi, tot_malam = int(omzet["Pagi"].sum()), int(omzet["Malam"].sum())

        st.markdown(
            '<div class="card-title">Omzet per Shift</div>'
            f'<div class="card-sub">Pagi <b>{rupiah(tot_pagi)}</b> &nbsp;·&nbsp; '
            f'Malam <b>{rupiah(tot_malam)}</b> &nbsp;·&nbsp; {ket_agregasi}</div>',
            unsafe_allow_html=True,
        )

        mode = "lines+markers" if len(idx) <= 20 else "lines"
        garis = {
            "Pagi": (ORANYE, "rgba(255,91,31,0.14)", "Pagi (< 15:00)"),
            "Malam": (INDIGO, "rgba(59,47,201,0.08)", "Malam (≥ 15:00)"),
        }
        fig_line = go.Figure()
        for shift, (warna_g, warna_isi, nama) in garis.items():
            nilai = omzet[shift]
            fig_line.add_trace(
                go.Scatter(
                    x=label,
                    y=(nilai / 1_000_000).tolist(),
                    name=nama,
                    mode=mode,
                    line=dict(color=warna_g, width=3, shape="spline", smoothing=0.7),
                    marker=dict(size=6),
                    fill="tozeroy",
                    fillcolor=warna_isi,
                    customdata=nilai.tolist(),
                    hovertemplate="Rp %{customdata:,.0f}<extra>" + nama + "</extra>",
                )
            )

        langkah = max(1, len(label) // 9)  # kurangi kepadatan label sumbu-x
        fig_line.update_xaxes(
            type="category", tickmode="array", tickvals=label[::langkah], ticktext=label[::langkah],
            showgrid=False, linecolor="#E6EAF2", tickangle=0,
        )
        fig_line.update_yaxes(
            title="Omzet (Rp juta)", gridcolor="#EEF1F6", griddash="dot", zeroline=False,
            rangemode="tozero", tickformat=",.0f" if omzet.to_numpy().max() >= 10_000_000 else ",.1f",
        )
        fig_line.update_layout(
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        )
        rapikan(fig_line, 360)
        st.plotly_chart(fig_line, config={"displayModeBar": False}, key="chart_omzet")
