"""
Peta Aliran Dana: uang mengalir ke mana, dan siapa yang menyerapnya.

Metode (semua dari harga & volume harian publik):
- Volume dolar      = harga x volume (crypto di Yahoo sudah dalam USD).
- Volume relatif    = rata-rata volume dolar 20 hari / 60 hari. >1 = uang yang berputar bertambah.
- CMF 20 hari       = Chaikin Money Flow: volume besar ditutup dekat high (akumulasi) atau low (distribusi).
- Aliran bersih 20h = jumlah Money Flow Volume x harga = estimasi dolar "bersih" yang menekan harga ke atas/bawah.
- Penyerap          = interpretasi gabungan arah harga, volume relatif, dan CMF, plus siapa pelaku utama
                      di instrumen itu (ETF = institusi/penasihat, spot crypto = ritel & whale, HYG = dana kredit).
"""
import numpy as np
import pandas as pd

# (label, ticker, kelas aset, pelaku utama instrumen)
INSTRUMENTS = [
    ("Saham", None, "Saham", "Institusi & ritel ekuitas"),
    ("Bitcoin spot", "BTC-USD", "Crypto", "Ritel & whale crypto"),
    ("ETF Bitcoin (IBIT)", "IBIT", "Crypto", "Institusi & penasihat keuangan"),
    ("ETF Emas (GLD)", "GLD", "Emas", "Institusi & dana makro"),
    ("Obligasi pemerintah (IEF)", "IEF", "Aman", "Dana pensiun & institusi defensif"),
    ("Obligasi high-yield (HYG)", "HYG", "Risiko", "Dana kredit"),
]
USD_VOLUME = {"BTC-USD", "ETH-USD"}


def _s(df, t):
    return df[t].astype(float) if t in df and not df[t].dropna().empty else None


def flow_table(md) -> pd.DataFrame:
    C, H, L, V = md.close, md.high, md.low, md.volume
    idr = _s(C, "IDR=X")
    rows = []
    for label, t, cls, who in INSTRUMENTS:
        t = t or md.equity_ticker
        c, h, l, v = _s(C, t), _s(H, t), _s(L, t), _s(V, t)
        if c is None or v is None or v.tail(60).sum() == 0:
            continue
        dv = v if t in USD_VOLUME else c * v
        if t == "^JKSE" and idr is not None:
            dv = dv / idr
        if label == "Saham":
            label = f"Saham ({t})"
        rng = (h - l).replace(0, np.nan)
        mfm = ((c - l) - (h - c)) / rng
        net20 = (mfm * dv).tail(20).sum()
        cmf20 = (mfm * v).tail(20).sum() / v.tail(20).sum()
        dv20, dv60 = dv.tail(20).mean(), dv.tail(60).mean()
        relvol = dv20 / dv60 if dv60 else np.nan
        chg20 = c.iloc[-1] / c.iloc[-21] - 1 if len(c.dropna()) > 21 else np.nan
        rows.append({"Instrumen": label, "Kelas": cls, "Pelaku utama": who, "ticker": t,
                     "Volume $/hari (20h)": dv20, "Volume relatif": relvol, "Harga 20h": chg20,
                     "CMF 20h": cmf20, "Aliran bersih 20h": net20,
                     "Penyerapan": absorption(chg20, relvol, cmf20, who)})
    return pd.DataFrame(rows)


def absorption(chg, relvol, cmf, who) -> str:
    if any(pd.isna(x) for x in (chg, relvol, cmf)):
        return "Data kurang"
    up, hot, acc, dist = chg > 0.01, relvol > 1.1, cmf > 0.05, cmf < -0.05
    if up and acc and hot:
        return f"Akumulasi kuat — uang baru masuk, diserap {who.lower()}"
    if up and acc:
        return f"Akumulasi tenang — {who.lower()} menambah posisi bertahap"
    if up and dist:
        return "Naik tapi didistribusi — pemain besar menjual ke kenaikan"
    if up and relvol < 0.9:
        return "Naik tanpa volume — dorongan lemah, rawan berbalik"
    if chg < -0.01 and acc:
        return "Penyerapan — pembeli besar menampung tekanan jual"
    if chg < -0.01 and dist and hot:
        return "Distribusi berat — uang keluar dengan volume tinggi"
    if chg < -0.01 and dist:
        return "Distribusi — smart money mengurangi posisi"
    return "Netral — belum ada arus dominan"


