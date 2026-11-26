"""
Halaman utama: Top 3 rekomendasi (dari sinyal model) + berita besar pasar (Google News RSS, gratis).
"""
import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

WIB = ZoneInfo("Asia/Jakarta")

NEWS_QUERIES = [
    ("id", "ID", "ID:id", "IHSG OR saham OR \"harga emas\" OR bitcoin OR \"The Fed\" OR rupiah"),
    ("en", "US", "US:en", "stock market OR Federal Reserve OR bitcoin OR gold price OR treasury yields"),
]
ASSET_KEYS = {
    "Saham": ["saham", "ihsg", "stock", "s&p", "nasdaq", "dow", "equit", "wall street", "bursa"],
    "Crypto": ["bitcoin", "btc", "crypto", "kripto", "ethereum", "etf bitcoin", "stablecoin"],
    "Emas": ["emas", "gold", "antam", "logam mulia"],
    "Makro": ["fed", "the fed", "suku bunga", "rate", "inflasi", "inflation", "yield", "obligasi", "treasury",
              "rupiah", "dolar", "dollar", "tarif", "tariff", "resesi", "recession", "bi rate", "jobs", "payroll"],
}
UP = ["naik", "menguat", "melonjak", "rekor", "reli", "rally", "surge", "jump", "soar", "gain", "record", "rise",
      "rebound", "bullish", "inflow", "beli", "pemangkasan suku bunga", "rate cut", "cuts rates"]
DOWN = ["turun", "melemah", "anjlok", "ambles", "jatuh", "koreksi", "tertekan", "plunge", "slump", "fall", "drop",
        "tumble", "sell-off", "selloff", "bearish", "outflow", "crash", "losses", "kenaikan suku bunga", "rate hike"]
BIG = ["fed", "the fed", "suku bunga", "rate", "rekor", "record", "anjlok", "crash", "plunge", "resesi", "recession",
       "inflasi", "inflation", "etf", "tarif", "tariff", "perang", "war", "bi rate", "surge", "melonjak"]


@st.cache_data(ttl=900, show_spinner=False)
def fetch_news(limit: int = 6) -> list[dict]:
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
            items.append({"title": title, "link": link, "source": source, "when": when, "lang": hl})
    if not items:
        return []
    for it in items:
        t = it["title"].lower()
        it["assets"] = [a for a, ks in ASSET_KEYS.items() if any(k in t for k in ks)]
        up = sum(k in t for k in UP)
        dn = sum(k in t for k in DOWN)
        it["tone"] = "naik" if up > dn else "turun" if dn > up else "netral"
        it["score"] = (2 * sum(k in t for k in BIG) + len(it["assets"]) + (up + dn)
                       + (1 if it["when"] and (pd.Timestamp.now(tz=WIB) - it["when"]).total_seconds() < 6 * 3600 else 0))
    seen, out = set(), []
    for it in sorted(items, key=lambda x: (x["score"], x["when"] or pd.Timestamp(0, tz=WIB)), reverse=True):
        key = re.sub(r"\W+", " ", it["title"].lower())[:60]
        if not it["assets"] or key in seen or not it["link"].startswith("http"):
            continue
        seen.add(key)
        out.append(it)
        if len(out) >= limit:
            break
    return out


