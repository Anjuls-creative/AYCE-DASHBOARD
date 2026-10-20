"""
input_data.py — HALAMAN INPUT PESANAN (peran: pegawai). Ditulis ulang total.

Urutan form (dari atas ke bawah):
  1. Data pemesan    : nama pemesan → Walk-in / Reservasi → jumlah orang
  ⚙  Opsi lanjutan   : waktu manual, status kedatangan, meja, anak/lansia/balita, metode bayar (boleh diabaikan)
  2. Pilih paket     : Reguler / Premium / Supreme (menampilkan batas durasi makan & harga per orang)
  3. Pilih topping   : jumlah porsi tiap topping (menampilkan harga)
  4. Rincian harga   : harga paket + topping + TOTAL, lalu tombol Simpan
Saat disimpan, data langsung masuk ke CSV (lihat store.simpan_pesanan).

╔══════════════════════ PETA UBAH CEPAT ═══════════════════════╗
║ Mau ubah ...                       → cari bagian ...          ║
║ • Jam buka / tutup / last order    → JAM_BUKA, JAM_TUTUP,     ║
║   (peringatan di form)               LAST_ORDER (di bawah)    ║
║ • Daftar & harga topping           → file data/topping.csv    ║
║ • Daftar paket, durasi, harga      → data/paket.csv &         ║
║                                      data/harga_paket.csv     ║
║ • Teks/judul di form               → cari tema.judul_kartu(   ║
║ • Batas jumlah orang (maks 40)     → number_input "Jumlah orang"║
║ • Pilihan metode pembayaran        → store.METODE             ║
║ • Aturan harga/overtime/diskon     → store.py (ATURAN BISNIS) ║
╚═══════════════════════════════════════════════════════════════╝
Cari kata "UBAH:" untuk menemukan nilai yang biasa Anda ganti.
"""

from __future__ import annotations

from datetime import time
from html import escape

import pandas as pd
import streamlit as st

import auth
import store
import tema

# UBAH: jam operasional (menit sejak 00:00). Hanya untuk PERINGATAN di form, tidak memblokir penyimpanan.
JAM_BUKA = 11 * 60
JAM_TUTUP = 22 * 60
LAST_ORDER = 20 * 60 + 30  # pelanggan Walk-in baru setelah jam ini → muncul peringatan

OTOMATIS = "Otomatis (meja kosong yang paling pas)"
URUTAN_HARGA = ["Lunch Weekday", "Lunch Weekend", "Dinner Weekday", "Dinner Weekend"]


# ===========================================================================
# HELPER TAMPILAN
# ===========================================================================
def _ver(nama: str) -> int:
    return st.session_state.setdefault(f"ver_{nama}", 0)


def _naik(nama: str):
    """Naikkan versi form → semua kolom isian memakai key baru → form kembali kosong setelah simpan."""
    st.session_state[f"ver_{nama}"] = _ver(nama) + 1


def _flash(jenis: str, pesan: str):
    """Simpan pesan agar tampil di atas halaman pada run berikutnya (setelah st.rerun)."""
    st.session_state["flash"] = (jenis, pesan)


def _tampilkan_flash():
    f = st.session_state.pop("flash", None)
    if not f:
        return
    {"success": st.success, "warning": st.warning}.get(f[0], st.info)(f[1])


def _tabel(df: pd.DataFrame, tinggi: int = 260):
    st.dataframe(df, hide_index=True, height=tinggi)


def _label_kategori(kat: str) -> str:
    """UBAH: nama kategori pelanggan yang tampil di rincian harga."""
    nama = {"Adult": "Dewasa", "Child": "Anak-anak", "Senior": "Lansia", "Toddler": "Balita"}[kat]
    p = store.PERSEN[kat]
    return nama if p == 100 else f"{nama} (gratis)" if p == 0 else f"{nama} ({p}%)"


def _tabel_harga_lengkap(paket: pd.DataFrame, harga: pd.DataFrame) -> pd.DataFrame:
    """Pivot daftar harga: baris = paket, kolom = Lunch/Dinner × Weekday/Weekend."""
    h = harga.merge(paket[["id_paket", "nama_paket"]], on="id_paket")
    h["kolom"] = h["waktu"] + " " + h["hari"]
    h["harga"] = pd.to_numeric(h["harga"], errors="coerce").fillna(0).map(store.rp)
    p = h.pivot_table(index="nama_paket", columns="kolom", values="harga", aggfunc="first")
    p = p.reindex(index=paket["nama_paket"].tolist(), columns=[c for c in URUTAN_HARGA if c in p.columns])
    p.index.name = "Paket (harga per orang dewasa)"
    return p.reset_index().fillna("-")


