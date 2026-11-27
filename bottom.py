"""
Bitcoin Bottom Signal — apakah Bitcoin sedang di zona bottom siklus?
Skor valuasi 0-100 dari indikator siklus + konfirmasi tren.
"""
import html
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

import style as S

st.set_page_config(page_title="Bitcoin Bottom Signal", page_icon="🟠", layout="wide")
S.inject()
WIB = ZoneInfo("Asia/Jakarta")
GENESIS = pd.Timestamp("2009-01-03")
# Siklus historis (close harian): tanggal ATH, tanggal bottom, drawdown
CYCLES = [
    {"name": "2013–2015", "ath": "2013-12-04", "bottom": "2015-01-14", "dd": -0.85},
    {"name": "2017–2018", "ath": "2017-12-16", "bottom": "2018-12-15", "dd": -0.84},
    {"name": "2021–2022", "ath": "2021-11-08", "bottom": "2022-11-21", "dd": -0.77},
]
DAYS_LO, DAYS_HI = 363, 406
RAINBOW = ["Obral besar", "Beli", "Akumulasi", "Masih murah", "HODL", "Mulai mahal", "FOMO",
           "Jual, serius", "Gelembung maksimum"]
RB_COLORS = ["#1D4ED8", "#2563EB", "#0EA5E9", "#10B981", "#84CC16", "#EAB308", "#F97316", "#EF4444", "#B91C1C"]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner="Mengambil riwayat harga Bitcoin…")
def load_btc() -> pd.Series:
    import yfinance as yf

    raw = yf.download("BTC-USD", period="max", interval="1d", auto_adjust=True, progress=False)
    c = raw["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    c = c.dropna().astype(float)
    c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
    return c[~c.index.duplicated(keep="last")]


@st.cache_data(ttl=60, show_spinner=False)
def live_price():
    try:
        r = requests.get("https://api.exchange.coinbase.com/products/BTC-USD/ticker", timeout=5,
                         headers={"User-Agent": "smart-money-tracker"})
        return float(r.json()["price"]), datetime.now(WIB)
    except Exception:
        return None, None


def _bgeo(path: str):
    """BGeometrics (gratis). Mengembalikan Series tanggal → nilai, atau None."""
    try:
        r = requests.get(f"https://bitcoin-data.com/v1/{path}", timeout=10,
                         headers={"User-Agent": "smart-money-tracker"})
        r.raise_for_status()
        js = r.json()
        rows = js if isinstance(js, list) else [js]
        out = {}
        for row in rows:
            d = row.get("d") or row.get("date") or row.get("theDay")
            vals = [v for k, v in row.items() if k not in ("d", "date", "theDay", "unixTs") and v is not None]
            if d and vals:
                try:
                    out[pd.Timestamp(d)] = float(vals[0])
                except Exception:
                    pass
        s = pd.Series(out).sort_index()
        return s if len(s) else None
    except Exception:
        return None


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_onchain() -> dict:
    return {"realized": _bgeo("realized-price"), "mvrv_z": _bgeo("mvrv-zscore")}


# ---------------------------------------------------------------------------
# Perhitungan
# ---------------------------------------------------------------------------
def lin(x, zero, full):
    """Skor 0-100: `zero` → 0, `full` → 100, linear & dibatasi."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return float(np.clip((x - zero) / (full - zero) * 100, 0, 100))


def power_law(dates) -> np.ndarray:
    d = (pd.DatetimeIndex(dates) - GENESIS).days.values.astype(float)
    return 1.0117e-17 * d ** 5.82  # model Santostasi


def rainbow_fit(daily: pd.Series):
    d = (daily.index - GENESIS).days.values.astype(float)
    x, y = np.log10(d), np.log10(daily.values)
    b, a = np.polyfit(x, y, 1)
    res = y - (a + b * x)
    lo, hi = np.percentile(res, 0.5), np.percentile(res, 99.5)
    edges = np.linspace(lo, hi, 10)
    return a, b, edges


def rainbow_lines(dates, a, b, edges):
    d = (pd.DatetimeIndex(dates) - GENESIS).days.values.astype(float)
    base = a + b * np.log10(d)
    return [10 ** (base + e) for e in edges]


def compute(daily: pd.Series, price: float, onchain: dict, manual_rp: float, manual_z: float) -> dict:
    today = pd.Timestamp.now(tz=WIB).tz_localize(None).normalize()
    d = daily.copy()
    d.loc[today] = price
    d = d.sort_index()
    wk = d.resample("W-SUN").last()
    w30, w50, w200 = (wk.rolling(n).mean() for n in (30, 50, 200))
    ath_date = d.idxmax()
    ath = float(d.max())
    days_ath = int((today - ath_date).days)
    dd = price / ath - 1
    prev = [c for c in CYCLES if pd.Timestamp(c["ath"]) < ath_date][-1]
    cyc_low = float(d.loc[pd.Timestamp(prev["ath"]):ath_date].min())
    fib786 = ath - 0.786 * (ath - cyc_low)
    pl_fair = float(power_law([today])[0])
    pl_ratio = price / pl_fair
    a, b, edges = rainbow_fit(daily)
    rl = [float(v[0]) for v in rainbow_lines([today], a, b, edges)]
    band = int(np.clip(np.searchsorted(rl, price), 1, 9))
    r200 = price / float(w200.iloc[-1]) if pd.notna(w200.iloc[-1]) else np.nan

    rp_s, z_s = onchain.get("realized"), onchain.get("mvrv_z")
    rp = manual_rp or (float(rp_s.iloc[-1]) if rp_s is not None else None)
    z = manual_z if manual_z else (float(z_s.iloc[-1]) if z_s is not None else None)
    mvrv = price / rp if rp else None

    # konfirmasi tren (tahapan Weinstein dengan 30WMA)
    slope = w30.iloc[-1] - w30.iloc[-5]
    above = price > w30.iloc[-1]
    if above and slope > 0:
        stage, stage_txt = 2, "Stage 2 — tren naik terkonfirmasi (harga di atas 30WMA yang menanjak)."
    elif above:
        stage, stage_txt = 1, "Stage 1 — fase dasar: harga kembali di atas 30WMA yang mulai mendatar. Tanda awal bottom."
    elif slope < 0:
        stage, stage_txt = 4, "Stage 4 — tren turun: harga di bawah 30WMA yang menurun. Belum ada konfirmasi bottom."
    else:
        stage, stage_txt = 3, "Stage 3 — fase puncak/distribusi: harga jatuh di bawah 30WMA yang masih naik."

    ind = []

    def add(key, name, val, sub, score, w, zone, tip):
        ind.append({"key": key, "name": name, "val": val, "sub": sub, "score": score, "w": w, "zone": zone, "tip": tip})

    add("200wma", "Harga / 200WMA", f"{r200:.2f}×" if pd.notna(r200) else "—",
        ("Di bawah 200WMA — zona bottom historis" if r200 < 1 else f"200WMA ${w200.iloc[-1]:,.0f}"),
        lin(r200, 2.0, 0.9), 20, bool(r200 < 1),
        "Rata-rata harga 200 minggu (~4 tahun). Setiap bottom siklus Bitcoin terjadi di sekitar atau di bawah garis ini.")
    add("mvrv", "MVRV (harga / realized)", f"{mvrv:.2f}" if mvrv else "—",
        (f"Realized price ${rp:,.0f} · bottom siklus ≤ 1,0" if rp else "Data on-chain tidak tersedia"),
        lin(mvrv, 2.5, 1.0) if mvrv else None, 15, bool(mvrv and mvrv <= 1.2),
        "Membandingkan harga dengan rata-rata harga beli seluruh pemegang (realized price). Di bawah 1 = rata-rata pemegang rugi — kapitulasi.")
    add("realized", "Realized price", f"${rp:,.0f}" if rp else "—",
        (f"Harga {(price / rp - 1) * 100:+.1f}% di atasnya" if rp else "isi manual di bagian bawah bila perlu"),
        None, 0, bool(rp and price <= rp * 1.1),
        "Harga rata-rata saat setiap koin terakhir berpindah tangan — 'modal rata-rata' pasar.")
    add("rainbow", "Rainbow band", RAINBOW[band - 1], f"Pita {band} dari 9", lin(band, 7, 1), 15, band <= 3,
        "Regresi logaritmik harga sepanjang sejarah, dibagi 9 pita warna dari 'obral besar' sampai 'gelembung'.")
    add("power", "Power law", f"{pl_ratio:.2f}× fair",
        (f"Di bawah support ${pl_fair * 0.42:,.0f} ({(price / (pl_fair * 0.42) - 1) * 100:+.1f}%)" if pl_ratio < 0.42
         else f"Fair value ${pl_fair:,.0f}"), lin(pl_ratio, 1.5, 0.42), 15, pl_ratio <= 0.5,
        "Model hukum pangkat (Santostasi): harga Bitcoin tumbuh mengikuti waktu sejak genesis. Support ≈ 0,42× nilai wajar.")
    add("mvrvz", "MVRV Z-Score", f"{z:.2f}" if z is not None else "—",
        ("Zona bottom historis < 0" if z is not None else "Data on-chain tidak tersedia"),
        lin(z, 3.0, 0.0) if z is not None else None, 10, bool(z is not None and z < 0.5),
        "Seberapa jauh market cap di atas realized cap, diukur dalam simpangan baku. < 0 = sangat murah secara historis.")
    add("days", "Hari sejak ATH", f"{days_ath} hari", f"Bottom historis: hari ke-{DAYS_LO}–{DAYS_HI}",
        lin(days_ath, 150, DAYS_LO), 10, days_ath >= DAYS_LO - 30,
        f"ATH ${ath:,.0f} ({ath_date:%d %b %Y}). Bottom siklus sebelumnya rata-rata ~1 tahun setelah puncak.")
    add("dd", "Drawdown dari ATH", f"{dd * 100:.0f}%", "Bottom historis: −77% s/d −85%", lin(dd, -0.20, -0.77), 15,
        dd <= -0.70, "Kedalaman koreksi dari puncak. Bear market Bitcoin biasanya berakhir di −77% sampai −85%.")
    add("fib", "Fib 0.786 (linear)", f"${fib786:,.0f}", f"Jarak {(fib786 / price - 1) * 100:+.1f}% · tidak masuk skor",
        None, 0, price <= fib786 * 1.05,
        f"Retracement 78,6% dari bottom siklus lalu (${cyc_low:,.0f}) ke ATH — level support terdalam yang sering diuji.")

    scored = [i for i in ind if i["score"] is not None and i["w"] > 0]
    tw = sum(i["w"] for i in scored)
    score = sum(i["score"] * i["w"] for i in scored) / tw if tw else 0
    return {"score": score, "ind": ind, "stage": stage, "stage_txt": stage_txt, "price": price, "daily": d,
            "wk": wk, "w30": w30, "w50": w50, "w200": w200, "ath": ath, "ath_date": ath_date, "fib": fib786,
            "rp_s": rp_s, "rp": rp, "z_s": z_s, "rb": (a, b, edges), "days": days_ath, "dd": dd,
            "n_scored": len(scored)}


def zone_label(s):
    if s >= 80:
        return "Zona bottom kuat", "#34D399"
    if s >= 60:
        return "Mendekati zona bottom", "#A3E635"
    if s >= 40:
        return "Netral", "#FBBF24"
    if s >= 20:
        return "Mahal", "#FB923C"
    return "Jauh dari bottom — zona puncak", "#FB7185"


# ---------------------------------------------------------------------------
# Tampilan
# ---------------------------------------------------------------------------
st.markdown("""
<style>
.bt-hero{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:16px;margin:4px 0 18px}
@media(max-width:820px){.bt-hero{grid-template-columns:minmax(0,1fr)}}
.bt-score{font-size:clamp(64px,9vw,96px);font-weight:800;line-height:1;letter-spacing:-.04em;color:#F7931A}
.bt-track{position:relative;height:10px;border-radius:99px;margin:18px 0 6px;
  background:linear-gradient(90deg,#3f1d1d,#5b3a12,#4d5b16,#14532d)}
.bt-knob{position:absolute;top:-5px;width:4px;height:20px;border-radius:2px;background:#fff;box-shadow:0 0 0 3px rgba(0,0,0,.35)}
.bt-ends{display:flex;justify-content:space-between;font-size:12.5px;color:#8B95A8}
.bt-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.bt-ind{background:linear-gradient(180deg,rgba(255,255,255,.06),rgba(255,255,255,.03));border:1px solid rgba(255,255,255,.08);
  border-radius:18px;padding:14px 16px}
.bt-ind.z{border-color:rgba(52,211,153,.55);box-shadow:0 0 0 1px rgba(52,211,153,.2) inset}
.bt-ind .h{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:13.5px;color:#AEB7C7}
.bt-ind .b{font-size:11.5px;padding:3px 9px;border-radius:99px;background:rgba(52,211,153,.15);color:#6EE7B7;white-space:nowrap}
.bt-ind .v{font-size:26px;font-weight:700;letter-spacing:-.02em;margin:6px 0 2px;font-variant-numeric:tabular-nums}
.bt-ind .s{font-size:13px;color:#8B95A8}
.bt-ind .p{height:4px;border-radius:99px;background:rgba(255,255,255,.07);margin-top:10px;overflow:hidden}
.bt-ind .p i{display:block;height:100%;background:#F7931A}
.bt-warn{border:1px solid rgba(251,191,36,.35);background:rgba(251,191,36,.08);color:#FDE68A;border-radius:14px;padding:10px 14px;font-size:14px}
</style>""", unsafe_allow_html=True)

try:
    daily = load_btc()
except Exception as ex:
    st.error(f"Riwayat harga Bitcoin gagal dimuat: {ex}")
    st.stop()
lp, lt = live_price()
price = lp or float(daily.iloc[-1])
onchain = load_onchain()

with st.sidebar:
    st.header("🟠 Bottom Signal")
    with st.expander("Data on-chain manual (opsional)"):
        st.caption("Dipakai bila sumber otomatis tidak tersedia. Nilai bisa dilihat di situs seperti Glassnode, CryptoQuant, atau LookIntoBitcoin.")
        manual_rp = st.number_input("Realized price (USD)", 0.0, 500000.0, 0.0, 100.0)
        manual_z = st.number_input("MVRV Z-Score", -5.0, 15.0, 0.0, 0.01)

R = compute(daily, price, onchain, manual_rp, manual_z)
label, lc = zone_label(R["score"])
src = f"Live dari Coinbase · ${price:,.0f} · update {lt:%d %b, %H:%M} WIB" if lp else f"Close terakhir ${price:,.0f}"

st.markdown(f"""
<div class="smt-card" style="margin-bottom:14px">
  <span class="smt-brand"><span class="smt-dot"></span>{src}</span>
  <div class="smt-title" style="background:linear-gradient(92deg,#F8FAFC 10%,#FDBA74 60%,#F7931A 95%);-webkit-background-clip:text;background-clip:text;color:transparent">Bitcoin Bottom Signal</div>
  <div class="smt-sub">Apakah Bitcoin sedang di zona bottom siklus? Skor gabungan {R['n_scored']} indikator valuasi on-chain & siklus, plus konfirmasi tren. Data harian s/d {R['daily'].index[-1]:%d %b %Y}.</div>
</div>
<div class="bt-warn">⚠️ Keberhasilan model di masa lalu bukan jaminan keberhasilan di masa depan. Bukan saran finansial.</div>
""", unsafe_allow_html=True)

knob = min(max(R["score"], 1), 99)
st.markdown(f"""
<div class="bt-hero" style="margin-top:16px">
  <div class="smt-card">
    <div class="smt-k">Skor bottom (valuasi)</div>
    <div class="bt-score">{R['score']:.0f}</div>
    <div style="font-size:22px;font-weight:700;color:{lc};margin-top:6px">{label}</div>
    <div class="bt-track"><div class="bt-knob" style="left:{knob}%"></div></div>
    <div class="bt-ends"><span>Jauh dari bottom</span><span>Zona bottom</span></div>
    <div class="smt-k" style="margin-top:12px">Konfirmasi tren: {R['stage_txt']}</div>
  </div>
  <div class="smt-card">
    <div class="smt-k">Harga sekarang</div>
    <div class="smt-signal" style="color:#F8FAFC">${price:,.0f}</div>
    <div class="smt-k">ATH ${R['ath']:,.0f} ({R['ath_date']:%d %b %Y}) · drawdown {R['dd'] * 100:.0f}% · {R['days']} hari sejak ATH</div>
    <div class="smt-k" style="margin-top:10px">Cara membaca: skor ≥ 80 = valuasi setara bottom siklus sebelumnya. Bottom yang "sah" biasanya dikonfirmasi saat tren berpindah ke Stage 1–2.</div>
  </div>
</div>""", unsafe_allow_html=True)

cards = []
for i in R["ind"]:
    badge = "<span class='b'>Zona bottom</span>" if i["zone"] else ""
    bar = f"<div class='p'><i style='width:{i['score']:.0f}%'></i></div>" if i["score"] is not None and i["w"] else ""
    cards.append(f"<div class='bt-ind{' z' if i['zone'] else ''}' title='{html.escape(i['tip'], quote=True)}'><div class='h'><span>{i['name']}</span>{badge}</div>"
                 f"<div class='v'>{i['val']}</div><div class='s'>{i['sub']}</div>{bar}</div>")
st.markdown("<div class='bt-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)
st.caption("Bilah oranye = seberapa 'bottom' indikator itu (0–100). Arahkan kursor ke kartu untuk penjelasan.")

# --- grafik utama ---------------------------------------------------------
S.section("📈 Grafik harga & level kunci", "skala logaritmik · data mingguan")
c1, c2 = st.columns([3, 1.4])
layers = c1.pills("Lapisan", ["MA 30/50/200", "Realized", "Fib 0.786", "Rainbow", "Power law"],
                  selection_mode="multi", default=["MA 30/50/200", "Realized"], label_visibility="collapsed")
tf = c2.segmented_control("Rentang", ["1Y", "2Y", "4Y", "8Y", "All"], default="4Y", label_visibility="collapsed") or "4Y"
weeks = {"1Y": 52, "2Y": 104, "4Y": 208, "8Y": 416, "All": 10_000}[tf]
wk = R["wk"].tail(weeks)
idx = wk.index
fig = go.Figure()
layers = layers or []
if "Rainbow" in layers:
    a, b, edges = R["rb"]
    lines = rainbow_lines(idx, a, b, edges)
    for k in range(9):
        fig.add_scatter(x=idx, y=lines[k], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=idx, y=lines[k + 1], mode="lines", line=dict(width=0), fill="tonexty",
                        fillcolor=RB_COLORS[k], opacity=0.25,
                        name=RAINBOW[k], hoverinfo="skip", showlegend=False)
if "Power law" in layers:
    pl = power_law(idx)
    fig.add_scatter(x=idx, y=pl, name="Power law fair", line=dict(color="#C084FC", dash="dash"))
    fig.add_scatter(x=idx, y=pl * 0.42, name="Power law support", line=dict(color="#C084FC", dash="dot"))
if "MA 30/50/200" in layers:
    for s, n, c in [(R["w30"], "30WMA", "#60A5FA"), (R["w50"], "50WMA", "#A78BFA"), (R["w200"], "200WMA", "#34D399")]:
        fig.add_scatter(x=idx, y=s.reindex(idx), name=n, line=dict(color=c, width=1.6))
if "Realized" in layers and R["rp_s"] is not None:
    rp = R["rp_s"].reindex(pd.date_range(R["rp_s"].index.min(), idx.max())).ffill().reindex(idx)
    fig.add_scatter(x=idx, y=rp, name="Realized price", line=dict(color="#F472B6", width=1.6))
elif "Realized" in layers and R["rp"]:
    fig.add_hline(y=R["rp"], line_color="#F472B6", line_dash="dot", annotation_text=f"Realized ${R['rp']:,.0f}")
if "Fib 0.786" in layers:
    fig.add_hline(y=R["fib"], line_color="#FBBF24", line_dash="dash", annotation_text=f"Fib 0.786 ${R['fib']:,.0f}")
fig.add_scatter(x=idx, y=wk.values, name="Harga BTC", line=dict(color="#F7931A", width=2.4))
fig.update_layout(height=470, yaxis_type="log", yaxis_title="USD (log)", hovermode="x unified",
                  margin=dict(t=10, l=0, r=0, b=0), legend=dict(orientation="h", y=1.08))
st.plotly_chart(fig, width="stretch", key="bt_main")

# --- siklus ----------------------------------------------------------------
c3, c4 = st.columns(2)
with c3:
    S.section("🔄 Siklus: waktu & kedalaman", f"{R['days']} hari · {R['dd'] * 100:.0f}%")
    d = R["daily"]
    fc = go.Figure()
    for cy, col in zip(CYCLES[1:], ["#60A5FA", "#A78BFA"]):
        start = pd.Timestamp(cy["ath"])
        seg = d.loc[start:start + pd.Timedelta(days=1100)]
        if len(seg) > 30:
            fc.add_scatter(x=(seg.index - start).days, y=(seg / seg.iloc[0] - 1) * 100, name=cy["name"],
                           line=dict(color=col, width=1.6))
    seg = d.loc[R["ath_date"]:]
    fc.add_scatter(x=(seg.index - R["ath_date"]).days, y=(seg / R["ath"] - 1) * 100, name="Siklus sekarang",
                   line=dict(color="#F7931A", width=3))
    fc.add_vrect(x0=DAYS_LO, x1=DAYS_HI, fillcolor="#34D399", opacity=0.10, line_width=0,
                 annotation_text="jendela bottom", annotation_position="top left")
    fc.update_layout(height=340, xaxis_title="Hari sejak ATH", yaxis_title="% dari ATH", hovermode="x unified",
                     margin=dict(t=10, l=0, r=0, b=0), legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fc, width="stretch", key="bt_cycle")
with c4:
    S.section("🌡️ MVRV Z-Score", "< 0 = zona bottom · > 7 = zona puncak")
    if R["z_s"] is not None:
        z = R["z_s"].loc[R["z_s"].index >= idx.min()]
        fz = go.Figure(go.Scatter(x=z.index, y=z.values, line=dict(color="#F7931A", width=1.8), name="MVRV Z"))
        fz.add_hrect(y0=-2, y1=0, fillcolor="#34D399", opacity=0.12, line_width=0)
        fz.add_hrect(y0=7, y1=12, fillcolor="#FB7185", opacity=0.12, line_width=0)
        fz.update_layout(height=340, margin=dict(t=10, l=0, r=0, b=0), showlegend=False)
        st.plotly_chart(fz, width="stretch", key="bt_z")
    else:
        st.info("Riwayat MVRV Z-Score belum tersedia dari sumber gratis saat ini. Skor dihitung dari indikator lain"
                + (" plus nilai manual Anda." if manual_z else "."))

with st.expander("📚 Penjelasan indikator untuk pemula"):
    for i in R["ind"]:
        st.markdown(f"**{i['name']}** — {i['tip']}")
    st.markdown("**Konfirmasi tren (Stage 1–4)** — Metode Stan Weinstein memakai rata-rata 30 minggu. "
                "Stage 4 = turun, Stage 1 = membentuk dasar, Stage 2 = naik. Valuasi murah + Stage 1/2 = bottom yang lebih meyakinkan.")
    st.markdown(f"**Bobot skor:** " + ", ".join(f"{i['name']} {i['w']}%" for i in R["ind"] if i["w"])
                + ". Indikator tanpa data otomatis dikeluarkan dan bobot dinormalisasi ulang.")
st.caption("Sumber: harga harian BTC-USD Yahoo Finance (sejak 2014) & harga live Coinbase; realized price & MVRV Z-Score "
           "dari BGeometrics bila tersedia; power law memakai formula Santostasi; rainbow di-fit sendiri dari data harga, "
           "jadi angkanya bisa sedikit berbeda dari grafik publik. Bukan saran finansial.")
