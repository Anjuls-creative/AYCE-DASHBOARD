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
- `reservasi_online.csv` = reservasi dari akun pelanggan (dibuat otomatis): siapa, kapan diinput, jam & meja reservasi, status `Aktif / Dibatalkan / Datang / Selesai / No-show`. Ikut bisa diunduh (difilter per tanggal reservasi).

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

# Aplikasi: 3 Peran (Pegawai, Bos, Pelanggan) — EKSPERIMEN

Jalankan: `streamlit run app.py`

## Struktur file
```
AYCE-DASHBOARD/
├── app.py              # titik masuk: login + halaman per peran + pilihan tema
├── auth.py             # login (Secrets atau akun demo), 3 peran
├── store.py            # baca/tulis CSV, harga, reservasi online, pesanan berjalan, overtime, log, unduh
├── input_data.py       # halaman Input Pesanan (pegawai)
├── data_masuk.py       # halaman Data Masuk & Unduh (bos)
├── dashboard.py        # halaman Dashboard (pegawai & bos)
├── pelanggan.py        # halaman Reservasi Online (pelanggan)
├── tema.py             # warna & CSS pegawai/bos (peach + oranye)
├── tema_pelanggan.py   # tampilan khusus pelanggan (hijau tua + krem + emas, huruf serif)
├── requirements.txt
├── .streamlit/config.toml  (+ secrets.toml.example)
└── data/*.csv          # + log_input.csv, pesanan_berjalan.csv, reservasi_online.csv (dibuat otomatis)
```
CSV boleh berada di folder `data/` ATAU sejajar dengan `app.py`; aplikasi memakai satu folder secara konsisten (lihat `_tentukan_data_dir` di `store.py`).

## Akun
| Peran | Username | Password (DEMO) | Halaman |
|---|---|---|---|
| Pegawai | `pegawai` | `pegawai123` | Input Pesanan, Dashboard |
| Bos | `bos` | `bos123` | Dashboard, Data Masuk & Unduh |
| Pelanggan | `pelanggan1`, `pelanggan2`, `pelanggan3` | `pelanggan123` | Reservasi Online (tanpa menu & tanpa statistik) |

Akun demo dipakai jika Secrets belum diisi. **Jika Secrets sudah diisi, akun pelanggan juga harus ditambahkan di sana** (lihat `.streamlit/secrets.toml.example`), karena Secrets menggantikan akun demo seluruhnya. Ganti password sebelum aplikasi dibuka ke orang lain.

## Reservasi online (pelanggan)
Tampilan sengaja berbeda total dari pegawai/bos (hijau tua + krem + emas, huruf serif, satu kolom, tanpa statistik).
1. **Buat Reservasi** — Data pemesan (nama, jumlah orang, komposisi usia) → Tanggal & jam → Paket (batas durasi, harga, topping/minuman/dessert yang didapat) → Meja (hanya meja yang kosong pada tanggal & jam itu) → Rincian harga sementara (belum termasuk overtime & denda food waste) → **Konfirmasi Reservasi**.
2. **Reservasi Saya** — otomatis terbuka setelah konfirmasi. Riwayat reservasi akun itu saja, dengan **hitung mundur** (hari / jam / menit), **pengingat 30 menit sebelum** jam reservasi, dan tombol **Batalkan** yang hanya ada selama jam reservasi belum tiba.
- Harga paket **dikunci** sesuai tanggal & jam reservasi. Meja ditahan untuk pemesan selama durasi paket.
- Reservasi dibatalkan pelanggan → tercatat di `reservasi.csv` sebagai Booking `Cancelled`.
- Reservasi baru dicatat di `reservasi_online.csv`; **belum** masuk CSV laporan sampai pelanggan selesai makan dan membayar.

## Alur pesanan (pegawai)
**Pesanan Baru** → pilih tipe kedatangan:
- **Walk-in** — nama → jumlah orang → paket → fasilitas paket → rincian harga → **Mulai Pesanan**. Timer langsung jalan.
- **Reservasi (sudah datang)** — cari nama pelanggan (tampil jam reservasi, kapan ia memesan, akun, paket, meja) → **Konfirmasi Pesanan & Mulai Timer**. Meja bisa diganti bila meja reservasi masih terpakai. Jika jam reservasi sudah lewat, tersedia tombol **Tandai No-show**.

**Sedang Makan** — tiap pesanan punya timer mundur sesuai batas paket (Reguler/Premium 90 menit, Supreme 120 menit). Tekan **Selesai makan** → isi berat makanan tersisa & metode bayar → overtime dan denda dihitung otomatis → **Konfirmasi Pembayaran**. **Baru sekarang** data masuk ke `reservasi.csv`, `transaksi.csv`, `pelanggan.csv`, `food_waste.csv`.

