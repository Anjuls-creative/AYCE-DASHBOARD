"""
store.py — LAPISAN DATA (baca/tulis CSV, hitung harga, pesanan berjalan, catat log).

File ini murni pandas (TIDAK memakai streamlit) supaya mudah diuji.
Dipakai oleh: input_data.py (pesanan & pembayaran), dashboard.py (baca data), data_masuk.py (unduh).

ALUR PESANAN (inti aplikasi):
  1) buat_pesanan_berjalan()  → pesanan disimpan di data/pesanan_berjalan.csv (file kerja), timer mulai jalan.
                                 BELUM masuk ke CSV laporan (reservasi/transaksi/pelanggan/food_waste).
  2) selesai_makan()          → timer berhenti, jam selesai dikunci.
  3) bayar_pesanan()          → hitung overtime + denda food waste → BARU masuk ke CSV laporan,
                                 lalu pesanan dihapus dari pesanan_berjalan.csv.

╔══════════════════════ PETA UBAH CEPAT ═══════════════════════╗
║ Mau ubah ...                              → cari bagian ...   ║
║ • Tarif overtime, toleransi, blok waktu   → "ATURAN BISNIS"   ║
║ • Diskon anak/lansia/balita & keterangan  → PERSEN, USIA      ║
║   usia (6-8 th / 0-5 th)                                      ║
║ • Batas jam Lunch/Dinner                  → BATAS_DINNER_MENIT║
║ • Daftar topping & minuman bawaan         → TOPPING_AWAL,     ║
║   (jika CSV-nya belum ada)                  MINUMAN_AWAL      ║
║ • Kolom tiap file CSV                     → SKEMA             ║
║ • Cara memilih meja otomatis              → pilih_meja_otomatis║
║ • Tanggal paling awal di filter           → TANGGAL_PALING_AWAL║
║ • Folder penyimpanan data                 → _tentukan_data_dir║
╚═══════════════════════════════════════════════════════════════╝
Cari kata "UBAH:" untuk menemukan nilai yang biasa Anda ganti.

CATATAN (perbaikan bug data hilang): semua pembacaan DAN penulisan CSV lewat satu pintu
(baca() dan _tulis()) dan satu folder (DATA_DIR). Dashboard juga memakai baca() ini.
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

# UBAH: tanggal paling awal yang bisa dipilih di filter dashboard & filter unduhan (walau belum ada datanya).
#       Tanggal paling AKHIR otomatis = hari ini.
TANGGAL_PALING_AWAL = date(2026, 1, 1)


def _jumlah_baris(p: Path) -> int:
    """Hitung baris data CSV dengan cepat (tanpa header). -1 jika file tidak terbaca."""
    try:
        return max(0, p.read_bytes().count(b"\n") - 1)
    except OSError:
        return -1


def _tentukan_data_dir() -> Path:
    """
    Tentukan SATU folder berisi CSV. Kandidat: <repo>/data/ dan <repo>/ (CSV sejajar app.py).
    Patokan = transaksi.csv. Jika dua-duanya punya, dipakai yang barisnya lebih banyak.
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
# UBAH: menambah kolom baru → tambahkan namanya di sini, lalu isi nilainya di fungsi bayar_pesanan().
#       File CSV lama otomatis ditambah kolom baru saat dibaca (kolom ekstra milik Anda tetap dipertahankan).
PB_KOLOM = [  # file kerja: pesanan yang sedang makan / menunggu bayar (dihapus setelah dibayar)
    "id_pesanan", "petugas", "tanggal", "mulai_ts", "nama_pemesan", "tipe_kedatangan", "jumlah_orang",
    "id_paket", "id_harga", "id_meja", "jml_child", "jml_senior", "jml_toddler", "subtotal_paket",
    "status", "selesai_ts",
]
SKEMA = {
    "paket": ["id_paket", "nama_paket", "durasi_menit"],
    "harga_paket": ["id_harga", "id_paket", "waktu", "hari", "harga"],
    "menu": ["id_menu", "nama_menu", "kategori", "paket_minimal", "sistem_penyajian", "status"],
    "meja": ["id_meja", "kapasitas", "area", "lantai", "status"],
    "topping": ["id_topping", "nama_topping", "paket_minimal", "status"],   # sudah termasuk harga paket
    "minuman": ["id_minuman", "nama_minuman", "paket_minimal", "status"],   # sudah termasuk harga paket
    "reservasi": ["id_reservasi", "tanggal", "jam", "id_meja", "nama_pemesan", "jumlah_orang", "tipe_kedatangan", "status"],
    "transaksi": [
        "id_transaksi", "tanggal", "id_reservasi", "id_meja", "id_paket", "id_harga", "waktu_mulai", "waktu_selesai",
        "durasi_makan_menit", "jumlah_orang", "subtotal_paket", "menit_overtime", "biaya_overtime",
        "denda_food_waste", "total_bayar", "metode_pembayaran",
    ],
    "pelanggan": ["id_customer", "id_transaksi", "kategori", "jumlah", "persen_harga", "harga_satuan", "subtotal"],
    "food_waste": ["id_waste", "id_transaksi", "berat_sisa_gram", "tarif_denda", "ukuran_blok_gram", "jumlah_blok", "total_denda"],
    "pesanan_berjalan": PB_KOLOM,
}
# Nilai isian untuk kolom yang hilang pada file lama (kolom lain yang hilang diisi teks kosong)
KOLOM_DEFAULT = {("topping", "paket_minimal"): "P001", ("minuman", "paket_minimal"): "P001"}

