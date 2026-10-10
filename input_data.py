"""Halaman Input Data (peran: pegawai). Semua input langsung ditulis ke CSV lewat store.py."""

from __future__ import annotations

from datetime import time

import pandas as pd
import streamlit as st

import auth
import store
import tema


# ---------------------------------------------------------------------------
# Helper UI
# ---------------------------------------------------------------------------
def _hari_ini():
    return store.sekarang().date()


def _ver(nama: str) -> int:
    return st.session_state.setdefault(f"ver_{nama}", 0)


def _naik(nama: str):
    """Naikkan versi form -> semua widget form memakai key baru -> kembali ke nilai awal."""
    st.session_state[f"ver_{nama}"] = _ver(nama) + 1


def _flash(jenis: str, pesan: str):
    st.session_state["flash"] = (jenis, pesan)


def _tampilkan_flash():
    f = st.session_state.pop("flash", None)
    if not f:
        return
    {"success": st.success, "warning": st.warning}.get(f[0], st.info)(f[1])


def _jam_default(tgl) -> time:
    if tgl == _hari_ini():
        n = store.sekarang()
        m = (n.hour * 60 + n.minute) // 5 * 5
        return time(m // 60, m % 60)
    return time(12, 0)


def _ke_time(menit: int) -> time:
    menit = max(0, min(menit, 23 * 60 + 59))
    return time(menit // 60, menit % 60)


def _tabel(df: pd.DataFrame, tinggi: int = 260):
    st.dataframe(df, hide_index=True, height=tinggi)


# ---------------------------------------------------------------------------
# Tab 1 — Kedatangan / Reservasi  (reservasi.csv)
# ---------------------------------------------------------------------------
def _tab_reservasi(tgl, user):
    v = _ver("res")
    k = lambda n: f"res_{n}_{v}"  # noqa: E731
    meja = store.baca("meja")
    res = store.baca("reservasi")

    with st.container(key="card_res"):
        tema.judul_kartu(
            "Catat Kedatangan",
            "Satu baris = satu grup tamu → <b>reservasi.csv</b>. Catat setelah hasil kedatangan diketahui "
            "(Completed / Cancelled / No-show).",
        )
        if meja.empty:
            st.error("meja.csv kosong — tambahkan meja dulu di tab Master Data.")
            return

        c1, c2 = st.columns(2)
        tipe = c1.selectbox("Tipe kedatangan", store.TIPE, key=k("tipe"))
        opsi_status = ["Completed"] if tipe == "Walk-in" else store.STATUS
        status = c2.selectbox("Status", opsi_status, key=k(f"status_{tipe}"),
                              help="Walk-in selalu Completed. Booking bisa Completed, Cancelled, atau No-show.")

        c3, c4 = st.columns(2)
        jam = c3.time_input("Jam kedatangan / jam booking", value=_jam_default(tgl), step=300, key=k("jam"))
        jumlah = int(c4.number_input("Jumlah orang", min_value=1, max_value=40, value=2, step=1, key=k("jml")))

        nama = st.text_input("Nama pemesan / grup", max_chars=60, key=k("nama"))

        m = meja.assign(_c=meja["kapasitas"].astype(int)).sort_values(["_c", "id_meja"])
        cocok = m[m["_c"] >= jumlah]
        opsi_meja = cocok if not cocok.empty else m
        label_meja = {r["id_meja"]: f"{r['id_meja']} · {r['kapasitas']} orang · {r['area']} · Lantai {r['lantai']}"
                      for _, r in m.iterrows()}
        id_meja = st.selectbox("Meja", opsi_meja["id_meja"].tolist(), format_func=label_meja.get,
                               key=k(f"meja_{jumlah}"),
                               help="Hanya meja dengan kapasitas cukup yang ditampilkan (urut dari yang paling pas).")

        # --- peringatan (tidak memblokir penyimpanan) ---
        menit = store.ke_menit(jam)
        if cocok.empty:
            st.warning("Tidak ada meja yang kapasitasnya cukup untuk jumlah orang ini.")
        if not (11 * 60 <= menit <= 22 * 60):
            st.warning("Jam di luar jam operasional (11:00–22:00).")
        elif menit > 20 * 60 + 30 and tipe == "Walk-in":
            st.warning("Lewat batas last order / pelanggan baru terakhir (20:30).")
        if status != "Cancelled":
            bentrok = res[(res["tanggal"] == tgl.isoformat()) & (res["id_meja"] == id_meja) & (res["status"] != "Cancelled")]
            dekat = [r for _, r in bentrok.iterrows() if abs(store.ke_menit(r["jam"]) - menit) < 90]
            if dekat:
                daftar = ", ".join(f"{r['id_reservasi']} ({r['jam']})" for r in dekat)
                st.warning(f"Meja {id_meja} sudah punya reservasi berdekatan: {daftar}. Pastikan tidak dobel.")

        next_id = store.id_berikut(res, "id_reservasi", "RS", 4)[0]
        st.caption(f"Akan disimpan sebagai **{next_id}** · tanggal {tgl.strftime('%d/%m/%Y')}")

        if st.button("💾 Simpan Kedatangan", type="primary", key=k("simpan")):
            if not nama.strip():
                st.error("Nama pemesan wajib diisi.")
            else:
                try:
                    rid = store.simpan_reservasi(user["username"], tgl, jam, nama, jumlah, tipe, status, id_meja)
                except store.DataError as e:
                    st.error(str(e))
                else:
                    _flash("success", f"Tersimpan: **{rid}** · {tipe} · {status} · {nama.strip()} · {jumlah} orang · {id_meja}.")
                    _naik("res")
                    st.rerun()

    with st.expander(f"Reservasi tanggal {tgl.strftime('%d/%m/%Y')} ({len(res[res['tanggal'] == tgl.isoformat()])})"):
        _tabel(res[res["tanggal"] == tgl.isoformat()].sort_values("jam", ascending=False))


# ---------------------------------------------------------------------------
# Tab 2 — Transaksi  (transaksi.csv + pelanggan.csv + food_waste.csv)
# ---------------------------------------------------------------------------
def _tab_transaksi(tgl, user):
    v = _ver("trx")
    iso = tgl.isoformat()
    res, trx = store.baca("reservasi"), store.baca("transaksi")
    paket, harga, meja = store.baca("paket"), store.baca("harga_paket"), store.baca("meja")

    sudah = set(trx["id_reservasi"])
    kand = res[(res["tanggal"] == iso) & (res["status"] == "Completed") & (~res["id_reservasi"].isin(sudah))].sort_values("jam")

    with st.container(key="card_trx"):
        tema.judul_kartu(
            "Catat Transaksi",
            "Satu kali input mengisi <b>transaksi.csv</b>, <b>pelanggan.csv</b> (komposisi tamu), dan "
            "<b>food_waste.csv</b> sekaligus.",
        )
        if paket.empty:
            st.error("paket.csv kosong — tambahkan paket dulu di tab Master Data.")
            return
        if kand.empty:
            st.info(
                f"Tidak ada reservasi **Completed** tanggal {tgl.strftime('%d/%m/%Y')} yang belum punya transaksi. "
                "Catat dulu kedatangannya di tab **Kedatangan**."
            )
            return

        label_res = {
            r["id_reservasi"]: f"{r['id_reservasi']} · {r['jam']} · {r['nama_pemesan']} · {r['jumlah_orang']} org · "
                               f"{r['id_meja']} · {r['tipe_kedatangan']}"
            for _, r in kand.iterrows()
        }
        rid = st.selectbox("Reservasi yang selesai makan", kand["id_reservasi"].tolist(),
                           format_func=label_res.get, key=f"trx_rid_{v}")
        r = kand[kand["id_reservasi"] == rid].iloc[0]
        pax = int(r["jumlah_orang"])
        kk = lambda n: f"trx_{n}_{v}_{rid}"  # noqa: E731

        label_paket = {p["id_paket"]: f"{p['nama_paket']} · {p['durasi_menit']} menit" for _, p in paket.iterrows()}
        id_paket = st.selectbox("Paket", paket["id_paket"].tolist(), format_func=label_paket.get, key=kk("paket"))
        durasi_paket = int(paket[paket["id_paket"] == id_paket].iloc[0]["durasi_menit"])

        jam_res = store.ke_menit(r["jam"])
        c1, c2, c3 = st.columns(3)
        mulai = c1.time_input("Waktu mulai (timer dimulai)", value=_ke_time(jam_res + 5), step=60, key=kk("mulai"))
        selesai = c2.time_input("Waktu selesai", value=_ke_time(jam_res + 5 + durasi_paket - 5), step=60,
                                key=kk(f"selesai_{id_paket}"))
        metode = c3.selectbox("Metode pembayaran", store.METODE, key=kk("metode"))

        st.markdown("**Komposisi pelanggan** → pelanggan.csv")
        a1, a2, a3, a4 = st.columns(4)
        kom = {
            "Adult": int(a1.number_input("Adult (100%)", 0, 60, pax, 1, key=kk("adult"))),
            "Child": int(a2.number_input("Child (70%)", 0, 60, 0, 1, key=kk("child"))),
            "Senior": int(a3.number_input("Senior (80%)", 0, 60, 0, 1, key=kk("senior"))),
            "Toddler": int(a4.number_input("Toddler (gratis)", 0, 60, 0, 1, key=kk("toddler"))),
        }

        st.markdown("**Food waste** → food_waste.csv")
        berat = int(st.number_input("Berat makanan tersisa (gram)", min_value=0, max_value=20000, value=0, step=10,
                                    key=kk("waste"), help="Denda Rp50.000 per 100 gram; sisa kurang dari 100 gram tetap dihitung 1 blok."))

        # --- hitung tagihan langsung ---
        try:
            t = store.hitung_tagihan(tgl, id_paket, store.ke_menit(mulai), store.ke_menit(selesai), kom, berat, harga, paket)
        except store.DataError as e:
            st.error(str(e))
            return

        st.markdown("**Rincian tagihan**")
        _tabel(
            pd.DataFrame([
                {"Kategori": x["kategori"], "Jumlah": x["jumlah"], "Harga": f"{x['persen']}%",
                 "Per orang": store.rp(x["satuan"]), "Subtotal": store.rp(x["subtotal"])}
                for x in t["rincian"]
            ]),
            tinggi=38 + 35 * len(t["rincian"]),
        )
        tema.tiles([
            ("Subtotal paket", store.rp(t["subtotal_paket"]), f"{t['waktu']} · {t['hari']} · {store.rp(t['harga'])}/org"),
            ("Overtime", store.rp(t["biaya_overtime"]),
             f"{t['menit_overtime']} menit lewat · {t['blok_overtime']} blok" if t["menit_overtime"] else "tidak overtime"),
            ("Denda food waste", store.rp(t["denda"]),
             f"{t['berat_gram']} g · {t['blok_waste']} blok" if t["berat_gram"] else "tidak ada sisa"),
            ("TOTAL BAYAR", store.rp(t["total"]), f"durasi makan {t['durasi']} menit (paket {t['durasi_paket']})"),
        ])

        # --- peringatan (tidak memblokir penyimpanan) ---
        if t["jumlah_orang"] != pax:
            st.warning(f"Jumlah pelanggan di sini {t['jumlah_orang']} orang, sedangkan di reservasi {pax} orang. "
                       "Transaksi memakai jumlah dari komposisi di atas.")
        if kom["Adult"] + kom["Senior"] < 1:
            st.warning("Tidak ada Adult/Senior dalam grup — pastikan komposisi sudah benar.")
        cap = meja[meja["id_meja"] == r["id_meja"]]
        if not cap.empty and t["jumlah_orang"] > int(cap.iloc[0]["kapasitas"]):
            st.warning(f"Meja {r['id_meja']} berkapasitas {cap.iloc[0]['kapasitas']} orang, kurang dari jumlah pelanggan.")
        m1, m2 = store.ke_menit(mulai), store.ke_menit(selesai)
        lain = trx[(trx["tanggal"] == iso) & (trx["id_meja"] == r["id_meja"])]
        for _, o in lain.iterrows():
            if m1 < store.ke_menit(o["waktu_selesai"]) and m2 > store.ke_menit(o["waktu_mulai"]):
                st.warning(f"Waktu bentrok dengan {o['id_transaksi']} di meja {r['id_meja']} "
                           f"({o['waktu_mulai']}–{o['waktu_selesai']}).")

        pel = store.baca("pelanggan")
        nid = store.id_berikut(trx, "id_transaksi", "TRX", 4)[0]
        cid = store.id_berikut(pel, "id_customer", "CU", 4, n=len(t["rincian"]))
        fid = store.id_berikut(store.baca("food_waste"), "id_waste", "FW", 4)[0]
        cu = cid[0] if len(cid) == 1 else f"{cid[0]}–{cid[-1]}"
        st.caption(f"Akan disimpan sebagai **{nid}** · pelanggan **{cu}** · food waste **{fid}** · meja {r['id_meja']}")

        if st.button("💾 Simpan Transaksi", type="primary", key=kk("simpan")):
            try:
                out = store.simpan_transaksi(user["username"], rid, id_paket, mulai, selesai, kom, berat, metode)
            except store.DataError as e:
                st.error(str(e))
            else:
                _flash("success", f"Tersimpan: **{out['id_transaksi']}** · total {store.rp(out['total'])} "
                                  f"(pelanggan {', '.join(out['id_customer'])} · food waste {out['id_waste']}).")
                _naik("trx")
                st.rerun()

    t_hari = trx[trx["tanggal"] == iso]
    with st.expander(f"Transaksi tanggal {tgl.strftime('%d/%m/%Y')} ({len(t_hari)})"):
        _tabel(t_hari.sort_values("waktu_mulai", ascending=False))


# ---------------------------------------------------------------------------
# Tab 3 — Master data (meja, menu, paket + harga)
# ---------------------------------------------------------------------------
def _tab_master(user):
    st.caption("Data master bersifat tambah-saja (belum ada edit). Kesalahan input bisa dibatalkan lewat tab Riwayat Saya.")
    sub_meja, sub_menu, sub_paket = st.tabs(["🪑 Meja", "🍽️ Menu", "📦 Paket + Harga"])

    with sub_meja:
        meja = store.baca("meja")
        with st.container(key="card_meja"):
            tema.judul_kartu("Tambah Meja", "→ <b>meja.csv</b> · ID otomatis (T##), status awal Tersedia.")
            with st.form("form_meja", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                kap = c1.number_input("Kapasitas (orang)", 1, 40, 4, 1)
                area = c2.selectbox("Area", ["Indoor", "Outdoor", "VIP"])
                lantai = c3.number_input("Lantai", 1, 10, 1, 1)
                st.caption(f"ID berikutnya: **{store.id_berikut(meja, 'id_meja', 'T', 2)[0]}**")
                kirim = st.form_submit_button("💾 Simpan Meja", type="primary")
            if kirim:
                try:
                    mid = store.simpan_meja(user["username"], kap, area, lantai)
                except store.DataError as e:
                    st.error(str(e))
                else:
                    _flash("success", f"Meja tersimpan: **{mid}** · {int(kap)} orang · {area} · lantai {int(lantai)}.")
                    st.rerun()
        with st.expander(f"Isi meja.csv ({len(meja)})"):
            _tabel(meja)

    with sub_menu:
        menu, paket = store.baca("menu"), store.baca("paket")
        with st.container(key="card_menu"):
            tema.judul_kartu("Tambah Menu", "→ <b>menu.csv</b> · ID otomatis (M###). Paket minimal menentukan paket yang boleh mengakses menu.")
            if paket.empty:
                st.error("paket.csv kosong.")
            else:
                label_paket = {p["id_paket"]: f"{p['id_paket']} · {p['nama_paket']}" for _, p in paket.iterrows()}
                with st.form("form_menu", clear_on_submit=True):
                    nama = st.text_input("Nama menu", max_chars=60)
                    c1, c2 = st.columns(2)
                    kat = c1.selectbox("Kategori", ["Makanan", "Minuman", "Dessert"])
                    pmin = c2.selectbox("Paket minimal", paket["id_paket"].tolist(), format_func=label_paket.get)
                    c3, c4 = st.columns(2)
                    sistem = c3.selectbox("Sistem penyajian", ["Table Service", "Self Service"])
                    status = c4.selectbox("Status", ["Tersedia", "Habis"])
                    st.caption(f"ID berikutnya: **{store.id_berikut(menu, 'id_menu', 'M', 3)[0]}**")
                    kirim = st.form_submit_button("💾 Simpan Menu", type="primary")
                if kirim:
                    try:
                        mid = store.simpan_menu(user["username"], nama, kat, pmin, sistem, status)
                    except store.DataError as e:
                        st.error(str(e))
                    else:
                        _flash("success", f"Menu tersimpan: **{mid}** · {nama.strip()}.")
                        st.rerun()
        with st.expander(f"Isi menu.csv ({len(menu)})"):
            _tabel(menu)

    with sub_paket:
        paket, harga = store.baca("paket"), store.baca("harga_paket")
        with st.container(key="card_paket"):
            tema.judul_kartu(
                "Tambah Paket Baru",
                "→ <b>paket.csv</b> + 4 baris <b>harga_paket.csv</b> (Lunch/Dinner × Weekday/Weekend). ID otomatis.",
            )
            with st.form("form_paket", clear_on_submit=True):
                c1, c2 = st.columns([2, 1])
                nama = c1.text_input("Nama paket", max_chars=40)
                durasi = c2.number_input("Durasi (menit)", 30, 300, 90, 15)
                h1, h2 = st.columns(2)
                inp = {
                    ("Lunch", "Weekday"): h1.number_input("Lunch · Weekday (Rp)", 1000, 2_000_000, 100_000, 1000),
                    ("Lunch", "Weekend"): h2.number_input("Lunch · Weekend (Rp)", 1000, 2_000_000, 120_000, 1000),
                    ("Dinner", "Weekday"): h1.number_input("Dinner · Weekday (Rp)", 1000, 2_000_000, 120_000, 1000),
                    ("Dinner", "Weekend"): h2.number_input("Dinner · Weekend (Rp)", 1000, 2_000_000, 140_000, 1000),
                }
                st.caption(f"ID berikutnya: **{store.id_berikut(paket, 'id_paket', 'P', 3)[0]}**")
                kirim = st.form_submit_button("💾 Simpan Paket", type="primary")
            if kirim:
                try:
                    out = store.simpan_paket(user["username"], nama, durasi, inp)
                except store.DataError as e:
                    st.error(str(e))
                else:
                    _flash("success", f"Paket tersimpan: **{out['id_paket']}** ({nama.strip()}) + harga {', '.join(out['id_harga'])}.")
                    st.rerun()
        with st.expander(f"Isi paket.csv ({len(paket)}) dan harga_paket.csv ({len(harga)})"):
            _tabel(paket, 140)
            _tabel(harga, 300)


# ---------------------------------------------------------------------------
# Tab 4 — Riwayat saya + batalkan input terakhir
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Halaman
# ---------------------------------------------------------------------------
def halaman_input():
    user = auth.wajib("pegawai")
    tema.header("Input Data", "Input Data Harian")
    _tampilkan_flash()

    tgl = st.date_input("Tanggal data", value=_hari_ini(), max_value=_hari_ini(), format="DD/MM/YYYY", key="tgl_kerja",
                        help="Tanggal untuk kedatangan dan transaksi yang diinput. Bisa mundur untuk input susulan.")

    rk = store.rekap_tanggal(tgl)
    st.markdown(f"**Rekap {tgl.strftime('%d/%m/%Y')}** (dihitung dari CSV)")
    tema.tiles([
        ("Transaksi", store.angka(rk["transaksi"]), f"{store.angka(rk['pelanggan'])} pelanggan"),
        ("Pendapatan", store.rp(rk["pendapatan"]), "total bayar"),
        ("Booking (total)", store.angka(rk["booking_total"][0]), f"{store.angka(rk['booking_total'][1])} orang"),
        ("Booking datang", store.angka(rk["booking_datang"][0]), f"{store.angka(rk['booking_datang'][1])} orang"),
        ("No-show", store.angka(rk["booking_noshow"][0]), f"{store.angka(rk['booking_noshow'][1])} orang"),
        ("Cancelled", store.angka(rk["booking_cancel"][0]), f"{store.angka(rk['booking_cancel'][1])} orang"),
        ("Walk-in", store.angka(rk["walkin"][0]), f"{store.angka(rk['walkin'][1])} orang"),
    ])

    t1, t2, t3, t4 = st.tabs(["📋 Kedatangan", "🧾 Transaksi", "🛠️ Master Data", "🕘 Riwayat Saya"])
    with t1:
        _tab_reservasi(tgl, user)
    with t2:
        _tab_transaksi(tgl, user)
    with t3:
        _tab_master(user)
    with t4:
        _tab_riwayat(user)
