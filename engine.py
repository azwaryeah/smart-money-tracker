"""
Smart Money Flow Engine
-----------------------
Mengambil data pasar global, menghitung indikator aliran dana ("smart money"),
memberi skor tiap kelas aset (Saham, Crypto, Emas), menentukan kapan harus
rotasi, dan melakukan backtest sederhana.

Semua sumber data gratis & tanpa API key:
  - Yahoo Finance (via yfinance): harga & volume saham, ETF, crypto, emas, makro
  - alternative.me: Crypto Fear & Greed Index
  - CoinGecko: dominasi BTC & kapitalisasi stablecoin
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Daftar ticker
# ---------------------------------------------------------------------------
EQUITY_CHOICES = {
    "S&P 500 (SPY)": "SPY",
    "Saham Global (ACWI)": "ACWI",
    "IHSG (^JKSE)": "^JKSE",
}

CORE = {
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
    "GLD": "ETF Emas (GLD)",
    "GC=F": "Emas futures",
    "^VIX": "VIX (indeks ketakutan)",
    "DX-Y.NYB": "Dollar Index (DXY)",
    "^TNX": "Yield obligasi AS 10 th",
    "HYG": "Obligasi high-yield",
    "IEF": "Obligasi pemerintah AS 7-10 th",
    "HG=F": "Tembaga",
    "BIL": "T-Bill (kas)",
    "IBIT": "ETF Bitcoin spot (BlackRock)",
    "IDR=X": "USD/IDR",
}

ASSETS = ["Saham", "Crypto", "Emas"]
CASH = "Kas"
GRAM_PER_OZ = 31.1035


@dataclass
class MarketData:
    close: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    volume: pd.DataFrame
    equity_ticker: str
    is_demo: bool = False
    missing: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pengambilan data
# ---------------------------------------------------------------------------
def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    idx = pd.bdate_range(df.index.min(), df.index.max())
    return df.reindex(idx).ffill()


def fetch_market_data(equity_ticker: str = "SPY", period: str = "3y") -> MarketData:
    import yfinance as yf

    tickers = [equity_ticker] + list(CORE.keys())
    raw = yf.download(tickers, period=period, auto_adjust=True,
                      progress=False, threads=True, group_by="column")
    if raw is None or raw.empty:
        raise RuntimeError("Tidak ada data dari Yahoo Finance. Cek koneksi internet.")

    def part(name):
        d = raw[name] if isinstance(raw.columns, pd.MultiIndex) else raw[[name]]
        return _normalize(d)

    close, high, low, vol = part("Close"), part("High"), part("Low"), part("Volume")
    missing = [t for t in tickers if t not in close or close[t].dropna().empty]
    if equity_ticker in missing or "BTC-USD" in missing or "GLD" in missing:
        raise RuntimeError(f"Data inti gagal diunduh: {missing}")
    return MarketData(close, high, low, vol, equity_ticker, False, missing)


def demo_market_data(equity_ticker: str = "SPY", days: int = 780, seed: int = 7) -> MarketData:
    """Data sintetis dengan beberapa rezim pasar, untuk mencoba aplikasi tanpa internet."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    n = len(idx)
    # rezim: 0 risk-on saham, 1 musim crypto, 2 risk-off (emas), berganti tiap ~130 hari
    regime = np.repeat(rng.permutation([0, 1, 2, 0, 2, 1, 0]), math.ceil(n / 7))[:n]
    drift = {  # drift harian per rezim: (saham, btc, emas)
        0: (0.0009, 0.0010, -0.0001),
        1: (0.0003, 0.0040, 0.0001),
        2: (-0.0012, -0.0030, 0.0012),
    }
    vols = (0.010, 0.035, 0.009)
    start = {equity_ticker: 450.0 if equity_ticker != "^JKSE" else 6800.0,
             "BTC-USD": 40000.0, "GLD": 180.0}
    close = {}
    for j, t in enumerate([equity_ticker, "BTC-USD", "GLD"]):
        mu = np.array([drift[r][j] for r in regime])
        rets = mu + rng.normal(0, vols[j], n)
        close[t] = start[t] * np.exp(np.cumsum(rets))
    risk = np.array([{0: 1, 1: 0.6, 2: -1}[r] for r in regime], dtype=float)
    risk_s = pd.Series(risk).rolling(20, min_periods=1).mean().values
    close["ETH-USD"] = close["BTC-USD"] / 18 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    close["GC=F"] = close["GLD"] * 10.8
    close["^VIX"] = np.clip(17 - 6 * risk_s + rng.normal(0, 1.5, n), 10, 60)
    close["DX-Y.NYB"] = 103 * np.exp(np.cumsum(-0.0002 * risk + rng.normal(0, 0.003, n)))
    close["^TNX"] = np.clip(4.2 + np.cumsum(rng.normal(0, 0.03, n)) * 0.3, 2.5, 6)
    close["HYG"] = 75 * np.exp(np.cumsum(0.0003 * risk + rng.normal(0, 0.003, n)))
    close["IEF"] = 95 * np.exp(np.cumsum(-0.0001 * risk + rng.normal(0, 0.003, n)))
    close["HG=F"] = 4.0 * np.exp(np.cumsum(0.0006 * risk + rng.normal(0, 0.012, n)))
    close["BIL"] = 91 * np.exp(np.arange(n) * 0.00018)
    close["IBIT"] = close["BTC-USD"] / 1650
    close["IDR=X"] = 15800 * np.exp(np.cumsum(-0.0001 * risk + rng.normal(0, 0.003, n)))
    close = pd.DataFrame(close, index=idx)
    spread = np.abs(rng.normal(0, 0.006, close.shape))
    pos = rng.uniform(0, 1, close.shape)
    # posisi close dalam range harian dibuat condong ke atas saat aset trending naik (akumulasi)
    trend = close.pct_change(10).fillna(0).values
    pos = np.clip(pos + np.tanh(trend * 15) * 0.25, 0, 1)
    high = close * (1 + spread * (1 - pos))
    low = close * (1 - spread * pos)
    volume = pd.DataFrame(rng.lognormal(16, 0.4, close.shape), index=idx, columns=close.columns)
    return MarketData(close, high, low, volume, equity_ticker, True, [])


