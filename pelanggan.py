"""
pelanggan.py — HALAMAN RESERVASI ONLINE (peran: pelanggan).

Tampilan sengaja berbeda total dari pegawai/bos (lihat tema_pelanggan.py) dan TIDAK menampilkan statistik.
Dua tampilan, dipilih lewat tombol pil di atas halaman:
  📝 Buat Reservasi : 1 Data (nama, jumlah orang, komposisi usia) → 2 Jadwal (tanggal & jam) →
                      3 Paket (batas durasi, harga, topping/minuman/dessert yang didapat) → 4 Meja (hanya yang kosong) →
                      5 Rincian harga sementara → [Konfirmasi Reservasi]
  📋 Reservasi Saya : riwayat reservasi akun ini + hitung mundur (hari/jam/menit) + pengingat 30 menit sebelum jam
                      reservasi + tombol Batalkan (hanya selama jam reservasi belum tiba).
Setelah konfirmasi, halaman otomatis pindah ke "Reservasi Saya".
Data disimpan di reservasi_online.csv; pegawai yang mengonfirmasi kedatangan, lalu timer → bayar → CSV laporan
(lihat input_data.py dan store.py).

╔══════════════════════ PETA UBAH CEPAT ═══════════════════════╗
║ Mau ubah ...                       → cari bagian ...          ║
║ • Jam buka, jam terakhir, lead     → store.py: JAM_BUKA,      ║
║   time, maks hari, pengingat         LAST_ORDER, RESERVASI_*, ║
║                                      PENGINGAT_MENIT          ║
║ • Meja yang ditawarkan             → store.MEJA_LEBIH_MAKS    ║
║ • Topping/minuman per paket        → data/topping.csv,        ║
║                                      data/minuman.csv         ║
║ • Kotak hitung mundur & pengingat  → _HITUNG_HTML (di bawah)  ║
║ • Teks form                        → tp.langkah(...) di       ║
║                                      _form_reservasi()        ║
║ • Warna / huruf / banner           → tema_pelanggan.py        ║
║ • Aturan batal                     → store.batalkan_reservasi_online ║
╚═══════════════════════════════════════════════════════════════╝
Cari kata "UBAH:" untuk menemukan nilai yang biasa Anda ganti.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from html import escape

import pandas as pd
import streamlit as st

import auth
import store
import tema_pelanggan as tp

try:  # komponen untuk hitung mundur yang berdetak di browser (JavaScript)
    import streamlit.components.v1 as components
except Exception:  # pragma: no cover
    components = None

VIEW_BUAT = "📝 Buat Reservasi"
VIEW_SAYA = "📋 Reservasi Saya"
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
URUTAN_HARGA = ["Lunch Weekday", "Lunch Weekend", "Dinner Weekday", "Dinner Weekend"]


# ===========================================================================
# HELPER
# ===========================================================================
def _tgl_indo(d: date) -> str:
    """Contoh: 'Sabtu, 10 Oktober 2026'. UBAH: format tanggal tampilan pelanggan."""
    return f"{HARI[d.weekday()]}, {d.day} {BULAN[d.month - 1]} {d.year}"


def _ver(nama: str) -> int:
    return st.session_state.setdefault(f"ver_{nama}", 0)


def _naik(nama: str):
    """Naikkan versi form → kolom isian memakai key baru → form kembali kosong."""
    st.session_state[f"ver_{nama}"] = _ver(nama) + 1


def _flash(jenis: str, pesan: str):
    st.session_state["pl_flash"] = (jenis, pesan)


def _tampilkan_flash():
    f = st.session_state.pop("pl_flash", None)
    if f:
        {"success": st.success, "warning": st.warning}.get(f[0], st.info)(f[1])


def _tabel(df: pd.DataFrame, tinggi: int = 200):
    st.dataframe(df, hide_index=True, height=tinggi)


def _dt(ts: str) -> str:
    """'2026-10-09 14:22:05' → '09/10/2026 14:22'."""
    d = datetime.fromisoformat(ts)
    return f"{d:%d/%m/%Y %H:%M}"


# ---------------------------------------------------------------------------
# HITUNG MUNDUR + PENGINGAT (JavaScript; angka awal dihitung server supaya tidak terpengaruh jam HP)
# ---------------------------------------------------------------------------
_HITUNG_HTML = """
<div style="font-family:'Inter',system-ui,sans-serif;background:#0B3B2E;border-radius:12px;padding:14px 16px;color:#F7F2E8">
<div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#E3C77B;font-weight:700">Menuju jam reservasi</div>
<div id="t" style="font-family:Georgia,'Playfair Display',serif;font-size:26px;font-weight:700;margin:4px 0 2px">--</div>
<div id="r" style="display:none;margin-top:8px;background:#FFF1D6;color:#7A4B00;border-radius:8px;padding:8px 10px;font-size:13px;font-weight:600"></div>
</div>
<script>
var SISA=__SISA__, T0=performance.now(), PENG=__PENGINGAT__;
function tick(){
  var s=SISA-Math.floor((performance.now()-T0)/1000), t=document.getElementById('t'), r=document.getElementById('r');
  if(s<=0){ t.textContent='Waktu reservasi telah tiba'; r.style.display='block';
            r.textContent='Silakan datang ke restoran dan sebutkan nama Anda kepada pegawai.'; return; }
  var d=Math.floor(s/86400), h=Math.floor((s%86400)/3600), m=Math.floor((s%3600)/60), c=s%60;
  var txt = d>0 ? d+' hari '+h+' jam '+m+' menit' : (h>0 ? h+' jam '+m+' menit' : m+' menit '+c+' detik');
  t.textContent = txt+' lagi';
  if(s<=PENG*60){ r.style.display='block';
    r.textContent='⏰ Pengingat: reservasi Anda dimulai '+Math.max(1,Math.ceil(s/60))+' menit lagi. Mohon bersiap dan tiba tepat waktu.'; }
}
tick(); setInterval(tick,1000);
</script>
"""


def _hitung_mundur(sisa: int):
    """
    Kotak hitung mundur. UBAH: teks & warna ada di _HITUNG_HTML di atas; lama pengingat = store.PENGINGAT_MENIT.
    Pengingat muncul otomatis di dalam kotak saat sisa waktu <= PENGINGAT_MENIT (tanpa perlu memuat ulang halaman).
    """
    if components is not None:
        try:
            html = _HITUNG_HTML.replace("__SISA__", str(int(sisa))).replace("__PENGINGAT__", str(store.PENGINGAT_MENIT))
            components.html(html, height=128)
            return
        except Exception:
            pass
    st.markdown(f"**Menuju jam reservasi:** {store.format_sisa(sisa)} lagi" if sisa > 0 else "**Waktu reservasi telah tiba**")


# ===========================================================================
# TAMPILAN 1 — BUAT RESERVASI
# ===========================================================================
def _form_reservasi(user):
    v = _ver("rsv")
    k = lambda n: f"r_{n}_{v}"  # noqa: E731  (key unik per versi form → form dikosongkan setelah konfirmasi)
    now = store.sekarang()
    paling_cepat = now.replace(tzinfo=None) + timedelta(minutes=store.RESERVASI_MIN_MENIT)

    paket, harga, meja = store.baca("paket"), store.baca("harga_paket"), store.baca("meja")
    topping, minuman, menu = store.baca("topping"), store.baca("minuman"), store.baca("menu")
    if paket.empty or meja.empty:
        st.error("Data paket / meja belum tersedia. Silakan hubungi restoran.")
        return

    # -----------------------------------------------------------------------
    # 1 · DATA PEMESAN  (nama, jumlah orang, komposisi usia)
    # -----------------------------------------------------------------------
    with st.container(key="pl_card_data"):
        tp.langkah(1, "Data Pemesan", "Nama, jumlah orang, dan komposisi usia (untuk harga anak & balita).")
        nama = st.text_input("Nama pelanggan", max_chars=60, placeholder="Nama lengkap", key=k("nama"))
        jumlah = int(st.number_input("Jumlah orang", min_value=1, max_value=40, value=2, step=1, key=k("jml")))  # UBAH: maks 40
        st.markdown("**Komposisi usia** — biarkan 0 jika semuanya dewasa")
        a1, a2, a3 = st.columns(3)
        anak = int(a1.number_input(store.label_kategori("Child"), 0, 40, 0, 1, key=k("anak")))
        lansia = int(a2.number_input(store.label_kategori("Senior"), 0, 40, 0, 1, key=k("lansia")))
        balita = int(a3.number_input(store.label_kategori("Toddler"), 0, 40, 0, 1, key=k("balita")))
        st.caption("Usia di luar kategori anak-anak & balita (dan bukan lansia) dihitung dewasa.")
    tambahan = {"Child": anak, "Senior": lansia, "Toddler": balita}
    try:
        kom = store.komposisi(jumlah, tambahan)
    except store.DataError as e:
        st.error(str(e))
        return

    # -----------------------------------------------------------------------
    # 2 · JADWAL  (tanggal & jam)
    # -----------------------------------------------------------------------
    with st.container(key="pl_card_jadwal"):
        tp.langkah(2, "Tanggal & Jam", f"Reservasi minimal {store.RESERVASI_MIN_MENIT} menit dari sekarang dan maksimal "
                                      f"{store.RESERVASI_MAKS_HARI} hari ke depan. Jam kedatangan "
                                      f"{store.dari_menit(store.JAM_BUKA)}–{store.dari_menit(store.LAST_ORDER)}.")
        hari_ini = now.date()
        terlalu_malam = paling_cepat.date() > hari_ini or (paling_cepat.hour * 60 + paling_cepat.minute) > store.LAST_ORDER
        tgl_default = hari_ini + timedelta(days=1) if terlalu_malam else hari_ini
        c1, c2 = st.columns(2)
        tanggal = c1.date_input("Tanggal kedatangan", value=tgl_default, min_value=hari_ini,
                                max_value=hari_ini + timedelta(days=store.RESERVASI_MAKS_HARI),
                                format="DD/MM/YYYY", key=k("tgl"))
        if tanggal == paling_cepat.date() and not terlalu_malam:
            m0 = min(max((paling_cepat.hour * 60 + paling_cepat.minute + 14) // 15 * 15, store.JAM_BUKA), store.LAST_ORDER)
            jam_default = time(m0 // 60, m0 % 60)
        else:
            jam_default = time(12, 0)
        jam = c2.time_input("Jam kedatangan", value=jam_default, step=900, key=k("jam"))

        mulai = jam.hour * 60 + jam.minute
        target = datetime.combine(tanggal, time(jam.hour, jam.minute))
        err_waktu = None
        if not (store.JAM_BUKA <= mulai <= store.LAST_ORDER):
            err_waktu = f"Jam kedatangan harus antara {store.dari_menit(store.JAM_BUKA)} dan {store.dari_menit(store.LAST_ORDER)}."
        elif target < paling_cepat:
            err_waktu = f"Reservasi minimal {store.RESERVASI_MIN_MENIT} menit dari sekarang. Pilih jam yang lebih lambat."
        if err_waktu:
            st.error(err_waktu)
        waktu, hari = store.konteks_harga(tanggal, mulai)
        st.caption(f"🗓️ {_tgl_indo(tanggal)} pukul {jam:%H:%M} · harga berlaku untuk **{waktu}** · **{hari}**")

    # -----------------------------------------------------------------------
    # 3 · PAKET  (batas durasi + harga + topping/minuman/dessert yang didapat)
    # -----------------------------------------------------------------------
    with st.container(key="pl_card_paket"):
        tp.langkah(3, "Pilih Paket", "Topping, minuman, dan dessert sudah termasuk harga paket — tanpa biaya tambahan.")
        label_paket = {}
        for _, p in paket.iterrows():
            hp = store.harga_paket_per_orang(p["id_paket"], waktu, hari, harga)
            label_paket[p["id_paket"]] = (
                f"{p['nama_paket']} · batas makan {p['durasi_menit']} menit · "
                + (f"{store.rp(hp[1])}/orang" if hp else "harga belum tersedia")
            )
        id_paket = st.radio("Paket", paket["id_paket"].tolist(), format_func=label_paket.get,
                            key=k("paket"), label_visibility="collapsed")
        pp = paket[paket["id_paket"] == id_paket].iloc[0]
        durasi = int(pp["durasi_menit"])
        st.caption(f"⏱️ Batas waktu makan paket **{pp['nama_paket']}**: **{durasi} menit**, dihitung sejak pesanan Anda dimulai di restoran. "
                   f"Melewati batas dikenakan {store.rp(store.TARIF_OT)} per {store.BLOK_OT} menit.")

        st.markdown(f"**Yang Anda dapatkan di paket {escape(pp['nama_paket'])}:**")
        fas = store.fasilitas_paket(id_paket, paket, topping, minuman, menu)
        for kolom, (judul, items) in zip(st.columns(3), fas.items()):
            baris = "".join(
                '<div class="pl-fas-item{}">• {}{}</div>'.format(
                    " pl-fas-habis" if x["habis"] else "", escape(x["nama"]),
                    ' <span class="pl-fas-baru">✨ baru</span>' if x["baru"] and not x["habis"] else (" (habis)" if x["habis"] else ""),
                )
                for x in items
            ) or '<div class="pl-fas-item">—</div>'
            with kolom:
                st.markdown(f'<div class="pl-fas-judul">{judul} ({len(items)})</div>{baris}', unsafe_allow_html=True)
        st.caption("✨ baru = tambahan khusus paket ini. Paket yang lebih tinggi mendapat semua yang ada di paket di bawahnya.")

    try:
        h = store.hitung_pesanan(tanggal, mulai, id_paket, kom, paket, harga)
    except store.DataError as e:
        st.error(str(e))
        return

    # -----------------------------------------------------------------------
    # 4 · MEJA  (hanya meja yang kosong pada tanggal & jam itu)
    # -----------------------------------------------------------------------
    id_meja = None
    with st.container(key="pl_card_meja"):
        tp.langkah(4, "Pilih Meja", "Hanya meja yang kosong pada tanggal & jam pilihan Anda yang ditampilkan.")
        bebas = store.meja_tersedia(tanggal, mulai, h["selesai"], jumlah)
        if bebas.empty:
            st.error(f"Maaf, tidak ada meja kosong untuk {jumlah} orang pada {tanggal:%d/%m/%Y} pukul {jam:%H:%M}. "
                     "Silakan coba jam atau tanggal lain.")
        else:
            label_meja = {r["id_meja"]: f"{r['id_meja']} · {r['kapasitas']} orang · {r['area']} · Lantai {r['lantai']}"
                          for _, r in bebas.iterrows()}
            id_meja = st.selectbox("Meja", list(label_meja), format_func=label_meja.get,
                                   key=k(f"meja_{jumlah}_{tanggal}_{mulai}_{id_paket}"))
            st.caption(f"{len(bebas)} meja tersedia untuk {jam:%H:%M}–{store.dari_menit(h['selesai'])}.")

    # -----------------------------------------------------------------------
    # 5 · RINCIAN HARGA SEMENTARA + KONFIRMASI
    # -----------------------------------------------------------------------
    with st.container(key="pl_card_rincian"):
        tp.langkah(5, "Rincian Harga Sementara", "Belum termasuk overtime dan denda food waste (dihitung setelah selesai makan).")
        baris = [
            {"Item": f"Paket {h['nama_paket']} — {store.label_kategori(x['kategori'])}", "Jumlah": x["jumlah"],
             "Harga": store.rp(x["satuan"]), "Subtotal": store.rp(x["subtotal"])}
            for x in h["rincian"]
        ]
        _tabel(pd.DataFrame(baris), tinggi=38 + 35 * len(baris))
        tp.tiles([
            ("Harga paket", store.rp(h["subtotal_paket"]), f"{h['nama_paket']} · {h['waktu']} · {h['hari']}"),
            ("Topping, minuman, dessert", "Termasuk", "tanpa biaya tambahan"),
            ("Batas makan", f"{h['durasi_paket']} menit", f"overtime {store.rp(store.TARIF_OT)}/{store.BLOK_OT} menit"),
            ("Total sementara", store.rp(h["total"]), "belum termasuk overtime & denda"),
        ], total=3)
        st.caption(f"Denda food waste {store.rp(store.TARIF_DENDA)} per {store.BLOK_GRAM} gram makanan tersisa. "
                   "Pembayaran dilakukan di restoran setelah selesai makan.")

        ringkas = f"{_tgl_indo(tanggal)} pukul {jam:%H:%M} · {jumlah} orang"
        if id_meja:
            ringkas += f" · meja {id_meja}"
        st.markdown(f"**Ringkasan:** {escape(ringkas)}")

        if st.button("✅ Konfirmasi Reservasi", type="primary", key=k("konfirmasi"),
                     disabled=bool(err_waktu) or id_meja is None):
            try:
                out = store.buat_reservasi_online(user["username"], nama, jumlah, tambahan, tanggal, jam, id_paket, id_meja)
            except store.DataError as e:
                st.error(str(e))
            else:
                _flash("success", f"Reservasi **{out['id_online']}** berhasil! {_tgl_indo(tanggal)} pukul {out['jam']} · meja "
                                  f"{out['id_meja']} · paket {out['nama_paket']}. Tunjukkan nama Anda ke pegawai saat tiba.")
                _naik("rsv")
                st.session_state["pl_view_next"] = VIEW_SAYA   # otomatis pindah ke riwayat
                st.rerun()


# ===========================================================================
# TAMPILAN 2 — RESERVASI SAYA (riwayat, hitung mundur, pengingat, batalkan)
# ===========================================================================
_STATUS = {  # status di CSV → (teks lencana, gaya). UBAH: teks yang dilihat pelanggan.
    "Aktif": ("Menunggu kedatangan", "aktif"),
    "Datang": ("Sudah dikonfirmasi — selamat menikmati", "datang"),
    "Selesai": ("Selesai", "selesai"),
    "Dibatalkan": ("Dibatalkan", "batal"),
    "No-show": ("Tidak hadir", "noshow"),
}


def _kartu_riwayat(user, r, now, nama_paket: dict, transaksi: pd.DataFrame):
    oid = r["id_online"]
    sisa = store.sisa_menuju(r, now)
    teks, gaya = _STATUS.get(r["status"], (r["status"], "selesai"))
    if r["status"] == "Aktif" and sisa <= 0:
        teks, gaya = "Jam reservasi telah tiba", "datang"
    tgl = date.fromisoformat(r["tanggal"])

    with st.container(key=f"pl_card_res_{oid}"):
        st.markdown(
            f'<div class="pl-res-title">{escape(r["nama_pemesan"])}{tp.badge(teks, gaya)}</div>'
            f'<div class="pl-res-sub">{oid} · {_tgl_indo(tgl)} pukul {r["jam"]} · {r["jumlah_orang"]} orang · '
            f'Paket {escape(nama_paket.get(r["id_paket"], r["id_paket"]))} · Meja {r["id_meja"]}<br>'
            f'{escape(store.komposisi_teks(r))}<br>'
            f'Estimasi harga paket {store.rp(r["subtotal_paket"])} · direservasi pada {_dt(r["dibuat_ts"])}</div>',
            unsafe_allow_html=True,
        )
        if r["status"] == "Aktif":
            _hitung_mundur(sisa)
            if sisa > 0:
                if st.button("Batalkan reservasi", key=f"pl_batal_{oid}"):
                    st.session_state[f"konfirmasi_batal_{oid}"] = True
                    st.rerun()
                if st.session_state.get(f"konfirmasi_batal_{oid}"):
                    st.warning("Yakin ingin membatalkan reservasi ini? Meja Anda akan dilepas.")
                    y, n = st.columns(2)
                    if y.button("Ya, batalkan", type="primary", key=f"pl_batal_ya_{oid}"):
                        st.session_state.pop(f"konfirmasi_batal_{oid}", None)
                        try:
                            store.batalkan_reservasi_online(user["username"], oid)
                        except store.DataError as e:
                            st.error(str(e))
                        else:
                            _flash("success", f"Reservasi {oid} telah dibatalkan.")
                            st.rerun()
                    if n.button("Tidak", key=f"pl_batal_tidak_{oid}"):
                        st.session_state.pop(f"konfirmasi_batal_{oid}", None)
                        st.rerun()
            else:
                st.info("Jam reservasi sudah tiba, sehingga reservasi tidak dapat dibatalkan lagi. "
                        "Silakan datang dan sebutkan nama Anda kepada pegawai.")
        elif r["status"] == "Selesai" and r["id_reservasi"]:
            t = transaksi[transaksi["id_reservasi"] == r["id_reservasi"]]
            if not t.empty:
                st.markdown(f"**Total pembayaran:** {store.rp(int(t.iloc[0]['total_bayar']))} "
                            f"(durasi makan {t.iloc[0]['durasi_makan_menit']} menit). Terima kasih sudah berkunjung!")


def _riwayat(user):
    df = store.daftar_reservasi_online(user["username"])
    if df.empty:
        st.markdown('<div class="pl-kosong">Belum ada reservasi. Buat reservasi pertama Anda di tab '
                    '<b>Buat Reservasi</b>.</div>', unsafe_allow_html=True)
        return
    now = store.sekarang()
    paket = store.baca("paket")
    nama_paket = dict(zip(paket["id_paket"], paket["nama_paket"]))
    transaksi = store.baca("transaksi")
    aktif = df[df["status"] == "Aktif"].sort_values(["tanggal", "jam"])                        # terdekat dulu
    lain = df[df["status"] != "Aktif"].sort_values(["tanggal", "jam"], ascending=False)        # terbaru dulu
    for _, r in pd.concat([aktif, lain]).iterrows():
        _kartu_riwayat(user, r, now, nama_paket, transaksi)


# ===========================================================================
# HALAMAN
# ===========================================================================
def halaman_reservasi():
    user = auth.wajib("pelanggan")  # UBAH: ganti/tambah peran yang boleh membuka halaman ini
    if "pl_view_next" in st.session_state:  # pindah tampilan setelah konfirmasi (harus sebelum radio dibuat)
        st.session_state["pl_view"] = st.session_state.pop("pl_view_next")

    tp.hero(user["nama"])

    # Pengingat: reservasi aktif yang dimulai <= PENGINGAT_MENIT menit lagi
    now = store.sekarang()
    for _, r in store.daftar_reservasi_online(user["username"]).iterrows():
        if r["status"] == "Aktif":
            sisa = store.sisa_menuju(r, now)
            if 0 < sisa <= store.PENGINGAT_MENIT * 60:
                st.warning(f"⏰ Pengingat: reservasi {r['id_online']} atas nama {r['nama_pemesan']} dimulai "
                           f"{store.format_sisa(sisa)} lagi (pukul {r['jam']}, meja {r['id_meja']}).")

    kiri, kanan = st.columns([4, 1])
    with kiri:
        tampilan = st.radio("Tampilan", [VIEW_BUAT, VIEW_SAYA], horizontal=True, key="pl_view", label_visibility="collapsed")
    with kanan:
        if st.button("Keluar", key="pl_logout"):
            auth.logout()

    _tampilkan_flash()
    if tampilan == VIEW_BUAT:
        _form_reservasi(user)
    else:
        _riwayat(user)
