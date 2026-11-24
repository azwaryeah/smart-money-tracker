"""
Smart Money Flow Tracker — jalankan dengan:  streamlit run app.py
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import engine as E

st.set_page_config(page_title="Smart Money Flow Tracker", page_icon="💹", layout="wide")

COLORS = {"Saham": "#2563eb", "Crypto": "#8b5cf6", "Emas": "#d4a017", "Kas": "#64748b",
          "Strategi Rotasi": "#16a34a", "Tahan Saham": "#2563eb", "Tahan Crypto": "#8b5cf6", "Tahan Emas": "#d4a017"}

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Pengaturan")
    mode = st.radio("Sumber data", ["Live (internet)", "Demo (data contoh)"], index=0)
    eq_label = st.selectbox("Acuan saham", list(E.EQUITY_CHOICES.keys()))
    period = st.selectbox("Riwayat data", ["2y", "3y", "5y", "10y"], index=1)
    st.subheader("Aturan rotasi")
    min_score = st.slider("Skor minimum untuk masuk aset", 50, 70, 55,
                          help="Jika semua aset di bawah ini, sinyal = pindah ke Kas.")
    margin = st.slider("Selisih skor agar pindah (poin)", 0, 20, 5,
                       help="Kandidat baru harus unggul sebanyak ini. Makin besar = makin jarang pindah.")
    confirm = st.slider("Hari konfirmasi", 1, 10, 3,
                        help="Sinyal harus bertahan sekian hari berturut-turut sebelum pindah.")
    cost = st.number_input("Biaya per pindah (%)", 0.0, 2.0, 0.2, 0.05) / 100
    if st.button("🔄 Muat ulang data"):
        st.cache_data.clear()
    st.caption("Data di-cache 1 jam. Sinyal dihitung dari harga penutupan harian.")


@st.cache_data(ttl=3600, show_spinner="Mengambil data pasar global…")
def load(mode, eq, period):
    if mode.startswith("Demo"):
        return E.demo_market_data(eq)
    return E.fetch_market_data(eq, period)


@st.cache_data(ttl=3600, show_spinner=False)
def load_crypto():
    return E.fetch_crypto_sentiment()


eq = E.EQUITY_CHOICES[eq_label]
try:
    md = load(mode, eq, period)
except Exception as ex:
    st.error(f"Gagal mengambil data live: {ex}\n\nMenampilkan data demo sebagai gantinya.")
    md = E.demo_market_data(eq)

sig = E.build_signals(md)
scores = sig["scores"]
path = E.rotation_path(scores, min_score, margin, confirm)
last, prev_w = scores.iloc[-1], scores.iloc[-6] if len(scores) > 6 else scores.iloc[0]
macro_last = sig["macro"].iloc[-1]
held = path.iloc[-1]
regime, regime_desc = E.regime_label(macro_last, last)
alloc = E.suggested_allocation(last, min_score)
since = path[path != path.shift()].index[-1]

# ---------------------------------------------------------------------------
# Header & sinyal utama
# ---------------------------------------------------------------------------
st.title("💹 Smart Money Flow Tracker")
st.caption(f"Data terakhir: {scores.index[-1]:%d %b %Y}  ·  Acuan saham: {eq_label}"
           + ("  ·  ⚠️ MODE DEMO — angka bukan data pasar nyata" if md.is_demo else ""))
if md.missing:
    st.warning(f"Sebagian data gagal diunduh dan diabaikan: {', '.join(md.missing)}")

icons = {"Saham": "📈", "Crypto": "₿", "Emas": "🥇", "Kas": "💵"}
c1, c2 = st.columns([1.3, 1])
with c1:
    st.markdown(f"### Sinyal saat ini: {icons[held]} **{held.upper()}**")
    st.markdown(f"Dipegang sejak **{since:%d %b %Y}** ({(scores.index[-1] - since).days} hari).")
    st.markdown(f"**Rezim pasar:** {regime} — {regime_desc}")
    # peringatan dini: kandidat yang mendekati syarat pindah
    leader = last.idxmax()
    if leader != held and held != "Kas" and last[leader] - last[held] > 0:
        gap = last[leader] - last[held]
        st.info(f"👀 **Pantau:** {leader} ({last[leader]:.0f}) mulai menyalip {held} ({last[held]:.0f}). "
                f"Selisih {gap:.0f} poin; pindah jika ≥ {margin} poin bertahan {confirm} hari.")
    elif held != "Kas" and last[held] < min_score:
        st.warning(f"⚠️ Skor {held} turun ke {last[held]:.0f} (< {min_score}). Pertimbangkan mengurangi posisi / ke Kas.")
with c2:
    fig = go.Figure(go.Pie(labels=list(alloc), values=list(alloc.values()), hole=0.55,
                           marker_colors=[COLORS[k] for k in alloc], sort=False))
    fig.update_layout(title="Alokasi indikatif", height=260, margin=dict(t=40, b=0, l=0, r=0),
                      legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")

cols = st.columns(3)
for col, a in zip(cols, E.ASSETS):
    with col:
        st.metric(f"{icons[a]} {a}", f"{last[a]:.0f} / 100", f"{last[a] - prev_w[a]:+.1f} vs minggu lalu")
        with st.expander("Kenapa?"):
            for p in E.explain(a, sig):
                st.write("• " + p)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
t1, t2, t3, t4, t5 = st.tabs(["📊 Skor & Rotasi", "🌍 Makro & Risiko", "🔁 Kekuatan Relatif",
                              "🧪 Backtest", "₿ Crypto & 🇮🇩 IDR"])

with t1:
    window = st.select_slider("Rentang grafik", ["3B", "6B", "1T", "2T", "Semua"], value="1T")
    days = {"3B": 63, "6B": 126, "1T": 252, "2T": 504, "Semua": len(scores)}[window]
    s = scores.tail(days)
    fig = go.Figure()
    for a in E.ASSETS:
        fig.add_scatter(x=s.index, y=s[a], name=a, line=dict(color=COLORS[a], width=2))
    fig.add_hline(y=min_score, line_dash="dot", line_color="gray", annotation_text="ambang masuk")
    fig.add_hline(y=50, line_color="lightgray")
    # pita posisi
    p = path.tail(days)
    blocks = (p != p.shift()).cumsum()
    for _, g in p.groupby(blocks):
        fig.add_vrect(x0=g.index[0], x1=g.index[-1], fillcolor=COLORS[g.iloc[0]], opacity=0.08, line_width=0)
    fig.update_layout(height=420, yaxis_title="Skor smart money (0-100)", hovermode="x unified",
                      margin=dict(t=20), legend=dict(orientation="h", y=1.08))
    st.plotly_chart(fig, width="stretch")
    st.caption("Latar berwarna = aset yang dipegang strategi pada periode itu.")
    st.subheader("Riwayat sinyal pindah aset")
    st.dataframe(E.rotation_events(path, scores), width="stretch", hide_index=True)

    st.subheader("Rincian indikator")
    rows = []
    for a in E.ASSETS:
        f = sig["feats"][a].iloc[-1]
        rows.append({"Aset": a, "Skor": round(last[a]), "Momentum": round(f.mom, 2), "Tren": round(f.trend, 2),
                     "CMF (aliran volume)": round(f.cmf_raw, 3), "Return 1B": f.r1m, "Return 3B": f.r3m, "Return 6B": f.r6m})
    st.dataframe(pd.DataFrame(rows).style.format({"Return 1B": "{:+.1%}", "Return 3B": "{:+.1%}", "Return 6B": "{:+.1%}"}),
                 width="stretch", hide_index=True)

with t2:
    m = sig["macro"]
    k = st.columns(4)
    k[0].metric("Selera risiko global", f"{macro_last.risk:+.2f}", help="-1 = sangat takut, +1 = sangat berani")
    k[1].metric("VIX", f"{macro_last.vix:.1f}", f"{macro_last.vix - m.vix.iloc[-6]:+.1f} (1 mgg)", delta_color="inverse")
    k[2].metric("Dollar Index", f"{macro_last.dxy:.1f}", f"{(macro_last.dxy / m.dxy.iloc[-22] - 1) * 100:+.1f}% (1 bln)", delta_color="inverse")
    k[3].metric("Yield AS 10th", f"{macro_last.tnx:.2f}%", f"{macro_last.tnx - m.tnx.iloc[-22]:+.2f} (1 bln)", delta_color="inverse")
    mm = m.loc[scores.index].tail(504)
    fig = go.Figure()
    for col, name in [("risk", "Selera risiko (gabungan)"), ("vix_sig", "VIX (dibalik)"),
                      ("credit_sig", "Kredit: HYG vs IEF"), ("cugold_sig", "Tembaga vs Emas")]:
        fig.add_scatter(x=mm.index, y=mm[col], name=name, line=dict(width=3 if col == "risk" else 1))
    fig.add_hline(y=0, line_color="lightgray")
    fig.update_layout(height=380, yaxis_range=[-1.05, 1.05], hovermode="x unified", margin=dict(t=20),
                      legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, width="stretch")
    st.markdown("""
