"""
Lapisan data AYCE-DASHBOARD.

Murni pandas (TIDAK memakai streamlit) supaya mudah diuji.
- Semua CSV dibaca sebagai teks agar isi file lama tidak berubah saat ditulis ulang.
- Penulisan atomik (file sementara -> os.replace) di bawah satu lock.
- ID dibuat otomatis mengikuti pola yang sudah ada (RS0001, TRX0001, CU0001, FW0001, M001, T01, P001, H001).
- Setiap input dicatat di data/log_input.csv (dipakai halaman Bos: "Data Baru Masuk" dan fitur batalkan).
"""

from __future__ import annotations

import io
import math
import os
import re
import tempfile
import threading
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
WIB = timezone(timedelta(hours=7))  # Surabaya

# Kolom tiap file (kolom pertama selalu ID)
SKEMA = {
    "paket": ["id_paket", "nama_paket", "durasi_menit"],
    "harga_paket": ["id_harga", "id_paket", "waktu", "hari", "harga"],
    "menu": ["id_menu", "nama_menu", "kategori", "paket_minimal", "sistem_penyajian", "status"],
    "meja": ["id_meja", "kapasitas", "area", "lantai", "status"],
    "reservasi": ["id_reservasi", "tanggal", "jam", "id_meja", "nama_pemesan", "jumlah_orang", "tipe_kedatangan", "status"],
    "transaksi": [
        "id_transaksi", "tanggal", "id_reservasi", "id_meja", "id_paket", "id_harga", "waktu_mulai", "waktu_selesai",
        "durasi_makan_menit", "jumlah_orang", "subtotal_paket", "menit_overtime", "biaya_overtime",
        "denda_food_waste", "total_bayar", "metode_pembayaran",
    ],
    "pelanggan": ["id_customer", "id_transaksi", "kategori", "jumlah", "persen_harga", "harga_satuan", "subtotal"],
    "food_waste": ["id_waste", "id_transaksi", "berat_sisa_gram", "tarif_denda", "ukuran_blok_gram", "jumlah_blok", "total_denda"],
}
LOG_NAMA = "log_input"
LOG_KOLOM = ["id_aksi", "waktu_input", "petugas", "tabel", "id_record", "ringkasan", "status"]
URUTAN_FILE = ["transaksi", "pelanggan", "food_waste", "reservasi", "meja", "menu", "paket", "harga_paket"]

# ---- Aturan bisnis (sama dengan yang dipakai saat membuat data) ----
TARIF_DENDA = 50000     # per blok food waste
BLOK_GRAM = 100         # tiap 100 gram ATAU bagiannya = 1 blok
TARIF_OT = 50000        # per blok overtime (per meja)
BLOK_OT = 30            # tiap 30 menit ATAU bagiannya = 1 blok
PERSEN = {"Adult": 100, "Child": 70, "Senior": 80, "Toddler": 0}
BATAS_DINNER_MENIT = 17 * 60  # waktu_mulai >= 17:00 = Dinner
TIPE = ["Walk-in", "Booking"]
STATUS = ["Completed", "Cancelled", "No-show"]
METODE = ["QRIS", "Debit", "Kartu Kredit", "Cash"]
KOMBINASI_HARGA = [("Lunch", "Weekday"), ("Lunch", "Weekend"), ("Dinner", "Weekday"), ("Dinner", "Weekend")]

_LOCK = threading.RLock()


class DataError(ValueError):
    """Kesalahan validasi data yang aman ditampilkan ke pengguna."""


# ---------------------------------------------------------------------------
# Utilitas
# ---------------------------------------------------------------------------
def ke_menit(x) -> int:
    """'HH:MM' atau objek time/datetime -> menit sejak tengah malam."""
    if isinstance(x, str):
        h, m = x.split(":")[:2]
        return int(h) * 60 + int(m)
    return x.hour * 60 + x.minute


