"""
Halaman Dashboard — Plotly.

Sumber data (dicari berurutan):
  1. data/<nama>.csv
  2. <nama>.csv (sejajar dengan app.py)
  3. tabel <nama> di ayce.db (cadangan)
Tabel yang dipakai: transaksi, reservasi, paket, (opsional) meja.
Cache otomatis diperbarui saat ada input baru (kunci cache = waktu ubah file).
"""

import sqlite3
from datetime import timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import store
import tema
from tema import ABU, INDIGO, ORANYE, ORANYE_MUDA, ORANYE_PUDAR, TEKS

BASE_DIR = Path(__file__).parent
BATAS_SHIFT_JAM = 15  # Pagi: mulai sebelum 15:00 | Malam: mulai 15:00 ke atas
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
FONT = dict(family="Plus Jakarta Sans, sans-serif", color="#5B6475", size=12)


# ---------------------------------------------------------------------------
# Helper format
# ---------------------------------------------------------------------------
def angka(v) -> str:
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


# ---------------------------------------------------------------------------
# Load data
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
def muat_data(versi):  # `versi` = penanda perubahan file -> cache dibuang otomatis saat ada input baru
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


# ---------------------------------------------------------------------------
# Halaman
# ---------------------------------------------------------------------------
def halaman_dashboard():
    try:
        trx, paket, total_meja = muat_data(store.versi_data())
    except FileNotFoundError as e:
        st.error(
            f"Tabel yang diperlukan tidak ditemukan: **{e}**. "
            "Pastikan folder `data/` (berisi file CSV) atau `ayce.db` berada di repo yang sama dengan `app.py`."
        )
        st.stop()

    if trx.empty:
        st.warning("Belum ada transaksi di transaksi.csv.")
        st.stop()

    DMIN = trx["tanggal"].min().date()
    DMAX = trx["tanggal"].max().date()

    # ---- Filter sidebar ----
    with st.sidebar:
        st.markdown('<div class="side-title">Filter</div>', unsafe_allow_html=True)
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
            f"Data {fmt_tgl(DMIN, True)} – {fmt_tgl(DMAX, True)} (termasuk input dari aplikasi).</div></div>",
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

    # ---- Filter data ----
    dasar = trx[trx["tipe"].isin(tipe_pilihan)]  # sudah terfilter tipe kedatangan (belum tanggal)
    cur = dasar[(dasar["tanggal"] >= pd.Timestamp(mulai)) & (dasar["tanggal"] <= pd.Timestamp(akhir))]

    label_tipe = " + ".join(tipe_pilihan) if tipe_pilihan else "—"
    tema.header(
        "Dashboard",
        "Dashboard Restoran AYCE",
        f"📅 {fmt_tgl(mulai, True)} – {fmt_tgl(akhir, True)} &nbsp;·&nbsp; {label_tipe}",
    )

    if cur.empty:
        st.warning(
            "Tidak ada transaksi untuk filter yang dipilih. "
            "Coba ubah rentang tanggal atau pilih minimal satu Tipe Kedatangan."
        )
        st.stop()

    # ---- KPI + perbandingan dengan periode sebelumnya ----
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

    col_bar, col_line = st.columns([2, 3], gap="medium")

    # ---- Bar chart: Paket Paling Favorit ----
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
            fig_bar.add_bar(  # "track" di belakang batang (gaya referensi)
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

    # ---- Line chart: omzet per shift ----
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
