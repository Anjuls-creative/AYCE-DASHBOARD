"""
data_masuk.py — HALAMAN BOS: melihat data yang baru masuk + mengunduh CSV (bisa per tanggal).

╔══════════════════════ PETA UBAH CEPAT ═══════════════════════╗
║ Mau ubah ...                       → cari bagian ...          ║
║ • Siapa boleh membuka halaman      → auth.wajib("bos") di     ║
║                                      halaman_data_masuk()     ║
║ • Kotak ringkasan di atas          → _tab_baru() → tema.tiles ║
║ • Kolom tabel aktivitas            → _tab_baru() → v[[...]]   ║
║ • Filter tanggal unduhan           → _pilih_tanggal()         ║
║ • Daftar file yang bisa diunduh    → store.URUTAN_FILE        ║
║ • File mana yang ikut difilter     → store.TABEL_BERTANGGAL   ║
║   per tanggal                                                 ║
║ • Jumlah baris pratinjau (200)     → _tab_unduh() → .tail(200)║
╚═══════════════════════════════════════════════════════════════╝
Cari kata "UBAH:" untuk menemukan nilai yang biasa Anda ganti.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import auth
import store
import tema


def _tabel(df: pd.DataFrame, tinggi: int = 300):
    st.dataframe(df, hide_index=True, height=tinggi)


# ===========================================================================
# TAB 1 — DATA BARU MASUK (dari log_input.csv) + PESANAN BERJALAN
# ===========================================================================
def _kartu_berjalan():
    """Pesanan yang sedang makan / menunggu bayar (belum masuk CSV laporan)."""
    pend = store.daftar_pesanan_berjalan()
    paket = store.baca("paket")
    durasi = dict(zip(paket["id_paket"], pd.to_numeric(paket["durasi_menit"], errors="coerce").fillna(90).astype(int)))
    nama_paket = dict(zip(paket["id_paket"], paket["nama_paket"]))
    with st.container(key="card_berjalan"):
        tema.judul_kartu("Pesanan Sedang Berjalan", "Belum dibayar, jadi belum masuk CSV laporan. Hanya untuk dilihat.")
        if pend.empty:
            st.info("Tidak ada pesanan yang sedang berjalan.")
            return
        now = store.sekarang()
        baris = []
        for _, r in pend.iterrows():
            sisa = store.sisa_detik(r, durasi.get(r["id_paket"], 90), now)
            baris.append({
                "ID": r["id_pesanan"], "Nama": r["nama_pemesan"],
                "Tipe": "Reservasi" if r["tipe_kedatangan"] == "Booking" else r["tipe_kedatangan"],
                "Orang": r["jumlah_orang"], "Paket": nama_paket.get(r["id_paket"], r["id_paket"]), "Meja": r["id_meja"],
                "Mulai": r["mulai_ts"][11:16], "Status": r["status"],
                "Sisa waktu": ("OVERTIME " if sisa < 0 else "") + f"{abs(sisa) // 60} menit" if r["status"] == "Makan" else "—",
                "Petugas": r["petugas"],
            })
        _tabel(pd.DataFrame(baris), 38 + 35 * min(len(baris), 8))


def _kartu_online():
    """Reservasi dari akun pelanggan (hanya dilihat). Konfirmasi kedatangan dilakukan pegawai di halaman Input Pesanan."""
    ol = store.daftar_reservasi_online()
    paket = store.baca("paket")
    nama_paket = dict(zip(paket["id_paket"], paket["nama_paket"]))
    with st.container(key="card_online"):
        tema.judul_kartu("Reservasi Online", "Reservasi dari akun pelanggan (100 terbaru). Hanya untuk dilihat.")
        if ol.empty:
            st.info("Belum ada reservasi online dari pelanggan.")
            return
        tampil = ol.sort_values(["tanggal", "jam"], ascending=False).head(100)
        baris = [{
            "ID": r["id_online"], "Nama": r["nama_pemesan"], "Akun": r["akun"], "Tanggal": r["tanggal"], "Jam": r["jam"],
            "Orang": r["jumlah_orang"], "Paket": nama_paket.get(r["id_paket"], r["id_paket"]), "Meja": r["id_meja"],
            "Diinput": r["dibuat_ts"][:16], "Status": r["status"],
        } for _, r in tampil.iterrows()]
        _tabel(pd.DataFrame(baris), 38 + 35 * min(len(baris), 8))


def _tab_baru():
    _kartu_berjalan()
    _kartu_online()
    log = store.baca(store.LOG_NAMA)
    if log.empty:
        st.info("Belum ada data yang masuk ke CSV lewat aplikasi. Data muncul di sini setelah pegawai menyelesaikan pembayaran.")
        return

    aktif = log[log["status"] == "Aktif"]
    # UBAH: kotak ringkasan di bagian atas
    tema.tiles([
        ("Input aktif", store.angka(aktif["id_aksi"].nunique()), "kali simpan"),
        ("Baris data baru", store.angka(len(aktif)), "di semua file CSV"),
        ("Petugas", store.angka(aktif["petugas"].nunique()), ", ".join(sorted(aktif["petugas"].unique())) or "-"),
        ("Dibatalkan", store.angka(log.loc[log["status"] == "Dibatalkan", "id_aksi"].nunique()), "input dibatalkan petugas"),
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
            _tabel(v[["waktu_input", "petugas", "tabel", "id_record", "ringkasan", "status"]], 340)  # UBAH: kolom yang tampil

    with st.container(key="card_isibaru"):
        tema.judul_kartu("Isi Data Baru per Tabel", "Hanya baris yang masuk lewat aplikasi (bukan data awal).")
        ada = [n for n in store.URUTAN_FILE if n in set(aktif["tabel"])]
        if not ada:
            st.info("Belum ada baris aktif.")
        else:
            for tab, nama in zip(st.tabs([f"{n} ({(aktif['tabel'] == n).sum()})" for n in ada]), ada):
                with tab:
                    _tabel(store.baris_baru(nama), 300)


# ===========================================================================
# TAB 2 — UNDUH CSV (semua tanggal / satu tanggal / rentang) + PRATINJAU + DIAGNOSTIK
# ===========================================================================
def _pilih_tanggal():
    """
    Filter tanggal unduhan. Mengembalikan (mulai, akhir) atau (None, None) = semua tanggal.
    Satu tanggal → mulai = akhir. UBAH: pilihan mode & bawaan tanggal ada di bawah.
    """
    awal_min, akhir_max = store.batas_tanggal()   # bisa dipilih sampai hari ini, walau tanggalnya belum ada datanya
    data_awal, data_akhir = store.rentang_data()
    mode = st.radio("Cakupan tanggal", ["Semua tanggal", "Satu tanggal", "Rentang tanggal"], horizontal=True, key="unduh_mode")
    if mode == "Satu tanggal":
        d = st.date_input("Tanggal", value=data_akhir, min_value=awal_min, max_value=akhir_max,
                          format="DD/MM/YYYY", key="unduh_tgl")
        if isinstance(d, (tuple, list)):
            d = d[0] if d else data_akhir
        return d, d
    if mode == "Rentang tanggal":
        r = st.date_input("Dari tanggal – sampai tanggal", value=(data_awal, data_akhir), min_value=awal_min,
                          max_value=akhir_max, format="DD/MM/YYYY", key="unduh_rentang",
                          help="Klik tanggal awal lalu tanggal akhir. Jika baru satu tanggal yang dipilih, dipakai sebagai satu tanggal.")
        if isinstance(r, (tuple, list)):
            if len(r) == 2:
                return r[0], r[1]
            if len(r) == 1:
                st.caption("Baru satu tanggal dipilih — sementara dipakai sebagai satu tanggal. Klik tanggal akhir untuk rentang.")
                return r[0], r[0]
            return None, None
        return r, r
    return None, None


def _label_rentang(mulai, akhir) -> str:
    if mulai is None:
        return ""
    return f"_{mulai.isoformat()}" if mulai == akhir else f"_{mulai.isoformat()}_sd_{akhir.isoformat()}"


def _tab_unduh():
    files = store.daftar_file()
    with st.container(key="card_unduh"):
        tema.judul_kartu(
            "Unduh CSV",
            "Pilih semua tanggal, satu tanggal, atau rentang tanggal. File master (meja, menu, paket, topping, minuman, harga) "
            "tidak punya tanggal sehingga selalu lengkap. Simpan salinannya berkala — penyimpanan server bersifat sementara.",
        )
        if not files:
            st.info("Belum ada file CSV.")
            return
        mulai, akhir = _pilih_tanggal()
        sufiks = _label_rentang(mulai, akhir)
        if mulai is not None:
            st.caption(f"Yang diunduh: data tanggal {mulai:%d/%m/%Y}" + ("" if mulai == akhir else f" sampai {akhir:%d/%m/%Y}") + ".")

        st.download_button("⬇️ Unduh semua (ZIP)", data=store.zip_semua(mulai, akhir), file_name=f"ayce_data{sufiks}.zip",
                           mime="application/zip", type="primary", key="dl_zip")
        st.write("")
        h1, h2, h3, h4 = st.columns([3, 1, 1, 2])
        h1.markdown("**File**")
        h2.markdown("**Baris**")
        h3.markdown("**Ukuran**")
        for nama in files:
            c1, c2, c3, c4 = st.columns([3, 1, 1, 2])
            data = store.bytes_csv(nama, mulai, akhir)
            n_baris = len(store.baca_rentang(nama, mulai, akhir))
            c1.markdown(f"`{nama}.csv`")
            c2.write(store.angka(n_baris))
            c3.write(f"{len(data) / 1024:,.0f} KB")
            c4.download_button("Unduh", data=data, file_name=f"{nama}{sufiks if nama in store.TABEL_BERTANGGAL else ''}.csv",
                               mime="text/csv", key=f"dl_{nama}", disabled=(n_baris == 0))

    with st.container(key="card_pratinjau"):
        tema.judul_kartu("Pratinjau Isi File", "Mengikuti filter tanggal di atas. Menampilkan 200 baris terakhir.")  # UBAH: angka 200 juga ada di .tail(200)
        pilih = st.selectbox("File", files, key="pratinjau_file")
        df = store.baca_rentang(pilih, mulai, akhir)
        st.caption(f"{store.angka(len(df))} baris")
        _tabel(df.tail(200).iloc[::-1], 340)

    with st.expander("🔧 Diagnostik lokasi data (untuk melacak masalah data hilang)"):
        st.caption(
            "Menunjukkan dari file mana tiap tabel dibaca. Dashboard, input, dan unduhan semuanya memakai "
            "lokasi yang sama. Jika jumlah baris tidak sesuai harapan, kirim tabel ini ke pembuat aplikasi."
        )
        _tabel(pd.DataFrame(store.info_sumber()), 460)
        st.caption(f"Folder data aktif: `{store.DATA_DIR}`")


# ===========================================================================
# HALAMAN
# ===========================================================================
def halaman_data_masuk():
    auth.wajib("bos")  # UBAH: ganti/tambah peran yang boleh membuka halaman ini
    tema.header("Data Masuk & Unduh", "Data Masuk & Unduh CSV")  # UBAH: judul halaman
    if st.button("🔄 Muat ulang", key="btn_muat_ulang"):
        st.rerun()
    tab1, tab2 = st.tabs(["🆕 Data Baru Masuk", "⬇️ Unduh CSV"])
    with tab1:
        _tab_baru()
    with tab2:
        _tab_unduh()