def _tabel_hari_ini(tgl) -> pd.DataFrame:
    """Daftar transaksi satu tanggal (digabung dengan nama pemesan & nama paket)."""
    trx, res, pak = store.baca("transaksi"), store.baca("reservasi"), store.baca("paket")
    t = trx[trx["tanggal"] == tgl.isoformat()]
    t = t.merge(res[["id_reservasi", "nama_pemesan", "tipe_kedatangan"]].drop_duplicates("id_reservasi"), on="id_reservasi", how="left")
    t = t.merge(pak[["id_paket", "nama_paket"]], on="id_paket", how="left").sort_values("waktu_mulai", ascending=False)
    for kolom in ("subtotal_paket", "subtotal_topping", "total_bayar"):
        t[kolom] = pd.to_numeric(t[kolom], errors="coerce").fillna(0).map(store.rp)
    out = t[["waktu_mulai", "nama_pemesan", "tipe_kedatangan", "jumlah_orang", "nama_paket", "id_meja",
             "subtotal_paket", "subtotal_topping", "total_bayar"]]
    return out.rename(columns={
        "waktu_mulai": "Jam", "nama_pemesan": "Nama", "tipe_kedatangan": "Tipe", "jumlah_orang": "Orang",
        "nama_paket": "Paket", "id_meja": "Meja", "subtotal_paket": "Paket (Rp)",
        "subtotal_topping": "Topping (Rp)", "total_bayar": "Total",
    })


