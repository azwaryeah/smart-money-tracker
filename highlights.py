"""
Halaman utama: sorotan finansial, Top 3 rekomendasi analitis, peta aliran dana,
aturan rotasi (status live), dan 5 berita pasar hari ini.
"""
import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from flow import fmt_usd
from style import section

WIB = ZoneInfo("Asia/Jakarta")
esc = html.escape

# ---------------------------------------------------------------------------
# Berita: 5 kejadian pasar hari ini
# ---------------------------------------------------------------------------
NEWS_QUERIES = [
    ("en", "US", "US:en", '"stock market today" OR "stocks close" OR "Wall Street" OR "markets wrap" OR '
                          '"bitcoin price" OR "gold price" OR "Treasury yields" OR "Fed"'),
    ("id", "ID", "ID:id", '"IHSG ditutup" OR "IHSG hari ini" OR "harga emas hari ini" OR "bitcoin hari ini" OR '
                          '"rupiah hari ini" OR "The Fed"'),
]
ASSET_KEYS = {
    "Saham": ["saham", "ihsg", "stock", "s&p", "nasdaq", "dow", "equit", "wall street", "bursa"],
    "Crypto": ["bitcoin", "btc", "crypto", "kripto", "ethereum", "stablecoin"],
    "Emas": ["emas", "gold", "antam", "logam mulia"],
    "Makro": ["fed", "suku bunga", "rate", "inflasi", "inflation", "yield", "obligasi", "treasury",
              "rupiah", "dolar", "dollar", "tarif", "tariff", "resesi", "recession", "bi rate", "jobs", "payroll", "cpi", "pce"],
}
NEG_FIRST = ["suku bunga naik", "kenaikan suku bunga", "rate hike", "hike rates", "inflasi naik", "inflation rises",
             "inflation jumps", "hotter-than-expected", "hotter than expected", "yields rise", "yields jump",
             "yield naik", "hike bets", "hawkish"]
POS_FIRST = ["rate cut", "cuts rates", "pemangkasan suku bunga", "suku bunga turun", "dovish", "inflasi turun",
             "inflation cools", "cooler-than-expected"]
UP = ["naik", "menguat", "melonjak", "rekor", "reli", "rally", "surge", "jump", "soar", "gain", "record", "rise",
      "rebound", "climb", "inflow", "higher"]
DOWN = ["turun", "melemah", "anjlok", "ambles", "jatuh", "koreksi", "tertekan", "plunge", "slump", "fall", "drop",
        "tumble", "sell-off", "selloff", "outflow", "crash", "losses", "lower", "slide", "sink"]
WRAP = ["today", "hari ini", "ditutup", "close", "closes", "wrap", "sesi", "session", "stocks", "markets"]
BIG = ["fed", "suku bunga", "rate", "rekor", "record", "anjlok", "crash", "plunge", "resesi", "recession",
       "inflasi", "inflation", "etf", "tarif", "tariff", "perang", "war", "bi rate", "surge", "melonjak", "cpi", "jobs"]


RATE_WORDS = ["suku bunga", "rate", "yield", "inflasi", "inflation", "cpi", "pce"]
RATE_UP = ["naik", "rise", "rises", "hike", "higher", "jump", "jumps", "meningkat", "panas", "hot"]


def _tone(t: str) -> str:
    if any(k in t for k in POS_FIRST):
        return "naik"
    if any(k in t for k in NEG_FIRST) or (any(k in t for k in RATE_WORDS) and any(re.search(rf"\b{k}\b", t) for k in RATE_UP)
                                          and not any(k in t for k in ("gold", "emas", "bitcoin", "saham", "stocks"))):
        return "turun"
    up, dn = sum(k in t for k in UP), sum(k in t for k in DOWN)
    return "naik" if up > dn else "turun" if dn > up else "netral"


