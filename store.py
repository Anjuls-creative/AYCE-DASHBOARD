"""
store.py — LAPISAN DATA (baca/tulis CSV, hitung harga, catat log).

File ini murni pandas (TIDAK memakai streamlit) supaya mudah diuji.
Dipakai oleh: input_data.py (simpan pesanan), dashboard.py (baca data), data_masuk.py (unduh).

╔══════════════════════ PETA UBAH CEPAT ═══════════════════════╗
║ Mau ubah ...                              → cari bagian ...   ║
║ • Tarif overtime / diskon anak-lansia     → "ATURAN BISNIS"   ║
║ • Batas jam Lunch/Dinner                  → BATAS_DINNER_MENIT║
║ • Daftar topping bawaan                   → TOPPING_AWAL      ║
║ • Kolom tiap file CSV                     → SKEMA             ║
║ • Cara memilih meja otomatis              → pilih_meja_otomatis║
║ • Isi catatan di log                      → _ringkas()        ║
║ • Folder penyimpanan data                 → _tentukan_data_dir║
╚═══════════════════════════════════════════════════════════════╝
Cari kata "UBAH:" untuk menemukan nilai yang biasa Anda ganti.

CATATAN PENTING (perbaikan bug data hilang):
  Semua pembacaan DAN penulisan CSV lewat satu pintu (fungsi baca() dan _tulis()) dan satu folder
  (DATA_DIR). Dashboard juga memakai baca() ini, jadi tidak mungkin lagi dashboard membaca file
  yang berbeda dari file yang ditulis saat input.
"""

from __future__ import annotations

import io
import math
import os
import re
import sqlite3
import tempfile
import threading
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

# ===========================================================================
# LOKASI DATA
# ===========================================================================
FOLDER_APP = Path(__file__).parent  # folder tempat app.py berada
WIB = timezone(timedelta(hours=7))  # UBAH: zona waktu (WIB = UTC+7; WITA = 8; WIT = 9)


def _jumlah_baris(p: Path) -> int:
    """Hitung baris data CSV dengan cepat (tanpa header). -1 jika file tidak terbaca."""
    try:
        return max(0, p.read_bytes().count(b"\n") - 1)
    except OSError:
        return -1


def _tentukan_data_dir() -> Path:
    """
    Tentukan SATU folder berisi CSV. Kandidat: <repo>/data/ dan <repo>/ (CSV sejajar app.py).
    Patokan = transaksi.csv. Jika dua-duanya punya, dipakai yang barisnya lebih banyak
    (supaya file kecil sisa bug lama tidak menutupi data asli).
    Jika tidak ada sama sekali, folder baru <repo>/data/ dipakai.
    """
    kandidat = [FOLDER_APP / "data", FOLDER_APP]
    ada = [(c, _jumlah_baris(c / "transaksi.csv")) for c in kandidat if (c / "transaksi.csv").exists()]
    if ada:
        return max(ada, key=lambda x: x[1])[0]  # jika seri, folder pertama (data/) menang
    return FOLDER_APP / "data"


DATA_DIR = _tentukan_data_dir()

# ===========================================================================
# SKEMA FILE (kolom pertama selalu ID)
# ===========================================================================
# UBAH: menambah kolom baru → tambahkan namanya di sini, lalu isi nilainya di fungsi simpan_pesanan().
#       File CSV lama otomatis ditambah kolom baru (diisi KOLOM_DEFAULT) saat dibaca.
SKEMA = {
    "paket": ["id_paket", "nama_paket", "durasi_menit"],
    "harga_paket": ["id_harga", "id_paket", "waktu", "hari", "harga"],
    "menu": ["id_menu", "nama_menu", "kategori", "paket_minimal", "sistem_penyajian", "status"],
    "meja": ["id_meja", "kapasitas", "area", "lantai", "status"],
    "topping": ["id_topping", "nama_topping", "harga", "status"],  # BARU: daftar topping + harga
    "reservasi": ["id_reservasi", "tanggal", "jam", "id_meja", "nama_pemesan", "jumlah_orang", "tipe_kedatangan", "status"],
    "transaksi": [
        "id_transaksi", "tanggal", "id_reservasi", "id_meja", "id_paket", "id_harga", "waktu_mulai", "waktu_selesai",
        "durasi_makan_menit", "jumlah_orang", "subtotal_paket",
        "subtotal_topping",  # BARU: total harga topping pada transaksi ini
        "menit_overtime", "biaya_overtime", "denda_food_waste", "total_bayar", "metode_pembayaran",
    ],
    "pelanggan": ["id_customer", "id_transaksi", "kategori", "jumlah", "persen_harga", "harga_satuan", "subtotal"],
    "topping_pesanan": [  # BARU: topping yang dipesan pada tiap transaksi
        "id_topping_pesanan", "id_transaksi", "id_topping", "nama_topping", "jumlah", "harga_satuan", "subtotal",
    ],
    "food_waste": ["id_waste", "id_transaksi", "berat_sisa_gram", "tarif_denda", "ukuran_blok_gram", "jumlah_blok", "total_denda"],
}
# Nilai isian untuk kolom baru pada file lama (kolom lain yang hilang diisi teks kosong)
KOLOM_DEFAULT = {("transaksi", "subtotal_topping"): "0"}

