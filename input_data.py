"""
input_data.py — HALAMAN INPUT PESANAN (peran: pegawai).

ALUR (tiga tab):
  🧾 Pesanan Baru   : pilih tipe kedatangan.
      • Walk-in → nama → jumlah orang → paket (durasi & harga) → fasilitas paket (topping, minuman, dessert — sudah
        termasuk harga) → rincian harga → [Mulai Pesanan] ⇒ timer langsung jalan.
      • Reservasi (sudah datang) → cari nama pelanggan yang reservasi online (tampil jam reservasi & kapan ia memesan)
        → [Konfirmasi Pesanan & Mulai Timer] ⇒ timer jalan. (Reservasi dibuat pelanggan di akunnya sendiri: pelanggan.py)
      Data BELUM masuk CSV laporan.
  ⏱️ Sedang Makan   : tiap pesanan tampil dengan timer mundur sesuai batas paket.
                      [Selesai makan] → timer berhenti → isi berat sisa makanan & metode bayar →
                      overtime & denda dihitung otomatis → [Konfirmasi Pembayaran]
                      ⇒ BARU SEKARANG data masuk ke CSV (reservasi, transaksi, pelanggan, food_waste).
  🕘 Riwayat Saya   : daftar input + tombol Batalkan input terakhir (pembayaran yang dibatalkan kembali ke 'Sedang Makan').
Logika hitung & simpan ada di store.py; file ini hanya tampilan & tombol.

╔══════════════════════ PETA UBAH CEPAT ═══════════════════════╗
║ Mau ubah ...                       → cari bagian ...          ║
║ • Jam buka / tutup / last order    → store.py: JAM_BUKA,      ║
║   (peringatan di form)               JAM_TUTUP, LAST_ORDER    ║
║ • Daftar topping / minuman         → data/topping.csv,        ║
║   per paket                          data/minuman.csv         ║
║                                      (kolom paket_minimal)    ║
║ • Daftar paket, durasi, harga      → data/paket.csv &         ║
║                                      data/harga_paket.csv     ║
║ • Tarif overtime, toleransi,       → store.py (ATURAN BISNIS) ║
║   denda food waste, diskon, usia                              ║
║ • Warna/teks timer                 → _timer_html() di bawah   ║
║ • Teks/judul di form               → cari tema.judul_kartu(   ║
║ • Batas jumlah orang (maks 40)     → number_input "Jumlah orang"║
║ • Pilihan metode pembayaran        → store.METODE             ║
╚═══════════════════════════════════════════════════════════════╝
Cari kata "UBAH:" untuk menemukan nilai yang biasa Anda ganti.
"""

from __future__ import annotations

import zlib
from datetime import date, datetime
from html import escape

import pandas as pd
import streamlit as st

import auth
import store
import tema

try:  # komponen untuk timer yang berdetak di browser (JavaScript)
    import streamlit.components.v1 as components
except Exception:  # pragma: no cover
    components = None

# Jam operasional dipakai bersama dengan reservasi online, jadi diatur di store.py (JAM_BUKA, JAM_TUTUP, LAST_ORDER).
JAM_BUKA, JAM_TUTUP, LAST_ORDER = store.JAM_BUKA, store.JAM_TUTUP, store.LAST_ORDER

TIPE_WALKIN = "Walk-in"
TIPE_RESERVASI = "Reservasi (sudah datang)"
SESUAI_RESERVASI = "Sesuai reservasi"

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
    """Nama kategori + usia + diskon, mis. 'Anak-anak 6–8 tahun (70%)'. UBAH: lihat store.label_kategori / USIA / PERSEN."""
    return store.label_kategori(kat)


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
    """Daftar transaksi yang SUDAH DIBAYAR pada satu tanggal (digabung dengan nama pemesan & nama paket)."""
    trx, res, pak = store.baca("transaksi"), store.baca("reservasi"), store.baca("paket")
    t = trx[trx["tanggal"] == tgl.isoformat()]
    t = t.merge(res[["id_reservasi", "nama_pemesan", "tipe_kedatangan"]].drop_duplicates("id_reservasi"), on="id_reservasi", how="left")
    t = t.merge(pak[["id_paket", "nama_paket"]], on="id_paket", how="left").sort_values("waktu_mulai", ascending=False)
    for kolom in ("subtotal_paket", "biaya_overtime", "denda_food_waste", "total_bayar"):
        t[kolom] = pd.to_numeric(t[kolom], errors="coerce").fillna(0).map(store.rp)
    out = t[["waktu_mulai", "waktu_selesai", "nama_pemesan", "tipe_kedatangan", "jumlah_orang", "nama_paket", "id_meja",
             "subtotal_paket", "biaya_overtime", "denda_food_waste", "total_bayar"]]
    return out.rename(columns={
        "waktu_mulai": "Mulai", "waktu_selesai": "Selesai", "nama_pemesan": "Nama", "tipe_kedatangan": "Tipe",
        "jumlah_orang": "Orang", "nama_paket": "Paket", "id_meja": "Meja", "subtotal_paket": "Paket (Rp)",
        "biaya_overtime": "Overtime", "denda_food_waste": "Denda", "total_bayar": "Total",
    })


