# AYCE-DASHBOARD — Data Fiktif

Periode data: 1 September 2026 – 7 Oktober 2026 (37 hari). Seluruh data fiktif, bukan data restoran sungguhan.

## Relasi antar file
- `reservasi.csv` mencatat SEMUA kedatangan (Booking dan Walk-in) beserta statusnya (Completed / Cancelled / No-show).
- `transaksi.csv` hanya ada untuk reservasi berstatus Completed (`id_reservasi` menghubungkan keduanya).
- `pelanggan.csv` memecah isi satu transaksi per kategori (Adult / Child / Senior / Toddler).
- `food_waste.csv` satu baris per transaksi (berat 0 = tidak ada sisa).
- `harga_paket.csv` = harga per paket x waktu (Lunch/Dinner) x hari (Weekday/Weekend); dipakai lewat `id_harga` di transaksi.
- `paket.csv`, `meja.csv`, `menu.csv` = master data.

## Aturan yang dipakai (eksplisit)
1. **Weekend** = Sabtu & Minggu. Tanggal merah belum dihitung.
2. **Lunch / Dinner** ditentukan dari `waktu_mulai` (saat timer dimulai): sebelum 17:00 = Lunch, 17:00 ke atas = Dinner.
3. **Harga per kategori** = harga paket x persen (Adult 100%, Child 70%, Senior 80%, Toddler 0%), dibulatkan ke Rp1.000 terdekat.
4. **Denda food waste**: Rp50.000 per blok 100 gram. Setiap 100 gram ATAU bagiannya dihitung 1 blok (`jumlah_blok = ceil(berat / 100)`). Contoh: 250 gram = 3 blok = Rp150.000.
5. **Overtime**: Rp50.000 per blok 30 menit, setiap 30 menit ATAU bagiannya dihitung 1 blok, per meja, tanpa toleransi (`menit_overtime` = durasi makan - durasi paket).
6. **Total bayar** = `subtotal_paket` + `biaya_overtime` + `denda_food_waste` (belum termasuk pajak/service).
7. **Jam operasional** 11:00–22:00. Last order / duduk terakhir 20:30. Paket Supreme (120 menit) tidak diberikan untuk waktu mulai setelah 20:00.
8. **Status meja** di `meja.csv` hanya nilai awal. Status "Terisi" dihitung aplikasi dari `waktu_mulai` dan `waktu_selesai` di transaksi (tidak ada dua transaksi yang bentrok di meja yang sama).