def flow_by_class(ft: pd.DataFrame) -> dict:
    """Ringkasan aliran bersih per kelas aset (USD)."""
    if ft.empty:
        return {}
    return ft.groupby("Kelas")["Aliran bersih 20h"].sum().to_dict()


def fmt_usd(x: float) -> str:
    if pd.isna(x):
        return "—"
    a = abs(x)
    s = "−" if x < 0 else ""
    if a >= 1e9:
        return f"{s}${a / 1e9:,.1f} miliar"
    if a >= 1e6:
        return f"{s}${a / 1e6:,.0f} juta"
    return f"{s}${a:,.0f}"


def highlights(md, macro: pd.DataFrame, crypto: dict) -> list[dict]:
    """Sorotan finansial ringkas: label, nilai, perubahan, nada (+/-/0)."""
    C = md.close
    out = []

    def chg(t, n=21):
        s = _s(C, t)
        return (s.iloc[-1] / s.iloc[-1 - n] - 1) * 100 if s is not None and len(s) > n else None

    dom = crypto.get("btc_dom")
    btc_eth = None
    b, e = _s(C, "BTC-USD"), _s(C, "ETH-USD")
    if b is not None and e is not None and len(b) > 31:
        r = b / e
        btc_eth = (r.iloc[-1] / r.iloc[-31] - 1) * 100
    out.append({"k": "Bitcoin Dominance", "v": f"{dom:.1f}%" if dom else "—",
                "d": (f"BTC vs ETH {btc_eth:+.1f}% (30h)" if btc_eth is not None else ""),
                "tone": 0 if btc_eth is None else (1 if btc_eth > 0 else -1)})
    sd = crypto.get("stable_dom")
    out.append({"k": "Porsi stablecoin", "v": f"{sd:.1f}%" if sd else "—",
                "d": "dana parkir di crypto", "tone": 0})
    f = crypto.get("fng")
    out.append({"k": "Crypto Fear & Greed", "v": f"{f}" if f is not None else "—",
                "d": crypto.get("fng_label", ""), "tone": 0 if f is None else (1 if f > 55 else -1 if f < 45 else 0)})
    m = macro.iloc[-1]
    d = chg("DX-Y.NYB")
    out.append({"k": "Dollar Index", "v": f"{m['dxy']:.1f}" if pd.notna(m["dxy"]) else "—",
                "d": f"{d:+.1f}% (1 bln)" if d is not None else "", "tone": 0 if d is None else (-1 if d > 0 else 1)})
    t = macro["tnx"].dropna()
    out.append({"k": "Yield AS 10 th", "v": f"{t.iloc[-1]:.2f}%" if len(t) else "—",
                "d": f"{(t.iloc[-1] - t.iloc[-22]) * 100:+.0f} bps (1 bln)" if len(t) > 22 else "",
                "tone": 0 if len(t) <= 22 else (-1 if t.iloc[-1] > t.iloc[-22] else 1)})
    out.append({"k": "VIX", "v": f"{m['vix']:.1f}" if pd.notna(m["vix"]) else "—",
                "d": "takut" if m["vix"] >= 25 else "waspada" if m["vix"] >= 18 else "tenang",
                "tone": -1 if m["vix"] >= 25 else 0 if m["vix"] >= 18 else 1})
    hy = chg("HYG")
    ie = chg("IEF")
    if hy is not None and ie is not None:
        out.append({"k": "Kredit (HYG − IEF)", "v": f"{hy - ie:+.1f} pp", "d": "selera risiko institusi (1 bln)",
                    "tone": 1 if hy - ie > 0 else -1})
    g = chg("GC=F")
    gs = _s(C, "GC=F")
    out.append({"k": "Emas /oz", "v": f"${gs.iloc[-1]:,.0f}" if gs is not None else "—",
                "d": f"{g:+.1f}% (1 bln)" if g is not None else "", "tone": 0 if g is None else (1 if g > 0 else -1)})
    return out