LOG_NAMA = "log_input"
LOG_KOLOM = ["id_aksi", "waktu_input", "petugas", "tabel", "id_record", "ringkasan", "status"]

# Urutan file pada halaman Bos (tab Unduh)
URUTAN_FILE = ["transaksi", "pelanggan", "topping_pesanan", "food_waste", "reservasi",
               "topping", "meja", "menu", "paket", "harga_paket"]

# UBAH: topping bawaan. Dipakai HANYA jika file topping.csv belum ada.
#       Untuk mengubah topping/harga seterusnya, edit langsung file data/topping.csv
#       (kolom: id_topping, nama_topping, harga, status → Tersedia / Habis).
TOPPING_AWAL = [
    ["TP001", "Telur Onsen", "8000", "Tersedia"],
    ["TP002", "Keju Mozzarella", "15000", "Tersedia"],
    ["TP003", "Saus Truffle", "20000", "Tersedia"],
    ["TP004", "Garlic Chips", "6000", "Tersedia"],
    ["TP005", "Nori & Furikake", "6000", "Tersedia"],
    ["TP006", "Boba Pearl", "10000", "Tersedia"],
    ["TP007", "Oreo Crumble", "8000", "Tersedia"],
    ["TP008", "Jelly Mix", "7000", "Tersedia"],
]

# ===========================================================================
# ATURAN BISNIS
# ===========================================================================
TARIF_OT = 50000   # UBAH: biaya overtime per blok (Rp)
BLOK_OT = 30       # UBAH: 1 blok overtime = 30 menit ATAU bagiannya (dikenakan per meja)
TARIF_DENDA = 50000  # UBAH: denda food waste per blok (belum dipakai di form baru; untuk fitur 'selesai makan')
BLOK_GRAM = 100      # UBAH: 1 blok denda = 100 gram ATAU bagiannya

# UBAH: persentase harga per kategori pelanggan (100 = harga penuh, 0 = gratis).
#       Urutan kunci dipakai saat menampilkan rincian — jangan ubah nama kuncinya.
PERSEN = {"Adult": 100, "Child": 70, "Senior": 80, "Toddler": 0}

BATAS_DINNER_MENIT = 17 * 60  # UBAH: mulai >= 17:00 dihitung Dinner (jam dalam menit sejak 00:00)
JEDA_BERSIH = 10              # UBAH: jeda bersih-bersih meja setelah dipakai (menit)

TIPE = ["Walk-in", "Booking"]               # nilai yang disimpan di CSV
TIPE_LABEL = {"Walk-in": "Walk-in", "Reservasi": "Booking"}  # tampilan form → nilai CSV
STATUS = ["Completed", "Cancelled", "No-show"]
METODE = ["Cash", "QRIS", "Debit", "Kartu Kredit"]  # UBAH: pilihan metode pembayaran (yang pertama = default)

_LOCK = threading.RLock()


class DataError(ValueError):
    """Kesalahan validasi yang aman ditampilkan langsung ke pengguna."""


# ===========================================================================
# UTILITAS UMUM
# ===========================================================================
def ke_menit(x) -> int:
    """'HH:MM' atau objek time/datetime -> menit sejak tengah malam."""
    if isinstance(x, str):
        h, m = x.split(":")[:2]
        return int(h) * 60 + int(m)
    return x.hour * 60 + x.minute