# ---------------------------------------------------------------------------
# TIMER (JavaScript di browser; angka awal dihitung server supaya tidak terpengaruh jam HP)
# ---------------------------------------------------------------------------
_TIMER_HTML = """
<div style="font-family:'Plus Jakarta Sans',system-ui,sans-serif;display:flex;align-items:baseline;gap:12px">
<span id="t" style="font-size:30px;font-weight:800;color:#1B2236;letter-spacing:-0.02em">--:--</span>
<span id="s" style="font-size:12.5px;color:#8A94A6;font-weight:600"></span></div>
<script>
var SISA=__SISA__, T0=performance.now(), TARIF=__TARIF__, BLOK=__BLOK__, TOL=__TOL__;
function p(n){return (n<10?'0':'')+n}
function f(s){var h=Math.floor(s/3600),m=Math.floor((s%3600)/60),d=s%60;return (h>0?h+':'+p(m):p(m))+':'+p(d)}
function rp(n){return 'Rp '+n.toLocaleString('id-ID')}
function tick(){
  var s=SISA-Math.floor((performance.now()-T0)/1000), t=document.getElementById('t'), u=document.getElementById('s');
  if(s>=0){ t.textContent=f(s); t.style.color=(s<300)?'#E4501A':'#1B2236'; u.textContent='sisa waktu makan'; }
  else { var o=-s, m=Math.max(0,Math.ceil(o/60)-TOL), b=m>0?Math.ceil(m/BLOK):0;
         t.textContent='+'+f(o); t.style.color='#DC2626'; u.textContent='OVERTIME · estimasi denda '+rp(b*TARIF); }
}
tick(); setInterval(tick,1000);
</script>
"""


def _tampilkan_timer(sisa: int):
    """
    Timer mundur. UBAH: warna/ukuran huruf ada di _TIMER_HTML di atas ('#E4501A' = warna saat < 5 menit,
    '#DC2626' = warna saat overtime, 300 = ambang peringatan dalam detik).
    """
    if components is not None:
        try:
            html = (_TIMER_HTML.replace("__SISA__", str(int(sisa))).replace("__TARIF__", str(store.TARIF_OT))
                    .replace("__BLOK__", str(store.BLOK_OT)).replace("__TOL__", str(store.TOLERANSI_OT_MENIT)))
            components.html(html, height=58)
            return
        except Exception:
            pass
    s = abs(int(sisa))  # cadangan bila komponen tidak tersedia: teks statis
    st.markdown(f"**{'OVERTIME +' if sisa < 0 else 'Sisa '}{s // 60:02d}:{s % 60:02d}** (segarkan halaman untuk memperbarui)")