# ===========================================================================
# FORM PESANAN BARU
# ===========================================================================
def _form_pesanan(user):
    v = _ver("pesan")
    k = lambda n: f"p_{n}_{v}"  # noqa: E731  (key unik per versi form, supaya bisa dikosongkan setelah simpan)
    now = store.sekarang()

    paket, harga = store.baca("paket"), store.baca("harga_paket")
    topping, meja = store.baca("topping"), store.baca("meja")
    if paket.empty or meja.empty:
        st.error("paket.csv atau meja.csv masih kosong — isi dulu datanya.")
        return

    # -----------------------------------------------------------------------
    # 1 · DATA PEMESAN  (nama → tipe → jumlah orang)
    # -----------------------------------------------------------------------
    with st.container(key="card_pemesan"):
        tema.judul_kartu("1 · Data Pemesan", "Isi nama pemesan, tipe kedatangan, dan jumlah orang.")
        nama = st.text_input("Nama pemesan", max_chars=60, placeholder="Contoh: Budi Santoso", key=k("nama"))
        c1, c2 = st.columns(2)
        tipe_label = c1.radio("Tipe kedatangan", list(store.TIPE_LABEL), horizontal=True, key=k("tipe"))
        jumlah = int(c2.number_input("Jumlah orang", min_value=1, max_value=40, value=2, step=1, key=k("jml")))  # UBAH: maks 40
    tipe = store.TIPE_LABEL[tipe_label]  # "Reservasi" di layar → "Booking" di CSV

    # -----------------------------------------------------------------------
    # ⚙ OPSI LANJUTAN (semua punya nilai otomatis; buka hanya bila perlu)
    # -----------------------------------------------------------------------
    with st.expander("⚙️ Opsi lanjutan — waktu, status, meja, anak/lansia/balita, pembayaran"):
        manual = st.checkbox("Atur tanggal & jam sendiri (jika tidak dicentang, memakai waktu sekarang)", key=k("manual"))
        if manual:
            ca, cb = st.columns(2)
            tanggal = ca.date_input("Tanggal", value=now.date(), max_value=now.date(), format="DD/MM/YYYY", key=k("tgl"))
            jam = cb.time_input("Jam", value=time(now.hour, now.minute), step=300, key=k("jam"))
        else:
            tanggal, jam = now.date(), time(now.hour, now.minute)

        if tipe == "Booking":
            status = st.selectbox(
                "Status kedatangan", store.STATUS, key=k("status"),
                help="Completed = tamu datang & makan. Cancelled / No-show hanya dicatat di reservasi (tanpa paket & topping).",
            )
        else:
            status = "Completed"
            st.caption("Walk-in selalu berstatus Completed.")

        opsi_meja = store.meja_cocok(jumlah, meja)
        label_meja = {OTOMATIS: OTOMATIS}
        for _, r in opsi_meja.iterrows():
            label_meja[r["id_meja"]] = f"{r['id_meja']} · {r['kapasitas']} orang · {r['area']} · Lantai {r['lantai']}"
        meja_pilih = st.selectbox("Meja", list(label_meja), format_func=label_meja.get, key=k(f"meja_{jumlah}"))

        st.markdown("**Komposisi usia** — biarkan 0 jika semuanya dewasa")
        a1, a2, a3 = st.columns(3)
        anak = int(a1.number_input(f"Anak-anak ({store.PERSEN['Child']}%)", 0, 40, 0, 1, key=k("anak")))
        lansia = int(a2.number_input(f"Lansia ({store.PERSEN['Senior']}%)", 0, 40, 0, 1, key=k("lansia")))
        balita = int(a3.number_input("Balita (gratis)", 0, 40, 0, 1, key=k("balita")))
        metode = st.selectbox("Metode pembayaran", store.METODE, key=k("metode"))

    tambahan = {"Child": anak, "Senior": lansia, "Toddler": balita}
    try:
        kom = store.komposisi(jumlah, tambahan)
    except store.DataError as e:
        st.error(str(e))
        return

    mulai = store.ke_menit(jam)
    id_meja_pilih = None if meja_pilih == OTOMATIS else meja_pilih

    # peringatan jam (tidak memblokir)
    if not (JAM_BUKA <= mulai <= JAM_TUTUP):
        st.warning("Jam di luar jam operasional (11:00–22:00).")
    elif mulai > LAST_ORDER and tipe == "Walk-in":
        st.warning("Lewat batas last order / pelanggan baru terakhir (20:30).")

    # -----------------------------------------------------------------------
    # Status BUKAN Completed → cukup catat reservasi (tanpa paket/topping)
    # -----------------------------------------------------------------------
    if status != "Completed":
        with st.container(key="card_reservasi_saja"):
            tema.judul_kartu("Catat Reservasi", f"Status <b>{status}</b>: hanya disimpan ke reservasi.csv (paket & topping tidak dicatat).")
            nid = store.id_berikut(store.baca("reservasi"), "id_reservasi", "RS", 4)[0]
            st.caption(f"Akan disimpan sebagai **{nid}** · {tanggal:%d/%m/%Y} {jam:%H:%M}")
            if st.button("💾 Simpan Reservasi", type="primary", key=k("simpan_res")):
                try:
                    rid = store.simpan_reservasi_saja(user["username"], tanggal, jam, nama, tipe, jumlah, status, id_meja_pilih)
                except store.DataError as e:
                    st.error(str(e))
                else:
                    _flash("success", f"Tersimpan: **{rid}** · {status} · {nama.strip()} · {jumlah} orang.")
                    _naik("pesan")
                    st.rerun()
        return

    # -----------------------------------------------------------------------
    # 2 · PILIH PAKET  (menampilkan batas durasi makan + harga per orang)
    # -----------------------------------------------------------------------
    waktu, hari = store.konteks_harga(tanggal, mulai)
    with st.container(key="card_paket"):
        tema.judul_kartu(
            "2 · Pilih Paket",
            f"Harga per orang dewasa · berlaku <b>{waktu}</b> · <b>{hari}</b> ({tanggal:%d/%m/%Y} {jam:%H:%M})",
        )
        label_paket = {}
        for _, p in paket.iterrows():
            hp = store.harga_paket_per_orang(p["id_paket"], waktu, hari, harga)
            label_paket[p["id_paket"]] = (
                f"{p['nama_paket']} · batas makan {p['durasi_menit']} menit · "
                + (f"{store.rp(hp[1])}/orang" if hp else "harga belum ada")
            )
        id_paket = st.radio("Paket", paket["id_paket"].tolist(), format_func=label_paket.get,
                            key=k("paket"), label_visibility="collapsed")
        pp = paket[paket["id_paket"] == id_paket].iloc[0]
        durasi = int(pp["durasi_menit"])
        st.caption(
            f"⏱️ Batas waktu makan paket **{pp['nama_paket']}**: **{durasi} menit** "
            f"(sampai {store.dari_menit(min(mulai + durasi, 24 * 60 - 1))}). "
            f"Melewati batas dikenakan {store.rp(store.TARIF_OT)} per {store.BLOK_OT} menit."
        )
        with st.expander("Lihat daftar harga paket lengkap"):
            _tabel(_tabel_harga_lengkap(paket, harga), tinggi=38 + 35 * len(paket))

    # -----------------------------------------------------------------------
    # 3 · PILIH TOPPING  (daftar & harga dari topping.csv)
    # -----------------------------------------------------------------------
    qty: dict[str, int] = {}
    with st.container(key="card_topping"):
        tema.judul_kartu("3 · Pilih Topping", "Isi jumlah porsi tiap topping. Biarkan 0 jika tidak mau.")
        if topping.empty:
            st.info("Belum ada topping di topping.csv.")
        else:
            kolom = st.columns(3)  # UBAH: jumlah kolom daftar topping
            for i, (_, t) in enumerate(topping.iterrows()):
                tersedia = t["status"] == "Tersedia"
                habis = "" if tersedia else ' · <span class="top-habis">Habis</span>'
                with kolom[i % 3]:
                    st.markdown(
                        f'<div class="top-name">{escape(t["nama_topping"])}</div>'
                        f'<div class="top-price">{store.rp(t["harga"])} / porsi{habis}</div>',
                        unsafe_allow_html=True,
                    )
                    qty[t["id_topping"]] = int(st.number_input(
                        t["nama_topping"], 0, 99, 0, 1, key=k(f"top_{t['id_topping']}"),
                        label_visibility="collapsed", disabled=not tersedia,
                    ))

    # -----------------------------------------------------------------------
    # 4 · RINCIAN HARGA + SIMPAN
    # -----------------------------------------------------------------------
    try:
        h = store.hitung_pesanan(tanggal, mulai, id_paket, kom, qty, paket, harga, topping)
    except store.DataError as e:
        st.error(str(e))
        return

    bisa_simpan = True
    with st.container(key="card_harga"):
        tema.judul_kartu("4 · Rincian Harga", "Semua harga yang akan dicatat untuk pesanan ini.")
        baris = [
            {"Item": f"Paket {h['nama_paket']} — {_label_kategori(x['kategori'])}", "Jumlah": x["jumlah"],
             "Harga": store.rp(x["satuan"]), "Subtotal": store.rp(x["subtotal"])}
            for x in h["rincian"]
        ] + [
            {"Item": f"Topping — {x['nama']}", "Jumlah": x["jumlah"],
             "Harga": store.rp(x["satuan"]), "Subtotal": store.rp(x["subtotal"])}
            for x in h["topping"]
        ]
        _tabel(pd.DataFrame(baris), tinggi=38 + 35 * len(baris))
        tema.tiles([
            ("Subtotal paket", store.rp(h["subtotal_paket"]), f"{h['nama_paket']} · {h['waktu']} · {h['hari']}"),
            ("Subtotal topping", store.rp(h["subtotal_topping"]),
             f"{sum(x['jumlah'] for x in h['topping'])} porsi" if h["topping"] else "tanpa topping"),
            ("TOTAL BAYAR", store.rp(h["total"]), f"{h['jumlah_orang']} orang"),
            ("Batas makan", f"{h['durasi_paket']} menit", f"sampai {store.dari_menit(h['selesai'])}"),
        ])
        st.caption("Belum termasuk overtime dan denda food waste (dihitung setelah selesai makan).")

        trx = store.baca("transaksi")
        if id_meja_pilih is None:
            id_meja_tampil = store.pilih_meja_otomatis(tanggal, mulai, h["selesai"], jumlah, trx, meja)
            if id_meja_tampil is None:
                bisa_simpan = False
                st.error(f"Tidak ada meja kosong untuk {jumlah} orang pada jam {store.dari_menit(mulai)}. "
                         "Pilih meja manual di Opsi lanjutan atau ubah jam.")
        else:
            id_meja_tampil = id_meja_pilih
            for _, o in trx[(trx["tanggal"] == tanggal.isoformat()) & (trx["id_meja"] == id_meja_pilih)].iterrows():
                if mulai < store.ke_menit(o["waktu_selesai"]) and h["selesai"] > store.ke_menit(o["waktu_mulai"]):
                    st.warning(f"Meja {id_meja_pilih} bentrok dengan {o['id_transaksi']} ({o['waktu_mulai']}–{o['waktu_selesai']}).")

        if id_meja_tampil:
            rid_next = store.id_berikut(store.baca("reservasi"), "id_reservasi", "RS", 4)[0]
            tid_next = store.id_berikut(trx, "id_transaksi", "TRX", 4)[0]
            st.caption(f"Akan disimpan sebagai **{rid_next}** / **{tid_next}** · meja **{id_meja_tampil}** · "
                       f"{tanggal:%d/%m/%Y} {jam:%H:%M}")

        if st.button("💾 Simpan Pesanan", type="primary", key=k("simpan"), disabled=not bisa_simpan):
            try:
                out = store.simpan_pesanan(
                    petugas=user["username"], tanggal=tanggal, jam=jam, nama=nama, tipe=tipe, jumlah=jumlah,
                    id_paket=id_paket, topping_qty=qty, tambahan_kom=tambahan, metode=metode, id_meja=id_meja_pilih,
                )
            except store.DataError as e:
                st.error(str(e))
            else:
                _flash("success",
                       f"Tersimpan: **{out['id_transaksi']}** ({out['id_reservasi']}) · {nama.strip()} · {jumlah} orang · "
                       f"{h['nama_paket']} · {out['n_topping']} jenis topping · meja {out['id_meja']} · "
                       f"total {store.rp(out['total'])}.")
                _naik("pesan")
                st.rerun()