**Cara membaca:**
- **VIX** turun / rendah → investor tenang, dana masuk ke aset berisiko.
- **HYG/IEF** naik → investor institusi berani membeli obligasi berisiko (sinyal *risk-on* klasik).
- **Tembaga/Emas** naik → pasar mengharapkan pertumbuhan ekonomi; turun → mencari aman.
- **DXY** melemah biasanya mendukung emas, crypto, dan pasar berkembang (termasuk IHSG).
- **Yield** naik cepat menekan emas dan saham growth.
""")

with t3:
    st.markdown("Rasio harga antar aset menunjukkan **ke mana dana berpindah**. Rasio naik = aset pertama lebih diminati.")
    pairs = [("Saham", "Emas"), ("Crypto", "Saham"), ("Crypto", "Emas")]
    cc = st.columns(3)
    for col, (a, b) in zip(cc, pairs):
        r = (sig["px"][a] / sig["px"][b]).loc[scores.index].tail(504)
        r = r / r.iloc[0] * 100
        fig = go.Figure()
        fig.add_scatter(x=r.index, y=r, name="Rasio", line=dict(color=COLORS[a]))
        fig.add_scatter(x=r.index, y=r.rolling(50).mean(), name="MA50", line=dict(color="gray", dash="dot"))
        up = r.iloc[-1] > r.rolling(50).mean().iloc[-1]
        fig.update_layout(title=f"{a} / {b} — {'dana ke ' + a if up else 'dana ke ' + b}", height=300,
                          showlegend=False, margin=dict(t=40, l=0, r=0))
        col.plotly_chart(fig, width="stretch")

with t4:
    curves, stats = E.backtest(sig, path, md, cost)
    fig = go.Figure()
    for c in curves:
        fig.add_scatter(x=curves.index, y=curves[c], name=c,
                        line=dict(color=COLORS[c], width=3 if c == "Strategi Rotasi" else 1.5))
    fig.update_layout(height=420, yaxis_type="log", yaxis_title="Pertumbuhan Rp1 (skala log)",
                      hovermode="x unified", margin=dict(t=20), legend=dict(orientation="h", y=1.08))
    st.plotly_chart(fig, width="stretch")
    st.dataframe(stats.style.format({"Total Return": "{:+.1%}", "CAGR": "{:+.1%}", "Max Drawdown": "{:.1%}", "Sharpe": "{:.2f}"}),
                 width="stretch", hide_index=True)
    st.caption("Backtest memakai aturan rotasi di sidebar, masuk H+1 setelah sinyal, termasuk biaya per pindah. "
               "Hasil masa lalu tidak menjamin hasil masa depan, dan parameter yang di-'tuning' ke data lama cenderung terlalu optimis.")

with t5:
    if md.is_demo:
        st.info("Data sentimen crypto hanya tersedia di mode Live.")
    else:
        cs = load_crypto()
        if cs:
            k = st.columns(4)
            if "fng" in cs:
                k[0].metric("Crypto Fear & Greed", f"{cs['fng']} ({cs['fng_label']})",
                            f"{cs['fng'] - cs['fng_7d_ago']:+d} (7 hari)" if cs.get("fng_7d_ago") else None)
            if "btc_dom" in cs:
                k[1].metric("Dominasi BTC", f"{cs['btc_dom']:.1f}%")
                k[2].metric("Porsi stablecoin", f"{cs['stable_dom']:.1f}%",
                            help="Porsi stablecoin naik = dana parkir/keluar dari crypto; turun = dana masuk ke koin.")
                k[3].metric("Total market cap", f"${cs['total_mcap'] / 1e12:.2f}T",
                            f"{cs['mcap_change_24h']:+.1f}% (24j)" if cs.get("mcap_change_24h") is not None else None)
            st.markdown("- **Fear & Greed < 25** (ketakutan ekstrem) sering jadi zona akumulasi smart money; **> 75** zona distribusi.\n"
                        "- **Dominasi BTC naik** = dana berlindung ke BTC; **turun** = musim altcoin / spekulasi tinggi.")
        else:
            st.warning("Gagal mengambil data sentimen crypto.")
    g = E.gold_idr_per_gram(md).loc[scores.index].dropna()
    if not g.empty:
        st.subheader("🇮🇩 Harga emas dunia dalam Rupiah per gram")
        st.metric("Emas spot (estimasi)", f"Rp{g.iloc[-1]:,.0f}/gr".replace(",", "."),
                  f"{(g.iloc[-1] / g.iloc[-22] - 1) * 100:+.1f}% (1 bln)")
        st.plotly_chart(px.line(g.tail(504), labels={"value": "Rp/gram", "index": ""}).update_layout(
            height=300, showlegend=False, margin=dict(t=10)), width="stretch")
        st.caption("Dihitung dari emas futures (GC=F) × kurs USD/IDR ÷ 31,1035. Harga emas batangan lokal (Antam dll.) biasanya lebih tinggi karena premi & pajak.")

st.divider()
with st.expander("ℹ️ Metodologi skor"):
    st.markdown("""
Skor tiap aset (0-100, 50 = netral) adalah gabungan:

| Komponen | Saham | Crypto | Emas |
|---|---|---|---|
| Momentum 1/3/6 bulan (disesuaikan volatilitas) | 35% | 35% | 35% |
| Tren (MA50 & MA200) | 20% | 20% | 20% |
| Chaikin Money Flow — aliran volume institusi | 15% | 10% | 15% |
| Selera risiko global (VIX, HYG/IEF, Tembaga/Emas) | 20% | 20% | – |
| Kekuatan relatif Saham vs Emas | 10% | – | – |
| Dolar melemah | – | 15% | 15% |
| Yield AS turun | – | – | 15% |

**Aturan rotasi:** pegang aset dengan skor tertinggi jika ≥ ambang masuk; pindah hanya jika kandidat unggul
sesuai *selisih skor* selama *hari konfirmasi*. Jika semua skor lemah → Kas.
""")
st.caption("⚠️ Alat bantu analisis, bukan nasihat keuangan. Saya bukan penasihat keuangan berlisensi — keputusan investasi sepenuhnya tanggung jawab Anda.")