# ===========================================================================
# TAB 1 — PESANAN BARU  (Walk-in langsung, atau Reservasi yang sudah datang)
# ===========================================================================
def _form_pesanan(user):
    v = _ver("pesan")
    k = lambda n: f"p_{n}_{v}"  # noqa: E731  (key unik per versi form, supaya bisa dikosongkan setelah simpan)
    now = store.sekarang()

    paket, harga, meja = store.baca("paket"), store.baca("harga_paket"), store.baca("meja")
    topping, minuman, menu = store.baca("topping"), store.baca("minuman"), store.baca("menu")
    if paket.empty or meja.empty:
        st.error("paket.csv atau meja.csv masih kosong — isi dulu datanya.")
        return

    # -----------------------------------------------------------------------
    # 1 · TIPE KEDATANGAN
    # -----------------------------------------------------------------------
    with st.container(key="card_tipe"):
        tema.judul_kartu(
            "1 · Tipe Kedatangan",
            "<b>Walk-in</b> = pelanggan datang langsung. <b>Reservasi</b> = pelanggan yang sudah reservasi online dan kini sudah tiba.",
        )
        tipe_label = st.radio("Tipe kedatangan", [TIPE_WALKIN, TIPE_RESERVASI], horizontal=True,
                              key=k("tipe"), label_visibility="collapsed")
    if tipe_label == TIPE_RESERVASI:
        _form_reservasi_datang(user, k, now, paket, harga, meja)
        return

    # ======================= WALK-IN =======================
    # -----------------------------------------------------------------------
    # 2 · DATA PEMESAN  (nama → jumlah orang)
    # -----------------------------------------------------------------------
    with st.container(key="card_pemesan"):
        tema.judul_kartu("2 · Data Pemesan", "Isi nama pemesan dan jumlah orang.")
        nama = st.text_input("Nama pemesan", max_chars=60, placeholder="Contoh: Budi Santoso", key=k("nama"))
        jumlah = int(st.number_input("Jumlah orang", min_value=1, max_value=40, value=2, step=1, key=k("jml")))  # UBAH: maks 40

    # ⚙ OPSI LANJUTAN (semua punya nilai otomatis; buka hanya bila perlu)
    with st.expander("⚙️ Opsi lanjutan — meja, anak-anak / lansia / balita"):
        opsi_meja = store.meja_cocok(jumlah, meja)
        label_meja = {OTOMATIS: OTOMATIS}
        for _, r in opsi_meja.iterrows():
            label_meja[r["id_meja"]] = f"{r['id_meja']} · {r['kapasitas']} orang · {r['area']} · Lantai {r['lantai']}"
        meja_pilih = st.selectbox("Meja", list(label_meja), format_func=label_meja.get, key=k(f"meja_{jumlah}"))

        st.markdown("**Komposisi usia** — biarkan 0 jika semuanya dewasa")
        a1, a2, a3 = st.columns(3)
        anak = int(a1.number_input(_label_kategori("Child"), 0, 40, 0, 1, key=k("anak")))
        lansia = int(a2.number_input(_label_kategori("Senior"), 0, 40, 0, 1, key=k("lansia")))
        balita = int(a3.number_input(_label_kategori("Toddler"), 0, 40, 0, 1, key=k("balita")))
        st.caption("Usia di luar kategori anak-anak & balita (dan bukan lansia) dihitung dewasa.")

    tambahan = {"Child": anak, "Senior": lansia, "Toddler": balita}
    try:
        kom = store.komposisi(jumlah, tambahan)
    except store.DataError as e:
        st.error(str(e))
        return

    mulai = now.hour * 60 + now.minute
    id_meja_pilih = None if meja_pilih == OTOMATIS else meja_pilih

    # peringatan jam (tidak memblokir)
    if not (JAM_BUKA <= mulai <= JAM_TUTUP):
        st.warning("Jam di luar jam operasional (11:00–22:00).")
    elif mulai > LAST_ORDER:
        st.warning("Lewat batas last order / pelanggan baru terakhir (20:30).")

    # -----------------------------------------------------------------------
    # 3 · PILIH PAKET  (batas durasi + harga per orang + fasilitas yang didapat)
    # -----------------------------------------------------------------------
    waktu, hari = store.konteks_harga(now.date(), mulai)
    with st.container(key="card_paket"):
        tema.judul_kartu(
            "3 · Pilih Paket",
            f"Harga per orang dewasa · berlaku <b>{waktu}</b> · <b>{hari}</b> ({now:%d/%m/%Y} {now:%H:%M})",
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
            f"(timer mulai saat pesanan dimulai, sampai {store.dari_menit(min(mulai + durasi, 24 * 60 - 1))}). "
            f"Melewati batas dikenakan {store.rp(store.TARIF_OT)} per {store.BLOK_OT} menit."
        )

        # Fasilitas: topping, minuman, dessert yang SUDAH TERMASUK harga paket (tanpa biaya tambahan)
        st.markdown(f"**Yang didapat paket {escape(pp['nama_paket'])}** — sudah termasuk harga, tanpa biaya tambahan:")
        fas = store.fasilitas_paket(id_paket, paket, topping, minuman, menu)
        for kolom, (judul, items) in zip(st.columns(3), fas.items()):
            baris = "".join(
                '<div class="fas-item{}">• {}{}</div>'.format(
                    " fas-habis" if x["habis"] else "", escape(x["nama"]),
                    ' <span class="fas-baru">✨ baru</span>' if x["baru"] and not x["habis"] else (" (habis)" if x["habis"] else ""),
                )
                for x in items
            ) or '<div class="fas-item">—</div>'
            with kolom:
                st.markdown(f'<div class="fas-judul">{judul} ({len(items)})</div>{baris}', unsafe_allow_html=True)
        st.caption("✨ baru = mulai tersedia di paket ini. Paket yang lebih tinggi mendapat semua yang ada di paket di bawahnya.")

        with st.expander("Lihat daftar harga paket lengkap"):
            _tabel(_tabel_harga_lengkap(paket, harga), tinggi=38 + 35 * len(paket))

    # -----------------------------------------------------------------------
    # 4 · RINCIAN HARGA + MULAI PESANAN
    # -----------------------------------------------------------------------
    try:
        h = store.hitung_pesanan(now.date(), mulai, id_paket, kom, paket, harga)
    except store.DataError as e:
        st.error(str(e))
        return

    bisa_mulai = True
    with st.container(key="card_harga"):
        tema.judul_kartu("4 · Rincian Harga", "Harga paket per kategori pelanggan. Pembayaran dilakukan setelah selesai makan.")
        baris = [
            {"Item": f"Paket {h['nama_paket']} — {_label_kategori(x['kategori'])}", "Jumlah": x["jumlah"],
             "Harga": store.rp(x["satuan"]), "Subtotal": store.rp(x["subtotal"])}
            for x in h["rincian"]
        ]
        _tabel(pd.DataFrame(baris), tinggi=38 + 35 * len(baris))
        tema.tiles([
            ("Harga paket", store.rp(h["subtotal_paket"]), f"{h['nama_paket']} · {h['waktu']} · {h['hari']}"),
            ("Topping & minuman", "Termasuk", "tanpa biaya tambahan"),
            ("Overtime", "Setelah makan", f"{store.rp(store.TARIF_OT)} / {store.BLOK_OT} menit lewat batas"),
            ("Batas makan", f"{h['durasi_paket']} menit", f"sampai {store.dari_menit(h['selesai'])}"),
        ])
        st.caption("Total akhir = harga paket + overtime (jika ada) + denda food waste (jika ada), dihitung saat pembayaran.")

        if id_meja_pilih is None:
            id_meja_tampil = store.pilih_meja_otomatis(now.date(), mulai, h["selesai"], jumlah)
            if id_meja_tampil is None:
                bisa_mulai = False
                st.error(f"Tidak ada meja kosong untuk {jumlah} orang saat ini. "
                         "Pilih meja manual di Opsi lanjutan atau tunggu ada meja yang selesai.")
        else:
            id_meja_tampil = id_meja_pilih
            bentrok = store.bentrok_meja(now.date(), mulai, h["selesai"], id_meja_pilih)
            if bentrok:
                st.warning(f"Meja {id_meja_pilih} masih dipakai / bentrok dengan: {', '.join(bentrok)}.")

        if id_meja_tampil:
            pid_next = store.id_berikut(store.baca("pesanan_berjalan"), "id_pesanan", "PB", 4)[0]
            st.caption(f"Akan dimulai sebagai **{pid_next}** · meja **{id_meja_tampil}** · timer **{h['durasi_paket']} menit**")

        if st.button("▶️ Mulai Pesanan & Timer", type="primary", key=k("simpan"), disabled=not bisa_mulai):
            try:
                out = store.buat_pesanan_berjalan(
                    user["username"], nama, "Walk-in", jumlah, id_paket, tambahan, id_meja_pilih,
                )
            except store.DataError as e:
                st.error(str(e))
            else:
                _flash("success",
                       f"Pesanan **{out['id_pesanan']}** dimulai · {nama.strip()} · {jumlah} orang · {out['nama_paket']} · "
                       f"meja {out['id_meja']} · timer {out['durasi_paket']} menit berjalan. "
                       "Lihat di tab **⏱️ Sedang Makan**; data masuk CSV setelah dibayar.")
                _naik("pesan")
                st.rerun()