def top3(scores: pd.DataFrame, path: pd.Series, macro: pd.DataFrame, min_score: float, margin: float,
         confirm: int, regime: str, crypto: dict | None) -> list[dict]:
    last = scores.iloc[-1]
    wk = scores.iloc[-6] if len(scores) > 6 else scores.iloc[0]
    held = path.iloc[-1]
    changed = len(path) > 1 and path.iloc[-1] != path.iloc[-2]
    prev_held = path.iloc[-2] if len(path) > 1 else held
    recs = []

    # 1) Aksi utama
    if changed:
        recs.append({"icon": "🔁", "title": f"Pindah dari {prev_held} ke {held}",
                     "body": f"Sinyal rotasi baru terkonfirmasi hari ini. Skor {held}: "
                             f"{last[held]:.0f}" if held != "Kas" else "Semua skor di bawah ambang — amankan ke kas/pasar uang.",
                     "tone": "action"})
    elif held == "Kas":
        best = last.idxmax()
        recs.append({"icon": "💵", "title": "Tahan di Kas / pasar uang",
                     "body": f"Belum ada aset yang layak dimasuki: skor tertinggi {best} {last[best]:.0f} (< {min_score:.0f}). "
                             "Hindari membeli besar-besaran dulu.", "tone": "hold"})
    else:
        trend = last[held] - wk[held]
        if last[held] < min_score:
            recs.append({"icon": "⚠️", "title": f"Kurangi posisi {held}",
                         "body": f"Skor {held} melemah ke {last[held]:.0f} (di bawah {min_score:.0f}). Pertimbangkan ambil sebagian untung.",
                         "tone": "warn"})
        else:
            recs.append({"icon": "✅", "title": f"Tetap pegang {held}",
                         "body": f"Skor {last[held]:.0f}, {'menguat' if trend >= 0 else 'melemah'} {trend:+.1f} poin dalam seminggu. "
                                 "Belum ada sinyal pindah.", "tone": "hold"})

    # 2) Aset yang perlu dipantau (kenaikan skor terbesar / paling dekat ambang)
    cands = [a for a in last.index if a != held]
    rise = {a: last[a] - wk[a] for a in cands}
    watch = max(cands, key=lambda a: (last[a] >= min_score - 10) * 100 + rise[a])
    gap = min_score - last[watch]
    if gap <= 0:
        body = (f"Skor {watch} {last[watch]:.0f} sudah di atas ambang. Pindah jika unggul ≥ {margin:.0f} poin "
                f"dari posisi sekarang selama {confirm} hari.")
    else:
        body = (f"Skor {watch} {last[watch]:.0f} ({rise[watch]:+.1f} seminggu), butuh +{gap:.0f} poin lagi untuk "
                f"ambang {min_score:.0f}. Siapkan rencana masuk bertahap.")
    recs.append({"icon": "👀", "title": f"Pantau {watch}", "body": body, "tone": "watch"})

    # 3) Catatan risiko makro / sentimen
    m = macro.iloc[-1]
    fng = (crypto or {}).get("fng")
    if fng is not None and fng <= 25:
        recs.append({"icon": "🧊", "title": "Crypto: ketakutan ekstrem",
                     "body": f"Fear & Greed {fng}. Secara historis zona akumulasi pemain besar — kalau tertarik, cicil (DCA) kecil, jangan sekaligus.",
                     "tone": "watch"})
    elif fng is not None and fng >= 75:
        recs.append({"icon": "🔥", "title": "Crypto: keserakahan ekstrem",
                     "body": f"Fear & Greed {fng}. Rawan koreksi — hindari FOMO, pertimbangkan ambil sebagian untung.",
                     "tone": "warn"})
    elif pd.notna(m.get("vix")) and m["vix"] >= 25:
        recs.append({"icon": "🛡️", "title": "Volatilitas tinggi — kecilkan risiko",
                     "body": f"VIX {m['vix']:.1f}. Pasar sedang takut: hindari leverage, perbesar porsi aman.", "tone": "warn"})
    elif m.get("dxy_sig", 0) > 0.3:
        recs.append({"icon": "💲", "title": "Dolar menguat",
                     "body": "DXY naik tajam — biasanya menekan emas, crypto, dan rupiah/IHSG. Hati-hati menambah posisi di sana.",
                     "tone": "warn"})
    elif m.get("dxy_sig", 0) < -0.3:
        recs.append({"icon": "🌤️", "title": "Dolar melemah",
                     "body": "DXY turun — angin segar untuk emas, crypto, dan pasar berkembang termasuk IHSG.", "tone": "hold"})
    else:
        recs.append({"icon": "🧭", "title": f"Rezim: {regime}",
                     "body": f"Selera risiko global {m.get('risk', 0):+.2f} (−1 takut … +1 berani). Disiplin pada sinyal, cek ulang mingguan.",
                     "tone": "hold"})
    return recs[:3]


TONE_BG = {"action": "#dcfce7", "hold": "#e0f2fe", "watch": "#fef9c3", "warn": "#fee2e2"}


def render_top3(recs: list[dict]):
    st.subheader("🎯 Top 3 rekomendasi hari ini")
    cols = st.columns(3)
    for i, (col, r) in enumerate(zip(cols, recs), 1):
        with col:
            st.markdown(
                f"<div style='background:{TONE_BG[r['tone']]};color:#111827;border-radius:12px;padding:14px 16px;"
                f"height:100%;min-height:150px'><div style='font-size:13px;opacity:.7'>#{i}</div>"
                f"<div style='font-size:19px;font-weight:700;margin:2px 0 6px'>{r['icon']} {html.escape(r['title'])}</div>"
                f"<div style='font-size:15px;line-height:1.45'>{html.escape(r['body'])}</div></div>",
                unsafe_allow_html=True)


def render_news(news: list[dict]):
    st.subheader("📰 Berita besar pasar (24 jam)")
    if not news:
        st.caption("Berita belum bisa dimuat saat ini.")
        return
    tone_icon = {"naik": "🟢", "turun": "🔴", "netral": "⚪"}
    for it in news:
        when = it["when"].strftime("%d %b %H:%M") if it["when"] else ""
        tags = " · ".join(it["assets"])
        title = it["title"].replace("[", "(").replace("]", ")").replace("$", "\\$")
        st.markdown(f"{tone_icon[it['tone']]} **[{title}]({it['link']})**  \n"
                    f"<span style='font-size:13px;opacity:.7'>{html.escape(it['source'])} · {when} WIB · {tags}</span>",
                    unsafe_allow_html=True)
    st.caption("Sumber: Google News. 🟢/🔴 = nada judul (naik/turun) terdeteksi otomatis dari kata kunci, bukan analisis isi.")
