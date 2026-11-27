"""
Panel Live: harga & arus dana hari ini, diperbarui otomatis tiap 5 detik.
- Crypto (BTC, ETH): Coinbase Exchange API, real-time, 24 jam.
- Saham, emas, VIX, dolar, rupiah: Yahoo Finance intraday 1 menit (berubah tiap menit saat pasar buka).
"""
import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

WIB = ZoneInfo("Asia/Jakarta")
NY = ZoneInfo("America/New_York")
CB_URL = "https://api.exchange.coinbase.com/products/{}/{}"
HEADERS = {"User-Agent": "smart-money-tracker"}
MAX_TICKS = 720  # 1 jam riwayat tick per 5 detik


@st.cache_data(ttl=4, show_spinner=False)
def coinbase_stats(pid: str) -> dict:
    r = requests.get(CB_URL.format(pid, "stats"), timeout=4, headers=HEADERS)
    r.raise_for_status()
    d = r.json()
    return {"last": float(d["last"]), "open": float(d["open"])}


@st.cache_data(ttl=60, show_spinner=False)
def coinbase_candles(pid: str) -> pd.Series:
    """300 candle 1 menit terakhir sebagai riwayat awal grafik."""
    r = requests.get(CB_URL.format(pid, "candles"), params={"granularity": 60}, timeout=6, headers=HEADERS)
    r.raise_for_status()
    rows = r.json()  # [time, low, high, open, close, volume], terbaru dulu
    s = pd.Series({pd.Timestamp(x[0], unit="s", tz="UTC"): float(x[4]) for x in rows}).sort_index()
    return s.tz_convert(WIB)


@st.cache_data(ttl=60, show_spinner=False)
def yahoo_intraday(tickers: tuple) -> dict:
    import yfinance as yf

    raw = yf.download(list(tickers), period="5d", interval="1m", progress=False,
                      auto_adjust=False, group_by="column", threads=True)
    if raw is None or raw.empty:
        return {}
    close = raw["Close"]
    if not isinstance(close, pd.DataFrame):
        close = close.to_frame(tickers[0])
    out = {}
    for t in tickers:
        if t not in close:
            continue
        s = close[t].dropna()
        if s.empty:
            continue
        if s.index.tz is None:
            s.index = s.index.tz_localize("UTC")
        day = s.index.tz_convert(NY).date
        today = s[day == day[-1]]
        prev = s[day < day[-1]]
        out[t] = {"series": today.tz_convert(WIB), "last": float(s.iloc[-1]),
                  "prev": float(prev.iloc[-1]) if not prev.empty else float(today.iloc[0]),
                  "at": s.index[-1].tz_convert(WIB)}
    return out


def us_market_open(now=None) -> bool:
    n = (now or datetime.now(NY)).astimezone(NY)
    return n.weekday() < 5 and (n.hour, n.minute) >= (9, 30) and n.hour < 16


def _metric(col, label, value, delta, spark=None, inverse=False):
    kw = dict(delta=delta, delta_color="inverse" if inverse else "normal", border=True)
    try:
        col.metric(label, value, chart_data=spark, chart_type="area", **kw)
    except TypeError:  # streamlit lama tanpa sparkline
        col.metric(label, value, delta=delta, delta_color=kw["delta_color"])


def _fmt(x, dec=2):
    return f"{x:,.{dec}f}"