def _form_reservasi_datang(user, k, now, paket, harga, meja):
    """
    Pelanggan RESERVASI ONLINE yang sudah tiba: cari nama → lihat info reservasi (jam reservasi, kapan diinput)
    → konfirmasi pesanan ⇒ timer mulai. Paket, usia, dan harga mengikuti reservasi (terkunci).
    """
    ol = store.daftar_reservasi_online()
    aktif = ol[ol["status"] == "Aktif"] if not ol.empty else ol
    nama_paket = dict(zip(paket["id_paket"], paket["nama_paket"]))
    durasi_paket = dict(zip(paket["id_paket"], pd.to_numeric(paket["durasi_menit"], errors="coerce").fillna(90).astype(int)))

    with st.container(key="card_rsv_datang"):
        tema.judul_kartu(
            "2 · Cari Reservasi Online",
            "Ketik nama pelanggan yang sudah reservasi. Timer baru dimulai setelah pesanannya dikonfirmasi.",
        )
        c1, c2 = st.columns([3, 2])
        cari = c1.text_input("Cari nama pemesan", placeholder="ketik sebagian nama", key=k("cari"))
        semua = c2.checkbox("Tampilkan tanggal lain (bukan hari ini)", key=k("semua_tgl"))

        data = aktif
        if not semua and not data.empty:
            data = data[data["tanggal"] == now.date().isoformat()]
        if cari.strip() and not data.empty:
            data = data[data["nama_pemesan"].str.contains(cari.strip(), case=False, regex=False)]
        if data.empty:
            st.info("Tidak ada reservasi online yang menunggu"
                    + (" dengan nama itu" if cari.strip() else (" pada tanggal ini" if not semua else ""))
                    + ". Centang 'Tampilkan tanggal lain' untuk melihat tanggal lain.")
            return
        data = data.sort_values(["tanggal", "jam"])

        label = {
            r["id_online"]: (f"{r['nama_pemesan']} · reservasi {date.fromisoformat(r['tanggal']):%d/%m/%Y} {r['jam']} · "
                             f"{r['jumlah_orang']} org · {nama_paket.get(r['id_paket'], r['id_paket'])} · Meja {r['id_meja']} · "
                             f"diinput {datetime.fromisoformat(r['dibuat_ts']):%d/%m %H:%M}")
            for _, r in data.iterrows()
        }
        kunci_opsi = zlib.crc32("|".join(label).encode())
        pilih = st.selectbox("Hasil pencarian", list(label), format_func=label.get, key=k(f"rsv_pilih_{kunci_opsi}"))
        r = data[data["id_online"] == pilih].iloc[0]

        sisa = store.sisa_menuju(r, now)
        ket_waktu = f"{store.format_sisa(sisa)} lagi" if sisa > 0 else f"terlambat {store.format_sisa(-sisa)}"
        mj = meja[meja["id_meja"] == r["id_meja"]]
        tema.tiles([
            ("Jam reservasi", r["jam"], f"{date.fromisoformat(r['tanggal']):%d/%m/%Y} · {ket_waktu}"),
            ("Diinput pada", f"{datetime.fromisoformat(r['dibuat_ts']):%d/%m %H:%M}", f"{datetime.fromisoformat(r['dibuat_ts']):%Y} · akun {r['akun']}"),
            ("Pelanggan", f"{r['jumlah_orang']} orang", store.komposisi_teks(r)),
            ("Paket", nama_paket.get(r["id_paket"], r["id_paket"]),
             f"{durasi_paket.get(r['id_paket'], 90)} menit · {store.rp(r['subtotal_paket'])}"),
            ("Meja", r["id_meja"], f"{mj.iloc[0]['area']} · lantai {mj.iloc[0]['lantai']}" if not mj.empty else ""),
        ])

        # meja: sesuai reservasi, atau ganti bila meja itu masih terpakai
        mulai = now.hour * 60 + now.minute
        selesai = min(mulai + durasi_paket.get(r["id_paket"], 90), 24 * 60 - 1)
        bebas = store.meja_tersedia(now.date(), mulai, selesai, int(r["jumlah_orang"]), abaikan_online=pilih)
        bentrok = store.bentrok_meja(now.date(), mulai, selesai, r["id_meja"], abaikan_online=pilih)
        if bentrok:
            st.warning(f"Meja reservasi ({r['id_meja']}) masih dipakai / bentrok dengan: {', '.join(bentrok)}. "
                       "Pilih meja lain di bawah bila perlu.")
        opsi = {SESUAI_RESERVASI: f"{SESUAI_RESERVASI} ({r['id_meja']})"}
        for _, m in bebas.iterrows():
            if m["id_meja"] != r["id_meja"]:
                opsi[m["id_meja"]] = f"{m['id_meja']} · {m['kapasitas']} orang · {m['area']} · Lantai {m['lantai']}"
        meja_ganti = st.selectbox("Meja untuk pelanggan ini", list(opsi), format_func=opsi.get, key=k(f"rsv_meja_{pilih}"))

        st.caption(f"Harga paket mengikuti reservasi (terkunci). Timer **{durasi_paket.get(r['id_paket'], 90)} menit** "
                   "mulai saat Anda menekan konfirmasi.")
        if st.button("✅ Konfirmasi Pesanan & Mulai Timer", type="primary", key=k(f"rsv_konfirm_{pilih}")):
            try:
                out = store.konfirmasi_kedatangan(user["username"], pilih, None if meja_ganti == SESUAI_RESERVASI else meja_ganti)
            except store.DataError as e:
                st.error(str(e))
            else:
                _flash("success",
                       f"Pesanan **{out['id_pesanan']}** dimulai · {out['nama']} (reservasi {pilih}) · {out['nama_paket']} · "
                       f"meja {out['id_meja']} · timer {out['durasi_paket']} menit berjalan. Lihat di tab **⏱️ Sedang Makan**.")
                _naik("pesan")
                st.rerun()
        if sisa <= 0:
            if st.button("🚫 Tandai No-show (pelanggan tidak datang)", key=k(f"rsv_noshow_{pilih}")):
                try:
                    out = store.tandai_noshow(user["username"], pilih)
                except store.DataError as e:
                    st.error(str(e))
                else:
                    _flash("success", f"Reservasi {pilih} ({out['nama']}) ditandai No-show dan dicatat ke reservasi.csv.")
                    _naik("pesan")
                    st.rerun()


