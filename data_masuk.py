"""Halaman Data Masuk & Unduh (peran: bos)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import auth
import store
import tema


def _tabel(df: pd.DataFrame, tinggi: int = 300):
    st.dataframe(df, hide_index=True, height=tinggi)


def _tab_baru():
    log = store.baca(store.LOG_NAMA)
    if log.empty:
        st.info("Belum ada data yang masuk lewat aplikasi. Data yang diinput pegawai akan muncul di sini.")
        return

    aktif = log[log["status"] == "Aktif"]
    tema.tiles([
        ("Input aktif", store.angka(aktif["id_aksi"].nunique()), "aksi simpan"),
        ("Baris data baru", store.angka(len(aktif)), "di semua file CSV"),
        ("Petugas", store.angka(aktif["petugas"].nunique()), ", ".join(sorted(aktif["petugas"].unique())) or "-"),
        ("Dibatalkan", store.angka(log.loc[log["status"] == "Dibatalkan", "id_aksi"].nunique()), "aksi dibatalkan petugas"),
        ("Input terakhir", aktif["waktu_input"].max()[11:16] if not aktif.empty else "-",
         aktif["waktu_input"].max()[:10] if not aktif.empty else ""),
    ])

    with st.container(key="card_aktivitas"):
        tema.judul_kartu("Aktivitas Input", "Urut dari yang terbaru. Sumber: <b>log_input.csv</b>.")
        f1, f2, f3 = st.columns([2, 2, 1])
        petugas = f1.multiselect("Petugas", sorted(log["petugas"].unique()), default=sorted(log["petugas"].unique()))
        tabel = f2.multiselect("Tabel", [n for n in store.URUTAN_FILE if n in set(log["tabel"])],
                               default=[n for n in store.URUTAN_FILE if n in set(log["tabel"])])
        dibatalkan = f3.checkbox("Tampilkan yang dibatalkan", value=False)

        v = log[log["petugas"].isin(petugas) & log["tabel"].isin(tabel)]
        if not dibatalkan:
            v = v[v["status"] == "Aktif"]
        v = v.sort_values(["waktu_input", "id_record"], ascending=False)
        if v.empty:
            st.info("Tidak ada aktivitas untuk filter ini.")
        else:
            _tabel(v[["waktu_input", "petugas", "tabel", "id_record", "ringkasan", "status"]], 340)

    with st.container(key="card_isibaru"):
        tema.judul_kartu("Isi Data Baru per Tabel", "Hanya baris yang masuk lewat aplikasi (bukan data awal).")
        ada = [n for n in store.URUTAN_FILE if n in set(aktif["tabel"])]
        if not ada:
            st.info("Belum ada baris aktif.")
        else:
            for tab, nama in zip(st.tabs([f"{n} ({(aktif['tabel'] == n).sum()})" for n in ada]), ada):
                with tab:
                    _tabel(store.baris_baru(nama), 300)


def _tab_unduh():
    files = store.daftar_file()
    with st.container(key="card_unduh"):
        tema.judul_kartu(
            "Unduh CSV",
            "File yang diunduh adalah kondisi terbaru (data awal + input aplikasi). "
            "Simpan salinannya secara berkala — penyimpanan server bersifat sementara.",
        )
        if not files:
            st.info("Belum ada file CSV.")
            return

        st.download_button("⬇️ Unduh semua (ZIP)", data=store.zip_semua(), file_name="ayce_data.zip",
                           mime="application/zip", type="primary", key="dl_zip")
        st.write("")
        h1, h2, h3, h4 = st.columns([3, 1, 1, 2])
        h1.markdown("**File**")
        h2.markdown("**Baris**")
        h3.markdown("**Ukuran**")
        for nama, p in files:
            c1, c2, c3, c4 = st.columns([3, 1, 1, 2])
            n_baris = len(store.baca(nama))
            c1.markdown(f"`{nama}.csv`")
            c2.write(store.angka(n_baris))
            c3.write(f"{p.stat().st_size / 1024:,.0f} KB")
            c4.download_button("Unduh", data=p.read_bytes(), file_name=f"{nama}.csv", mime="text/csv", key=f"dl_{nama}")

    with st.container(key="card_pratinjau"):
        tema.judul_kartu("Pratinjau Isi File", "Menampilkan 200 baris terakhir.")
        pilih = st.selectbox("File", [n for n, _ in files], key="pratinjau_file")
        df = store.baca(pilih)
        st.caption(f"{store.angka(len(df))} baris total")
        _tabel(df.tail(200).iloc[::-1], 340)


def halaman_data_masuk():
    auth.wajib("bos")
    tema.header("Data Masuk & Unduh", "Data Masuk & Unduh CSV")
    if st.button("🔄 Muat ulang", key="btn_muat_ulang"):
        st.rerun()
    tab1, tab2 = st.tabs(["🆕 Data Baru Masuk", "⬇️ Unduh CSV"])
    with tab1:
        _tab_baru()
    with tab2:
        _tab_unduh()