def render_live(eq_ticker: str, eq_label: str, is_demo: bool):
    from style import section
    section("⚡ Live — arus dana hari ini", "harga bergerak tiap 5 detik")
    c1, c2 = st.columns([1, 2])
    on = c1.toggle("Update tiap 5 detik", value=True, key="live_on")
    focus = c2.selectbox("Grafik bergerak", ["Bitcoin", "Ethereum", eq_label, "Emas", "VIX", "USD/IDR"],
                         key="live_focus", label_visibility="collapsed")

    @st.fragment(run_every=5 if on else None)
    def _panel():
        ticks = st.session_state.setdefault("ticks", {"BTC-USD": [], "ETH-USD": []})
        crypto, errs = {}, []
        for pid in ("BTC-USD", "ETH-USD"):
            try:
                d = coinbase_stats(pid)
                crypto[pid] = d
                tl = ticks[pid]
                now = pd.Timestamp.now(tz=WIB).floor("s")
                if not tl or tl[-1][0] != now:
                    tl.append((now, d["last"]))
                    del tl[:-MAX_TICKS]
            except Exception:
                errs.append(pid)
        ytick = (eq_ticker, "GC=F", "^VIX", "IDR=X", "DX-Y.NYB")
        try:
            yd = yahoo_intraday(ytick)
        except Exception:
            yd = {}
        if not yd:
            errs.append("Yahoo intraday")

        def ychg(t):
            d = yd.get(t)
            return (d["last"] / d["prev"] - 1) * 100 if d else None

        def crypto_series(pid):
            try:
                hist = coinbase_candles(pid)
            except Exception:
                hist = pd.Series(dtype=float)
            live = pd.Series(dict(ticks[pid])) if ticks[pid] else pd.Series(dtype=float)
            s = pd.concat([hist, live]).sort_index()
            return s[~s.index.duplicated(keep="last")]

        # --- kartu harga ---
        cols = st.columns(3) + st.columns(3)
        for col, pid, name in [(cols[0], "BTC-USD", "₿ Bitcoin"), (cols[1], "ETH-USD", "Ξ Ethereum")]:
            d = crypto.get(pid)
            if d:
                spark = crypto_series(pid).tail(60).round(2).tolist()
                _metric(col, name, f"${_fmt(d['last'])}", f"{(d['last'] / d['open'] - 1) * 100:+.2f}% (24j)", spark)
            else:
                col.metric(name, "—")
        for col, t, name, dec, inv in [(cols[2], eq_ticker, f"📈 {eq_label.split(' (')[0]}", 2, False),
                                       (cols[3], "GC=F", "🥇 Emas /oz", 1, False),
                                       (cols[4], "^VIX", "😨 VIX", 2, True),
                                       (cols[5], "IDR=X", "🇮🇩 USD/IDR", 0, True)]:
            d = yd.get(t)
            if d:
                spark = d["series"].tail(60).round(4).tolist()
                _metric(col, name, _fmt(d["last"], dec), f"{ychg(t):+.2f}%", spark, inv)
            else:
                col.metric(name, "—")

        # --- grafik bergerak ---
        g1, g2 = st.columns([2.2, 1])
        with g1:
            mp = {"Bitcoin": "BTC-USD", "Ethereum": "ETH-USD", eq_label: eq_ticker, "Emas": "GC=F",
                  "VIX": "^VIX", "USD/IDR": "IDR=X"}
            key = mp.get(focus, "BTC-USD")
            if key in ("BTC-USD", "ETH-USD"):
                s = crypto_series(key).tail(400)
                ref = crypto[key]["open"] if key in crypto else None
            else:
                d = yd.get(key)
                s = d["series"] if d else pd.Series(dtype=float)
                ref = d["prev"] if d else None
            if not s.empty:
                up = ref is None or s.iloc[-1] >= ref
                color = "#34D399" if up else "#FB7185"
                fig = go.Figure()
                fig.add_scatter(x=s.index, y=s.values, mode="lines", line=dict(color=color, width=2),
                                fill="tozeroy", fillcolor="rgba(52,211,153,0.10)" if up else "rgba(251,113,133,0.10)",
                                hovertemplate="%{x|%H:%M:%S} WIB<br>%{y:,.2f}<extra></extra>")
                fig.add_scatter(x=[s.index[-1]], y=[s.iloc[-1]], mode="markers",
                                marker=dict(size=11, color=color, line=dict(width=3, color="rgba(10,13,20,0.9)")),
                                hoverinfo="skip")
                if ref:
                    fig.add_hline(y=ref, line_dash="dot", line_color="gray",
                                  annotation_text="pembukaan 24j" if key in crypto else "tutup kemarin")
                lo, hi = float(s.min()), float(s.max())
                pad = (hi - lo) * 0.1 or hi * 0.001
                fig.update_layout(height=330, showlegend=False, margin=dict(t=30, l=0, r=10, b=24),
                                  title=f"{focus}: {_fmt(s.iloc[-1])}",
                                  yaxis_range=[min(lo, ref or lo) - pad, max(hi, ref or hi) + pad],
                                  xaxis=dict(tickformat="%H:%M"), uirevision=focus)
                st.plotly_chart(fig, width="stretch", key="live_chart")
            else:
                st.info("Data grafik belum tersedia.")

        # --- denyut risiko & arus dana hari ini ---
        with g2:
            chg = {
                "Saham": ychg(eq_ticker),
                "Bitcoin": (crypto["BTC-USD"]["last"] / crypto["BTC-USD"]["open"] - 1) * 100 if "BTC-USD" in crypto else None,
                "Emas": ychg("GC=F"),
                "Dolar": ychg("DX-Y.NYB"),
            }
            parts = []
            if chg["Saham"] is not None:
                parts.append(math.tanh(chg["Saham"] / 1.0))
            if chg["Bitcoin"] is not None:
                parts.append(math.tanh(chg["Bitcoin"] / 3.0))
            if ychg("^VIX") is not None:
                parts.append(-math.tanh(ychg("^VIX") / 5.0))
            if chg["Emas"] is not None:
                parts.append(-0.5 * math.tanh(chg["Emas"] / 1.0))
            pulse = float(np.mean(parts)) * 100 if parts else 0.0
            label = ("Dana masuk ke aset berisiko" if pulse > 20 else
                     "Dana lari ke aset aman" if pulse < -20 else "Arus dana seimbang")
            fig = go.Figure(go.Indicator(
                mode="gauge+number", value=round(pulse), number={"suffix": ""},
                title={"text": f"Denyut risiko hari ini<br><span style='font-size:0.8em'>{label}</span>"},
                gauge={"axis": {"range": [-100, 100]}, "bar": {"color": "#E6EAF2", "thickness": 0.22}, "bgcolor": "rgba(0,0,0,0)", "borderwidth": 0,
                       "steps": [{"range": [-100, -20], "color": "rgba(251,113,133,.35)"}, {"range": [-20, 20], "color": "rgba(148,163,184,.18)"},
                                 {"range": [20, 100], "color": "rgba(52,211,153,.35)"}]}))
            fig.update_layout(height=210, margin=dict(t=60, b=10, l=45, r=45))
            st.plotly_chart(fig, width="stretch", key="live_gauge")
            bars = {k: v for k, v in chg.items() if v is not None}
            if bars:
                items = sorted(bars.items(), key=lambda kv: kv[1])
                fb = go.Figure(go.Bar(x=[v for _, v in items], y=[k for k, _ in items], orientation="h",
                                      marker_color=["#34D399" if v >= 0 else "#FB7185" for _, v in items],
                                      text=[f"{v:+.2f}%" for _, v in items], textposition="auto", cliponaxis=False))
                m = max(abs(v) for v in bars.values()) * 1.15 or 1
                fb.update_layout(height=170, margin=dict(t=25, b=0, l=0, r=50), title="Perubahan hari ini",
                                 xaxis=dict(range=[-m, m], visible=False))
                st.plotly_chart(fb, width="stretch", key="live_bars")

        stamp = datetime.now(WIB).strftime("%H:%M:%S")
        mkt = "🟢 Bursa AS buka" if us_market_open() else "⚪ Bursa AS tutup (harga saham dari sesi terakhir)"
        note = f"Diperbarui {stamp} WIB · {mkt} · Crypto real-time 24 jam; saham/emas/VIX per menit"
        if errs:
            note += f" · ⚠️ gagal: {', '.join(errs)}"
        st.caption(note)

    _panel()
    st.caption("Panel Live untuk memantau pergerakan intrahari. **Sinyal pindah aset tetap dihitung dari harga "
               "penutupan harian** agar tidak terpancing gejolak sesaat.")