# ===========================================================================
# TAB 2 — SEDANG MAKAN (timer, selesai makan, pembayaran)
# ===========================================================================
def _kartu_pesanan(user, r, paket, harga, now):
    pid = r["id_pesanan"]
    p = paket[paket["id_paket"] == r["id_paket"]]
    nama_paket = p.iloc[0]["nama_paket"] if not p.empty else r["id_paket"]
    durasi = int(p.iloc[0]["durasi_menit"]) if not p.empty else 90
    sisa = store.sisa_detik(r, durasi, now)
    mulai_hm = r["mulai_ts"][11:16]
    batas_hm = store.dari_menit(min(store.ke_menit(mulai_hm) + durasi, 24 * 60 - 1))
    tipe_tampil = "Reservasi" if r["tipe_kedatangan"] == "Booking" else r["tipe_kedatangan"]
    asal = f" · reservasi online {r['id_online']}" if r["id_online"] else ""

    if r["status"] == "Menunggu Bayar":
        badge = '<span class="badge badge-bayar">Menunggu bayar</span>'
    elif sisa < 0:
        badge = '<span class="badge badge-lewat">Overtime</span>'
    else:
        badge = '<span class="badge badge-makan">Sedang makan</span>'

    with st.container(key=f"card_pb_{pid}"):
        st.markdown(
            f'<div class="card-title">{escape(r["nama_pemesan"])}{badge}</div>'
            f'<div class="card-sub">{pid} · {tipe_tampil} · {r["jumlah_orang"]} orang · Paket {escape(nama_paket)} · '
            f'Meja {r["id_meja"]} · mulai {mulai_hm} · batas {batas_hm}{asal}</div>',
            unsafe_allow_html=True,
        )

        # ---------------- Masih makan: timer + tombol ----------------
        if r["status"] == "Makan":
            _tampilkan_timer(sisa)
            c1, c2 = st.columns(2)
            if c1.button("✅ Selesai makan", type="primary", key=f"pb_selesai_{pid}"):
                try:
                    store.selesai_makan(pid)
                except store.DataError as e:
                    st.error(str(e))
                else:
                    st.rerun()
            if c2.button("🗑️ Batalkan pesanan", key=f"pb_batal_{pid}"):
                st.session_state[f"konfirmasi_pb_{pid}"] = True
                st.rerun()
            if st.session_state.get(f"konfirmasi_pb_{pid}"):
                st.warning("Pesanan ini akan dihapus (belum ada yang masuk CSV). Lanjutkan?")
                y, n = st.columns(2)
                if y.button("Ya, hapus pesanan", type="primary", key=f"pb_batal_ya_{pid}"):
                    st.session_state.pop(f"konfirmasi_pb_{pid}", None)
                    try:
                        store.batalkan_pesanan_berjalan(pid)
                    except store.DataError as e:
                        st.error(str(e))
                    else:
                        _flash("success", f"Pesanan {pid} dibatalkan.")
                        st.rerun()
                if n.button("Tidak", key=f"pb_batal_tidak_{pid}"):
                    st.session_state.pop(f"konfirmasi_pb_{pid}", None)
                    st.rerun()
            return

        # ---------------- Menunggu bayar: tagihan final ----------------
        a, b = st.columns(2)
        berat = int(a.number_input("Berat makanan tersisa (gram)", 0, 20000, 0, 10, key=f"pb_waste_{pid}",
                                   help=f"Denda {store.rp(store.TARIF_DENDA)} per {store.BLOK_GRAM} gram; "
                                        f"kurang dari {store.BLOK_GRAM} gram tetap dihitung 1 blok."))
        metode = b.selectbox("Metode pembayaran", store.METODE, key=f"pb_metode_{pid}")
        try:
            t = store.tagihan_akhir(r, berat, harga, paket)
        except store.DataError as e:
            st.error(str(e))
            return

        baris = [{"Item": f"Paket {t['nama_paket']} — {_label_kategori(x['kategori'])}", "Jumlah": x["jumlah"],
                  "Harga": store.rp(x["satuan"]), "Subtotal": store.rp(x["subtotal"])} for x in t["rincian"]]
        _tabel(pd.DataFrame(baris), tinggi=38 + 35 * len(baris))
        if t["menit_overtime"]:
            ket_ot = f"{t['menit_overtime']} menit lewat · {t['blok_overtime']} blok"
        else:
            ket_ot = "tidak overtime ✅"
        tema.tiles([
            ("Durasi makan", f"{t['durasi_menit']} menit", f"batas {t['durasi_paket']} menit"),
            ("Overtime", store.rp(t["biaya_overtime"]), ket_ot),
            ("Denda food waste", store.rp(t["denda"]), f"{berat} g · {t['blok_waste']} blok" if berat else "tidak ada sisa"),
            ("TOTAL BAYAR", store.rp(t["total"]), f"paket {store.rp(t['subtotal_paket'])}"),
        ])
        st.caption(f"Mulai {t['mulai']:%H:%M:%S} · selesai {t['selesai']:%H:%M:%S} (waktu dikunci saat tombol 'Selesai makan' ditekan).")

        if st.button("💳 Konfirmasi Pembayaran & Simpan ke CSV", type="primary", key=f"pb_bayar_{pid}"):
            try:
                out = store.bayar_pesanan(user["username"], pid, berat, metode)
            except store.DataError as e:
                st.error(str(e))
            else:
                _flash("success",
                       f"Pembayaran selesai: **{out['id_transaksi']}** ({out['id_reservasi']}) · {out['nama']} · "
                       f"total {store.rp(out['total'])} (paket {store.rp(out['subtotal_paket'])} + overtime "
                       f"{store.rp(out['biaya_overtime'])} + denda {store.rp(out['denda'])}). Data sudah masuk CSV.")
                st.rerun()