- **Overtime**: Rp50.000 per 30 menit (atau bagiannya), per meja. Toleransi bisa diatur (`TOLERANSI_OT_MENIT`).
- **Denda food waste**: Rp50.000 per 100 gram (atau bagiannya).
- **Usia**: anak-anak 6–8 tahun harga 70%, balita 0–5 tahun gratis, lansia 80%; di luar itu dihitung dewasa.
- **Batalkan input terakhir** (Riwayat Saya): pembayaran yang dibatalkan mengembalikan pesanan ke "Sedang Makan"; No-show yang dibatalkan mengembalikan reservasinya ke Aktif.
- Pesanan berjalan disimpan di `pesanan_berjalan.csv` sehingga tetap ada saat halaman di-refresh dan terlihat semua pegawai.

## Bos
- **Data Baru Masuk**: pesanan sedang berjalan, **reservasi online**, aktivitas input, dan isi baris baru per tabel.
- **Unduh CSV**: **Semua tanggal / Satu tanggal / Rentang tanggal** (sampai hari ini walau belum ada datanya). `transaksi`, `reservasi`, `reservasi_online`, `pelanggan`, `food_waste`, dan `log_input` ikut difilter; file master selalu lengkap.

## Panduan ubah mandiri
Setiap file kode punya kotak **PETA UBAH CEPAT** di bagian atas. Cari juga kata `UBAH:` di semua file.

| Mau ubah | Lokasi |
|---|---|
| Akun pelanggan (tambah / ganti password) | `auth.py` → `AKUN_DEMO` atau Secrets (role harus `pelanggan`) |
| Jam buka, jam kedatangan terakhir, jam tutup | `store.py` → `JAM_BUKA`, `LAST_ORDER`, `JAM_TUTUP` |
| Reservasi minimal berapa menit dari sekarang / maksimal berapa hari | `store.py` → `RESERVASI_MIN_MENIT`, `RESERVASI_MAKS_HARI` |
| Pengingat berapa menit sebelum jam reservasi | `store.py` → `PENGINGAT_MENIT` |
| Meja yang ditawarkan ke pelanggan (kelebihan kursi) | `store.py` → `MEJA_LEBIH_MAKS` |
| Topping / minuman per paket (tambah, hapus, tandai Habis) | `data/topping.csv`, `data/minuman.csv` (kolom `paket_minimal`, `status`) |
| Nama paket, durasi, harga | `data/paket.csv`, `data/harga_paket.csv` |
| Tarif & blok overtime, toleransi, denda food waste | `store.py` → *ATURAN BISNIS* (`TARIF_OT`, `BLOK_OT`, `TOLERANSI_OT_MENIT`, `TARIF_DENDA`, `BLOK_GRAM`) |
| Diskon anak/lansia/balita & keterangan usia | `store.py` → `PERSEN`, `USIA` |
| Batas jam Lunch/Dinner, aturan weekend | `store.py` → `BATAS_DINNER_MENIT`, `konteks_harga()` |
| Cara memilih meja otomatis (walk-in), jeda bersih meja | `store.py` → `pilih_meja_otomatis()`, `JEDA_BERSIH` |
| Tanggal paling awal di filter (dashboard & unduh) | `store.py` → `TANGGAL_PALING_AWAL` |
| Pilihan metode pembayaran | `store.py` → `METODE` |
| Teks & urutan form pelanggan, kotak hitung mundur | `pelanggan.py` → `_form_reservasi()`, `_HITUNG_HTML` |
| Warna, huruf, banner halaman pelanggan | `tema_pelanggan.py` → *PALET WARNA*, `hero()` |
| Teks & urutan form pegawai, warna timer | `input_data.py` → `_form_pesanan()`, `_TIMER_HTML` |
| Batas jam shift Pagi/Malam | `dashboard.py` → `BATAS_SHIFT_JAM` |
| Rumus KPI & grafik | `dashboard.py` (blok KPI / BAR CHART / LINE CHART) |
| Halaman tiap peran | `app.py` → `AKSES` |
| Warna pegawai/bos, kotak, sudut | `tema.py` → *PALET WARNA* dan `_CSS` |
| Nama brand | `tema.py` → `brand_html()`, `tema_pelanggan.py` → `hero()` |

## Catatan penting
- Data disimpan sebagai file CSV di server. Di Streamlit Community Cloud file itu **hilang saat aplikasi restart / redeploy / tertidur lama** — termasuk reservasi online dan pesanan yang belum dibayar. Unduh CSV secara berkala (halaman Bos).
- Pengingat 30 menit dan hitung mundur berjalan di browser selama halaman reservasi terbuka (tidak ada notifikasi push saat halaman ditutup).
- Halaman Bos → Unduh CSV → *Diagnostik lokasi data* menunjukkan dari file mana tiap tabel dibaca.
- `ayce.db` hanya dipakai sebagai cadangan baca bila CSV tidak ada; input tidak menulis ke `ayce.db`.
- Login ini sederhana (tanpa pemulihan password) — untuk eksperimen.