LOG_NAMA = "log_input"
LOG_KOLOM = ["id_aksi", "waktu_input", "petugas", "tabel", "id_record", "ringkasan", "status"]

# Urutan file pada halaman Bos (tab Unduh). pesanan_berjalan sengaja TIDAK ikut (file kerja sementara).
URUTAN_FILE = ["transaksi", "pelanggan", "food_waste", "reservasi", "topping", "minuman",
               "meja", "menu", "paket", "harga_paket"]
# File yang punya kolom tanggal → bisa difilter per tanggal saat diunduh. Sisanya (master) selalu lengkap.
TABEL_BERTANGGAL = ["transaksi", "pelanggan", "food_waste", "reservasi", LOG_NAMA]

# UBAH: topping bawaan — dipakai HANYA jika topping.csv belum ada.
#   Semua topping SUDAH TERMASUK harga paket (tanpa biaya tambahan).
#   paket_minimal = paket terendah yang boleh mengambilnya (P001 Reguler, P002 Premium, P003 Supreme);
#   paket yang lebih tinggi otomatis boleh juga. Dikelompokkan dari harga lama:
#   ≤ Rp8.000 → Reguler, Rp10.000–15.000 → Premium, Rp20.000 → Supreme.
TOPPING_AWAL = [
    ["TP001", "Telur Onsen", "P001", "Tersedia"],
    ["TP002", "Keju Mozzarella", "P002", "Tersedia"],
    ["TP003", "Saus Truffle", "P003", "Tersedia"],
    ["TP004", "Garlic Chips", "P001", "Tersedia"],
    ["TP005", "Nori & Furikake", "P001", "Tersedia"],
    ["TP006", "Boba Pearl", "P002", "Tersedia"],
    ["TP007", "Oreo Crumble", "P001", "Tersedia"],
    ["TP008", "Jelly Mix", "P001", "Tersedia"],
]
# UBAH: minuman bawaan — dipakai HANYA jika minuman.csv belum ada. Aturan paket_minimal sama seperti topping.
MINUMAN_AWAL = [
    ["MN001", "Es Teh", "P001", "Tersedia"],
    ["MN002", "Teh Panas", "P001", "Tersedia"],
    ["MN003", "Air Mineral", "P001", "Tersedia"],
    ["MN004", "Lemon Tea", "P001", "Tersedia"],
    ["MN005", "Soda Gembira", "P001", "Tersedia"],
    ["MN006", "Jus Jeruk Segar", "P002", "Tersedia"],
    ["MN007", "Melon Squash", "P002", "Tersedia"],
    ["MN008", "Iced Latte", "P002", "Tersedia"],
    ["MN009", "Lychee Tea", "P002", "Tersedia"],
    ["MN010", "Matcha Latte", "P003", "Tersedia"],
    ["MN011", "Mocktail Blue Ocean", "P003", "Tersedia"],
    ["MN012", "Sparkling Yuzu", "P003", "Tersedia"],
    ["MN013", "Thai Tea Premium", "P003", "Tersedia"],
]
_BAWAAN = {"topping": TOPPING_AWAL, "minuman": MINUMAN_AWAL}

# ===========================================================================
# ATURAN BISNIS
# ===========================================================================
TARIF_OT = 50000           # UBAH: denda overtime per blok (Rp)
BLOK_OT = 30               # UBAH: 1 blok overtime = 30 menit ATAU bagiannya (dikenakan per meja)
TOLERANSI_OT_MENIT = 0     # UBAH: toleransi sebelum overtime dihitung (0 = tanpa toleransi; mis. 5 = 5 menit gratis)
TARIF_DENDA = 50000        # UBAH: denda food waste per blok (Rp)
BLOK_GRAM = 100            # UBAH: 1 blok denda = 100 gram ATAU bagiannya

# UBAH: persentase harga per kategori pelanggan (100 = harga penuh, 0 = gratis).
#       Jangan ubah NAMA kuncinya (Adult/Child/Senior/Toddler), hanya angkanya.
PERSEN = {"Adult": 100, "Child": 70, "Senior": 80, "Toddler": 0}
# UBAH: keterangan usia yang ditampilkan di form. Usia di luar kategori ini dihitung Dewasa.
USIA = {"Child": "6–8 tahun", "Toddler": "0–5 tahun"}

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
    """Waktu sekarang (zona WIB). Dipakai di mana-mana agar konsisten."""
    return datetime.now(WIB)


