# AYCE-DASHBOARD — Data Fiktif

Periode data: 1 September 2026 – 7 Oktober 2026 (37 hari). Seluruh data fiktif, bukan data restoran sungguhan.

## Relasi antar file
- `reservasi.csv` mencatat SEMUA kedatangan (Booking dan Walk-in) beserta statusnya (Completed / Cancelled / No-show).
- `transaksi.csv` hanya ada untuk reservasi berstatus Completed (`id_reservasi` menghubungkan keduanya).
- `pelanggan.csv` memecah isi satu transaksi per kategori (Adult / Child / Senior / Toddler).
- `food_waste.csv` satu baris per transaksi (berat 0 = tidak ada sisa), termasuk pesanan baru dari aplikasi.
- `harga_paket.csv` = harga per paket x waktu (Lunch/Dinner) x hari (Weekday/Weekend); dipakai lewat `id_harga` di transaksi.
- `paket.csv`, `meja.csv`, `menu.csv` = master data.
- `topping.csv` dan `minuman.csv` = topping & minuman per paket. **Sudah termasuk harga paket (tanpa biaya tambahan)**; kolom `paket_minimal` menentukan paket terendah yang boleh mengambilnya (P001 Reguler, P002 Premium, P003 Supreme) dan paket di atasnya otomatis boleh juga.
- `pesanan_berjalan.csv` = file KERJA sementara (dibuat otomatis): pesanan yang sedang makan / menunggu bayar. Dihapus per pesanan setelah dibayar; tidak ikut diunduh.

## Aturan yang dipakai (eksplisit)
1. **Weekend** = Sabtu & Minggu. Tanggal merah belum dihitung.
2. **Lunch / Dinner** ditentukan dari `waktu_mulai` (saat timer dimulai): sebelum 17:00 = Lunch, 17:00 ke atas = Dinner.
3. **Harga per kategori** = harga paket x persen (Adult 100%, Child 70%, Senior 80%, Toddler 0%), dibulatkan ke Rp1.000 terdekat.
4. **Denda food waste**: Rp50.000 per blok 100 gram. Setiap 100 gram ATAU bagiannya dihitung 1 blok (`jumlah_blok = ceil(berat / 100)`). Contoh: 250 gram = 3 blok = Rp150.000.
5. **Overtime**: Rp50.000 per blok 30 menit, setiap 30 menit ATAU bagiannya dihitung 1 blok, per meja, tanpa toleransi (`menit_overtime` = durasi makan - durasi paket).
6. **Total bayar** = `subtotal_paket` + `biaya_overtime` + `denda_food_waste` (belum termasuk pajak/service).
7. **Jam operasional** 11:00–22:00. Last order / duduk terakhir 20:30. Paket Supreme (120 menit) tidak diberikan untuk waktu mulai setelah 20:00.
8. **Status meja** di `meja.csv` hanya nilai awal. Status "Terisi" dihitung aplikasi dari `waktu_mulai` dan `waktu_selesai` di transaksi (tidak ada dua transaksi yang bentrok di meja yang sama).



---

# Aplikasi: Login, Input Pesanan (timer), dan Unduh (EKSPERIMEN)

Jalankan: `streamlit run app.py`

## Struktur file
```
AYCE-DASHBOARD/
├── app.py            # titik masuk: login + menu per peran
├── auth.py           # login (Secrets atau akun demo)
├── store.py          # baca/tulis CSV, harga, pesanan berjalan, overtime, log, unduh
├── input_data.py     # halaman Input Pesanan (pegawai)
├── data_masuk.py     # halaman Data Masuk & Unduh (bos)
├── dashboard.py      # halaman Dashboard
├── tema.py           # warna & CSS
├── requirements.txt
├── .streamlit/config.toml  (+ secrets.toml.example)
└── data/*.csv        # + log_input.csv & pesanan_berjalan.csv (dibuat otomatis)
```
CSV boleh berada di folder `data/` ATAU sejajar dengan `app.py`; aplikasi memakai satu folder secara konsisten (lihat `_tentukan_data_dir` di `store.py`).

## Akun
| Peran | Username | Password (DEMO) | Halaman |
|---|---|---|---|
| Pegawai | `pegawai` | `pegawai123` | Input Pesanan, Dashboard |
| Bos | `bos` | `bos123` | Dashboard, Data Masuk & Unduh |

Akun demo dipakai jika Secrets belum diisi. **Ganti lewat Secrets** (contoh: `.streamlit/secrets.toml.example`) sebelum aplikasi dibuka ke orang lain.