@st.cache_data(ttl=900, show_spinner=False)
def fetch_news(limit: int = 5) -> list[dict]:
    items = []
    for hl, gl, ceid, q in NEWS_QUERIES:
        url = f"https://news.google.com/rss/search?q={quote_plus(q + ' when:1d')}&hl={hl}&gl={gl}&ceid={ceid}"
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0 smart-money-tracker"})
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception:
            continue
        for it in root.iter("item"):
            title = html.unescape(it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            src = it.find("source")
            source = src.text.strip() if src is not None and src.text else ""
            if source and title.endswith(" - " + source):
                title = title[: -len(source) - 3]
            try:
                when = parsedate_to_datetime(it.findtext("pubDate")).astimezone(WIB)
            except Exception:
                when = None
            items.append({"title": title, "link": link, "source": source, "when": when})
    now = pd.Timestamp.now(tz=WIB)
    for it in items:
        t = it["title"].lower()
        it["assets"] = [a for a, ks in ASSET_KEYS.items() if any(k in t for k in ks)]
        it["tone"] = _tone(t)
        fresh = it["when"] is not None and (now - it["when"]).total_seconds() < 8 * 3600
        it["score"] = (2 * sum(k in t for k in BIG) + 2 * any(k in t for k in WRAP) + len(it["assets"])
                       + (it["tone"] != "netral") + 2 * fresh)
    pool, seen = [], set()
    for it in sorted(items, key=lambda x: (x["score"], x["when"] or pd.Timestamp(0, tz=WIB)), reverse=True):
        key = re.sub(r"\W+", " ", it["title"].lower())[:60]
        if it["assets"] and key not in seen and it["link"].startswith("http"):
            seen.add(key)
            pool.append(it)
    # pilih beragam: satu per kelas aset dulu, lalu isi sisanya
    out = []
    for cls in ("Saham", "Makro", "Crypto", "Emas"):
        for it in pool:
            if cls in it["assets"] and it not in out:
                out.append(it)
                break
    for it in pool:
        if len(out) >= limit:
            break
        if it not in out:
            out.append(it)
    return sorted(out[:limit], key=lambda x: x["when"] or pd.Timestamp(0, tz=WIB), reverse=True)


def render_news(news: list[dict]):
    section("📰 Apa yang terjadi di pasar hari ini", "5 berita penggerak pasar · Google News")
    if not news:
        st.caption("Berita belum bisa dimuat saat ini.")
        return
    tone_c = {"naik": "#34D399", "turun": "#FB7185", "netral": "#64748B"}
    rows = []
    for it in news:
        when = it["when"].strftime("%H:%M") + " WIB" if it["when"] else ""
        meta = " · ".join(x for x in [when, it["source"], " · ".join(it["assets"])] if x)
        link = it["link"] if it["link"].startswith("http") else "#"
        rows.append(f"<a class='smt-item' href='{esc(link, quote=True)}' target='_blank' rel='noopener'>"
                    f"<span class='smt-tone' style='background:{tone_c[it['tone']]}'></span>"
                    f"<div><div class='h'>{esc(it['title'])}</div><div class='m'>{esc(meta)}</div></div></a>")
    st.markdown("<div class='smt-news'>" + "".join(rows) + "</div>", unsafe_allow_html=True)
    st.caption("Titik hijau/merah = dampak judul bagi aset berisiko (positif/negatif), dibaca otomatis dari kata kunci.")


# ---------------------------------------------------------------------------
# Sorotan finansial
# ---------------------------------------------------------------------------
def render_highlights(items: list[dict]):
    section("📌 Sorotan finansial", "kondisi pasar global saat ini")
    tone_c = {1: "#34D399", -1: "#FB7185", 0: "#8B95A8"}
    cells = "".join(
        f"<div class='smt-stat'><div class='k'>{esc(i['k'])}</div><div class='v'>{esc(i['v'])}</div>"
        f"<div class='d' style='color:{tone_c[i['tone']]}'>{esc(i['d'])}</div></div>" for i in items)
    st.markdown(f"<div class='smt-stats'>{cells}</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Peta aliran dana
# ---------------------------------------------------------------------------
def render_flow(ft: pd.DataFrame):
    section("💧 Peta aliran dana", "estimasi aliran bersih 20 hari (miliar USD) · diserap oleh siapa")
    if ft.empty:
        st.caption("Data volume belum tersedia.")
        return
    d = ft.sort_values("Aliran bersih 20h")
    fig = go.Figure(go.Bar(
        x=d["Aliran bersih 20h"] / 1e9, y=d["Instrumen"], orientation="h",
        marker_color=["#34D399" if v >= 0 else "#FB7185" for v in d["Aliran bersih 20h"]],
        text=[fmt_usd(v) for v in d["Aliran bersih 20h"]], textposition="inside", insidetextanchor="middle",
        textfont=dict(color="#0A0D14"),
        hovertemplate="%{y}<br>Aliran bersih 20 hari: %{text}<extra></extra>"))
    m = float(np.nanmax(np.abs(d["Aliran bersih 20h"] / 1e9))) * 1.2 or 1
    fig.update_layout(height=60 + 46 * len(d), margin=dict(t=10, b=10, l=0, r=10),
                      xaxis=dict(range=[-m, m], zeroline=True, ticksuffix=" M$"),
                      showlegend=False)
    st.plotly_chart(fig, width="stretch", key="flow_bars")
    rows = []
    for _, r in ft.sort_values("Aliran bersih 20h", ascending=False).iterrows():
        good = r["Aliran bersih 20h"] >= 0
        rows.append(
            f"<div class='smt-flow'><div class='fl-n'><b>{esc(r['Instrumen'])}</b>"
            f"<span>{esc(r['Pelaku utama'])}</span></div>"
            f"<div class='fl-m'><span>Volume/hari<b>{fmt_usd(r['Volume $/hari (20h)'])}</b></span>"
            f"<span>Vol. relatif<b>{r['Volume relatif']:.2f}×</b></span>"
            f"<span>Harga 20h<b>{r['Harga 20h'] * 100:+.1f}%</b></span>"
            f"<span>CMF<b>{r['CMF 20h']:+.2f}</b></span></div>"
            f"<div class='fl-a' style='color:{'#A7F3D0' if good else '#FECDD3'}'>{esc(r['Penyerapan'])}</div></div>")
    st.markdown("<div class='smt-flows'>" + "".join(rows) + "</div>", unsafe_allow_html=True)
    with st.expander("Cara membaca peta aliran dana"):
        st.markdown("""
- **Aliran bersih** = volume dolar yang terjadi saat harga ditutup dekat harga tertinggi (tekanan beli) dikurangi yang ditutup dekat terendah (tekanan jual), dijumlah 20 hari. Positif = uang bersih **masuk**.
- **Volume relatif** > 1,1× = uang yang berputar di instrumen itu sedang **bertambah** dibanding 3 bulan terakhir.
- **CMF** > +0,05 = **akumulasi** (pembeli besar menyerap); < −0,05 = **distribusi** (pemain besar melepas).
- **Diserap oleh siapa**: ETF (IBIT, GLD) mencerminkan institusi & penasihat keuangan; spot crypto mencerminkan ritel & whale; HYG mencerminkan dana kredit; IEF mencerminkan dana defensif.
- Volume crypto spot dari Yahoo adalah agregat bursa dan bisa lebih besar dari volume riil; bandingkan arah & perubahannya, bukan angka absolutnya.
""")


# ---------------------------------------------------------------------------
# Top 3 rekomendasi analitis
# ---------------------------------------------------------------------------
PRIMARY = {"Saham": "Saham", "Crypto": "ETF Bitcoin (IBIT)", "Emas": "ETF Emas (GLD)"}


def _row(ft, cls, prefer=None):
    if ft.empty:
        return None
    sub = ft[ft["Instrumen"].str.startswith(prefer or PRIMARY.get(cls, cls))]
    if sub.empty:
        sub = ft[ft["Kelas"] == cls]
    return None if sub.empty else sub.iloc[0]


def _flow_line(r) -> str:
    if r is None:
        return ""
    return (f"{r['Instrumen']}: aliran bersih {fmt_usd(r['Aliran bersih 20h'])}, vol. relatif {r['Volume relatif']:.2f}×, "
            f"CMF {r['CMF 20h']:+.2f} → {r['Penyerapan'].split(' — ')[0].lower()}")


def _pct(x):
    return "n/a" if pd.isna(x) else f"{x * 100:+.1f}%"


def top3(scores, path, status, macro, feats, ft, crypto, md, min_score, margin, confirm, regime) -> list[dict]:
    last = scores.iloc[-1]
    wk = scores.iloc[-6] if len(scores) > 6 else scores.iloc[0]
    held = path.iloc[-1]
    m = macro.iloc[-1]
    by_cls = ft.groupby("Kelas")["Aliran bersih 20h"].sum() if not ft.empty else pd.Series(dtype=float)
    hy_ie = None
    try:
        hy = md.close["HYG"].dropna()
        ie = md.close["IEF"].dropna()
        hy_ie = ((hy.iloc[-1] / hy.iloc[-22]) - (ie.iloc[-1] / ie.iloc[-22])) * 100
    except Exception:
        pass
    dxy = macro["dxy"].dropna()
    dxy1m = (dxy.iloc[-1] / dxy.iloc[-22] - 1) * 100 if len(dxy) > 22 else np.nan
    tnx = macro["tnx"].dropna()
    tnx1m = (tnx.iloc[-1] - tnx.iloc[-22]) * 100 if len(tnx) > 22 else np.nan
    macro_line = (f"VIX {m['vix']:.1f} · DXY {dxy1m:+.1f}% (1 bln) · yield 10th {tnx1m:+.0f} bps"
                  + (f" · kredit HYG−IEF {hy_ie:+.1f} pp" if hy_ie is not None else ""))
    recs = []

    # 1) POSISI UTAMA ---------------------------------------------------------
    if held == "Kas":
        best = last.idxmax()
        bil = md.close["BIL"].dropna() if "BIL" in md.close else pd.Series(dtype=float)
        cash_y = ((bil.iloc[-1] / bil.iloc[-64]) ** 4 - 1) * 100 if len(bil) > 64 else np.nan
        recs.append({
            "stance": "POSISI", "c": "#94A3B8", "title": "Tetap di Kas / pasar uang",
            "thesis": (f"Tidak ada kelas aset yang lolos ambang {min_score:.0f}: tertinggi {best} {last[best]:.0f}. "
                       f"Rezim {regime.lower()} — uang global sedang menghindari risiko."),
            "ev": [
                "Aliran bersih 20h per kelas: " + ", ".join(f"{k} {fmt_usd(v)}" for k, v in by_cls.items()),
                _flow_line(_row(ft, best)),
                macro_line,
                (f"Kas (T-Bill) memberi ±{cash_y:.1f}%/thn tanpa risiko harga" if pd.notna(cash_y) else ""),
            ],
            "trigger": f"Masuk {best} bila skornya ≥ {min_score:.0f}, unggul ≥ {margin:.0f} poin, bertahan {confirm} hari (kini {last[best]:.0f}).",
        })
    else:
        f = feats[held].iloc[-1]
        weak = last[held] < min_score
        r = _row(ft, held)
        recs.append({
            "stance": "POSISI", "c": "#F59E0B" if weak else "#34D399",
            "title": f"{'Kurangi' if weak else 'Pegang'} {held}",
            "thesis": (f"Skor {held} {last[held]:.0f} ({last[held] - wk[held]:+.1f} seminggu). "
                       + ("Momentum melemah di bawah ambang — lindungi keuntungan." if weak else
                   ("Masih memimpin rotasi; uang belum keluar dari aset ini." if last.idxmax() == held else
                    f"{last.idxmax()} unggul {last.max() - last[held]:.0f} poin, belum memenuhi syarat pindah "
                    f"(≥ {margin:.0f} poin selama {confirm} hari)."))),
            "ev": [
                f"Return 1B {_pct(f.r1m)} · 3B {_pct(f.r3m)} · 6B {_pct(f.r6m)}",
                _flow_line(r),
                macro_line,
            ],
            "trigger": (f"Keluar bila skor < {min_score - margin:.0f} atau aset lain unggul ≥ {margin:.0f} poin "
                        f"selama {confirm} hari."),
        })

    # 2) ARUS DANA TERKUAT ----------------------------------------------------
    cands = [a for a in last.index if a != held]
    flow_rank = {a: (by_cls.get(a, 0.0)) for a in cands}
    tgt = max(cands, key=lambda a: (flow_rank[a], last[a]))
    r = _row(ft, tgt)
    spot = _row(ft, "Crypto", "Bitcoin spot") if tgt == "Crypto" else None
    gap_th = min_score - last[tgt]
    st_ = status or {}
    streak = st_.get("streak", 0) if st_.get("cand") == tgt else 0
    ev = [_flow_line(r)]
    if spot is not None:
        ev.append(_flow_line(spot))
    ev.append(f"Skor {last[tgt]:.0f} ({last[tgt] - wk[tgt]:+.1f} seminggu) · "
              f"{'sudah di atas' if gap_th <= 0 else f'butuh +{gap_th:.0f} poin ke'} ambang {min_score:.0f}")
    ev.append(f"Hitungan konfirmasi rotasi: {streak}/{confirm} hari")
    inflow = by_cls.get(tgt, 0.0) > 0
    recs.append({
        "stance": "ARUS DANA", "c": "#60A5FA",
        "title": f"Uang {'mengalir ke' if inflow else 'paling sedikit keluar dari'} {tgt}",
        "thesis": (f"Dari kelas aset di luar posisi Anda, {tgt} menerima aliran bersih terbesar "
                   f"({fmt_usd(by_cls.get(tgt, np.nan))} dalam 20 hari). "
                   + ("Siapkan rencana masuk bertahap." if inflow else "Belum ada uang baru yang masuk — tunggu.")),
        "ev": ev,
        "trigger": f"Rotasi ke {tgt} sah bila skor ≥ {min_score:.0f} dan unggul ≥ {margin:.0f} poin dari {held} selama {confirm} hari.",
    })

    # 3) RISIKO & STRUKTUR CRYPTO --------------------------------------------
    dom, sdom, fng = crypto.get("btc_dom"), crypto.get("stable_dom"), crypto.get("fng")
    b, e = md.close.get("BTC-USD"), md.close.get("ETH-USD")
    btc_eth = None
    if b is not None and e is not None:
        rr = (b / e).dropna()
        if len(rr) > 31:
            btc_eth = (rr.iloc[-1] / rr.iloc[-31] - 1) * 100
    ev, title, thesis = [], "Struktur risiko pasar", ""
    if dom is not None:
        ev.append(f"Bitcoin dominance {dom:.1f}%" + (f" · BTC vs ETH {btc_eth:+.1f}% (30h)" if btc_eth is not None else ""))
    if sdom is not None:
        ev.append(f"Porsi stablecoin {sdom:.1f}% dari kapitalisasi crypto (dana menunggu di pinggir)")
    if fng is not None:
        ev.append(f"Crypto Fear & Greed {fng} ({crypto.get('fng_label', '')})")
    ibit, spot = _row(ft, "Crypto", "ETF Bitcoin"), _row(ft, "Crypto", "Bitcoin spot")
    if ibit is not None and spot is not None:
        ev.append(f"Institusi (IBIT) {fmt_usd(ibit['Aliran bersih 20h'])} vs spot {fmt_usd(spot['Aliran bersih 20h'])}")
    ev.append(macro_line)
    if fng is not None and fng <= 25:
        title = "Crypto: ketakutan ekstrem"
        thesis = "Sentimen di titik terendah; secara historis smart money mulai mengakumulasi di sini. Hanya cicil kecil (DCA), jangan sekaligus."
    elif fng is not None and fng >= 75:
        title = "Crypto: keserakahan ekstrem"
        thesis = "Euforia tinggi; risiko koreksi besar. Hindari FOMO, pertimbangkan ambil sebagian untung."
    elif dom is not None and btc_eth is not None and dom >= 55 and btc_eth > 0:
        title = "Crypto defensif: dana berlindung di Bitcoin"
        thesis = "Dominance tinggi dan BTC mengungguli ETH — uang menghindari altcoin. Jika masuk crypto, utamakan BTC."
    elif btc_eth is not None and btc_eth < -5 and (fng or 50) > 55:
        title = "Spekulasi memanas: rotasi ke altcoin"
        thesis = "BTC kalah dari ETH dan sentimen serakah — ciri fase akhir reli. Perketat manajemen risiko."
    elif m["vix"] >= 25:
        title = "Volatilitas tinggi — kecilkan risiko"
        thesis = "VIX di zona takut. Hindari leverage, perbesar porsi aman sampai volatilitas mereda."
    elif pd.notna(dxy1m) and dxy1m > 1.5:
        title = "Dolar menguat — tekanan untuk emas, crypto, IHSG"
        thesis = "Dolar naik tajam menyedot likuiditas global dari aset non-dolar."
    else:
        title = f"Rezim {regime}"
        thesis = f"Selera risiko global {m.get('risk', 0):+.2f} (−1 takut … +1 berani). Tidak ada tekanan ekstrem; disiplin pada sinyal."
    recs.append({"stance": "RISIKO", "c": "#FB7185" if "takut" in title.lower() or "tinggi" in title.lower() else "#A78BFA",
                 "title": title, "thesis": thesis, "ev": ev,
                 "trigger": "Pandangan berubah bila dominance turun tajam, stablecoin menyusut (dana masuk), atau VIX < 18."})
    for rc in recs:
        rc["ev"] = [x for x in rc["ev"] if x]
    return recs


def render_top3(recs: list[dict]):
    section("🎯 Top 3 rekomendasi hari ini", "tesis · bukti angka · pemicu perubahan")
    cols = st.columns(3)
    for i, (col, r) in enumerate(zip(cols, recs), 1):
        ev = "".join(f"<li>{esc(x)}</li>" for x in r["ev"])
        col.markdown(
            f"<div class='smt-rec' style='--c:{r['c']}'><div class='n'>0{i} · {esc(r['stance'])}</div>"
            f"<div class='t'>{esc(r['title'])}</div><div class='b'>{esc(r['thesis'])}</div>"
            f"<ul class='ev'>{ev}</ul><div class='tr'><b>Pemicu:</b> {esc(r['trigger'])}</div></div>",
            unsafe_allow_html=True)
    st.caption("Rekomendasi otomatis dari model sinyal, bukan nasihat keuangan pribadi.")


# ---------------------------------------------------------------------------
# Aturan rotasi (status live)
# ---------------------------------------------------------------------------
def render_rules(scores, path, status, min_score, margin, confirm, cost):
    section("🔁 Aturan rotasi", "kapan tepatnya pindah aset — status hari ini")
    last = scores.iloc[-1]
    held = path.iloc[-1]
    st_ = status or {}
    best, bs = last.idxmax(), last.max()
    cand = st_.get("cand", best if bs >= min_score else "Kas")
    held_s = last[held] if held in last else 50.0
    cand_s = last[cand] if cand in last else 50.0
    streak = st_.get("streak", 0)
    switched = len(path) > 1 and path.iloc[-1] != path.iloc[-2]
    ok1 = bs >= min_score
    gap = cand_s - held_s
    ok2 = cand != held and gap >= margin
    exit_ = held != "Kas" and held_s < min_score - margin
    steps = [
        (ok1, "Ambang masuk", f"Aset terkuat harus punya skor ≥ {min_score:.0f}. Jika tidak ada, kandidat = Kas.",
         f"{best} {bs:.0f} → {'lolos' if ok1 else 'belum lolos, kandidat = Kas'}"),
        (ok2 or cand == held, "Keunggulan", f"Kandidat harus unggul ≥ {margin:.0f} poin dari posisi sekarang.",
         "kandidat = posisi sekarang, tidak perlu pindah" if cand == held else
         f"{cand} {cand_s:.0f} vs {held} {held_s:.0f} → selisih {gap:+.0f}"),
        (streak >= confirm or cand == held, "Konfirmasi", f"Syarat 1–2 harus bertahan {confirm} hari bursa berturut-turut (anti sinyal palsu).",
         "tidak berjalan" if cand == held else f"hari ke-{streak} dari {confirm}"),
        (not exit_, "Jalur keluar", f"Jika skor posisi turun < {min_score - margin:.0f}, keluar ke kandidat terbaik atau Kas.",
         "tidak berlaku (sedang di Kas)" if held == "Kas" else f"{held} {held_s:.0f} → {'AKTIF, siapkan keluar' if exit_ else 'aman'}"),
        (True, "Eksekusi", f"Pindah pada pembukaan hari berikutnya (H+1) setelah konfirmasi. Biaya diasumsikan {cost * 100:.2f}% per pindah.",
         "sinyal dari harga penutupan harian, bukan pergerakan intrahari"),
    ]
    if switched:
        decision, dc = f"PINDAH ke {held} — terkonfirmasi hari ini, eksekusi besok", "#34D399"
    elif cand != held and streak > 0:
        decision, dc = f"CALON PINDAH ke {cand} — konfirmasi hari ke-{streak}/{confirm}", "#FBBF24"
    else:
        decision, dc = f"TAHAN {held}", "#93C5FD"
    rows = "".join(
        f"<div class='smt-step'><span class='ic' style='color:{'#34D399' if ok else '#FB7185'}'>{'✓' if ok else '✗'}</span>"
        f"<div><div class='st'>{i}. {esc(t)}</div><div class='sd'>{esc(d)}</div>"
        f"<div class='sn'>Hari ini: {esc(n)}</div></div></div>" for i, (ok, t, d, n) in enumerate(steps, 1))
    st.markdown(f"<div class='smt-card smt-rules'><div class='dec' style='color:{dc}'>Keputusan hari ini: {esc(decision)}</div>"
                f"{rows}</div>", unsafe_allow_html=True)
    st.caption("Parameter ambang, selisih, dan hari konfirmasi bisa diatur di sidebar (tombol » kiri atas).")