def fetch_crypto_sentiment() -> dict:
    """Data tambahan crypto (opsional). Mengembalikan dict kosong bila gagal."""
    import requests

    out = {}
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=30", timeout=10).json()
        vals = [int(x["value"]) for x in r["data"]]
        out["fng"] = vals[0]
        out["fng_label"] = r["data"][0]["value_classification"]
        out["fng_7d_ago"] = vals[7] if len(vals) > 7 else None
    except Exception:
        pass
    try:
        g = requests.get("https://api.coingecko.com/api/v3/global", timeout=10).json()["data"]
        pct = g["market_cap_percentage"]
        out["btc_dom"] = pct.get("btc")
        out["stable_dom"] = sum(pct.get(k, 0) for k in ("usdt", "usdc", "dai", "usde", "fdusd"))
        out["total_mcap"] = g["total_market_cap"]["usd"]
        out["mcap_change_24h"] = g.get("market_cap_change_percentage_24h_usd")
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# Indikator
# ---------------------------------------------------------------------------
def _col(df: pd.DataFrame, t: str) -> pd.Series:
    if t in df and not df[t].dropna().empty:
        return df[t].astype(float)
    return pd.Series(np.nan, index=df.index)


def momentum(c: pd.Series) -> pd.Series:
    """Momentum tertimbang 1/3/6 bulan, disesuaikan volatilitas (mirip Sharpe), skala -1..1."""
    r = 0.2 * c.pct_change(21) + 0.3 * c.pct_change(63) + 0.5 * c.pct_change(126)
    vol = c.pct_change().rolling(126, min_periods=40).std() * math.sqrt(126)
    return np.tanh(r / vol)