def dari_menit(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def rp(v) -> str:
    """12345 -> 'Rp 12.345'. UBAH: format mata uang di seluruh aplikasi."""
    return "Rp " + f"{int(v):,}".replace(",", ".")


def angka(v) -> str:
    return f"{int(v):,}".replace(",", ".")


def sekarang() -> datetime:
    return datetime.now(WIB)


# ===========================================================================
# BACA / TULIS CSV
# ===========================================================================
def _path(nama: str) -> Path:
    return DATA_DIR / f"{nama}.csv"


def kolom_file(nama: str) -> list[str]:
    return LOG_KOLOM if nama == LOG_NAMA else SKEMA[nama]


def _baca_db(nama: str):
    """Cadangan: baca tabel dari ayce.db bila CSV-nya tidak ada. None jika tidak tersedia."""
    db = FOLDER_APP / "ayce.db"
    if not db.exists():
        return None
    try:
        with sqlite3.connect(db) as con:
            ada = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nama,)).fetchone()
            if not ada:
                return None
            df = pd.read_sql(f"SELECT * FROM {nama}", con)
        return df.convert_dtypes().astype("string").fillna("").astype(str)
    except Exception:
        return None


def _selaraskan(df: pd.DataFrame, nama: str) -> pd.DataFrame:
    """Pastikan semua kolom skema ada & berurutan (kolom tambahan milik Anda tetap dipertahankan)."""
    cols = kolom_file(nama)
    df = df.copy()
    for c in cols:
        if c not in df.columns:
            df[c] = KOLOM_DEFAULT.get((nama, c), "")
    return df[cols + [c for c in df.columns if c not in cols]]


def baca(nama: str) -> pd.DataFrame:
    """
    SATU-SATUNYA pintu baca data. Seluruh isi dibaca sebagai teks.
    Urutan sumber: DATA_DIR/<nama>.csv → tabel di ayce.db → (khusus topping) TOPPING_AWAL → kosong.
    """
    p = _path(nama)
    if p.exists():
        df = pd.read_csv(p, dtype=str, keep_default_na=False)
    else:
        df = _baca_db(nama)
        if df is None:
            if nama == "topping":
                df = pd.DataFrame(TOPPING_AWAL, columns=SKEMA["topping"], dtype=str)
            else:
                df = pd.DataFrame(columns=kolom_file(nama), dtype=str)
    return _selaraskan(df, nama)


def versi_data() -> tuple:
    """Penanda perubahan file — dipakai dashboard sebagai kunci cache agar data baru langsung terbaca."""
    out = []
    for n in list(SKEMA) + [LOG_NAMA]:
        p = _path(n)
        out.append(p.stat().st_mtime_ns if p.exists() else 0)
    return tuple(out)


def id_berikut(df: pd.DataFrame, kolom: str, awalan: str, lebar: int, n: int = 1) -> list[str]:
    """
    Buat ID berikutnya mengikuti pola yang ada, mis. awalan 'TRX', lebar 4 → TRX1916.
    UBAH: pola ID (awalan/lebar) ditentukan di tiap fungsi simpan_* di bawah.
    """
    pola = re.compile(rf"^{re.escape(awalan)}(\d+)$")
    nomor = []
    for v in df[kolom]:
        m = pola.match(str(v))
        if m:
            nomor.append(int(m.group(1)))
    mulai = (max(nomor) if nomor else 0) + 1
    return [f"{awalan}{mulai + i:0{lebar}d}" for i in range(n)]