# ===========================================================================
# RIWAYAT SAYA + BATALKAN INPUT TERAKHIR
# ===========================================================================
def _tab_riwayat(user):
    with st.container(key="card_riwayat"):
        tema.judul_kartu("Riwayat Input Saya", "Semua input tercatat di <b>log_input.csv</b> (bisa dilihat bos).")
        akhir = store.aksi_terakhir(user["username"])
        if not akhir:
            st.info("Belum ada input aktif dari akun ini.")
        else:
            st.markdown(f"**Input terakhir** · {akhir[0]['id_aksi']} · {akhir[0]['waktu_input']}")
            _tabel(pd.DataFrame(akhir)[["tabel", "id_record", "ringkasan"]], tinggi=38 + 35 * min(len(akhir), 6))

            if not st.session_state.get("konfirmasi_batal"):
                if st.button("↩️ Batalkan input terakhir", key="btn_batal"):
                    st.session_state["konfirmasi_batal"] = True
                    st.rerun()
            else:
                st.warning("Data di atas akan dihapus dari CSV. Lanjutkan?")
                y, n = st.columns(2)
                if y.button("Ya, batalkan", type="primary", key="btn_batal_ya"):
                    st.session_state["konfirmasi_batal"] = False
                    try:
                        rows = store.batalkan_aksi_terakhir(user["username"])
                    except store.DataError as e:
                        st.error(str(e))
                    else:
                        _flash("success", f"Dibatalkan: {', '.join(r['id_record'] for r in rows)}.")
                        st.rerun()
                if n.button("Tidak", key="btn_batal_tidak"):
                    st.session_state["konfirmasi_batal"] = False
                    st.rerun()

        log = store.baca(store.LOG_NAMA)
        mine = log[log["petugas"] == user["username"]].sort_values(["waktu_input", "id_record"], ascending=False).head(60)
        if not mine.empty:
            st.markdown("**60 input terakhir**")
            _tabel(mine[["waktu_input", "tabel", "id_record", "ringkasan", "status"]], 320)


