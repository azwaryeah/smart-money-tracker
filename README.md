# 💹 Smart Money Flow Tracker

Aplikasi untuk memantau ke mana **aliran dana besar (smart money)** bergerak di pasar global, lalu
memberi sinyal kapan sebaiknya **memindahkan aset** antara **Saham ↔ Crypto ↔ Emas ↔ Kas**.

## Cara menjalankan

1. Install **Python 3.10+** dari https://www.python.org/downloads/ (Windows: centang *"Add Python to PATH"*).
2. Ekstrak folder ini.
3. Klik dua kali:
   - Windows: `jalankan_windows.bat`
   - Mac/Linux: `jalankan_mac_linux.sh` (atau di terminal: `bash jalankan_mac_linux.sh`)
4. Browser akan terbuka otomatis di `http://localhost:8501`.

Pertama kali akan mengunduh library (±1-2 menit). Selanjutnya langsung jalan.

Manual: `pip install -r requirements.txt` lalu `streamlit run app.py`.

## Apa yang dipantau

| Kategori | Data | Arti sinyal |
|---|---|---|
| Harga & tren | SPY / ACWI / IHSG, Bitcoin, ETF Emas (GLD) | Momentum 1/3/6 bulan, MA50/MA200 |
| Aliran volume | Chaikin Money Flow tiap aset | Akumulasi (beli) vs distribusi (jual) oleh pemain besar |
| Selera risiko | VIX, obligasi high-yield vs pemerintah (HYG/IEF), rasio Tembaga/Emas | Risk-on vs risk-off |
| Makro | Dollar Index (DXY), yield AS 10 tahun | Angin pendorong/penahan emas & crypto |
| Rotasi | Rasio Saham/Emas, BTC/Saham, BTC/Emas | Ke mana dana berpindah |
| Crypto | Fear & Greed Index, dominasi BTC, porsi stablecoin | Sentimen & posisi dana di crypto |
| Rupiah | Emas dunia dalam Rp/gram, USD/IDR | Konteks untuk investor Indonesia |

Semua data gratis, tanpa API key (Yahoo Finance, alternative.me, CoinGecko).

## Cara memakai sinyal

- **Sinyal saat ini** = aset yang sebaiknya dipegang menurut aturan rotasi.
- **Skor 0-100** per aset: > 55 kuat, 45-55 netral, < 45 lemah.
- **"Pantau"** muncul saat aset lain mulai menyalip — peringatan dini sebelum sinyal pindah resmi.
- Atur sensitivitas di sidebar: *selisih skor* dan *hari konfirmasi* yang lebih besar = lebih jarang pindah
  (biaya lebih kecil, tapi telat bereaksi).
- Tab **Backtest** menunjukkan bagaimana aturan ini berperforma di masa lalu dibanding sekadar menahan satu aset.

Tips: buka aplikasi seminggu sekali (atau setelah penutupan pasar AS, pagi hari WIB). Sinyal berbasis data harian,
bukan untuk trading intraday.

## Batasan

- Data "smart money" yang sebenarnya (posisi institusi, 13F, COT, aliran ETF harian) sebagian besar berbayar atau
  terlambat; aplikasi ini memakai **proksi publik** yang dipakai luas oleh analis.
- Backtest bersifat historis dan rawan *overfitting* bila parameter terus disetel ulang.
- **Bukan nasihat keuangan.** Gunakan sebagai salah satu bahan pertimbangan.

## Struktur file

- `app.py` — tampilan (Streamlit)
- `engine.py` — pengambilan data, indikator, skor, aturan rotasi, backtest (bisa dipakai terpisah, mis. untuk notifikasi Telegram)