def _tulis(nama: str, df: pd.DataFrame):
    """Tulis CSV secara atomik (file sementara lalu diganti) agar tidak rusak jika terputus."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=f".{nama}_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            df.to_csv(f, index=False, lineterminator="\n")
        os.replace(tmp, _path(nama))
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _tulis_banyak(perubahan: dict[str, pd.DataFrame]):
    """Tulis beberapa file sekaligus; bila ada yang gagal, file yang sudah terlanjur berubah dikembalikan."""
    cadangan = {n: baca(n) for n in perubahan}
    ada = {n: _path(n).exists() for n in perubahan}
    selesai = []
    try:
        for n, df in perubahan.items():
            _tulis(n, df)
            selesai.append(n)
    except Exception:
        for n in selesai:
            if ada[n]:
                _tulis(n, cadangan[n])
            else:
                _path(n).unlink(missing_ok=True)
        raise


def _ringkas(tabel: str, r: dict) -> str:
    """UBAH: teks ringkasan yang tampil di log (halaman Riwayat Saya & Data Baru Masuk milik Bos)."""
    if tabel == "reservasi":
        return (f"{r['tipe_kedatangan']} {r['status']} · {r['nama_pemesan']} · {r['jumlah_orang']} org · "
                f"{r['id_meja']} · {r['tanggal']} {r['jam']}")
    if tabel == "transaksi":
        return (f"{r['tanggal']} {r['waktu_mulai']}–{r['waktu_selesai']} · {r['id_meja']} · {r['id_paket']} · "
                f"{r['jumlah_orang']} org · {rp(r['total_bayar'])}")
    if tabel == "pelanggan":
        return f"{r['kategori']} x{r['jumlah']} · {rp(r['subtotal'])}"
    if tabel == "topping_pesanan":
        return f"{r['nama_topping']} x{r['jumlah']} · {rp(r['subtotal'])}"
    return ""


def _commit(petugas: str, baris_per_tabel: dict[str, list[dict]]) -> str:
    """
    Tambahkan baris ke tiap tabel + catat ke log_input.csv (satu 'aksi' = satu kali simpan).
    HARUS dipanggil di dalam `with _LOCK`. Tabel dengan daftar baris kosong dilewati.
    """
    log = baca(LOG_NAMA)
    id_aksi = id_berikut(log, "id_aksi", "LOG", 4)[0]
    waktu = sekarang().strftime("%Y-%m-%d %H:%M:%S")
    baru, log_rows = {}, []
    for tabel, rows in baris_per_tabel.items():
        if not rows:
            continue
        cols = SKEMA[tabel]
        tambah = pd.DataFrame([{c: str(r[c]) for c in cols} for r in rows], columns=cols)
        baru[tabel] = pd.concat([baca(tabel), tambah], ignore_index=True)
        for r in rows:
            log_rows.append({
                "id_aksi": id_aksi, "waktu_input": waktu, "petugas": petugas, "tabel": tabel,
                "id_record": str(r[cols[0]]), "ringkasan": _ringkas(tabel, r), "status": "Aktif",
            })
    baru[LOG_NAMA] = pd.concat([log, pd.DataFrame(log_rows, columns=LOG_KOLOM)], ignore_index=True)
    _tulis_banyak(baru)
    return id_aksi


# ===========================================================================
# HARGA & PESANAN
# ===========================================================================
def konteks_harga(tanggal: date, mulai: int) -> tuple[str, str]:
    """(Lunch/Dinner, Weekday/Weekend) untuk tanggal & jam mulai. UBAH: aturan weekend/lunch di sini."""
    waktu = "Lunch" if mulai < BATAS_DINNER_MENIT else "Dinner"
    hari = "Weekend" if tanggal.weekday() >= 5 else "Weekday"  # Sabtu=5, Minggu=6 (tanggal merah belum dihitung)
    return waktu, hari


def harga_paket_per_orang(id_paket: str, waktu: str, hari: str, harga_df: pd.DataFrame):
    """(id_harga, harga dewasa) dari harga_paket.csv, atau None jika kombinasinya belum ada."""
    h = harga_df[(harga_df["id_paket"] == id_paket) & (harga_df["waktu"] == waktu) & (harga_df["hari"] == hari)]
    if h.empty:
        return None
    return h.iloc[0]["id_harga"], int(h.iloc[0]["harga"])


def komposisi(jumlah: int, tambahan: dict | None = None) -> dict:
    """
    Pecah jumlah orang per kategori. Dewasa = jumlah − (anak + lansia + balita).
    UBAH: aturan 'minimal 1 dewasa/lansia' ada di bawah.
    """
    tambahan = tambahan or {}
    ekstra = {k: int(tambahan.get(k, 0) or 0) for k in ("Child", "Senior", "Toddler")}
    if any(v < 0 for v in ekstra.values()):
        raise DataError("Jumlah anak/lansia/balita tidak boleh negatif.")
    dewasa = int(jumlah) - sum(ekstra.values())
    if dewasa < 0:
        raise DataError(f"Anak + lansia + balita ({sum(ekstra.values())}) melebihi jumlah orang ({jumlah}).")
    if dewasa + ekstra["Senior"] < 1:
        raise DataError("Minimal harus ada 1 dewasa atau lansia dalam grup.")
    return {"Adult": dewasa, **ekstra}


def hitung_pesanan(tanggal: date, mulai: int, id_paket: str, kom: dict, topping_qty: dict,
                   paket_df: pd.DataFrame, harga_df: pd.DataFrame, topping_df: pd.DataFrame) -> dict:
    """
    Hitung seluruh harga sebuah pesanan (paket + topping). Overtime & denda food waste BELUM termasuk
    (baru diketahui setelah selesai makan).
    mulai = menit sejak 00:00; topping_qty = {id_topping: jumlah porsi}.
    """
    kom = {k: int(kom.get(k, 0) or 0) for k in PERSEN}
    orang = sum(kom.values())
    if orang < 1:
        raise DataError("Jumlah orang minimal 1.")

    p = paket_df[paket_df["id_paket"] == id_paket]
    if p.empty:
        raise DataError(f"Paket {id_paket} tidak ditemukan di paket.csv.")
    nama_paket, durasi_paket = p.iloc[0]["nama_paket"], int(p.iloc[0]["durasi_menit"])

    waktu, hari = konteks_harga(tanggal, mulai)
    hp = harga_paket_per_orang(id_paket, waktu, hari, harga_df)
    if hp is None:
        raise DataError(f"Harga paket {nama_paket} untuk {waktu} · {hari} belum ada di harga_paket.csv.")
    id_harga, harga = hp

    # --- harga paket per kategori pelanggan ---
    rincian, subtotal_paket = [], 0
    for kat in PERSEN:
        n = kom[kat]
        if n:
            # UBAH: pembulatan harga anak/lansia (sekarang ke Rp1.000 terdekat)
            satuan = int(harga * PERSEN[kat] / 100 / 1000 + 0.5) * 1000
            sub = satuan * n
            subtotal_paket += sub
            rincian.append({"kategori": kat, "jumlah": n, "persen": PERSEN[kat], "satuan": satuan, "subtotal": sub})

    # --- harga topping ---
    topping, subtotal_topping = [], 0
    for tid, q in (topping_qty or {}).items():
        q = int(q or 0)
        if q < 0:
            raise DataError("Jumlah topping tidak boleh negatif.")
        if q == 0:
            continue
        t = topping_df[topping_df["id_topping"] == tid]
        if t.empty:
            raise DataError(f"Topping {tid} tidak ditemukan di topping.csv.")
        t = t.iloc[0]
        if t["status"] != "Tersedia":
            raise DataError(f"Topping '{t['nama_topping']}' sedang habis.")
        sat = int(t["harga"])
        topping.append({"id_topping": tid, "nama": t["nama_topping"], "jumlah": q, "satuan": sat, "subtotal": sat * q})
        subtotal_topping += sat * q

    # Jam selesai sementara = jam mulai + batas durasi paket (maksimal 23:59)
    selesai = min(mulai + durasi_paket, 24 * 60 - 1)
    return {
        "id_harga": id_harga, "waktu": waktu, "hari": hari, "harga": harga,
        "nama_paket": nama_paket, "durasi_paket": durasi_paket,
        "jumlah_orang": orang, "komposisi": kom, "rincian": rincian, "subtotal_paket": subtotal_paket,
        "topping": topping, "subtotal_topping": subtotal_topping,
        "total": subtotal_paket + subtotal_topping, "mulai": mulai, "selesai": selesai,
    }


# ===========================================================================
# PEMILIHAN MEJA OTOMATIS
# ===========================================================================
def pilih_meja_otomatis(tanggal: date, mulai: int, selesai: int, pax: int,
                        trx_df: pd.DataFrame, meja_df: pd.DataFrame):
    """
    Pilih meja kosong yang paling pas untuk `pax` orang pada [mulai, selesai]. None jika tidak ada.
    Meja dianggap terpakai oleh transaksi lain di tanggal yang sama (ditambah JEDA_BERSIH).
    UBAH: aturan 'paling pas' (toleransi kapasitas berlebih) ada pada variabel `batas`.
    """
    terpakai: dict[str, list[tuple[int, int]]] = {}
    for _, r in trx_df[trx_df["tanggal"] == tanggal.isoformat()].iterrows():
        terpakai.setdefault(r["id_meja"], []).append((ke_menit(r["waktu_mulai"]), ke_menit(r["waktu_selesai"]) + JEDA_BERSIH))

    def bebas(id_meja):
        return all(not (mulai < e and selesai + JEDA_BERSIH > s) for s, e in terpakai.get(id_meja, []))

    m = meja_df.assign(_c=pd.to_numeric(meja_df["kapasitas"], errors="coerce").fillna(0).astype(int))
    m = m.sort_values(["_c", "id_meja"])
    batas = max(4, pax + 2) if pax <= 2 else pax + 2  # UBAH: 1-2 orang boleh pakai meja 4; selain itu maks +2 kursi
    for _, r in m[(m["_c"] >= pax) & (m["_c"] <= batas)].iterrows():
        if bebas(r["id_meja"]):
            return r["id_meja"]
    for _, r in m[m["_c"] > batas].iterrows():  # cadangan: meja lebih besar
        if bebas(r["id_meja"]):
            return r["id_meja"]
    return None


def meja_cocok(pax: int, meja_df: pd.DataFrame) -> pd.DataFrame:
    """Meja berkapasitas cukup, diurutkan dari yang terkecil (untuk pilihan manual)."""
    m = meja_df.assign(_c=pd.to_numeric(meja_df["kapasitas"], errors="coerce").fillna(0).astype(int))
    return m[m["_c"] >= pax].sort_values(["_c", "id_meja"])


# ===========================================================================
# SIMPAN PESANAN (satu-satunya fungsi input data)
# ===========================================================================
def _cek_dasar(nama, tipe, jumlah):
    nama = (nama or "").strip()
    if not nama:
        raise DataError("Nama pemesan wajib diisi.")
    if tipe not in TIPE:
        raise DataError("Tipe kedatangan tidak valid.")
    if int(jumlah) < 1:
        raise DataError("Jumlah orang minimal 1.")
    return nama


def simpan_pesanan(petugas, tanggal: date, jam, nama, tipe, jumlah, id_paket, topping_qty,
                   tambahan_kom, metode, id_meja=None) -> dict:
    """
    Simpan pesanan LENGKAP (tamu datang & memesan paket). Mengisi sekaligus:
      reservasi.csv (status Completed) · transaksi.csv · pelanggan.csv · topping_pesanan.csv (jika ada topping)
    id_meja=None → meja dipilih otomatis. Harga SELALU dihitung ulang di sini dari CSV (bukan dari layar).
    """
    nama = _cek_dasar(nama, tipe, jumlah)
    jumlah = int(jumlah)
    if metode not in METODE:
        raise DataError("Metode pembayaran tidak valid.")
    with _LOCK:
        paket, harga, top = baca("paket"), baca("harga_paket"), baca("topping")
        meja, res, trx = baca("meja"), baca("reservasi"), baca("transaksi")

        mulai = ke_menit(jam)
        h = hitung_pesanan(tanggal, mulai, id_paket, komposisi(jumlah, tambahan_kom), topping_qty, paket, harga, top)

        if id_meja is None:
            id_meja = pilih_meja_otomatis(tanggal, mulai, h["selesai"], jumlah, trx, meja)
            if id_meja is None:
                raise DataError(f"Tidak ada meja kosong untuk {jumlah} orang pada jam {dari_menit(mulai)}. "
                                "Pilih meja manual di Opsi lanjutan atau ubah jam.")
        elif id_meja not in set(meja["id_meja"]):
            raise DataError(f"Meja {id_meja} tidak ada di meja.csv.")

        rid = id_berikut(res, "id_reservasi", "RS", 4)[0]        # UBAH: pola ID reservasi
        tid = id_berikut(trx, "id_transaksi", "TRX", 4)[0]       # UBAH: pola ID transaksi
        cids = id_berikut(baca("pelanggan"), "id_customer", "CU", 4, n=len(h["rincian"]))
        pids = id_berikut(baca("topping_pesanan"), "id_topping_pesanan", "TPO", 4, n=len(h["topping"]))

        res_row = {
            "id_reservasi": rid, "tanggal": tanggal.isoformat(), "jam": dari_menit(mulai), "id_meja": id_meja,
            "nama_pemesan": nama, "jumlah_orang": jumlah, "tipe_kedatangan": tipe, "status": "Completed",
        }
        trx_row = {
            "id_transaksi": tid, "tanggal": tanggal.isoformat(), "id_reservasi": rid, "id_meja": id_meja,
            "id_paket": id_paket, "id_harga": h["id_harga"],
            "waktu_mulai": dari_menit(mulai), "waktu_selesai": dari_menit(h["selesai"]),
            # durasi_makan_menit sementara = batas paket (belum ada fitur 'selesai makan')
            "durasi_makan_menit": h["selesai"] - mulai, "jumlah_orang": jumlah,
            "subtotal_paket": h["subtotal_paket"], "subtotal_topping": h["subtotal_topping"],
            "menit_overtime": 0, "biaya_overtime": 0, "denda_food_waste": 0,  # diisi nanti saat selesai makan
            "total_bayar": h["total"], "metode_pembayaran": metode,
        }
        pel_rows = [
            {"id_customer": cid, "id_transaksi": tid, "kategori": x["kategori"], "jumlah": x["jumlah"],
             "persen_harga": x["persen"], "harga_satuan": x["satuan"], "subtotal": x["subtotal"]}
            for cid, x in zip(cids, h["rincian"])
        ]
        top_rows = [
            {"id_topping_pesanan": pid, "id_transaksi": tid, "id_topping": x["id_topping"], "nama_topping": x["nama"],
             "jumlah": x["jumlah"], "harga_satuan": x["satuan"], "subtotal": x["subtotal"]}
            for pid, x in zip(pids, h["topping"])
        ]
        _commit(petugas, {"reservasi": [res_row], "transaksi": [trx_row], "pelanggan": pel_rows, "topping_pesanan": top_rows})
    return {"id_reservasi": rid, "id_transaksi": tid, "id_meja": id_meja, "total": h["total"],
            "subtotal_paket": h["subtotal_paket"], "subtotal_topping": h["subtotal_topping"], "n_topping": len(top_rows)}


def simpan_reservasi_saja(petugas, tanggal: date, jam, nama, tipe, jumlah, status, id_meja=None) -> str:
    """
    Catat kedatangan yang TIDAK jadi makan (Cancelled / No-show) → hanya reservasi.csv.
    Hanya untuk tipe Booking (Walk-in selalu Completed).
    """
    nama = _cek_dasar(nama, tipe, jumlah)
    jumlah = int(jumlah)
    if status not in STATUS or status == "Completed":
        raise DataError("Gunakan 'Simpan Pesanan' untuk status Completed.")
    if tipe == "Walk-in":
        raise DataError("Walk-in hanya boleh berstatus Completed. Tamu yang batal / tidak datang dicatat sebagai Reservasi.")
    with _LOCK:
        meja = baca("meja")
        if id_meja is None:
            cocok = meja_cocok(jumlah, meja)
            if cocok.empty:
                raise DataError(f"Tidak ada meja berkapasitas {jumlah} orang.")
            id_meja = cocok.iloc[0]["id_meja"]
        elif id_meja not in set(meja["id_meja"]):
            raise DataError(f"Meja {id_meja} tidak ada di meja.csv.")
        rid = id_berikut(baca("reservasi"), "id_reservasi", "RS", 4)[0]
        row = {"id_reservasi": rid, "tanggal": tanggal.isoformat(), "jam": dari_menit(ke_menit(jam)), "id_meja": id_meja,
               "nama_pemesan": nama, "jumlah_orang": jumlah, "tipe_kedatangan": tipe, "status": status}
        _commit(petugas, {"reservasi": [row]})
    return rid


# ===========================================================================
# REKAP, LOG, BATALKAN
# ===========================================================================
def rekap_tanggal(tgl: date) -> dict:
    """Angka ringkas satu tanggal (dipakai kotak rekap di halaman Input)."""
    iso = tgl.isoformat()
    res = baca("reservasi")
    res = res[res["tanggal"] == iso].copy()
    res["_o"] = pd.to_numeric(res["jumlah_orang"], errors="coerce").fillna(0).astype(int)

    def hitung(tipe=None, status=None):
        d = res
        if tipe:
            d = d[d["tipe_kedatangan"] == tipe]
        if status:
            d = d[d["status"] == status]
        return len(d), int(d["_o"].sum())

    trx = baca("transaksi")
    trx = trx[trx["tanggal"] == iso]
    return {
        "booking_total": hitung("Booking"),
        "booking_datang": hitung("Booking", "Completed"),
        "booking_noshow": hitung("Booking", "No-show"),
        "booking_cancel": hitung("Booking", "Cancelled"),
        "walkin": hitung("Walk-in"),
        "transaksi": len(trx),
        "pelanggan": int(pd.to_numeric(trx["jumlah_orang"], errors="coerce").fillna(0).sum()),
        "pendapatan": int(pd.to_numeric(trx["total_bayar"], errors="coerce").fillna(0).sum()),
    }


def aksi_terakhir(petugas: str):
    """Baris log dari aksi aktif terakhir milik `petugas` (atau None)."""
    log = baca(LOG_NAMA)
    a = log[(log["petugas"] == petugas) & (log["status"] == "Aktif")]
    if a.empty:
        return None
    idk = a["id_aksi"].iloc[-1]
    return log[log["id_aksi"] == idk].to_dict("records")


def batalkan_aksi_terakhir(petugas: str):
    """Hapus data dari aksi terakhir petugas lalu tandai di log sebagai 'Dibatalkan'."""
    with _LOCK:
        rows = aksi_terakhir(petugas)
        if not rows:
            return None
        idk = rows[0]["id_aksi"]
        per_tabel: dict[str, list[str]] = {}
        for r in rows:
            per_tabel.setdefault(r["tabel"], []).append(r["id_record"])

        trx = baca("transaksi")
        if "reservasi" in per_tabel and trx["id_reservasi"].isin(per_tabel["reservasi"]).any() and "transaksi" not in per_tabel:
            raise DataError("Reservasi ini sudah dipakai oleh sebuah transaksi, sehingga tidak bisa dibatalkan.")

        baru = {}
        for tabel, ids in per_tabel.items():
            df = baca(tabel)
            baru[tabel] = df[~df[SKEMA[tabel][0]].isin(ids)].reset_index(drop=True)
        log = baca(LOG_NAMA)
        log.loc[log["id_aksi"] == idk, "status"] = "Dibatalkan"
        baru[LOG_NAMA] = log
        _tulis_banyak(baru)
        return rows


def baris_baru(nama: str) -> pd.DataFrame:
    """Baris di tabel `nama` yang masuk lewat aplikasi (aktif), terbaru di atas."""
    cols = ["waktu_input", "petugas"] + SKEMA[nama]
    log = baca(LOG_NAMA)
    sub = log[(log["tabel"] == nama) & (log["status"] == "Aktif")][["id_record", "waktu_input", "petugas"]]
    if sub.empty:
        return pd.DataFrame(columns=cols)
    idcol = SKEMA[nama][0]
    m = baca(nama).merge(sub, left_on=idcol, right_on="id_record", how="inner").drop(columns="id_record")
    return m[cols].sort_values(["waktu_input", idcol], ascending=False).reset_index(drop=True)


# ===========================================================================
# UNDUH & DIAGNOSTIK (dipakai halaman Bos)
# ===========================================================================
def daftar_file() -> list[str]:
    """Nama tabel yang punya file CSV (atau tabel di ayce.db) untuk diunduh."""
    out = []
    for n in URUTAN_FILE + [LOG_NAMA]:
        if _path(n).exists() or _baca_db(n) is not None:
            out.append(n)
    return out


def bytes_csv(nama: str) -> bytes:
    p = _path(nama)
    if p.exists():
        return p.read_bytes()
    return baca(nama).to_csv(index=False, lineterminator="\n").encode("utf-8")


def zip_semua() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in daftar_file():
            z.writestr(f"data/{n}.csv", bytes_csv(n))
    return buf.getvalue()


def info_sumber() -> list[dict]:
    """Dari mana tiap tabel dibaca & berapa barisnya (untuk melacak masalah lokasi data)."""
    out = []
    for n in URUTAN_FILE + [LOG_NAMA]:
        p = _path(n)
        if p.exists():
            sumber, lokasi = "CSV", os.path.relpath(p, FOLDER_APP)
        elif _baca_db(n) is not None:
            sumber, lokasi = "ayce.db (belum disalin ke CSV)", "ayce.db"
        elif n == "topping":
            sumber, lokasi = "bawaan kode (TOPPING_AWAL)", "-"
        else:
            sumber, lokasi = "belum ada", "-"
        out.append({"tabel": n, "sumber": sumber, "lokasi": lokasi, "baris": len(baca(n))})
    return out