## Alur pesanan (pegawai)
1. **🧾 Pesanan Baru** — nama pemesan → Walk-in / Reservasi → jumlah orang → paket (batas durasi & harga tampil) → fasilitas paket (topping, minuman, dessert yang sudah termasuk) → rincian harga → **Mulai Pesanan**. Timer langsung jalan. **Belum masuk CSV laporan.**
2. **⏱️ Sedang Makan** — tiap pesanan punya timer mundur sesuai batas paket (Reguler/Premium 90 menit, Supreme 120 menit). Tekan **Selesai makan** → timer berhenti & jam selesai dikunci.
3. Isi **berat makanan tersisa** dan **metode bayar** → overtime & denda dihitung otomatis → **Konfirmasi Pembayaran**. **Baru sekarang** data masuk ke `reservasi.csv`, `transaksi.csv`, `pelanggan.csv`, `food_waste.csv`.

- **Overtime**: lewat batas paket → Rp50.000 per 30 menit (atau bagiannya), per meja. Toleransi bisa diatur (`TOLERANSI_OT_MENIT`).
- **Denda food waste**: Rp50.000 per 100 gram (atau bagiannya).
- **Usia**: anak-anak 6–8 tahun harga 70%, balita 0–5 tahun gratis, lansia 80%; di luar itu dihitung dewasa.
- **Reservasi Cancelled / No-show** (Opsi lanjutan) langsung dicatat ke `reservasi.csv` tanpa timer.
- **Batalkan input terakhir** (tab Riwayat Saya): jika yang dibatalkan sebuah pembayaran, pesanannya kembali ke "Sedang Makan" (Menunggu bayar) agar bisa dibayar ulang.
- Pesanan berjalan disimpan di `pesanan_berjalan.csv`, sehingga tetap ada saat halaman di-refresh dan terlihat oleh semua pegawai (dan bos, read-only).

## Bos
- **Data Baru Masuk**: pesanan sedang berjalan, aktivitas input, dan isi baris baru per tabel.
- **Unduh CSV**: pilih **Semua tanggal / Satu tanggal / Rentang tanggal** (bisa sampai hari ini walau belum ada datanya). `transaksi`, `reservasi`, `pelanggan`, `food_waste`, dan `log_input` ikut difilter; file master (meja, menu, paket, topping, minuman, harga) selalu lengkap. Unduh per file atau semuanya (ZIP).

## Panduan ubah mandiri
Setiap file kode punya kotak **PETA UBAH CEPAT** di bagian atas. Cari juga kata `UBAH:` di semua file.

| Mau ubah | Lokasi |
|---|---|
| Topping / minuman per paket (tambah, hapus, tandai Habis) | `data/topping.csv`, `data/minuman.csv` (kolom `paket_minimal`, `status`) |
| Nama paket, durasi, harga | `data/paket.csv`, `data/harga_paket.csv` |
| Tarif & blok overtime, toleransi, denda food waste | `store.py` → *ATURAN BISNIS* (`TARIF_OT`, `BLOK_OT`, `TOLERANSI_OT_MENIT`, `TARIF_DENDA`, `BLOK_GRAM`) |
| Diskon anak/lansia/balita & keterangan usia | `store.py` → `PERSEN`, `USIA` |
| Batas jam Lunch/Dinner, aturan weekend | `store.py` → `BATAS_DINNER_MENIT`, `konteks_harga()` |
| Cara memilih meja otomatis, jeda bersih meja | `store.py` → `pilih_meja_otomatis()`, `JEDA_BERSIH` |
| Tanggal paling awal di filter (dashboard & unduh) | `store.py` → `TANGGAL_PALING_AWAL` |
| Pilihan metode pembayaran | `store.py` → `METODE` |
| Jam buka/tutup/last order (peringatan) | `input_data.py` → `JAM_BUKA`, `JAM_TUTUP`, `LAST_ORDER` |
| Teks & urutan form, warna timer | `input_data.py` → `_form_pesanan()`, `_TIMER_HTML` |
| Batas jam shift Pagi/Malam | `dashboard.py` → `BATAS_SHIFT_JAM` |
| Rumus KPI & grafik | `dashboard.py` (blok KPI / BAR CHART / LINE CHART) |
| Username & password | `auth.py` → `AKUN_DEMO` atau Secrets |
| Halaman tiap peran | `app.py` → `AKSES` |
| Warna, kotak, sudut | `tema.py` → *PALET WARNA* dan `_CSS` |
| Nama brand | `tema.py` → `brand_html()` |

## Catatan penting
- Data disimpan sebagai file CSV di server. Di Streamlit Community Cloud file itu **hilang saat aplikasi restart / redeploy / tertidur lama** — termasuk pesanan yang belum dibayar. Unduh CSV secara berkala (halaman Bos).
- Halaman Bos → Unduh CSV → *Diagnostik lokasi data* menunjukkan dari file mana tiap tabel dibaca (berguna jika jumlah data terlihat janggal).
- `ayce.db` hanya dipakai sebagai cadangan baca bila CSV tidak ada; input tidak menulis ke `ayce.db`.
- Login ini sederhana (tanpa pemulihan password) — untuk eksperimen.
