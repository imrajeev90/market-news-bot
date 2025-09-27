#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hinglish WhatsApp-style Market News Watcher (Indexes + Stocks)
- Polls key RSS feeds every POLL_SECS
- Scores headlines (importance) + classifies index & stock impact
- Sends concise Telegram alerts: Summary + Impact + Scalp Plan + Stocks to watch
"""

import os, time, re, hashlib, requests, feedparser, datetime as dt
from dotenv import load_dotenv

load_dotenv()
BOT  = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TZ   = os.getenv("TZ", "Asia/Kolkata")
POLL = int(os.getenv("POLL_SECS", "45"))
MIN_SCORE = int(os.getenv("MIN_IMPORTANCE", "60"))  # 0-100

# ---------- Telegram ----------
def tg_send(text: str):
    if not (BOT and CHAT): return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT}/sendMessage",
            data={"chat_id": CHAT, "text": text, "parse_mode":"Markdown", "disable_web_page_preview": True},
            timeout=15
        )
    except Exception:
        pass

# ---------- Feeds ----------
FEEDS = [
    "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://www.livemint.com/rss/markets",
    "https://www.cnbctv18.com/api/v1/rss/markets.xml",
    "https://www.reuters.com/markets/asia/rss",
    "https://www.reuters.com/markets/us/rss",
    "https://www.reuters.com/markets/europe/rss",
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
]

# ---------- Words / Scoring ----------
STRICT_WORDS = r"(BREAKING|ALERT|FLASH|JUST IN|URGENT|UPDATE|EMERGENCY)"
BULL_WORDS   = r"(surge|beats|record high|upgrade|eases|cooling|cut|dovish|rall(y|ies)|jump)"
BEAR_WORDS   = r"(plunge|miss(es)?|downgrade|spike in|soars inflation|hawkish|ban|raid|tax hike|probe|defaults?)"

def score_title(title: str, source: str) -> int:
    t = title.upper()
    score = 0
    if re.search(STRICT_WORDS, t): score += 30
    if re.search(BEAR_WORDS,   t): score += 14
    if re.search(BULL_WORDS,   t): score += 12
    if re.search(r"\b\d+(\.\d+)?%|\+\d+|\-\d+", t): score += 8
    if any(s in source.lower() for s in ["reuters","moneycontrol","economictimes","livemint","cnbctv18","wsj"]):
        score += 16
    caps = sum(1 for c in title if c.isupper())
    if caps > len(title)*0.30: score += 5
    return min(score, 100)

def sentiment(title: str) -> str:
    t = title.lower()
    if re.search(BEAR_WORDS, t): return "bearish"
    if re.search(BULL_WORDS, t): return "bullish"
    return "neutral"

# ---------- Index impact rules (broad) ----------
INDEX_RULES = [
    (r"\b(RBI|MPC|repo rate|CRR|SLR|liquidity|monetary policy|bond yield)\b", "BankNifty", "Policy/Hawkish?"),
    (r"\b(Fed|FOMC|Powell|dot plot|rate (hike|cut)|QE|QT|Treasury)\b",        "Nifty",     "Global risk"),
    (r"\b(brent|crude|opec|WTI|inventory)\b",                                 "Nifty",     "Crude move"),
    (r"\b(USDINR|dollar index|DXY|rupee weak|RBI intervene)\b",               "Nifty",     "FX move"),
    (r"\b(CPI|inflation|PPI|jobs|payrolls|unemployment|GDP)\b",               "Nifty",     "Macro print"),
    (r"\b(MSCI|FTSE|rebalanc|inclusion|exclusion|FPI|FII (inflow|outflow))\b","Nifty",     "Flow event"),
    (r"\b(SEBI|margin|F&O|lot size|ban list|ASM|GSM|circular)\b",             "Nifty",     "Microstructure"),
    (r"\b(China|Middle East|war|missile|attack|geopolitics|sanction|shutdown)\b","Nifty",   "Geopolitics"),
]

# ---------- Stock impact map (ticker synonyms -> (index_focus, pretty_name, default_plan)) ----------
# Add/edit as you like
STOCK_MAP = {
    r"\b(HDFC Bank|HDFCBANK)\b": ("BankNifty","HDFC Bank","Result/guidance pe 5m close ke baad trade; avoid far OTM."),
    r"\b(ICICI Bank|ICICIBANK)\b": ("BankNifty","ICICI Bank","News spike fade/breakout with VWAP confirm."),
    r"\b(State Bank of India|SBI|SBIN)\b": ("BankNifty","SBI","PSU banks volatile; size kam."),
    r"\b(Kotak Mahindra|KOTAKBANK)\b": ("BankNifty","Kotak Bank","Structure-follow; SL prev swing."),
    r"\b(Axis Bank|AXISBANK)\b": ("BankNifty","Axis Bank","News-driven; VWAP retest entry."),
    r"\b(IndusInd Bank|INDUSINDBK)\b": ("BankNifty","IndusInd Bank","Use 5m trend filter."),
    r"\b(Reliance|RIL)\b": ("Nifty","Reliance","Gap move fade/continue per VWAP; energy news sensitive."),
    r"\b(TCS)\b": ("Nifty","TCS","IT strength on DXY up; buy dips."),
    r"\b(Infosys|INFY)\b": ("Nifty","Infosys","DXY up supportive; dips buy with SL VWAP-0.2%."),
    r"\b(HCL Tech|HCLTECH)\b": ("Nifty","HCL Tech","Follow IT basket."),
    r"\b(Larsen|L&T|LT)\b": ("Nifty","Larsen & Toubro","Infra/policy headlines—trend follow."),
    r"\b(ITC)\b": ("Nifty","ITC","Excise/duty news sensitive."),
    r"\b(Hindustan Unilever|HUL)\b": ("Nifty","HUL","Rural/consumption prints matter."),
    r"\b(Bharti Airtel|Airtel|BHARTIARTL)\b": ("Nifty","Bharti Airtel","Tariff/AGR headlines—trend follow."),
    r"\b(Tata Motors)\b": ("Nifty","Tata Motors","JLR/news—gap rules."),
    r"\b(Maruti)\b": ("Nifty","Maruti","Auto prints—trend follow."),
    r"\b(Bajaj Finance|BAJFINANCE)\b": ("Nifty","Bajaj Finance","Rate-sensitive; use tight SL."),
    r"\b(Adani Ports)\b": ("Nifty","Adani Ports","Flows/news sensitive."),
    r"\b(Adani Enterprises)\b": ("Nifty","Adani Enterprises","Volatile; size small."),
    r"\b(ONGC)\b": ("Nifty","ONGC","Crude up ⇒ ONGC up; watch gap rules."),
    r"\b(Coal India)\b": ("Nifty","Coal India","Volume prints; trend follow."),
    r"\b(JSW Steel)\b": ("Nifty","JSW Steel","Metal news—momentum follow."),
    r"\b(Tata Steel)\b": ("Nifty","Tata Steel","China/steel prints—momentum."),
    r"\b(Ultratech|ULTRACEMCO)\b": ("Nifty","UltraTech Cem","Cement price updates sensitive."),
    r"\b(Asian Paints)\b": ("Nifty","Asian Paints","Crude up ⇒ paints weak; fade pops."),
    r"\b(BPCL)\b": ("Nifty","BPCL","Crude up ⇒ OMCs weak; fade pops."),
    r"\b(HPCL)\b": ("Nifty","HPCL","Same as OMCs."),
    r"\b(IOC)\b": ("Nifty","IOC","Same as OMCs."),
    r"\b(Power Grid|POWERGRID)\b": ("Nifty","Power Grid","Defensive; trend follow."),
    r"\b(NTPC)\b": ("Nifty","NTPC","Power theme; follow-through only."),
}

# ---------- Plans ----------
def plan_for_index(focus: str, senti: str) -> str:
    if focus == "BankNifty":
        if senti == "bearish": return "BN weak bias. VWAP ke paas spike aaye to fade karo; SL last swing high; partials @ -0.5%."
        if senti == "bullish": return "BN strength. Pullback to VWAP pe buy; SL last swing low; partials @ +0.5%."
        return "BN neutral. Range edges trade karo; only post-VWAP reclaim/reject."
    else:  # Nifty or Sensex
        if senti == "bearish": return "NIFTY down-bias. Pops short near VWAP; SL VWAP+0.15%; partials @ -0.4%."
        if senti == "bullish": return "NIFTY up-bias. Dips buy near VWAP; SL VWAP-0.15%; partials @ +0.4%."
        return "NIFTY neutral. Structure follow; avoid chop."
        
def stock_list_from_title(title: str):
    hits = []
    for pat, (idx, nice, default) in STOCK_MAP.items():
        if re.search(pat, title, flags=re.I):
            hits.append((nice, idx, default))
    return hits[:6]  # keep message short

# ---------- Helpers ----------
DB = set()
def seen(k: str) -> bool:
    h = hashlib.sha256(k.encode("utf-8")).hexdigest()
    if h in DB: return True
    DB.add(h); return False

def classify_index(title: str):
    for pat, focus, tone in INDEX_RULES:
        if re.search(pat, title, flags=re.I):
            return focus, tone
    # fallback: if title has Bank names, tilt to BN
    if re.search(r"\b(HDFC|ICICI|SBI|KOTAK|AXIS|INDUSIND)\b", title, flags=re.I):
        return "BankNifty", "Banks-driven"
    return "Nifty", "Market"

def make_summary(t: str) -> str:
    t = re.sub(r"^\s*(BREAKING|JUST IN|ALERT)[:\-]\s*", "", t, flags=re.I)
    t = re.sub(r"\s*\|\s*", " — ", t)
    return t.strip()

def fmt_msg(title: str, link: str, src: str, focus: str, tone: str, senti: str, stocks_hit):
    emoji = "🚨" if re.search(STRICT_WORDS, title.upper()) else ("🟢" if senti=="bullish" else ("🔴" if senti=="bearish" else "⚠️"))
    idx_emoji = {"Nifty":"📊","BankNifty":"🏦","Sensex":"📈"}.get(focus,"📊")
    clock = dt.datetime.now().strftime("%I:%M %p").lstrip("0")
    summary = make_summary(title)

    plan = plan_for_index(focus, senti)
    # stock lines
    stock_lines = []
    for nice, idx, default in stocks_hit:
        sp = ("Buy dips" if senti=="bullish" else "Fade pops" if senti=="bearish" else "Structure follow")
        stock_lines.append(f"- {nice}: {sp}; {default}")
    stocks_block = "\n".join(stock_lines) if stock_lines else "—"

    msg = (
        f"{emoji} *{idx_emoji} {focus} — {tone} ({senti})*\n"
        f"{summary}\n\n"
        f"*Index Plan:* {plan}\n"
        f"*Stocks to watch:*\n{stocks_block}\n"
        f"🕒 {clock} • Source: {src}\n"
    )
    if link: msg += link
    return msg

def gather_entries():
    out = []
    for url in FEEDS:
        try:
            feed = feedparser.parse(url)
            src = (feed.feed.get("title") or feed.feed.get("link") or url).split("//")[-1][:40]
            for e in feed.entries[:15]:
                out.append({"title": e.get("title",""), "link": e.get("link",""), "source": src})
        except Exception:
            continue
    return out

# ---------- Main loop ----------
def main():
    tg_send("🟢 *News watcher online* — Hinglish Index+Stocks mode.")
    while True:
        for e in gather_entries():
            title = (e.get("title") or "").strip()
            if not title: continue
            link  = e.get("link","")
            src   = e.get("source","")
            key = title + link
            if seen(key): continue

            s = score_title(title, src)
            if s < MIN_SCORE: 
                continue

            focus, tone = classify_index(title)
            senti = sentiment(title)
            stocks_hit = stock_list_from_title(title)

            # ignore if nothing indexy and no stock hit (noise)
            if not focus and not stocks_hit:
                continue

            msg = fmt_msg(title, link, src, focus, tone, senti, stocks_hit)
            tg_send(msg)
        time.sleep(POLL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        tg_send("🔴 News watcher stopped.")
    except Exception as ex:
        tg_send(f"⚠️ News watcher error: {ex}")