def dari_menit(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def rp(v) -> str:
    return "Rp " + f"{int(v):,}".replace(",", ".")


def angka(v) -> str:
    return f"{int(v):,}".replace(",", ".")


def sekarang() -> datetime:
    return datetime.now(WIB)


def _path(nama: str) -> Path:
    return DATA_DIR / f"{nama}.csv"


def kolom_file(nama: str) -> list[str]:
    return LOG_KOLOM if nama == LOG_NAMA else SKEMA[nama]


def baca(nama: str) -> pd.DataFrame:
    """Baca satu CSV sebagai teks. File belum ada -> DataFrame kosong dengan kolom yang benar."""
    p = _path(nama)
    if not p.exists():
        return pd.DataFrame(columns=kolom_file(nama), dtype=str)
    return pd.read_csv(p, dtype=str, keep_default_na=False)


def versi_data() -> tuple:
    """Penanda perubahan file (dipakai sebagai kunci cache dashboard)."""
    out = []
    for n in list(SKEMA) + [LOG_NAMA]:
        p = _path(n)
        out.append(p.stat().st_mtime_ns if p.exists() else 0)
    return tuple(out)


def id_berikut(df: pd.DataFrame, kolom: str, awalan: str, lebar: int, n: int = 1) -> list[str]:
    pola = re.compile(rf"^{re.escape(awalan)}(\d+)$")
    nomor = []
    for v in df[kolom]:
        m = pola.match(str(v))
        if m:
            nomor.append(int(m.group(1)))
    mulai = (max(nomor) if nomor else 0) + 1
    return [f"{awalan}{mulai + i:0{lebar}d}" for i in range(n)]


def _tulis(nama: str, df: pd.DataFrame):
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
    """Tulis beberapa file; jika ada yang gagal, kembalikan file yang sudah terlanjur berubah."""
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
    if tabel == "meja":
        return f"{r['id_meja']} · {r['kapasitas']} org · {r['area']} L{r['lantai']}"
    if tabel == "menu":
        return f"{r['nama_menu']} · {r['kategori']} · {r['sistem_penyajian']} · {r['status']}"
    if tabel == "paket":
        return f"{r['nama_paket']} · {r['durasi_menit']} menit"
    if tabel == "harga_paket":
        return f"{r['id_paket']} {r['waktu']} {r['hari']} · {rp(r['harga'])}"
    return ""


def _commit(petugas: str, baris_per_tabel: dict[str, list[dict]]) -> str:
    """Tambahkan baris ke tiap tabel + catat ke log. HARUS dipanggil di dalam _LOCK."""
    log = baca(LOG_NAMA)
    id_aksi = id_berikut(log, "id_aksi", "LOG", 4)[0]
    waktu = sekarang().strftime("%Y-%m-%d %H:%M:%S")
    baru, log_rows = {}, []
    for tabel, rows in baris_per_tabel.items():
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


# ---------------------------------------------------------------------------
# Perhitungan tagihan
# ---------------------------------------------------------------------------
def hitung_tagihan(tanggal: date, id_paket: str, mulai: int, selesai: int, komposisi: dict,
                   berat_gram: int, harga_df: pd.DataFrame, paket_df: pd.DataFrame) -> dict:
    """Hitung seluruh komponen tagihan sesuai aturan. `mulai`/`selesai` dalam menit sejak 00:00."""
    kom = {k: int(komposisi.get(k, 0) or 0) for k in PERSEN}
    if any(v < 0 for v in kom.values()):
        raise DataError("Jumlah pelanggan tidak boleh negatif.")
    orang = sum(kom.values())
    if orang < 1:
        raise DataError("Jumlah pelanggan minimal 1 orang.")
    if selesai <= mulai:
        raise DataError("Waktu selesai harus setelah waktu mulai.")
    berat_gram = int(berat_gram or 0)
    if berat_gram < 0:
        raise DataError("Berat sisa makanan tidak boleh negatif.")

    p = paket_df[paket_df["id_paket"] == id_paket]
    if p.empty:
        raise DataError(f"Paket {id_paket} tidak ditemukan di paket.csv.")
    durasi_paket = int(p.iloc[0]["durasi_menit"])

    waktu = "Lunch" if mulai < BATAS_DINNER_MENIT else "Dinner"
    hari = "Weekend" if tanggal.weekday() >= 5 else "Weekday"
    h = harga_df[(harga_df["id_paket"] == id_paket) & (harga_df["waktu"] == waktu) & (harga_df["hari"] == hari)]
    if h.empty:
        raise DataError(f"Harga untuk paket {id_paket} ({waktu}, {hari}) belum ada di harga_paket.csv.")
    id_harga, harga = h.iloc[0]["id_harga"], int(h.iloc[0]["harga"])

    rincian, subtotal = [], 0
    for kat in PERSEN:
        n = kom[kat]
        if n:
            satuan = int(harga * PERSEN[kat] / 100 / 1000 + 0.5) * 1000  # dibulatkan ke Rp1.000 terdekat
            sub = satuan * n
            subtotal += sub
            rincian.append({"kategori": kat, "jumlah": n, "persen": PERSEN[kat], "satuan": satuan, "subtotal": sub})

    durasi = selesai - mulai
    over = max(0, durasi - durasi_paket)
    blok_ot = math.ceil(over / BLOK_OT) if over else 0
    biaya_ot = blok_ot * TARIF_OT
    blok_waste = math.ceil(berat_gram / BLOK_GRAM) if berat_gram else 0
    denda = blok_waste * TARIF_DENDA

    return {
        "id_harga": id_harga, "waktu": waktu, "hari": hari, "harga": harga,
        "durasi": durasi, "durasi_paket": durasi_paket, "jumlah_orang": orang, "komposisi": kom,
        "rincian": rincian, "subtotal_paket": subtotal,
        "menit_overtime": over, "blok_overtime": blok_ot, "biaya_overtime": biaya_ot,
        "berat_gram": berat_gram, "blok_waste": blok_waste, "denda": denda,
        "total": subtotal + biaya_ot + denda,
    }


# ---------------------------------------------------------------------------
# Simpan data (semua append-only, dengan ID otomatis)
# ---------------------------------------------------------------------------
def simpan_reservasi(petugas, tanggal: date, jam, nama, jumlah, tipe, status, id_meja) -> str:
    nama = (nama or "").strip()
    if not nama:
        raise DataError("Nama pemesan wajib diisi.")
    jumlah = int(jumlah)
    if jumlah < 1:
        raise DataError("Jumlah orang minimal 1.")
    if tipe not in TIPE:
        raise DataError("Tipe kedatangan tidak valid.")
    if status not in STATUS:
        raise DataError("Status tidak valid.")
    if tipe == "Walk-in" and status != "Completed":
        raise DataError("Walk-in hanya boleh berstatus Completed. Tamu yang batal / tidak datang dicatat sebagai Booking.")
    with _LOCK:
        if id_meja not in set(baca("meja")["id_meja"]):
            raise DataError(f"Meja {id_meja} tidak ada di meja.csv.")
        rid = id_berikut(baca("reservasi"), "id_reservasi", "RS", 4)[0]
        row = {
            "id_reservasi": rid, "tanggal": tanggal.isoformat(), "jam": dari_menit(ke_menit(jam)), "id_meja": id_meja,
            "nama_pemesan": nama, "jumlah_orang": jumlah, "tipe_kedatangan": tipe, "status": status,
        }
        _commit(petugas, {"reservasi": [row]})
    return rid


def simpan_transaksi(petugas, id_reservasi: str, id_paket: str, mulai, selesai, komposisi: dict,
                     berat_gram: int, metode: str) -> dict:
    """Simpan 1 transaksi + baris pelanggan + 1 baris food_waste sekaligus."""
    if metode not in METODE:
        raise DataError("Metode pembayaran tidak valid.")
    with _LOCK:
        res = baca("reservasi")
        r = res[res["id_reservasi"] == id_reservasi]
        if r.empty:
            raise DataError(f"Reservasi {id_reservasi} tidak ditemukan.")
        r = r.iloc[0]
        if r["status"] != "Completed":
            raise DataError("Transaksi hanya untuk reservasi berstatus Completed.")
        trx = baca("transaksi")
        if id_reservasi in set(trx["id_reservasi"]):
            raise DataError(f"Reservasi {id_reservasi} sudah punya transaksi (mungkin sudah disimpan pegawai lain).")

        m1, m2 = ke_menit(mulai), ke_menit(selesai)
        t = hitung_tagihan(date.fromisoformat(r["tanggal"]), id_paket, m1, m2, komposisi, berat_gram,
                           baca("harga_paket"), baca("paket"))

        tid = id_berikut(trx, "id_transaksi", "TRX", 4)[0]
        cids = id_berikut(baca("pelanggan"), "id_customer", "CU", 4, n=len(t["rincian"]))
        fid = id_berikut(baca("food_waste"), "id_waste", "FW", 4)[0]

        trx_row = {
            "id_transaksi": tid, "tanggal": r["tanggal"], "id_reservasi": id_reservasi, "id_meja": r["id_meja"],
            "id_paket": id_paket, "id_harga": t["id_harga"], "waktu_mulai": dari_menit(m1), "waktu_selesai": dari_menit(m2),
            "durasi_makan_menit": t["durasi"], "jumlah_orang": t["jumlah_orang"], "subtotal_paket": t["subtotal_paket"],
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
        _commit(petugas, {"transaksi": [trx_row], "pelanggan": pel_rows, "food_waste": [fw_row]})
    return {"id_transaksi": tid, "id_customer": cids, "id_waste": fid, "total": t["total"]}


def simpan_meja(petugas, kapasitas, area, lantai) -> str:
    kapasitas, lantai = int(kapasitas), int(lantai)
    if kapasitas < 1:
        raise DataError("Kapasitas minimal 1 orang.")
    if not area:
        raise DataError("Area wajib diisi.")
    with _LOCK:
        mid = id_berikut(baca("meja"), "id_meja", "T", 2)[0]
        _commit(petugas, {"meja": [{"id_meja": mid, "kapasitas": kapasitas, "area": area, "lantai": lantai, "status": "Tersedia"}]})
    return mid


def simpan_menu(petugas, nama, kategori, paket_minimal, sistem, status) -> str:
    nama = (nama or "").strip()
    if not nama:
        raise DataError("Nama menu wajib diisi.")
    with _LOCK:
        menu = baca("menu")
        if nama.lower() in set(menu["nama_menu"].str.lower()):
            raise DataError(f"Menu '{nama}' sudah ada di menu.csv.")
        if paket_minimal not in set(baca("paket")["id_paket"]):
            raise DataError(f"Paket {paket_minimal} tidak ditemukan.")
        mid = id_berikut(menu, "id_menu", "M", 3)[0]
        _commit(petugas, {"menu": [{
            "id_menu": mid, "nama_menu": nama, "kategori": kategori, "paket_minimal": paket_minimal,
            "sistem_penyajian": sistem, "status": status,
        }]})
    return mid


def simpan_paket(petugas, nama, durasi, harga: dict) -> dict:
    """Paket baru + 4 baris harga (Lunch/Dinner x Weekday/Weekend)."""
    nama = (nama or "").strip()
    durasi = int(durasi)
    if not nama:
        raise DataError("Nama paket wajib diisi.")
    if durasi < 1:
        raise DataError("Durasi paket harus lebih dari 0 menit.")
    for k in KOMBINASI_HARGA:
        if int(harga.get(k, 0) or 0) <= 0:
            raise DataError(f"Harga {k[0]} {k[1]} harus lebih dari 0.")
    with _LOCK:
        paket = baca("paket")
        if nama.lower() in set(paket["nama_paket"].str.lower()):
            raise DataError(f"Paket '{nama}' sudah ada di paket.csv.")
        pid = id_berikut(paket, "id_paket", "P", 3)[0]
        hids = id_berikut(baca("harga_paket"), "id_harga", "H", 3, n=len(KOMBINASI_HARGA))
        hrows = [
            {"id_harga": hid, "id_paket": pid, "waktu": w, "hari": h, "harga": int(harga[(w, h)])}
            for hid, (w, h) in zip(hids, KOMBINASI_HARGA)
        ]
        _commit(petugas, {
            "paket": [{"id_paket": pid, "nama_paket": nama, "durasi_menit": durasi}],
            "harga_paket": hrows,
        })
    return {"id_paket": pid, "id_harga": hids}


# ---------------------------------------------------------------------------
# Rekap, log, batalkan
# ---------------------------------------------------------------------------
def rekap_tanggal(tgl: date) -> dict:
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
    """Hapus data dari aksi terakhir petugas dan tandai di log sebagai Dibatalkan."""
    with _LOCK:
        rows = aksi_terakhir(petugas)
        if not rows:
            return None
        idk = rows[0]["id_aksi"]
        per_tabel: dict[str, list[str]] = {}
        for r in rows:
            per_tabel.setdefault(r["tabel"], []).append(r["id_record"])

        trx, res = baca("transaksi"), baca("reservasi")
        if "reservasi" in per_tabel and trx["id_reservasi"].isin(per_tabel["reservasi"]).any():
            raise DataError("Reservasi ini sudah dipakai oleh sebuah transaksi, sehingga tidak bisa dibatalkan.")
        if "meja" in per_tabel and (res["id_meja"].isin(per_tabel["meja"]).any() or trx["id_meja"].isin(per_tabel["meja"]).any()):
            raise DataError("Meja ini sudah dipakai oleh data lain, sehingga tidak bisa dibatalkan.")
        if "paket" in per_tabel and trx["id_paket"].isin(per_tabel["paket"]).any():
            raise DataError("Paket ini sudah dipakai oleh transaksi, sehingga tidak bisa dibatalkan.")

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


def daftar_file() -> list[tuple[str, Path]]:
    """File CSV yang tersedia untuk diunduh: (nama, path)."""
    out = []
    for n in URUTAN_FILE + [LOG_NAMA]:
        p = _path(n)
        if p.exists():
            out.append((n, p))
    return out


def zip_semua() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, p in daftar_file():
            z.write(p, arcname=f"data/{n}.csv")
    return buf.getvalue()