# ===========================================================================
# HALAMAN
# ===========================================================================
def halaman_input():
    user = auth.wajib("pegawai")  # UBAH: ganti/tambah peran yang boleh membuka halaman ini
    tema.header("Input Pesanan", "Input Pesanan Pelanggan")  # UBAH: judul halaman
    _tampilkan_flash()

    hari_ini = store.sekarang().date()
    rk = store.rekap_tanggal(hari_ini)
    st.markdown(f"**Rekap hari ini** · {hari_ini:%d/%m/%Y} (dihitung dari CSV)")
    tema.tiles([
        ("Transaksi", store.angka(rk["transaksi"]), f"{store.angka(rk['pelanggan'])} pelanggan"),
        ("Pendapatan", store.rp(rk["pendapatan"]), "total bayar"),
        ("Reservasi (total)", store.angka(rk["booking_total"][0]), f"{store.angka(rk['booking_total'][1])} orang"),
        ("Reservasi datang", store.angka(rk["booking_datang"][0]), f"{store.angka(rk['booking_datang'][1])} orang"),
        ("No-show", store.angka(rk["booking_noshow"][0]), f"{store.angka(rk['booking_noshow'][1])} orang"),
        ("Cancelled", store.angka(rk["booking_cancel"][0]), f"{store.angka(rk['booking_cancel'][1])} orang"),
        ("Walk-in", store.angka(rk["walkin"][0]), f"{store.angka(rk['walkin'][1])} orang"),
    ])

    tab_pesan, tab_riwayat = st.tabs(["🧾 Pesanan Baru", "🕘 Riwayat Saya"])
    with tab_pesan:
        _form_pesanan(user)
        with st.expander(f"Pesanan hari ini ({hari_ini:%d/%m/%Y})"):
            _tabel(_tabel_hari_ini(hari_ini), 300)
    with tab_riwayat:
        _tab_riwayat(user)
