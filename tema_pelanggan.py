"""
tema_pelanggan.py — TAMPILAN KHUSUS AKUN PELANGGAN (reservasi online).

Sengaja dibuat SANGAT BERBEDA dari tampilan pegawai/bos (tema.py: peach + oranye + panel bulat):
  hijau tua + krem + emas, huruf serif untuk judul, satu kolom sempit, tanpa menu samping.
Dipasang hanya untuk peran "pelanggan" (lihat app.py).

╔══════════════════════ PETA UBAH CEPAT ═══════════════════════╗
║ Mau ubah ...                       → cari bagian ...          ║
║ • Warna hijau / krem / emas        → "PALET WARNA" (di bawah) ║
║ • Nama restoran & teks banner      → hero()                   ║
║ • Lebar halaman pelanggan (780px)  → ".block-container" di _CSS║
║ • Bentuk kartu & nomor langkah     → ".pl-step", "pl_card_"   ║
║ • Jenis huruf judul (serif)        → @import & 'Playfair      ║
║                                      Display' di _CSS         ║
╚═══════════════════════════════════════════════════════════════╝
Cari kata "UBAH:" untuk menemukan nilai yang biasa Anda ganti.
"""

from __future__ import annotations

from html import escape

import streamlit as st

# ===== PALET WARNA =====
# UBAH: kode warna di bawah dipakai lewat token __NAMA__ di dalam _CSS (diganti otomatis).
HIJAU_TUA = "#0B3B2E"   # banner, judul, kotak total
HIJAU = "#14594A"       # tombol utama, badge aktif
KREM = "#F7F2E8"        # latar halaman
KARTU = "#FFFDF8"       # latar kartu
GARIS = "#E8DFC8"       # garis tepi kartu
EMAS = "#C9A24A"        # nomor langkah, garis aksen
TEKS_REDUP = "#7A7260"  # teks keterangan

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700;800&family=Inter:wght@400;500;600;700&display=swap');

html, body, .stApp, .stMarkdown, .stMarkdown p, label, [data-testid="stCaptionContainer"] {
    font-family: 'Inter', sans-serif;
}

/* ---------- Kerangka halaman: satu kolom sempit, tanpa menu samping ---------- */
.stApp { background: __KREM__; }
header[data-testid="stHeader"] { display: none; }
#MainMenu, footer { visibility: hidden; }
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] { display: none !important; }
.block-container {
    max-width: 780px; margin: 0 auto; padding: 1.2rem 1.1rem 4rem 1.1rem;
    background: transparent; box-shadow: none; border-radius: 0;
}

