# AYCE-DASHBOARD — Data Fiktif

Periode data: 1 September 2026 – 7 Oktober 2026 (37 hari). Seluruh data fiktif, bukan data restoran sungguhan.

## Relasi antar file
- `reservasi.csv` mencatat SEMUA kedatangan (Booking dan Walk-in) beserta statusnya (Completed / Cancelled / No-show).
- `transaksi.csv` hanya ada untuk reservasi berstatus Completed (`id_reservasi` menghubungkan keduanya).
- `pelanggan.csv` memecah isi satu transaksi per kategori (Adult / Child / Senior / Toddler).
- `food_waste.csv` satu baris per transaksi pada data awal. Pesanan baru dari form belum membuat baris food waste (menunggu fitur 'selesai makan').
- `harga_paket.csv` = harga per paket x waktu (Lunch/Dinner) x hari (Weekday/Weekend); dipakai lewat `id_harga` di transaksi.
- `paket.csv`, `meja.csv`, `menu.csv` = master data.
- `topping.csv` = daftar topping + harga (ubah di sini untuk mengganti topping). `topping_pesanan.csv` = topping yang dipesan per transaksi.
- `transaksi.csv` punya kolom `subtotal_topping` (data lama otomatis diisi 0 saat dibaca).

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

# Aplikasi: Login, Input Pesanan, dan Unduh (EKSPERIMEN)

Jalankan: `streamlit run app.py`

## Struktur file
```
AYCE-DASHBOARD/
├── app.py            # titik masuk: login + menu per peran
├── auth.py           # login (Secrets atau akun demo)
├── store.py          # baca/tulis CSV, ID otomatis, hitung harga, log, batalkan
├── input_data.py     # halaman Input Pesanan (pegawai)
├── data_masuk.py     # halaman Data Masuk & Unduh (bos)
├── dashboard.py      # halaman Dashboard
├── tema.py           # warna & CSS
├── requirements.txt
├── .streamlit/config.toml  (+ secrets.toml.example)
└── data/*.csv        # + log_input.csv (dibuat otomatis saat input pertama)
```
CSV boleh berada di folder `data/` ATAU sejajar dengan `app.py`; aplikasi memakai satu folder secara konsisten (lihat `_tentukan_data_dir` di `store.py`).

## Akun
| Peran | Username | Password (DEMO) | Halaman |
|---|---|---|---|
| Pegawai | `pegawai` | `pegawai123` | Input Pesanan, Dashboard |
| Bos | `bos` | `bos123` | Dashboard, Data Masuk & Unduh |

Akun demo dipakai jika Secrets belum diisi. **Ganti lewat Secrets** (contoh: `.streamlit/secrets.toml.example`) sebelum aplikasi dibuka ke orang lain.

## Form Input Pesanan (pegawai)
1. **Nama pemesan** → **Walk-in / Reservasi** → **Jumlah orang**
2. **Paket** Reguler / Premium / Supreme (tampil batas durasi makan & harga per orang)
3. **Topping** (jumlah porsi tiap topping, tampil harga)
4. **Rincian harga** (paket + topping + total) → **Simpan**

*Opsi lanjutan* (boleh diabaikan): tanggal & jam manual (default sekarang), status kedatangan (Completed / Cancelled / No-show untuk Reservasi), pilih meja (default otomatis), anak/lansia/balita, metode pembayaran.

Sekali simpan mengisi: `reservasi.csv` · `transaksi.csv` · `pelanggan.csv` · `topping_pesanan.csv` (bila ada topping). Cancelled / No-show hanya mengisi `reservasi.csv`.
Overtime dan denda food waste belum dihitung (0) karena belum ada langkah "selesai makan".

## Panduan ubah mandiri
Setiap file kode punya kotak **PETA UBAH CEPAT** di bagian atas. Cari juga kata `UBAH:` di semua file.

| Mau ubah | Lokasi |
|---|---|
| Daftar / harga / status topping | `data/topping.csv` |
| Nama paket, durasi, harga | `data/paket.csv`, `data/harga_paket.csv` |
| Tarif overtime, diskon anak/lansia, batas Lunch/Dinner | `store.py` → *ATURAN BISNIS* |
| Pilihan metode pembayaran | `store.py` → `METODE` |
| Jam buka/tutup/last order (peringatan) | `input_data.py` → `JAM_BUKA`, `JAM_TUTUP`, `LAST_ORDER` |
| Teks & urutan form input | `input_data.py` → `_form_pesanan()` |
| Tanggal paling awal di filter dashboard | `dashboard.py` → `TANGGAL_PALING_AWAL` |
| Batas jam shift Pagi/Malam | `dashboard.py` → `BATAS_SHIFT_JAM` |
| Rumus KPI & grafik | `dashboard.py` (blok KPI / BAR CHART / LINE CHART) |
| Username & password | `auth.py` → `AKUN_DEMO` atau Secrets |
| Halaman tiap peran | `app.py` → `AKSES` |
| Warna, kotak, sudut | `tema.py` → *PALET WARNA* dan `_CSS` |
| Nama brand | `tema.py` → `brand_html()` |

## Catatan penting
- Data disimpan sebagai file CSV di server. Di Streamlit Community Cloud file itu **hilang saat aplikasi restart / redeploy / tertidur lama**. Unduh CSV secara berkala (halaman Bos).
- Halaman Bos → Unduh CSV → *Diagnostik lokasi data* menunjukkan dari file mana tiap tabel dibaca (berguna jika jumlah data terlihat janggal).
- `ayce.db` hanya dipakai sebagai cadangan baca bila CSV tidak ada; input tidak menulis ke `ayce.db`.
- Login ini sederhana (tanpa pemulihan password) — untuk eksperimen.