def _tab_berjalan(user):
    pend = store.daftar_pesanan_berjalan()
    if pend.empty:
        st.info("Belum ada pesanan yang sedang makan. Mulai pesanan baru di tab **🧾 Pesanan Baru**.")
        return
    st.caption(f"{len(pend)} pesanan berjalan · data baru masuk CSV setelah dibayar.")
    paket, harga, now = store.baca("paket"), store.baca("harga_paket"), store.sekarang()
    for _, r in pend.iterrows():
        _kartu_pesanan(user, r, paket, harga, now)


# ===========================================================================
# TAB 3 — RIWAYAT SAYA + BATALKAN INPUT TERAKHIR
# ===========================================================================
def _tab_riwayat(user):
    with st.container(key="card_riwayat"):
        tema.judul_kartu("Riwayat Input Saya", "Semua yang masuk CSV tercatat di <b>log_input.csv</b> (bisa dilihat bos).")
        akhir = store.aksi_terakhir(user["username"])
        if not akhir:
            st.info("Belum ada input aktif dari akun ini.")
        else:
            st.markdown(f"**Input terakhir** · {akhir[0]['id_aksi']} · {akhir[0]['waktu_input']}")
            _tabel(pd.DataFrame(akhir)[["tabel", "id_record", "ringkasan"]], tinggi=38 + 35 * min(len(akhir), 6))
            ada_bayar = any(x["tabel"] == "transaksi" for x in akhir)

            if not st.session_state.get("konfirmasi_batal"):
                if st.button("↩️ Batalkan input terakhir", key="btn_batal"):
                    st.session_state["konfirmasi_batal"] = True
                    st.rerun()
            else:
                st.warning("Data di atas akan dihapus dari CSV."
                           + (" Pesanannya dikembalikan ke tab 'Sedang Makan' (Menunggu bayar) agar bisa dibayar ulang." if ada_bayar else "")
                           + " Lanjutkan?")
                y, n = st.columns(2)
                if y.button("Ya, batalkan", type="primary", key="btn_batal_ya"):
                    st.session_state["konfirmasi_batal"] = False
                    try:
                        hasil = store.batalkan_aksi_terakhir(user["username"])
                    except store.DataError as e:
                        st.error(str(e))
                    else:
                        rows, pulih = hasil
                        _flash("success", f"Dibatalkan: {', '.join(r['id_record'] for r in rows)}."
                                          + (" Pesanan dikembalikan ke 'Sedang Makan'." if pulih else ""))
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
    st.markdown(f"**Rekap hari ini** · {hari_ini:%d/%m/%Y} (dihitung dari CSV; pesanan yang belum dibayar belum dihitung)")
    tema.tiles([
        ("Reservasi online menunggu", store.angka(rk["online_aktif"][0]), f"{store.angka(rk['online_aktif'][1])} orang · belum datang"),
        ("Sedang makan", store.angka(rk["berjalan"][0]), f"{store.angka(rk['berjalan'][1])} orang · belum dibayar"),
        ("Transaksi (lunas)", store.angka(rk["transaksi"]), f"{store.angka(rk['pelanggan'])} pelanggan"),
        ("Pendapatan", store.rp(rk["pendapatan"]), "total bayar"),
        ("Reservasi (total)", store.angka(rk["booking_total"][0]), f"{store.angka(rk['booking_total'][1])} orang"),
        ("Reservasi datang", store.angka(rk["booking_datang"][0]), f"{store.angka(rk['booking_datang'][1])} orang"),
        ("No-show", store.angka(rk["booking_noshow"][0]), f"{store.angka(rk['booking_noshow'][1])} orang"),
        ("Cancelled", store.angka(rk["booking_cancel"][0]), f"{store.angka(rk['booking_cancel'][1])} orang"),
        ("Walk-in", store.angka(rk["walkin"][0]), f"{store.angka(rk['walkin'][1])} orang"),
    ])

    # Label tab dibuat TETAP (tanpa angka) supaya tab yang sedang dibuka tidak berpindah saat halaman diperbarui.
    tab_pesan, tab_makan, tab_riwayat = st.tabs(["🧾 Pesanan Baru", "⏱️ Sedang Makan", "🕘 Riwayat Saya"])
    with tab_pesan:
        _form_pesanan(user)
        with st.expander(f"Transaksi lunas hari ini ({hari_ini:%d/%m/%Y})"):
            _tabel(_tabel_hari_ini(hari_ini), 300)
    with tab_makan:
        _tab_berjalan(user)
    with tab_riwayat:
        _tab_riwayat(user)