def trend(c: pd.Series) -> pd.Series:
    sma50, sma200 = c.rolling(50).mean(), c.rolling(200, min_periods=120).mean()
    t = (c > sma200).astype(float) * 0.5 + (sma50 > sma200).astype(float) * 0.5
    return (2 * t - 1).where(sma200.notna())


def cmf(h, l, c, v, n=20) -> pd.Series:
    """Chaikin Money Flow: apakah volume besar masuk saat harga ditutup dekat high (akumulasi)."""
    rng = (h - l).replace(0, np.nan)
    mfv = ((c - l) - (h - c)) / rng * v
    return mfv.rolling(n).sum() / v.rolling(n).sum()


def ratio_trend(a: pd.Series, b: pd.Series | None = None, n=50, k=10.0) -> pd.Series:
    r = a if b is None else a / b
    return np.tanh((r / r.rolling(n).mean() - 1) * k)


def build_signals(md: MarketData) -> dict:
    C, H, L, V = md.close, md.high, md.low, md.volume
    eq = md.equity_ticker
    px = {"Saham": _col(C, eq), "Crypto": _col(C, "BTC-USD"), "Emas": _col(C, "GLD")}
    vt = {"Saham": eq, "Crypto": "BTC-USD", "Emas": "GLD"}

    feats = {}
    for a, c in px.items():
        t = vt[a]
        f = pd.DataFrame(index=C.index)
        f["mom"] = momentum(c)
        f["trend"] = trend(c)
        f["cmf_raw"] = cmf(_col(H, t), _col(L, t), c, _col(V, t))
        f["cmf"] = np.tanh(f["cmf_raw"] * 4)
        f["r1m"], f["r3m"], f["r6m"] = c.pct_change(21), c.pct_change(63), c.pct_change(126)
        feats[a] = f

    # --- makro / selera risiko ---
    vix = _col(C, "^VIX")
    vix_z = (vix - vix.rolling(50).mean()) / vix.rolling(50).std()
    macro = pd.DataFrame(index=C.index)
    macro["vix"] = vix
    macro["vix_sig"] = 0.5 * np.tanh(-vix_z) + 0.5 * np.tanh(-(vix - 20) / 5)
    macro["credit_sig"] = ratio_trend(_col(C, "HYG"), _col(C, "IEF"), k=25)
    macro["cugold_sig"] = ratio_trend(_col(C, "HG=F"), _col(C, "GC=F"), k=10)
    macro["risk"] = macro[["vix_sig", "credit_sig", "cugold_sig"]].mean(axis=1, skipna=True)
    macro["dxy"] = _col(C, "DX-Y.NYB")
    macro["dxy_sig"] = ratio_trend(macro["dxy"], k=25).fillna(0)
    macro["tnx"] = _col(C, "^TNX")
    macro["yield_sig"] = np.tanh(macro["tnx"].diff(21) / 0.3).fillna(0)
    macro["rs_eq_gold"] = ratio_trend(px["Saham"], px["Emas"], k=8)
    macro["rs_btc_eq"] = ratio_trend(px["Crypto"], px["Saham"], k=4)
    macro["rs_btc_gold"] = ratio_trend(px["Crypto"], px["Emas"], k=4)
    risk = macro["risk"].fillna(0)

    def F(a, k):
        return feats[a][k].fillna(0)

    comp = pd.DataFrame(index=C.index)
    comp["Saham"] = (0.35 * F("Saham", "mom") + 0.20 * F("Saham", "trend") + 0.15 * F("Saham", "cmf")
                     + 0.20 * risk + 0.10 * macro["rs_eq_gold"].fillna(0))
    comp["Crypto"] = (0.35 * F("Crypto", "mom") + 0.20 * F("Crypto", "trend") + 0.10 * F("Crypto", "cmf")
                      + 0.20 * risk - 0.15 * macro["dxy_sig"])
    comp["Emas"] = (0.35 * F("Emas", "mom") + 0.20 * F("Emas", "trend") + 0.15 * F("Emas", "cmf")
                    - 0.15 * macro["dxy_sig"] - 0.15 * macro["yield_sig"])
    scores = (50 + 50 * comp).clip(0, 100)
    warm = max(feats[a]["mom"].first_valid_index() or C.index[0] for a in ASSETS)
    scores = scores.loc[scores.index >= warm]

    return {"px": px, "feats": feats, "macro": macro, "scores": scores}