def _ts(dt: datetime) -> str:
    """datetime → teks 'YYYY-MM-DD HH:MM:SS' (tanpa zona; selalu waktu lokal WIB)."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _dari_ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


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
    Urutan sumber: DATA_DIR/<nama>.csv → tabel di ayce.db → (topping/minuman) daftar bawaan → kosong.
    """
    p = _path(nama)
    if p.exists():
        df = pd.read_csv(p, dtype=str, keep_default_na=False)
    else:
        df = _baca_db(nama)
        if df is None:
            if nama in _BAWAAN:
                df = pd.DataFrame(_BAWAAN[nama], columns=SKEMA[nama], dtype=str)
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
    UBAH: pola ID (awalan/lebar) ditentukan di fungsi bayar_pesanan() / buat_pesanan_berjalan() di bawah.
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
    """UBAH: teks ringkasan yang tampil di log (Riwayat Saya & Data Baru Masuk milik Bos)."""
    if tabel == "reservasi":
        return (f"{r['tipe_kedatangan']} {r['status']} · {r['nama_pemesan']} · {r['jumlah_orang']} org · "
                f"{r['id_meja']} · {r['tanggal']} {r['jam']}")
    if tabel == "transaksi":
        return (f"{r['tanggal']} {r['waktu_mulai']}–{r['waktu_selesai']} · {r['id_meja']} · {r['id_paket']} · "
                f"{r['jumlah_orang']} org · {rp(r['total_bayar'])}")
    if tabel == "pelanggan":
        return f"{r['kategori']} x{r['jumlah']} · {rp(r['subtotal'])}"
    if tabel == "food_waste":
        return f"{r['berat_sisa_gram']} g · {r['jumlah_blok']} blok · denda {rp(r['total_denda'])}"
    return ""


def _commit(petugas: str, baris_per_tabel: dict[str, list[dict]], ganti: dict[str, pd.DataFrame] | None = None) -> str:
    """
    Tambahkan baris ke tiap tabel + catat ke log_input.csv (satu 'aksi' = satu kali simpan).
    `ganti` = tabel lain yang ditulis ulang bersamaan (mis. pesanan_berjalan setelah dibayar).
    HARUS dipanggil di dalam `with _LOCK`. Tabel dengan daftar baris kosong dilewati.
    """
    log = baca(LOG_NAMA)
    id_aksi = id_berikut(log, "id_aksi", "LOG", 4)[0]
    waktu = _ts(sekarang())
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
    baru.update(ganti or {})
    _tulis_banyak(baru)
    return id_aksi


# ===========================================================================
# HARGA PAKET
# ===========================================================================
def konteks_harga(tanggal: date, mulai: int) -> tuple[str, str]:
    """(Lunch/Dinner, Weekday/Weekend). UBAH: aturan weekend/lunch di sini."""
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


def rincian_harga(harga: int, kom: dict) -> tuple[list[dict], int]:
    """Harga paket per kategori pelanggan → (daftar rincian, subtotal)."""
    rincian, subtotal = [], 0
    for kat in PERSEN:
        n = int(kom.get(kat, 0) or 0)
        if n:
            # UBAH: pembulatan harga anak/lansia (sekarang ke Rp1.000 terdekat)
            satuan = int(harga * PERSEN[kat] / 100 / 1000 + 0.5) * 1000
            sub = satuan * n
            subtotal += sub
            rincian.append({"kategori": kat, "jumlah": n, "persen": PERSEN[kat], "satuan": satuan, "subtotal": sub})
    return rincian, subtotal


