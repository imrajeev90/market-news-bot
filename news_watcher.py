#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, time, json, re, hashlib, datetime as dt
import requests, feedparser
from dotenv import load_dotenv

load_dotenv()
BOT  = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TZ   = os.getenv("TZ", "Asia/Kolkata")
POLL = int(os.getenv("POLL_SECS", "60"))  # seconds

def send_tg(text: str):
    if not (BOT and CHAT): return
    try:
        url = f"https://api.telegram.org/bot{BOT}/sendMessage"
        requests.post(url, data={"chat_id": CHAT, "text": text, "parse_mode":"Markdown",
                                 "disable_web_page_preview": True}, timeout=15)
    except Exception:
        pass

# Feeds (fast + reliable)
FEEDS = [
  "https://www.moneycontrol.com/rss/MCtopnews.xml",
  "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
  "https://www.livemint.com/rss/markets",
  "https://www.cnbctv18.com/api/v1/rss/markets.xml",
  "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
  "https://www.reuters.com/markets/asia/rss",
  "https://www.reuters.com/markets/us/rss",
  "https://www.reuters.com/markets/europe/rss",
]

# Rules: (regex, impact, index_focus, plan)
RULES = [
  (r"\b(RBI|MPC|repo rate|CRR|SLR|liquidity|monetary policy)\b", "Policy/Hawkish?", "BankNifty",
   "Hawkish tone ⇒ BN weak. Fade pops near VWAP; SL last swing high."),
  (r"\b(Fed|FOMC|Powell|dot plot|rate hike|hawkish)\b", "Global risk-off", "Nifty",
   "Wait 1st 5m close; sell-on-rise till VWAP reclaimed; size small."),
  (r"\b(crude|brent|opec|inventory)\b", "Crude spike", "Nifty",
   "Brent > +2% ⇒ index down-bias; short pops; OMC/paints soft."),
  (r"\b(USDINR|dollar index|DXY)\b", "FX move", "Nifty",
   "USDINR↑/DXY↑ ⇒ equities weak; IT relative strong."),
  (r"\b(duty|import duty|export tax|PLI|subsidy|ban|restriction)\b", "Policy shock", "Nifty",
   "Fade knee-jerk; re-enter on retest; keep SL tight."),
  (r"\b(SEBI|margin|F&O|lot size|ban list|ASM|GSM)\b", "Microstructure", "Nifty",
   "Framework tight ⇒ vol crush; reduce leverage."),
  (r"\b(HDFC|ICICI|SBI|KOTAK|AXIS)\b", "Large bank driver", "BankNifty",
   "Result/Guidance ⇒ trade parent; avoid lotto OTM; wait 5m close."),
  (r"\b(inflation|CPI|PPI|jobs|payrolls|unemployment)\b", "Macro print", "Nifty",
   "Hot print sell spike; cool print buy dips; use 5m VWAP."),
  (r"\b(Moody's|S&P|Fitch|rating)\b", "Rating action", "Nifty",
   "Downgrade ⇒ hedge via short futures/puts."),
  (r"\b(MSCI|FTSE|rebalanc|inclusion|exclusion)\b", "Flow event", "Nifty",
   "Follow-through after 10–15m only; avoid chasing first tick."),
]

DB = set()
def seen(key: str) -> bool:
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    if h in DB: return True
    DB.add(h); return False

def classify(title: str):
    for pat, impact, focus, plan in RULES:
        if re.search(pat, title, flags=re.I):
            return impact, focus, plan
    return None, None, None

def fmt_alert(title, link, impact, focus, plan):
    t = f"*BREAKING* [{focus}] — {impact}\n{title}\n"
    if link: t += f"{link}\n"
    t += f"\n*Scalp plan:* {plan}\n—"
    return t

def gather_entries():
    entries = []
    for url in FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:15]:
                entries.append({"title": e.get("title",""), "link": e.get("link","")})
        except Exception:
            continue
    return entries

def main_loop():
    send_tg("🟢 *News watcher online* (Nifty/BankNifty/Sensex)")
    while True:
        for e in gather_entries():
            title = (e.get("title") or "").strip()
            link  = e.get("link","")
            if not title: continue
            key = title + link
            if seen(key): continue
            impact, focus, plan = classify(title)
            if impact:
                send_tg(fmt_alert(title, link, impact, focus, plan))
        time.sleep(POLL)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        send_tg("🔴 News watcher stopped.")
    except Exception as ex:
        send_tg(f"⚠️ News watcher error: {ex}")