# ---------------------------------------------------------------------------
# Rotasi
# ---------------------------------------------------------------------------
def rotation_path(scores: pd.DataFrame, min_score=55.0, margin=5.0, confirm=3) -> pd.Series:
    """
    Tentukan aset yang dipegang tiap hari, dengan histeresis supaya tidak bolak-balik:
    - Pindah hanya jika kandidat baru unggul >= `margin` poin selama `confirm` hari berturut.
    - Jika skor tertinggi < `min_score`, kandidatnya Kas.
    """
    held, streak, cand_prev = None, 0, None
    out = []
    st = {}
    for _, row in scores.iterrows():
        best = row.idxmax()
        cand = best if row[best] >= min_score else CASH
        cur_score = row[held] if held in row else 50.0
        cand_score = row[cand] if cand in row else 50.0
        if held is None:
            held = cand
        elif cand != held and (cand_score - cur_score >= margin or (held != CASH and row[held] < min_score - margin)):
            streak = streak + 1 if cand == cand_prev else 1
            if streak >= confirm:
                held, streak = cand, 0
        else:
            streak = 0
        cand_prev = cand
        out.append(held)
        st = {"cand": cand, "best": best, "best_score": float(row[best]), "streak": streak,
              "cand_score": float(cand_score), "held_score": float(row[held]) if held in row else 50.0}
    ser = pd.Series(out, index=scores.index, name="posisi")
    ser.attrs["status"] = st
    return ser


def rotation_events(path: pd.Series, scores: pd.DataFrame) -> pd.DataFrame:
    chg = path != path.shift()
    ev = []
    prev = None
    for d in path.index[chg]:
        cur = path.loc[d]
        ev.append({
            "Tanggal": d.date(), "Dari": prev or "-", "Ke": cur,
            "Skor Saham": round(scores.loc[d, "Saham"]), "Skor Crypto": round(scores.loc[d, "Crypto"]),
            "Skor Emas": round(scores.loc[d, "Emas"]),
        })
        prev = cur
    return pd.DataFrame(ev[::-1])


def suggested_allocation(row: pd.Series, min_score=55.0) -> dict:
    """Alokasi indikatif: proporsional terhadap kelebihan skor di atas 50; sisanya kas."""
    excess = {a: max(row[a] - 50, 0) for a in ASSETS}
    strong = {a: e for a, e in excess.items() if row[a] >= min_score - 5}
    tot = sum(strong.values())
    if tot == 0:
        return {CASH: 100.0}
    invested = min(100.0, 40 + tot * 1.5)  # makin kuat sinyal, makin besar porsi investasi
    alloc = {a: invested * e / tot for a, e in strong.items()}
    alloc[CASH] = 100 - invested
    return {k: round(v, 1) for k, v in alloc.items() if v > 0.5}


def regime_label(macro_row: pd.Series, scores_row: pd.Series) -> tuple[str, str]:
    risk = macro_row.get("risk", 0) or 0
    leader = scores_row.idxmax()
    if risk > 0.25 and leader == "Crypto":
        return "Risk-On Agresif", "Dana mengalir ke aset spekulatif; crypto memimpin."
    if risk > 0.15:
        return "Risk-On", "Selera risiko sehat: VIX rendah, kredit kuat, ekonomi tumbuh."
    if risk < -0.25:
        return "Risk-Off", "Dana keluar dari aset berisiko menuju aset aman (emas, kas, obligasi)."
    if leader == "Emas" and (macro_row.get("dxy_sig", 0) or 0) < 0:
        return "Lindung Nilai / Dolar Melemah", "Emas diuntungkan dolar yang melemah."
    return "Netral / Transisi", "Sinyal campuran; hati-hati, tunggu konfirmasi."