def hitung_pesanan(tanggal: date, mulai: int, id_paket: str, kom: dict,
                   paket_df: pd.DataFrame, harga_df: pd.DataFrame) -> dict:
    """
    Harga paket sebuah pesanan (topping & minuman sudah termasuk, jadi tidak ada biaya tambahan).
    Overtime & denda food waste baru dihitung setelah selesai makan (lihat tagihan_akhir).
    mulai = menit sejak 00:00.
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
    rincian, subtotal = rincian_harga(harga, kom)
    return {
        "id_harga": id_harga, "waktu": waktu, "hari": hari, "harga": harga,
        "nama_paket": nama_paket, "durasi_paket": durasi_paket, "jumlah_orang": orang, "komposisi": kom,
        "rincian": rincian, "subtotal_paket": subtotal, "total": subtotal,
        "mulai": mulai, "selesai": min(mulai + durasi_paket, 24 * 60 - 1),
    }


# ===========================================================================
# FASILITAS PAKET (topping, minuman, dessert yang SUDAH TERMASUK harga paket)
# ===========================================================================
def fasilitas_paket(id_paket: str, paket_df: pd.DataFrame, topping_df: pd.DataFrame,
                    minuman_df: pd.DataFrame, menu_df: pd.DataFrame) -> dict:
    """
    Daftar yang didapat pelanggan pada paket `id_paket`: {'Topping': [...], 'Minuman': [...], 'Dessert': [...]}.
    Aturan: item boleh diambil bila paket_minimal-nya SAMA atau LEBIH RENDAH dari paket yang dipilih.
    Tingkatan paket = urutan baris di paket.csv (baris pertama = terendah).
    'baru' = item yang mulai tersedia di paket ini (tidak ada di paket di bawahnya).
    """
    rank = {p: i for i, p in enumerate(paket_df["id_paket"])}
    nama_paket = dict(zip(paket_df["id_paket"], paket_df["nama_paket"]))
    pilih = rank.get(id_paket, 0)

    def ambil(df: pd.DataFrame, kolom_nama: str) -> list[dict]:
        out = []
        for _, r in df.iterrows():
            rk = rank.get(r["paket_minimal"], 0)
            if rk <= pilih:
                out.append({
                    "nama": r[kolom_nama], "baru": pilih > 0 and rk == pilih, "habis": r["status"] != "Tersedia",
                    "dari": nama_paket.get(r["paket_minimal"], r["paket_minimal"]),
                })
        return out

    return {
        "Topping": ambil(topping_df, "nama_topping"),
        "Minuman": ambil(minuman_df, "nama_minuman"),
        "Dessert": ambil(menu_df[menu_df["kategori"] == "Dessert"], "nama_menu"),
    }


# ===========================================================================
# MEJA (otomatis & pengecekan bentrok — memperhitungkan pesanan yang sedang berjalan)
# ===========================================================================
def _meja_terpakai(tanggal: date) -> dict[str, list[tuple[int, int, str]]]:
    """
    {id_meja: [(mulai_menit, selesai_menit + JEDA_BERSIH, kode), ...]} pada `tanggal`.
    Sumber: transaksi yang sudah dibayar + pesanan_berjalan (yang masih makan dianggap memakai meja
    sampai batas paket, atau sampai sekarang bila sudah lewat batas).
    """
    iso = tanggal.isoformat()
    terpakai: dict[str, list[tuple[int, int, str]]] = {}
    trx = baca("transaksi")
    for _, r in trx[trx["tanggal"] == iso].iterrows():
        terpakai.setdefault(r["id_meja"], []).append(
            (ke_menit(r["waktu_mulai"]), ke_menit(r["waktu_selesai"]) + JEDA_BERSIH, r["id_transaksi"]))

    paket = baca("paket")
    durasi = dict(zip(paket["id_paket"], pd.to_numeric(paket["durasi_menit"], errors="coerce").fillna(90)))
    now = sekarang()
    for _, r in baca("pesanan_berjalan").iterrows():
        if r["tanggal"] != iso:
            continue
        s = _dari_ts(r["mulai_ts"])
        mulai = s.hour * 60 + s.minute
        if r["status"] == "Menunggu Bayar" and r["selesai_ts"]:
            e = _dari_ts(r["selesai_ts"])
            akhir = e.hour * 60 + e.minute
        else:
            akhir = mulai + int(durasi.get(r["id_paket"], 90))
            if now.date() == tanggal:
                akhir = max(akhir, now.hour * 60 + now.minute)
        terpakai.setdefault(r["id_meja"], []).append((mulai, akhir + JEDA_BERSIH, r["id_pesanan"]))
    return terpakai


def bentrok_meja(tanggal: date, mulai: int, selesai: int, id_meja: str) -> list[str]:
    """Daftar kode (TRX…/PB…) yang bentrok dengan pemakaian `id_meja` pada [mulai, selesai]. Kosong = aman."""
    return [k for s, e, k in _meja_terpakai(tanggal).get(id_meja, []) if mulai < e and selesai + JEDA_BERSIH > s]


def meja_cocok(pax: int, meja_df: pd.DataFrame) -> pd.DataFrame:
    """Meja berkapasitas cukup, diurutkan dari yang terkecil (untuk pilihan manual)."""
    m = meja_df.assign(_c=pd.to_numeric(meja_df["kapasitas"], errors="coerce").fillna(0).astype(int))
    return m[m["_c"] >= pax].sort_values(["_c", "id_meja"])


def pilih_meja_otomatis(tanggal: date, mulai: int, selesai: int, pax: int):
    """
    Pilih meja kosong yang paling pas untuk `pax` orang pada [mulai, selesai]. None jika tidak ada.
    UBAH: aturan 'paling pas' (toleransi kapasitas berlebih) ada pada variabel `batas`.
    """
    terpakai = _meja_terpakai(tanggal)

    def bebas(id_meja):
        return all(not (mulai < e and selesai + JEDA_BERSIH > s) for s, e, _ in terpakai.get(id_meja, []))

    m = meja_cocok(pax, baca("meja"))  # kapasitas cukup, urut dari yang terkecil
    batas = max(4, pax + 2) if pax <= 2 else pax + 2  # UBAH: 1-2 orang boleh pakai meja 4; selain itu maks +2 kursi
    for _, r in m[m["_c"] <= batas].iterrows():
        if bebas(r["id_meja"]):
            return r["id_meja"]
    for _, r in m[m["_c"] > batas].iterrows():  # cadangan: meja lebih besar
        if bebas(r["id_meja"]):
            return r["id_meja"]
    return None


# ===========================================================================
# PESANAN BERJALAN (timer) → SELESAI MAKAN → BAYAR → CSV
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


def daftar_pesanan_berjalan() -> pd.DataFrame:
    """Pesanan yang sedang makan / menunggu bayar, urut dari yang paling dulu mulai."""
    df = baca("pesanan_berjalan")
    return df.sort_values("mulai_ts").reset_index(drop=True) if not df.empty else df


def buat_pesanan_berjalan(petugas, nama, tipe, jumlah, id_paket, tambahan_kom, id_meja=None) -> dict:
    """
    Mulai pesanan: timer jalan sekarang. Disimpan di pesanan_berjalan.csv (BELUM di CSV laporan).
    id_meja=None → meja dipilih otomatis. Harga paket dikunci pada saat ini (Lunch/Dinner, Weekday/Weekend).
    """
    nama = _cek_dasar(nama, tipe, jumlah)
    jumlah = int(jumlah)
    with _LOCK:
        paket, harga, meja = baca("paket"), baca("harga_paket"), baca("meja")
        now = sekarang()
        mulai = now.hour * 60 + now.minute
        h = hitung_pesanan(now.date(), mulai, id_paket, komposisi(jumlah, tambahan_kom), paket, harga)

        if id_meja is None:
            id_meja = pilih_meja_otomatis(now.date(), mulai, h["selesai"], jumlah)
            if id_meja is None:
                raise DataError(f"Tidak ada meja kosong untuk {jumlah} orang saat ini. Pilih meja manual di Opsi lanjutan "
                                "atau tunggu ada meja yang selesai.")
        elif id_meja not in set(meja["id_meja"]):
            raise DataError(f"Meja {id_meja} tidak ada di meja.csv.")

        pend = baca("pesanan_berjalan")
        pid = id_berikut(pend, "id_pesanan", "PB", 4)[0]  # UBAH: pola ID pesanan berjalan
        kom = h["komposisi"]
        row = {
            "id_pesanan": pid, "petugas": petugas, "tanggal": now.date().isoformat(), "mulai_ts": _ts(now),
            "nama_pemesan": nama, "tipe_kedatangan": tipe, "jumlah_orang": jumlah, "id_paket": id_paket,
            "id_harga": h["id_harga"], "id_meja": id_meja, "jml_child": kom["Child"], "jml_senior": kom["Senior"],
            "jml_toddler": kom["Toddler"], "subtotal_paket": h["subtotal_paket"], "status": "Makan", "selesai_ts": "",
        }
        baru = pd.concat([pend, pd.DataFrame([{c: str(row[c]) for c in PB_KOLOM}], columns=PB_KOLOM)], ignore_index=True)
        _tulis("pesanan_berjalan", baru)
    return {"id_pesanan": pid, "id_meja": id_meja, "nama_paket": h["nama_paket"], "durasi_paket": h["durasi_paket"],
            "subtotal_paket": h["subtotal_paket"], "mulai_ts": _ts(now)}


def _ambil_pesanan(pend: pd.DataFrame, id_pesanan: str) -> pd.Series:
    r = pend[pend["id_pesanan"] == id_pesanan]
    if r.empty:
        raise DataError(f"Pesanan {id_pesanan} tidak ditemukan (mungkin sudah dibayar / dibatalkan pegawai lain).")
    return r.iloc[0]


def sisa_detik(row, durasi_paket_menit: int, now: datetime | None = None) -> int:
    """Sisa waktu makan dalam detik (NEGATIF = sudah overtime). Untuk pesanan Menunggu Bayar dihitung sampai jam selesai."""
    now = now or sekarang()
    if row["status"] == "Menunggu Bayar" and row["selesai_ts"]:
        akhir = _dari_ts(row["selesai_ts"])
    else:
        akhir = now.replace(tzinfo=None)
    terpakai = (akhir - _dari_ts(row["mulai_ts"])).total_seconds()
    return int(durasi_paket_menit * 60 - terpakai)


def selesai_makan(id_pesanan: str) -> dict:
    """Timer berhenti & jam selesai dikunci (status → Menunggu Bayar). Aman dipanggil dua kali."""
    with _LOCK:
        pend = baca("pesanan_berjalan")
        r = _ambil_pesanan(pend, id_pesanan)
        if r["status"] == "Makan":
            mask = pend["id_pesanan"] == id_pesanan
            pend.loc[mask, "status"] = "Menunggu Bayar"
            pend.loc[mask, "selesai_ts"] = _ts(sekarang())
            _tulis("pesanan_berjalan", pend)
            r = _ambil_pesanan(pend, id_pesanan)
    return r.to_dict()


def tagihan_akhir(row, berat_gram: int, harga_df: pd.DataFrame, paket_df: pd.DataFrame) -> dict:
    """
    Tagihan FINAL setelah selesai makan = harga paket + overtime + denda food waste.
    Overtime: lewat batas durasi paket → tiap BLOK_OT menit (atau bagiannya) = TARIF_OT, per meja.
    """
    if row["status"] != "Menunggu Bayar" or not row["selesai_ts"]:
        raise DataError("Tekan 'Selesai makan' dulu supaya waktu makan terkunci.")
    berat_gram = int(berat_gram or 0)
    if berat_gram < 0:
        raise DataError("Berat sisa makanan tidak boleh negatif.")

    p = paket_df[paket_df["id_paket"] == row["id_paket"]]
    if p.empty:
        raise DataError(f"Paket {row['id_paket']} tidak ditemukan di paket.csv.")
    nama_paket, durasi_paket = p.iloc[0]["nama_paket"], int(p.iloc[0]["durasi_menit"])

    h = harga_df[harga_df["id_harga"] == row["id_harga"]]
    if h.empty:
        raise DataError(f"Harga {row['id_harga']} tidak ditemukan di harga_paket.csv.")
    kom = {"Adult": int(row["jumlah_orang"]) - int(row["jml_child"]) - int(row["jml_senior"]) - int(row["jml_toddler"]),
           "Child": int(row["jml_child"]), "Senior": int(row["jml_senior"]), "Toddler": int(row["jml_toddler"])}
    rincian, subtotal = rincian_harga(int(h.iloc[0]["harga"]), kom)

    mulai, selesai = _dari_ts(row["mulai_ts"]), _dari_ts(row["selesai_ts"])
    detik = max(0, int((selesai - mulai).total_seconds()))
    durasi_menit = math.ceil(detik / 60)
    lewat_detik = detik - durasi_paket * 60
    menit_lewat = math.ceil(lewat_detik / 60) if lewat_detik > 0 else 0
    menit_kena = max(0, menit_lewat - TOLERANSI_OT_MENIT)  # menit yang dikenakan denda
    blok_ot = math.ceil(menit_kena / BLOK_OT) if menit_kena else 0
    biaya_ot = blok_ot * TARIF_OT
    blok_waste = math.ceil(berat_gram / BLOK_GRAM) if berat_gram else 0
    denda = blok_waste * TARIF_DENDA
    return {
        "nama_paket": nama_paket, "durasi_paket": durasi_paket, "id_harga": row["id_harga"], "harga": int(h.iloc[0]["harga"]),
        "komposisi": kom, "rincian": rincian, "subtotal_paket": subtotal,
        "mulai": mulai, "selesai": selesai, "durasi_menit": durasi_menit,
        "menit_lewat": menit_lewat, "menit_overtime": menit_kena, "blok_overtime": blok_ot, "biaya_overtime": biaya_ot,
        "berat_gram": berat_gram, "blok_waste": blok_waste, "denda": denda,
        "total": subtotal + biaya_ot + denda,
    }


def bayar_pesanan(petugas, id_pesanan: str, berat_gram: int, metode: str) -> dict:
    """
    PEMBAYARAN: hitung tagihan final → BARU sekarang data masuk ke CSV laporan:
      reservasi.csv (Completed) · transaksi.csv · pelanggan.csv · food_waste.csv
    lalu pesanan dihapus dari pesanan_berjalan.csv.
    """
    if metode not in METODE:
        raise DataError("Metode pembayaran tidak valid.")
    with _LOCK:
        pend = baca("pesanan_berjalan")
        r = _ambil_pesanan(pend, id_pesanan)
        t = tagihan_akhir(r, berat_gram, baca("harga_paket"), baca("paket"))

        res, trx = baca("reservasi"), baca("transaksi")
        tanggal = t["mulai"].date().isoformat()
        rid = id_berikut(res, "id_reservasi", "RS", 4)[0]        # UBAH: pola ID reservasi
        tid = id_berikut(trx, "id_transaksi", "TRX", 4)[0]       # UBAH: pola ID transaksi
        cids = id_berikut(baca("pelanggan"), "id_customer", "CU", 4, n=len(t["rincian"]))
        fid = id_berikut(baca("food_waste"), "id_waste", "FW", 4)[0]

        hm = lambda d: f"{d.hour:02d}:{d.minute:02d}"  # noqa: E731
        res_row = {
            "id_reservasi": rid, "tanggal": tanggal, "jam": hm(t["mulai"]), "id_meja": r["id_meja"],
            "nama_pemesan": r["nama_pemesan"], "jumlah_orang": r["jumlah_orang"],
            "tipe_kedatangan": r["tipe_kedatangan"], "status": "Completed",
        }
        trx_row = {
            "id_transaksi": tid, "tanggal": tanggal, "id_reservasi": rid, "id_meja": r["id_meja"],
            "id_paket": r["id_paket"], "id_harga": t["id_harga"], "waktu_mulai": hm(t["mulai"]), "waktu_selesai": hm(t["selesai"]),
            "durasi_makan_menit": t["durasi_menit"], "jumlah_orang": r["jumlah_orang"], "subtotal_paket": t["subtotal_paket"],
            "menit_overtime": t["menit_overtime"], "biaya_overtime": t["biaya_overtime"], "denda_food_waste": t["denda"],
            "total_bayar": t["total"], "metode_pembayaran": metode,
        }
        pel_rows = [
            {"id_customer": cid, "id_transaksi": tid, "kategori": x["kategori"], "jumlah": x["jumlah"],
             "persen_harga": x["persen"], "harga_satuan": x["satuan"], "subtotal": x["subtotal"]}
            for cid, x in zip(cids, t["rincian"])
        ]
        fw_row = {
            "id_waste": fid, "id_transaksi": tid, "berat_sisa_gram": t["berat_gram"], "tarif_denda": TARIF_DENDA,
            "ukuran_blok_gram": BLOK_GRAM, "jumlah_blok": t["blok_waste"], "total_denda": t["denda"],
        }
        sisa = pend[pend["id_pesanan"] != id_pesanan].reset_index(drop=True)
        _commit(petugas, {"reservasi": [res_row], "transaksi": [trx_row], "pelanggan": pel_rows, "food_waste": [fw_row]},
                ganti={"pesanan_berjalan": sisa})
    return {"id_reservasi": rid, "id_transaksi": tid, "total": t["total"], "subtotal_paket": t["subtotal_paket"],
            "biaya_overtime": t["biaya_overtime"], "denda": t["denda"], "menit_overtime": t["menit_overtime"],
            "nama": r["nama_pemesan"]}


def batalkan_pesanan_berjalan(id_pesanan: str) -> dict:
    """Hapus pesanan yang belum dibayar (mis. salah input / tamu batal). Tidak ada yang masuk CSV laporan."""
    with _LOCK:
        pend = baca("pesanan_berjalan")
        r = _ambil_pesanan(pend, id_pesanan)
        _tulis("pesanan_berjalan", pend[pend["id_pesanan"] != id_pesanan].reset_index(drop=True))
    return r.to_dict()


def simpan_reservasi_saja(petugas, tanggal: date, jam, nama, tipe, jumlah, status, id_meja=None) -> str:
    """
    Catat reservasi yang TIDAK jadi makan (Cancelled / No-show) → langsung ke reservasi.csv (tanpa timer/pembayaran).
    Hanya untuk tipe Booking (Walk-in selalu Completed).
    """
    nama = _cek_dasar(nama, tipe, jumlah)
    jumlah = int(jumlah)
    if status not in STATUS or status == "Completed":
        raise DataError("Status Completed dicatat lewat alur pesanan (mulai → selesai makan → bayar).")
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
    pb = baca("pesanan_berjalan")
    pb = pb[pb["tanggal"] == iso]
    return {
        "booking_total": hitung("Booking"),
        "booking_datang": hitung("Booking", "Completed"),
        "booking_noshow": hitung("Booking", "No-show"),
        "booking_cancel": hitung("Booking", "Cancelled"),
        "walkin": hitung("Walk-in"),
        "transaksi": len(trx),
        "pelanggan": int(pd.to_numeric(trx["jumlah_orang"], errors="coerce").fillna(0).sum()),
        "pendapatan": int(pd.to_numeric(trx["total_bayar"], errors="coerce").fillna(0).sum()),
        "berjalan": (len(pb), int(pd.to_numeric(pb["jumlah_orang"], errors="coerce").fillna(0).sum())),
    }


def aksi_terakhir(petugas: str):
    """Baris log dari aksi aktif terakhir milik `petugas` (atau None)."""
    log = baca(LOG_NAMA)
    a = log[(log["petugas"] == petugas) & (log["status"] == "Aktif")]
    if a.empty:
        return None
    idk = a["id_aksi"].iloc[-1]
    return log[log["id_aksi"] == idk].to_dict("records")


def _pesanan_dari_pembayaran(petugas: str, ids_trx: list[str]) -> dict | None:
    """
    Susun ulang baris pesanan_berjalan dari data transaksi yang akan dihapus (dipakai saat pembayaran dibatalkan,
    supaya pesanan kembali ke daftar 'Sedang Makan' dengan status Menunggu Bayar dan bisa dibayar ulang).
    """
    trx = baca("transaksi")
    t = trx[trx["id_transaksi"].isin(ids_trx)]
    if t.empty:
        return None
    t = t.iloc[0]
    res = baca("reservasi")
    r = res[res["id_reservasi"] == t["id_reservasi"]].iloc[0]
    pel = baca("pelanggan")
    jml = {x["kategori"]: int(x["jumlah"]) for _, x in pel[pel["id_transaksi"] == t["id_transaksi"]].iterrows()}
    mulai = _dari_ts(f"{t['tanggal']} {t['waktu_mulai']}:00")
    selesai = _dari_ts(f"{t['tanggal']} {t['waktu_selesai']}:00")
    if selesai < mulai:
        selesai += timedelta(days=1)
    return {
        "petugas": petugas, "tanggal": t["tanggal"], "mulai_ts": _ts(mulai), "nama_pemesan": r["nama_pemesan"],
        "tipe_kedatangan": r["tipe_kedatangan"], "jumlah_orang": r["jumlah_orang"], "id_paket": t["id_paket"],
        "id_harga": t["id_harga"], "id_meja": t["id_meja"], "jml_child": jml.get("Child", 0),
        "jml_senior": jml.get("Senior", 0), "jml_toddler": jml.get("Toddler", 0), "subtotal_paket": t["subtotal_paket"],
        "status": "Menunggu Bayar", "selesai_ts": _ts(selesai),
    }


def batalkan_aksi_terakhir(petugas: str):
    """
    Hapus data dari aksi terakhir petugas lalu tandai di log sebagai 'Dibatalkan'.
    Jika aksi itu sebuah PEMBAYARAN, pesanannya dikembalikan ke daftar 'Sedang Makan' (Menunggu Bayar).
    Mengembalikan (daftar_baris_log, pesanan_dipulihkan: bool) atau None bila tidak ada aksi.
    """
    with _LOCK:
        rows = aksi_terakhir(petugas)
        if not rows:
            return None
        idk = rows[0]["id_aksi"]
        per_tabel: dict[str, list[str]] = {}
        for r in rows:
            per_tabel.setdefault(r["tabel"], []).append(r["id_record"])

        pulih = None
        if "transaksi" in per_tabel:
            pulih = _pesanan_dari_pembayaran(petugas, per_tabel["transaksi"])

        baru = {}
        for tabel, ids in per_tabel.items():
            df = baca(tabel)
            baru[tabel] = df[~df[SKEMA[tabel][0]].isin(ids)].reset_index(drop=True)
        if pulih:
            pend = baca("pesanan_berjalan")
            pulih["id_pesanan"] = id_berikut(pend, "id_pesanan", "PB", 4)[0]
            baru["pesanan_berjalan"] = pd.concat(
                [pend, pd.DataFrame([{c: str(pulih[c]) for c in PB_KOLOM}], columns=PB_KOLOM)], ignore_index=True)
        log = baca(LOG_NAMA)
        log.loc[log["id_aksi"] == idk, "status"] = "Dibatalkan"
        baru[LOG_NAMA] = log
        _tulis_banyak(baru)
        return rows, bool(pulih)


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
# UNDUH (bisa per rentang tanggal) & DIAGNOSTIK — dipakai halaman Bos
# ===========================================================================
def daftar_file() -> list[str]:
    """Nama tabel yang punya file CSV (atau tabel di ayce.db / daftar bawaan) untuk diunduh."""
    out = []
    for n in URUTAN_FILE + [LOG_NAMA]:
        if _path(n).exists() or _baca_db(n) is not None or n in _BAWAAN:
            out.append(n)
    return out


def rentang_data() -> tuple[date, date]:
    """(tanggal data paling awal, tanggal data paling akhir) di transaksi & reservasi. Tanpa data → hari ini."""
    tgl = []
    for n in ("transaksi", "reservasi"):
        tgl += [d for d in baca(n)["tanggal"] if d]
    if not tgl:
        h = sekarang().date()
        return h, h
    return date.fromisoformat(min(tgl)), date.fromisoformat(max(tgl))


def batas_tanggal() -> tuple[date, date]:
    """(tanggal paling awal, tanggal paling akhir) yang boleh dipilih di filter: tidak bergantung ada/tidaknya data."""
    awal, akhir = rentang_data()
    return min(TANGGAL_PALING_AWAL, awal), max(sekarang().date(), akhir)


def baca_rentang(nama: str, mulai: date | None = None, akhir: date | None = None) -> pd.DataFrame:
    """
    Isi tabel `nama` pada rentang tanggal [mulai, akhir] (keduanya termasuk). mulai/akhir None → semua.
    reservasi & transaksi → kolom tanggal; pelanggan & food_waste → ikut transaksi di rentang itu;
    log_input → tanggal input. Tabel master (meja, menu, paket, ...) tidak punya tanggal → selalu lengkap.
    """
    df = baca(nama)
    if mulai is None or akhir is None or nama not in TABEL_BERTANGGAL:
        return df
    m, a = mulai.isoformat(), akhir.isoformat()
    if nama in ("reservasi", "transaksi"):
        return df[(df["tanggal"] >= m) & (df["tanggal"] <= a)]
    if nama in ("pelanggan", "food_waste"):
        t = baca("transaksi")
        ids = set(t[(t["tanggal"] >= m) & (t["tanggal"] <= a)]["id_transaksi"])
        return df[df["id_transaksi"].isin(ids)]
    d = df["waktu_input"].str[:10]  # log_input
    return df[(d >= m) & (d <= a)]


def bytes_csv(nama: str, mulai: date | None = None, akhir: date | None = None) -> bytes:
    """Isi CSV siap unduh. Tanpa rentang tanggal → file apa adanya."""
    if mulai is None or akhir is None or nama not in TABEL_BERTANGGAL:
        p = _path(nama)
        if p.exists():
            return p.read_bytes()
        return baca(nama).to_csv(index=False, lineterminator="\n").encode("utf-8")
    return baca_rentang(nama, mulai, akhir).to_csv(index=False, lineterminator="\n").encode("utf-8")


def zip_semua(mulai: date | None = None, akhir: date | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in daftar_file():
            z.writestr(f"data/{n}.csv", bytes_csv(n, mulai, akhir))
    return buf.getvalue()


def info_sumber() -> list[dict]:
    """Dari mana tiap tabel dibaca & berapa barisnya (untuk melacak masalah lokasi data)."""
    out = []
    for n in URUTAN_FILE + ["pesanan_berjalan", LOG_NAMA]:
        p = _path(n)
        if p.exists():
            sumber, lokasi = "CSV", os.path.relpath(p, FOLDER_APP)
        elif _baca_db(n) is not None:
            sumber, lokasi = "ayce.db (belum disalin ke CSV)", "ayce.db"
        elif n in _BAWAAN:
            sumber, lokasi = "bawaan kode", "-"
        else:
            sumber, lokasi = "belum ada", "-"
        out.append({"tabel": n, "sumber": sumber, "lokasi": lokasi, "baris": len(baca(n))})
    return out