/* ---------- Banner ---------- */
.pl-hero {
    position: relative; overflow: hidden; border-radius: 18px; padding: 28px 26px 24px 26px; color: __KREM__;
    background:
        radial-gradient(circle at 92% 8%, rgba(201,162,74,0.30) 0 16%, transparent 17%),
        radial-gradient(circle at 78% 120%, rgba(247,242,232,0.10) 0 30%, transparent 31%),
        linear-gradient(135deg, __HIJAU_TUA__ 0%, #14594A 62%, #1B6E58 100%);
}
.pl-kicker { letter-spacing: 0.24em; font-size: 0.68rem; color: #E3C77B; font-weight: 700; text-transform: uppercase; }
.pl-hero-title { font-family: 'Playfair Display', serif; font-size: 2.05rem; font-weight: 700; line-height: 1.15; margin: 0.35rem 0 0.45rem 0; }
.pl-hero-sub { font-size: 0.9rem; opacity: 0.92; line-height: 1.5; }

/* ---------- Kartu (container ber-key "pl_card_*") ---------- */
[class*="st-key-pl_card_"] {
    background: __KARTU__; border: 1px solid __GARIS__; border-radius: 14px; padding: 20px 22px 12px 22px;
}
.pl-step { display: flex; gap: 12px; align-items: center; margin-bottom: 0.55rem; }
.pl-step-no {
    width: 30px; height: 30px; border-radius: 50%; flex: none; background: __EMAS__; color: __HIJAU_TUA__;
    font-family: 'Playfair Display', serif; font-weight: 800; display: flex; align-items: center; justify-content: center;
}
.pl-step-title { font-family: 'Playfair Display', serif; font-size: 1.15rem; font-weight: 700; color: __HIJAU_TUA__; line-height: 1.2; }
.pl-step-sub { font-size: 0.78rem; color: __TEKS_REDUP__; }

/* ---------- Kotak ringkasan ---------- */
.pl-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 0.5rem 0 0.8rem 0; }
.pl-tile { background: __KREM__; border: 1px solid __GARIS__; border-radius: 12px; padding: 12px 14px; }
.pl-t-l { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.08em; color: __TEKS_REDUP__; font-weight: 600; }
.pl-t-v { font-family: 'Playfair Display', serif; font-size: 1.3rem; font-weight: 700; color: __HIJAU_TUA__; line-height: 1.3; }
.pl-t-s { font-size: 0.72rem; color: #8C8470; }
.pl-tile-total { background: __HIJAU_TUA__; border-color: __HIJAU_TUA__; }
.pl-tile-total .pl-t-l { color: #E3C77B; }
.pl-tile-total .pl-t-v { color: #FFFFFF; }
.pl-tile-total .pl-t-s { color: #CFE3DA; }

/* ---------- Fasilitas paket ---------- */
.pl-fas-judul { font-weight: 700; color: __HIJAU_TUA__; font-size: 0.85rem; border-bottom: 2px solid __EMAS__; display: inline-block; margin-bottom: 0.35rem; }
.pl-fas-item { font-size: 0.82rem; color: #3B3A33; line-height: 1.65; }
.pl-fas-baru { color: #A9780D; font-weight: 700; }
.pl-fas-habis { color: #A39B86; text-decoration: line-through; }

/* ---------- Lencana status ---------- */
.pl-badge { display: inline-block; padding: 3px 11px; border-radius: 999px; font-size: 0.7rem; font-weight: 700; margin-left: 8px; vertical-align: middle; }
.pl-b-aktif { background: #E3F1EA; color: __HIJAU__; }
.pl-b-datang { background: #FFF1D6; color: #9A6A00; }
.pl-b-selesai { background: #E8EAE6; color: #4A5A52; }
.pl-b-batal { background: #FBE4E1; color: #B3382C; }
.pl-b-noshow { background: #ECE8DE; color: #7A7260; }
.pl-res-title { font-family: 'Playfair Display', serif; font-size: 1.15rem; font-weight: 700; color: __HIJAU_TUA__; }
.pl-res-sub { font-size: 0.8rem; color: __TEKS_REDUP__; line-height: 1.6; margin-bottom: 0.4rem; }
.pl-kosong { text-align: center; color: __TEKS_REDUP__; padding: 1.2rem 0.5rem; font-size: 0.9rem; }

/* ---------- Tombol & pilihan berwarna hijau (menggantikan oranye bawaan) ---------- */
.stApp button[kind="primary"], .stApp [data-testid="stBaseButton-primary"], .stApp [data-testid="stBaseButton-primaryFormSubmit"] {
    background-color: __HIJAU__ !important; border-color: __HIJAU__ !important; color: #FFFFFF !important; border-radius: 10px; font-weight: 700;
}
.stApp button[kind="primary"]:hover, .stApp [data-testid="stBaseButton-primary"]:hover { background-color: __HIJAU_TUA__ !important; }
.stApp button[kind="secondary"], .stApp [data-testid="stBaseButton-secondary"] {
    border-radius: 10px; border: 1px solid #CFC4A6; color: __HIJAU_TUA__; background: __KARTU__; font-weight: 600;
}
[data-baseweb="radio"]:has(input:checked) > div:first-child { background-color: __HIJAU__ !important; border-color: __HIJAU__ !important; }
[data-baseweb="checkbox"]:has(input:checked) > div:first-child { background-color: __HIJAU__ !important; border-color: __HIJAU__ !important; }

/* ---------- Pilihan tampilan (radio berbentuk pil) ---------- */
[class*="st-key-pl_view"] [role="radiogroup"] { gap: 0.5rem; }
[class*="st-key-pl_view"] [role="radiogroup"] label {
    background: __KARTU__; border: 1px solid #D9CFB4; border-radius: 999px; padding: 0.4rem 1.05rem; margin: 0;
}
[class*="st-key-pl_view"] [role="radiogroup"] label > div:first-child { display: none; }
[class*="st-key-pl_view"] [role="radiogroup"] label:has(input:checked) { background: __HIJAU__; border-color: __HIJAU__; }
[class*="st-key-pl_view"] [role="radiogroup"] label:has(input:checked) p { color: #FFFFFF; }
[class*="st-key-pl_view"] [role="radiogroup"] label p { font-weight: 600; font-size: 0.88rem; }
"""

for _token, _nilai in {
    "__KREM__": KREM, "__KARTU__": KARTU, "__GARIS__": GARIS, "__EMAS__": EMAS,
    "__HIJAU_TUA__": HIJAU_TUA, "__HIJAU__": HIJAU, "__TEKS_REDUP__": TEKS_REDUP,
}.items():
    _CSS = _CSS.replace(_token, _nilai)
_CSS_MIN = "\n".join(line for line in _CSS.splitlines() if line.strip())


def terapkan():
    """Pasang tema pelanggan. Dipanggil di app.py hanya untuk peran 'pelanggan'."""
    st.markdown(f"<style>{_CSS_MIN}</style>", unsafe_allow_html=True)


def hero(nama: str):
    """
    Banner atas halaman pelanggan.
    UBAH: nama restoran / tagline / sapaan ada di teks di bawah.
    """
    st.markdown(
        '<div class="pl-hero">'
        '<div class="pl-kicker">Reservasi Online</div>'
        '<div class="pl-hero-title">Pesan Meja Anda<br>di AYCE Dash</div>'
        f'<div class="pl-hero-sub">Halo, <b>{escape(nama)}</b>. Pilih tanggal, paket, dan meja — semua makan sepuasnya '
        'dengan satu harga paket.</div></div>',
        unsafe_allow_html=True,
    )


def langkah(no: int, judul: str, sub: str = ""):
    """Judul langkah bernomor di dalam kartu."""
    st.markdown(
        f'<div class="pl-step"><div class="pl-step-no">{no}</div><div>'
        f'<div class="pl-step-title">{judul}</div><div class="pl-step-sub">{sub}</div></div></div>',
        unsafe_allow_html=True,
    )


def tiles(items, total: int | None = None):
    """items = list of (label, nilai, keterangan); `total` = indeks kotak yang disorot gelap (mis. total harga)."""
    html = "".join(
        f'<div class="pl-tile{" pl-tile-total" if i == total else ""}"><div class="pl-t-l">{l}</div>'
        f'<div class="pl-t-v">{v}</div><div class="pl-t-s">{s}</div></div>'
        for i, (l, v, s) in enumerate(items)
    )
    st.markdown(f'<div class="pl-tiles">{html}</div>', unsafe_allow_html=True)


def badge(teks: str, jenis: str) -> str:
    """HTML lencana status. jenis: aktif | datang | selesai | batal | noshow."""
    return f'<span class="pl-badge pl-b-{jenis}">{escape(teks)}</span>'