def explain(asset: str, sig: dict) -> list[str]:
    f = sig["feats"][asset].iloc[-1]
    m = sig["macro"].iloc[-1]
    pts = []
    def pct(x):
        return "n/a" if pd.isna(x) else f"{x*100:+.1f}%"
    pts.append(f"Return 1B {pct(f.r1m)} · 3B {pct(f.r3m)} · 6B {pct(f.r6m)}")
    pts.append("Momentum kuat" if f.mom > 0.3 else "Momentum lemah" if f.mom < -0.3 else "Momentum netral")
    pts.append({1.0: "Tren naik (di atas MA200, MA50 > MA200)", 0.0: "Tren campuran",
                -1.0: "Tren turun (di bawah MA200)"}.get(round(f.trend, 0) if not pd.isna(f.trend) else 0.0, "Tren campuran"))
    if not pd.isna(f.cmf_raw):
        pts.append(f"Akumulasi volume (CMF {f.cmf_raw:+.2f}) — smart money membeli" if f.cmf_raw > 0.05 else
                   f"Distribusi volume (CMF {f.cmf_raw:+.2f}) — smart money menjual" if f.cmf_raw < -0.05 else
                   f"Volume netral (CMF {f.cmf_raw:+.2f})")
    if asset in ("Saham", "Crypto"):
        r = m.risk
        pts.append("Selera risiko global mendukung" if r > 0.15 else "Selera risiko global menekan" if r < -0.15 else "Selera risiko netral")
    if asset in ("Crypto", "Emas"):
        pts.append("Dolar (DXY) melemah → mendukung" if m.dxy_sig < -0.1 else "Dolar (DXY) menguat → menekan" if m.dxy_sig > 0.1 else "Dolar stabil")
    if asset == "Emas":
        pts.append("Yield AS naik → menekan emas" if m.yield_sig > 0.2 else "Yield AS turun → mendukung emas" if m.yield_sig < -0.2 else "Yield AS stabil")
    return pts


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------
def backtest(sig: dict, path: pd.Series, md: MarketData, cost=0.002) -> tuple[pd.DataFrame, pd.DataFrame]:
    idx = path.index
    rets = pd.DataFrame({a: sig["px"][a].reindex(idx).pct_change() for a in ASSETS})
    cash = _col(md.close, "BIL").reindex(idx).pct_change()
    rets[CASH] = cash.fillna(0.04 / 252)
    rets = rets.fillna(0)
    pos = path.shift(1).bfill()
    strat = pd.Series([rets.at[d, p] for d, p in zip(idx, pos)], index=idx)
    switches = (pos != pos.shift()).astype(float)
    switches.iloc[0] = 0
    strat -= switches * cost
    curves = pd.DataFrame({"Strategi Rotasi": (1 + strat).cumprod()})
    for a in ASSETS:
        curves[f"Tahan {a}"] = (1 + rets[a]).cumprod()

    yrs = max(len(idx) / 252, 1e-9)
    stats = []
    for col in curves:
        c = curves[col]
        dr = c.pct_change().dropna()
        stats.append({
            "Strategi": col,
            "Total Return": c.iloc[-1] - 1,
            "CAGR": c.iloc[-1] ** (1 / yrs) - 1,
            "Max Drawdown": (c / c.cummax() - 1).min(),
            "Sharpe": (dr.mean() / dr.std() * math.sqrt(252)) if dr.std() > 0 else np.nan,
            "Jumlah Pindah": int(switches.sum()) if col == "Strategi Rotasi" else 0,
        })
    return curves, pd.DataFrame(stats)


def gold_idr_per_gram(md: MarketData) -> pd.Series:
    return _col(md.close, "GC=F") * _col(md.close, "IDR=X") / GRAM_PER_OZ
