"""Tema visual: latar grafit bercahaya, kartu kaca, tipografi Geist."""
import html

import streamlit as st

ACCENT = {"Saham": "#60A5FA", "Crypto": "#A78BFA", "Emas": "#FBBF24", "Kas": "#94A3B8"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700;800&family=Geist+Mono:wght@400;500;600&display=swap');
:root{
  --bg:#0A0D14; --panel:rgba(255,255,255,.035); --panel-2:rgba(255,255,255,.06);
  --line:rgba(255,255,255,.08); --ink:#E6EAF2; --muted:#8B95A8;
  --up:#34D399; --down:#FB7185; --brand:#34D399; --brand-2:#818CF8;
}
/* latar dengan cahaya gradasi */
[data-testid="stAppViewContainer"]{
  background:
    radial-gradient(900px 520px at 8% -10%, rgba(52,211,153,.16), transparent 60%),
    radial-gradient(800px 520px at 100% 0%, rgba(129,140,248,.18), transparent 60%),
    radial-gradient(700px 600px at 50% 120%, rgba(56,189,248,.08), transparent 60%),
    var(--bg) !important;
  background-attachment: fixed !important;
}
[data-testid="stHeader"]{background:transparent !important}
[data-testid="stSidebar"]{background:rgba(12,16,25,.85) !important; backdrop-filter:blur(14px)}
.block-container{max-width:1240px; padding-top:2.2rem !important}
h1,h2,h3{letter-spacing:-.02em}
h3{font-weight:650 !important}

/* kartu kaca untuk metric, expander, tabel */
[data-testid="stMetric"]{
  background:linear-gradient(180deg,var(--panel-2),var(--panel)) !important;
  border:1px solid var(--line) !important; border-radius:18px !important;
  padding:14px 16px !important; backdrop-filter:blur(10px);
  box-shadow:0 1px 0 rgba(255,255,255,.04) inset, 0 12px 30px -18px rgba(0,0,0,.6);
}
[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums; letter-spacing:-.03em; font-weight:650}
[data-testid="stMetricLabel"] p{color:var(--muted) !important; font-weight:500}
[data-testid="stExpander"] details{border:1px solid var(--line) !important; border-radius:14px !important; background:var(--panel)}
[data-testid="stDataFrame"]{border-radius:14px; overflow:hidden}
[data-testid="stPlotlyChart"]{background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:6px 8px}

/* tab bergaya pil */
.stTabs [data-baseweb="tab-list"]{gap:6px; background:var(--panel); padding:6px; border-radius:14px; border:1px solid var(--line); overflow-x:auto}
.stTabs [data-baseweb="tab"]{border-radius:10px; padding:8px 14px; height:auto; white-space:nowrap}
.stTabs [aria-selected="true"]{background:rgba(52,211,153,.14) !important; color:var(--ink) !important}
.stTabs [data-baseweb="tab-highlight"],.stTabs [data-baseweb="tab-border"]{display:none}
hr{border-color:var(--line) !important}
[data-testid="stAlert"]{border-radius:14px}

/* hero */
.smt-hero{display:grid; grid-template-columns:minmax(0,1.25fr) minmax(0,1fr); gap:18px; margin:4px 0 26px}
@media(max-width:820px){.smt-hero{grid-template-columns:minmax(0,1fr)}}
.smt-card{background:linear-gradient(180deg,var(--panel-2),var(--panel)); border:1px solid var(--line);
  border-radius:22px; padding:22px 24px; backdrop-filter:blur(12px); position:relative; overflow:hidden}
.smt-brand{display:inline-flex; align-items:center; gap:8px; font-size:13px; color:var(--muted);
  border:1px solid var(--line); border-radius:999px; padding:5px 12px; background:rgba(255,255,255,.03)}
.smt-dot{width:8px; height:8px; border-radius:50%; background:var(--up); box-shadow:0 0 0 0 rgba(52,211,153,.6); animation:smtPulse 2s infinite}
@keyframes smtPulse{0%{box-shadow:0 0 0 0 rgba(52,211,153,.55)}70%{box-shadow:0 0 0 10px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}
@media (prefers-reduced-motion:reduce){.smt-dot{animation:none}}
.smt-title{font-size:clamp(32px,4.4vw,50px); line-height:1.04; font-weight:800; letter-spacing:-.035em; margin:14px 0 10px;
  background:linear-gradient(92deg,#F8FAFC 10%,#A7F3D0 55%,#C7D2FE 95%); -webkit-background-clip:text; background-clip:text; color:transparent}
.smt-sub{color:var(--muted); font-size:16px; line-height:1.55; max-width:56ch}
.smt-meta{display:flex; flex-wrap:wrap; gap:8px; margin-top:16px}
.smt-chip{font-size:13px; padding:5px 11px; border-radius:999px; background:rgba(255,255,255,.05); border:1px solid var(--line); color:#C9D1E0; white-space:nowrap}
.smt-chip.warn{background:rgba(251,191,36,.12); border-color:rgba(251,191,36,.35); color:#FDE68A}
.smt-k{font-size:13px; color:var(--muted)}
.smt-signal{font-size:clamp(40px,5.4vw,60px); font-weight:800; letter-spacing:-.04em; line-height:1; margin:6px 0 8px}
.smt-glow{position:absolute; inset:auto -40px -60px auto; width:220px; height:220px; border-radius:50%; filter:blur(50px); opacity:.35}
.smt-bars{display:grid; gap:10px; margin-top:16px}
.smt-row{display:grid; grid-template-columns:62px minmax(0,1fr) 38px; align-items:center; gap:10px; font-size:14px}
.smt-track{position:relative; height:8px; border-radius:99px; background:rgba(255,255,255,.07)}
.smt-fill{position:absolute; inset:0 auto 0 0; border-radius:99px}
.smt-th{position:absolute; top:-4px; bottom:-4px; width:2px; background:rgba(255,255,255,.55); border-radius:2px}
.smt-num{font-family:'Geist Mono',monospace; text-align:right; font-variant-numeric:tabular-nums}

/* top 3 */
.smt-rec{height:100%; min-height:168px; border-radius:20px; padding:18px 18px 16px; border:1px solid var(--line);
  background:linear-gradient(180deg,var(--panel-2),var(--panel)); position:relative; overflow:hidden}
.smt-rec::before{content:""; position:absolute; left:0; right:0; top:0; height:3px; background:var(--c)}
.smt-rec::after{content:""; position:absolute; right:-50px; top:-50px; width:150px; height:150px; border-radius:50%; background:var(--c); opacity:.12; filter:blur(30px)}
.smt-rec .n{font-family:'Geist Mono',monospace; font-size:12px; color:var(--muted)}
.smt-rec .t{font-size:18px; font-weight:700; margin:6px 0 8px; color:var(--ink)}
.smt-rec .b{font-size:15px; line-height:1.5; color:#C3CBDA}

/* berita */
.smt-news{display:grid; gap:8px}
.smt-item{display:grid; grid-template-columns:10px minmax(0,1fr); gap:12px; align-items:start; padding:12px 14px;
  border-radius:14px; border:1px solid var(--line); background:var(--panel); text-decoration:none !important; transition:background .15s, border-color .15s}
.smt-item:hover{background:var(--panel-2); border-color:rgba(255,255,255,.16)}
.smt-tone{width:8px; height:8px; border-radius:50%; margin-top:8px}
.smt-item .h{color:var(--ink); font-weight:600; font-size:15.5px; line-height:1.4}
.smt-item .m{color:var(--muted); font-size:13px; margin-top:3px}
.smt-section{display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between; gap:4px 12px; margin:34px 0 14px}
.smt-section .ttl{font-size:23px; font-weight:700; letter-spacing:-.02em; color:var(--ink)}
.smt-section span{color:var(--muted); font-size:13px}
</style>
"""


def _transparent_plotly():
    """Latar grafik transparan agar menyatu dengan kartu kaca."""
    if getattr(st.plotly_chart, "_smt", False):
        return
    orig = st.plotly_chart

    def wrapped(fig, *a, **k):
        try:
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_family="Geist, Inter, system-ui, sans-serif")
            fig.update_xaxes(gridcolor="rgba(255,255,255,.06)", zerolinecolor="rgba(255,255,255,.08)")
            fig.update_yaxes(gridcolor="rgba(255,255,255,.06)", zerolinecolor="rgba(255,255,255,.08)")
        except Exception:
            pass
        return orig(fig, *a, **k)

    wrapped._smt = True
    st.plotly_chart = wrapped


def inject():
    st.markdown(CSS, unsafe_allow_html=True)
    _transparent_plotly()


def section(title: str, note: str = ""):
    st.markdown(f"<div class='smt-section'><div class='ttl'>{html.escape(title)}</div><span>{html.escape(note)}</span></div>",
                unsafe_allow_html=True)


def hero(held, since, days, regime, regime_desc, date, eq_label, is_demo, last, min_score):
    c = ACCENT.get(held, "#34D399")
    rows = []
    for a in ("Saham", "Crypto", "Emas"):
        v = float(last[a])
        rows.append(
            f"<div class='smt-row'><span>{a}</span><div class='smt-track'>"
            f"<div class='smt-fill' style='width:{v:.0f}%;background:{ACCENT[a]}'></div>"
            f"<div class='smt-th' style='left:{min_score:.0f}%'></div></div>"
            f"<span class='smt-num'>{v:.0f}</span></div>")
    demo = "<span class='smt-chip warn'>Mode demo — bukan data pasar nyata</span>" if is_demo else ""
    st.markdown(f"""
<div class="smt-hero">
  <div class="smt-card">
    <span class="smt-brand"><span class="smt-dot"></span>Smart Money Flow · diperbarui otomatis</span>
    <div class="smt-title">Ke mana uang besar mengalir hari ini</div>
    <div class="smt-sub">Pantau rotasi dana global antara saham, crypto, emas, dan kas — lalu ketahui kapan waktunya memindahkan aset.</div>
    <div class="smt-meta">
      <span class="smt-chip">Data {date:%d %b %Y}</span>
      <span class="smt-chip">Acuan: {html.escape(eq_label)}</span>
      <span class="smt-chip">Rezim: {html.escape(regime)}</span>{demo}
    </div>
  </div>
  <div class="smt-card">
    <div class="smt-glow" style="background:{c}"></div>
    <div class="smt-k">Sinyal saat ini</div>
    <div class="smt-signal" style="color:{c}">{html.escape(held.upper())}</div>
    <div class="smt-k">Sejak {since:%d %b %Y} · {days} hari · {html.escape(regime_desc)}</div>
    <div class="smt-bars">{''.join(rows)}</div>
    <div class="smt-k" style="margin-top:10px">Garis putih = ambang masuk {min_score:.0f}</div>
  </div>
</div>""", unsafe_allow_html=True)
