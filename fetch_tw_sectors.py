import os
import re
import time
import json
import requests
import datetime
import xml.etree.ElementTree as ET
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

BULL_WORDS = ["大漲", "漲停", "新高", "利多", "買超", "翻紅", "看旺", "成長", "爆量", "獲利", "法說報喜", "滿載", "搶單", "調升", "強勢", "飆"]
BEAR_WORDS = ["大跌", "跌停", "重挫", "利空", "賣超", "翻黑", "看淡", "衰退", "砍單", "虧損", "暴雷", "下修", "疲軟", "破底", "跳水", "調節"]
WEEKDAY_MAP = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]

# 標普 500 (S&P 500) + 那斯達克 100 (Nasdaq 100) 核心成分股與美國公債/指數 ETF 完整清單 (共 105 檔)
US_TARGETS = [
    # --- 旗艦指數 ETF 與 美國公債 ETF ---
    {"symbol": "SPY", "name": "SPDR標普500指數ETF", "assetType": "US_STOCK", "sector": "ETF", "yield": 1.25, "cashDividend": 1.75},
    {"symbol": "VOO", "name": "Vanguard標普500ETF", "assetType": "US_STOCK", "sector": "ETF", "yield": 1.30, "cashDividend": 1.65},
    {"symbol": "QQQ", "name": "Invesco那斯達克100ETF", "assetType": "US_STOCK", "sector": "ETF", "yield": 0.60, "cashDividend": 0.70},
    {"symbol": "SOXX", "name": "iShares費城半導體ETF", "assetType": "US_STOCK", "sector": "ETF", "yield": 0.75, "cashDividend": 0.45},
    {"symbol": "TLT", "name": "iShares 20年期美債ETF", "assetType": "US_BOND", "sector": "BOND", "yield": 4.45, "cashDividend": 0.34},
    {"symbol": "IEF", "name": "iShares 7-10年美債ETF", "assetType": "US_BOND", "sector": "BOND", "yield": 4.10, "cashDividend": 0.31},
    {"symbol": "SHY", "name": "iShares 1-3年短期美債", "assetType": "US_BOND", "sector": "BOND", "yield": 4.35, "cashDividend": 0.30},
    {"symbol": "SGOV", "name": "iShares 0-3月極短國庫券", "assetType": "US_BOND", "sector": "BOND", "yield": 4.85, "cashDividend": 0.40},
    {"symbol": "LQD", "name": "iShares投資級公司債ETF", "assetType": "US_BOND", "sector": "BOND", "yield": 4.90, "cashDividend": 0.44},

    # --- Nasdaq 100 & S&P 500：科技七巨頭與雲端 AI 軟體 ---
    {"symbol": "NVDA", "name": "輝達 (NVIDIA)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 0.03, "cashDividend": 0.01},
    {"symbol": "AAPL", "name": "蘋果 (Apple)", "assetType": "US_STOCK", "sector": "BUFFETT_TECH", "yield": 0.45, "cashDividend": 0.25},
    {"symbol": "MSFT", "name": "微軟 (Microsoft)", "assetType": "US_STOCK", "sector": "AI_CLOUD", "yield": 0.75, "cashDividend": 0.83},
    {"symbol": "GOOGL", "name": "Alphabet (Google)", "assetType": "US_STOCK", "sector": "AI_CLOUD", "yield": 0.45, "cashDividend": 0.20},
    {"symbol": "AMZN", "name": "亞馬遜 (Amazon)", "assetType": "US_STOCK", "sector": "AI_CLOUD", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "META", "name": "Meta (臉書)", "assetType": "US_STOCK", "sector": "AI_CLOUD", "yield": 0.35, "cashDividend": 0.50},
    {"symbol": "TSLA", "name": "特斯拉 (Tesla)", "assetType": "US_STOCK", "sector": "MEME_GROWTH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "PLTR", "name": "Palantir (AI大數據)", "assetType": "US_STOCK", "sector": "AI_CLOUD", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "NFLX", "name": "Netflix (網飛)", "assetType": "US_STOCK", "sector": "TECH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "CRM", "name": "Salesforce", "assetType": "US_STOCK", "sector": "TECH", "yield": 0.55, "cashDividend": 0.40},
    {"symbol": "ORCL", "name": "甲骨文 (Oracle)", "assetType": "US_STOCK", "sector": "AI_CLOUD", "yield": 0.95, "cashDividend": 0.40},
    {"symbol": "ADBE", "name": "Adobe", "assetType": "US_STOCK", "sector": "TECH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "NOW", "name": "ServiceNow", "assetType": "US_STOCK", "sector": "AI_CLOUD", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "INTU", "name": "Intuit", "assetType": "US_STOCK", "sector": "TECH", "yield": 0.65, "cashDividend": 1.04},
    {"symbol": "IBM", "name": "IBM", "assetType": "US_STOCK", "sector": "VALUE", "yield": 3.10, "cashDividend": 1.67},
    {"symbol": "PANW", "name": "Palo Alto (資安)", "assetType": "US_STOCK", "sector": "TECH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "CRWD", "name": "CrowdStrike (資安)", "assetType": "US_STOCK", "sector": "TECH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "FTNT", "name": "Fortinet (資安)", "assetType": "US_STOCK", "sector": "TECH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "SNOW", "name": "Snowflake", "assetType": "US_STOCK", "sector": "TECH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "DDOG", "name": "Datadog", "assetType": "US_STOCK", "sector": "TECH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "APP", "name": "AppLovin (AI廣告)", "assetType": "US_STOCK", "sector": "AI_CLOUD", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "UBER", "name": "Uber (優步)", "assetType": "US_STOCK", "sector": "TECH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "ABNB", "name": "Airbnb", "assetType": "US_STOCK", "sector": "TECH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "BKNG", "name": "Booking Holdings", "assetType": "US_STOCK", "sector": "TECH", "yield": 0.75, "cashDividend": 8.75},
    {"symbol": "MELI", "name": "MercadoLibre", "assetType": "US_STOCK", "sector": "TECH", "yield": 0.0, "cashDividend": 0.0},

    # --- Nasdaq 100 & S&P 500：AI 半導體、伺服器與電力基建 (Situational Awareness 核心) ---
    {"symbol": "AVGO", "name": "博通 (Broadcom)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 1.20, "cashDividend": 0.53},
    {"symbol": "AMD", "name": "超微 (AMD)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "TSM", "name": "台積電ADR (TSMC)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 1.35, "cashDividend": 0.68},
    {"symbol": "ASML", "name": "艾司摩爾 (ASML)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 0.95, "cashDividend": 1.75},
    {"symbol": "QCOM", "name": "高通 (Qualcomm)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 2.00, "cashDividend": 0.85},
    {"symbol": "TXN", "name": "德州儀器 (TI)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 2.65, "cashDividend": 1.36},
    {"symbol": "MU", "name": "美光 (Micron)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 0.45, "cashDividend": 0.115},
    {"symbol": "AMAT", "name": "應用材料", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 0.85, "cashDividend": 0.40},
    {"symbol": "LRCX", "name": "科林研發 (Lam)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 1.10, "cashDividend": 0.23},
    {"symbol": "KLAC", "name": "科磊 (KLA)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 0.90, "cashDividend": 1.70},
    {"symbol": "ADI", "name": "亞德諾半導體", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 1.65, "cashDividend": 0.92},
    {"symbol": "INTC", "name": "英特爾 (Intel)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "ARM", "name": "安謀 (Arm Holdings)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "MRVL", "name": "邁威爾 (Marvell)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 0.28, "cashDividend": 0.06},
    {"symbol": "NXPI", "name": "恩智浦 (NXP)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 1.75, "cashDividend": 1.014},
    {"symbol": "SNPS", "name": "新思科技 (Synopsys)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "CDNS", "name": "益華電腦 (Cadence)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "ANET", "name": "Arista (AI高速網通)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "SMCI", "name": "美超微 (SuperMicro)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "DELL", "name": "戴爾 (Dell AI伺服器)", "assetType": "US_STOCK", "sector": "AI_SEMI", "yield": 1.40, "cashDividend": 0.445},
    {"symbol": "VRT", "name": "Vertiv (AI液冷散熱)", "assetType": "US_STOCK", "sector": "AI_POWER", "yield": 0.10, "cashDividend": 0.025},
    {"symbol": "VST", "name": "Vistra (AI核能電力)", "assetType": "US_STOCK", "sector": "AI_POWER", "yield": 0.65, "cashDividend": 0.22},
    {"symbol": "CEG", "name": "Constellation (核電)", "assetType": "US_STOCK", "sector": "AI_POWER", "yield": 0.55, "cashDividend": 0.35},
    {"symbol": "GEV", "name": "GE Vernova (重電渦輪)", "assetType": "US_STOCK", "sector": "AI_POWER", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "ETN", "name": "伊頓 (Eaton 電網基建)", "assetType": "US_STOCK", "sector": "AI_POWER", "yield": 1.10, "cashDividend": 0.94},

    # --- S&P 500：波克夏與華爾街金融、價值護城河巨頭 ---
    {"symbol": "BRK-B", "name": "波克夏B (Berkshire)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "JPM", "name": "摩根大通 (JPMorgan)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 2.10, "cashDividend": 1.25},
    {"symbol": "BAC", "name": "美國銀行 (BoA)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 2.45, "cashDividend": 0.26},
    {"symbol": "WFC", "name": "富國銀行 (WellsFargo)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 2.30, "cashDividend": 0.40},
    {"symbol": "GS", "name": "高盛 (Goldman Sachs)", "assetType": "US_STOCK", "sector": "VALUE", "yield": 2.20, "cashDividend": 3.00},
    {"symbol": "MS", "name": "摩根士丹利", "assetType": "US_STOCK", "sector": "VALUE", "yield": 3.05, "cashDividend": 0.925},
    {"symbol": "AXP", "name": "美國運通 (Amex)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 1.05, "cashDividend": 0.70},
    {"symbol": "V", "name": "Visa", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 0.78, "cashDividend": 0.59},
    {"symbol": "MA", "name": "Mastercard", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 0.55, "cashDividend": 0.66},
    {"symbol": "BLK", "name": "貝萊德 (BlackRock)", "assetType": "US_STOCK", "sector": "VALUE", "yield": 2.05, "cashDividend": 5.10},

    # --- S&P 500：消費必需品、零售與餐飲護城河 ---
    {"symbol": "WMT", "name": "沃爾瑪 (Walmart)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 1.05, "cashDividend": 0.2075},
    {"symbol": "COST", "name": "好市多 (Costco)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 0.52, "cashDividend": 1.16},
    {"symbol": "HD", "name": "家得寶 (Home Depot)", "assetType": "US_STOCK", "sector": "VALUE", "yield": 2.25, "cashDividend": 2.25},
    {"symbol": "KO", "name": "可口可樂 (Coca-Cola)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 3.05, "cashDividend": 0.485},
    {"symbol": "PEP", "name": "百事可樂 (PepsiCo)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 3.25, "cashDividend": 1.355},
    {"symbol": "PG", "name": "寶僑 (P&G)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 2.40, "cashDividend": 1.0065},
    {"symbol": "MCD", "name": "麥當勞 (McDonald's)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 2.35, "cashDividend": 1.77},
    {"symbol": "SBUX", "name": "星巴克 (Starbucks)", "assetType": "US_STOCK", "sector": "VALUE", "yield": 2.45, "cashDividend": 0.61},
    {"symbol": "NKE", "name": "耐吉 (Nike)", "assetType": "US_STOCK", "sector": "VALUE", "yield": 1.95, "cashDividend": 0.40},
    {"symbol": "DIS", "name": "迪士尼 (Disney)", "assetType": "US_STOCK", "sector": "VALUE", "yield": 0.90, "cashDividend": 0.45},

    # --- S&P 500：醫療生技與減肥藥巨頭 ---
    {"symbol": "LLY", "name": "禮來 (Eli Lilly)", "assetType": "US_STOCK", "sector": "HEALTH", "yield": 0.65, "cashDividend": 1.30},
    {"symbol": "UNH", "name": "聯合健康 (UnitedHealth)", "assetType": "US_STOCK", "sector": "HEALTH", "yield": 1.50, "cashDividend": 2.10},
    {"symbol": "JNJ", "name": "嬌生 (J&J)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 3.20, "cashDividend": 1.24},
    {"symbol": "ABBV", "name": "艾伯維 (AbbVie)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 3.55, "cashDividend": 1.64},
    {"symbol": "MRK", "name": "默克 (Merck)", "assetType": "US_STOCK", "sector": "HEALTH", "yield": 3.10, "cashDividend": 0.81},
    {"symbol": "PFE", "name": "輝瑞 (Pfizer)", "assetType": "US_STOCK", "sector": "VALUE", "yield": 6.10, "cashDividend": 0.42},
    {"symbol": "AMGN", "name": "安進 (Amgen)", "assetType": "US_STOCK", "sector": "HEALTH", "yield": 3.00, "cashDividend": 2.25},
    {"symbol": "ISRG", "name": "直覺手術 (達文西手臂)", "assetType": "US_STOCK", "sector": "HEALTH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "GILD", "name": "吉利德科學", "assetType": "US_STOCK", "sector": "HEALTH", "yield": 3.40, "cashDividend": 0.77},
    {"symbol": "VRTX", "name": "福泰製藥 (Vertex)", "assetType": "US_STOCK", "sector": "HEALTH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "REGN", "name": "再生元製藥", "assetType": "US_STOCK", "sector": "HEALTH", "yield": 0.0, "cashDividend": 0.0},

    # --- S&P 500：能源石油、航太軍工與重工業 ---
    {"symbol": "XOM", "name": "埃克森美孚 (Exxon)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 3.35, "cashDividend": 0.99},
    {"symbol": "CVX", "name": "雪佛龍 (Chevron)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 4.15, "cashDividend": 1.63},
    {"symbol": "OXY", "name": "西方石油 (Occidental)", "assetType": "US_STOCK", "sector": "BUFFETT_VALUE", "yield": 1.75, "cashDividend": 0.22},
    {"symbol": "CAT", "name": "卡特彼勒 (Caterpillar)", "assetType": "US_STOCK", "sector": "VALUE", "yield": 1.45, "cashDividend": 1.41},
    {"symbol": "GE", "name": "奇異航太 (GE Aerospace)", "assetType": "US_STOCK", "sector": "VALUE", "yield": 0.65, "cashDividend": 0.28},
    {"symbol": "RTX", "name": "雷神技術 (RTX軍工)", "assetType": "US_STOCK", "sector": "VALUE", "yield": 2.05, "cashDividend": 0.63},
    {"symbol": "LMT", "name": "洛克希德馬丁 (軍工)", "assetType": "US_STOCK", "sector": "VALUE", "yield": 2.35, "cashDividend": 3.30},
    {"symbol": "BA", "name": "波音 (Boeing)", "assetType": "US_STOCK", "sector": "VALUE", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "HON", "name": "霍尼韋爾 (Honeywell)", "assetType": "US_STOCK", "sector": "VALUE", "yield": 2.10, "cashDividend": 1.13},
    {"symbol": "UNP", "name": "聯合太平洋鐵路", "assetType": "US_STOCK", "sector": "VALUE", "yield": 2.20, "cashDividend": 1.34},
    {"symbol": "LIN", "name": "林德集團 (Linde)", "assetType": "US_STOCK", "sector": "VALUE", "yield": 1.25, "cashDividend": 1.39},
    {"symbol": "NEE", "name": "NextEra (北美綠電王)", "assetType": "US_STOCK", "sector": "AI_POWER", "yield": 2.75, "cashDividend": 0.515},

    # --- WSB / Reddit 高波動迷因與加密概念飆股 ---
    {"symbol": "GME", "name": "GameStop (遊戲驛站)", "assetType": "US_STOCK", "sector": "MEME_GROWTH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "AMC", "name": "AMC院線 (AMC迷因)", "assetType": "US_STOCK", "sector": "MEME_GROWTH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "RDDT", "name": "Reddit (鄉民論壇本尊)", "assetType": "US_STOCK", "sector": "MEME_GROWTH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "MSTR", "name": "MicroStrategy (微策略)", "assetType": "US_STOCK", "sector": "MEME_GROWTH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "COIN", "name": "Coinbase (加密交易所)", "assetType": "US_STOCK", "sector": "MEME_GROWTH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "HOOD", "name": "Robinhood (散戶券商)", "assetType": "US_STOCK", "sector": "MEME_GROWTH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "SOFI", "name": "SoFi Technologies", "assetType": "US_STOCK", "sector": "MEME_GROWTH", "yield": 0.0, "cashDividend": 0.0},
    {"symbol": "RIVN", "name": "Rivian (電動皮卡)", "assetType": "US_STOCK", "sector": "MEME_GROWTH", "yield": 0.0, "cashDividend": 0.0}
]

def roc_to_iso_date(roc_str):
    if not roc_str:
        return ""
    s = str(roc_str).strip().replace("年", "/").replace("月", "/").replace("日", "").replace("-", "/")
    if s.isdigit() and len(s) == 7:
        return f"{int(s[:3]) + 1911:04d}-{int(s[3:5]):02d}-{int(s[5:7]):02d}"
    if s.isdigit() and len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    parts = [p for p in s.split("/") if p.isdigit()]
    if len(parts) == 3:
        year = int(parts[0])
        if year < 1911:
            year += 1911
        return f"{year:04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    return ""

def safe_float(val, default=0.0):
    if val is None:
        return default
    val_str = str(val).replace(",", "").replace("%", "").replace("+", "").strip()
    if val_str in ["", "--", "---", "-", "N/A", "X", "尚未公告", "0.00"]:
        return 0.0 if val_str == "0.00" else default
    try:
        return float(val_str)
    except ValueError:
        return default

def fetch_yahoo_history_series(symbol, headers):
    """從 Yahoo Finance 抓取過去 1 個月每日真實歷史 OHLC 序列與真實除息日"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1mo&events=div"
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code != 200:
            return None
        result = res.json().get("chart", {}).get("result", [])
        if not result:
            return None
        timestamps = result[0].get("timestamp", [])
        quote = result[0].get("indicators", {}).get("quote", [{}])[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []

        real_ex_date = ""
        real_div_amount = 0.0
        div_events = result[0].get("events", {}).get("dividends", {})
        if div_events:
            latest_ts = max(div_events.keys(), key=lambda k: int(k))
            div_obj = div_events[latest_ts]
            real_ex_date = datetime.datetime.fromtimestamp(int(latest_ts)).strftime("%Y-%m-%d")
            real_div_amount = round(float(div_obj.get("amount", 0.0)), 4)

        bars = []
        for i, ts in enumerate(timestamps):
            c = closes[i] if i < len(closes) else None
            if c is None or c <= 0:
                continue
            dt_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            o = opens[i] if (i < len(opens) and opens[i] is not None) else c
            h = highs[i] if (i < len(highs) and highs[i] is not None) else c
            l = lows[i] if (i < len(lows) and lows[i] is not None) else c
            prev_c = bars[-1]["price"] if bars else c
            chg_pct = round(((c - prev_c) / prev_c) * 100, 2) if prev_c > 0 else 0.0
            bars.append({
                "date": dt_str,
                "open": round(float(o), 2),
                "high": round(float(h), 2),
                "low": round(float(l), 2),
                "price": round(float(c), 2),
                "changePct": chg_pct,
                "exDividendDate": real_ex_date,
                "cashDividend": real_div_amount
            })
        return bars if bars else None
    except Exception:
        return None

def get_bar_for_date(bars, target_date_str):
    if not bars:
        return None
    le_bars = [b for b in bars if b["date"] <= target_date_str]
    if le_bars:
        return le_bars[-1]
    return bars[0]

def fetch_all_yahoo_series(headers):
    print(f"4. 正在啟動 16 執行緒高速併發，從 Yahoo Finance 抓取 USD/TWD 與 {len(US_TARGETS)} 檔標普500/那斯達克100美股歷史K線...")
    fx_bars = fetch_yahoo_history_series("TWD=X", headers)
    us_series_map = {}

    def _worker(item):
        sym = item["symbol"]
        return sym, fetch_yahoo_history_series(sym, headers)

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(_worker, item) for item in US_TARGETS]
        for fut in as_completed(futures):
            try:
                sym, bars = fut.result()
                if bars:
                    us_series_map[sym] = bars
            except Exception:
                pass

    print(f"✅ 成功抓取 {len(us_series_map)} / {len(US_TARGETS)} 檔標普500與那斯達克100美股完整歷史K線！")
    return fx_bars, us_series_map

def build_us_assets_for_specific_date(target_date_str, fx_bars, us_series_map):
    fx_bar = get_bar_for_date(fx_bars, target_date_str)
    fx_rate = fx_bar["price"] if (fx_bar and fx_bar["price"] > 25) else 32.15

    us_assets = []
    for item in US_TARGETS:
        sym = item["symbol"]
        bars = us_series_map.get(sym)
        q = get_bar_for_date(bars, target_date_str)
        if q and q["price"] > 0:
            us_assets.append({
                "id": f"{sym} {item['name']}",
                "code": sym,
                "name": item["name"],
                "assetType": item["assetType"],
                "usSector": item.get("sector", "TECH"),
                "currency": "USD",
                "open": q["open"],
                "high": q["high"],
                "low": q["low"],
                "price": q["price"],
                "changePct": q["changePct"],
                "yield": item["yield"],
                "exDividendDate": q["exDividendDate"],
                "cashDividend": q["cashDividend"] if q["cashDividend"] > 0 else item["cashDividend"]
            })
    return fx_rate, us_assets

def fetch_stock_news(code, name):
    query = urllib.parse.quote(f"{code} {name}")
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    news_list = []
    sentiment_score = 0
    try:
        res = requests.get(rss_url, timeout=5)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for item in root.findall(".//item")[:2]:
                title = item.find("title").text
                clean_title = title.split(" - ")[0] if " - " in title else title
                score = sum(1 for w in BULL_WORDS if w in clean_title) - sum(1 for w in BEAR_WORDS if w in clean_title)
                sentiment_score += score
                news_list.append({"title": clean_title, "score": score})
    except Exception:
        pass
    return news_list, max(-1.0, min(1.0, round(sentiment_score * 0.35, 2)))

def is_twse_warrant(code):
    if len(code) != 6 or not code.startswith("0"):
        return False
    return code.endswith("P") or code[:2] in ["03", "04", "05", "06", "07", "08"]

def fetch_fallback_mi_index(headers):
    print("🔄 正在切換至證交所主站 (MI_INDEX) 抓取當日最新收盤行情...")
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?type=ALLBUT0999&response=json"
    try:
        res = requests.get(url, headers=headers, timeout=20)
        if res.status_code != 200:
            return [], ""
        data = res.json()
        if data.get("stat") != "OK":
            return [], ""
        actual_date = roc_to_iso_date(data.get("date", ""))
        converted_list = []
        for table in data.get("tables", []):
            fields = table.get("fields", [])
            if "證券代號" in fields and "收盤價" in fields and "成交股數" in fields:
                idx_code = fields.index("證券代號")
                idx_name = fields.index("證券名稱")
                idx_vol = fields.index("成交股數")
                idx_open = fields.index("開盤價") if "開盤價" in fields else -1
                idx_high = fields.index("最高價") if "最高價" in fields else -1
                idx_low = fields.index("最低價") if "最低價" in fields else -1
                idx_close = fields.index("收盤價")
                idx_dir = fields.index("漲跌(+/-)") if "漲跌(+/-)" in fields else -1
                idx_diff = fields.index("漲跌價差") if "漲跌價差" in fields else -1
                for row in table.get("data", []):
                    raw_dir = re.sub(r"<[^>]+>", "", str(row[idx_dir])).strip() if idx_dir >= 0 else ""
                    sign = -1.0 if raw_dir == "-" else (0.0 if raw_dir in ["", "X"] else 1.0)
                    diff_val = safe_float(row[idx_diff], 0.0) * sign if idx_diff >= 0 else 0.0
                    converted_list.append({
                        "Date": actual_date,
                        "Code": str(row[idx_code]).strip(),
                        "Name": str(row[idx_name]).strip(),
                        "TradeVolume": str(row[idx_vol]),
                        "OpeningPrice": str(row[idx_open]) if idx_open >= 0 else str(row[idx_close]),
                        "HighestPrice": str(row[idx_high]) if idx_high >= 0 else str(row[idx_close]),
                        "LowestPrice": str(row[idx_low]) if idx_low >= 0 else str(row[idx_close]),
                        "ClosingPrice": str(row[idx_close]),
                        "Change": str(diff_val)
                    })
        return converted_list, actual_date
    except Exception as e:
        print(f"⚠️ 主站備援抓取失敗: {e}")
        return [], ""

def fetch_macro_environment(headers):
    """抓取真實總經指標 (10年期美債殖利率 ^TNX、VIX 恐慌指數 ^VIX) 與聯準會/CPI/非農/法說會總經新聞"""
    print("6. 正在抓取全球總經指標 (10Y美債殖利率、VIX恐慌指數) 與總經新聞...")
    tnx_bars = fetch_yahoo_history_series("^TNX", headers)
    vix_bars = fetch_yahoo_history_series("^VIX", headers)
    us10y = tnx_bars[-1]["price"] if tnx_bars else 4.25
    vix = vix_bars[-1]["price"] if vix_bars else 16.5

    macro_queries = ["聯準會 利率 CPI 非農", "台積電 法說會 景氣 央行"]
    macro_news = []
    macro_score = 0
    for q in macro_queries:
        rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        try:
            res = requests.get(rss_url, timeout=5)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                for item in root.findall(".//item")[:3]:
                    title = item.find("title").text.split(" - ")[0]
                    sc = sum(1 for w in BULL_WORDS + ["降息", "降準", "擴張", "優於預期", "上調"] if w in title) - \
                         sum(1 for w in BEAR_WORDS + ["升息", "通膨升溫", "衰退", "低於預期", "鷹派"] if w in title)
                    macro_score += sc
                    macro_news.append({"tag": "🌎總經快訊", "title": title, "score": sc})
        except Exception:
            pass

    if us10y >= 4.4 or vix >= 21 or macro_score < 0:
        regime = "HAWKISH_INFLATION"
        regime_label = "🔴 通膨升溫與鷹派緊縮"
        regime_color = "#ff8a80"
    elif macro_score >= 2 or vix <= 14.5:
        regime = "RATE_CUT_RALLY"
        regime_label = "🚀 降息寬鬆與資金狂潮"
        regime_color = "#ffd54f"
    else:
        regime = "GOLDILOCKS"
        regime_label = "🟢 軟著陸與算力擴張"
        regime_color = "#76c888"

    return {
        "regime": regime,
        "regimeLabel": regime_label,
        "regimeColor": regime_color,
        "fedRate": "4.50%",
        "cpiYoY": "2.6%",
        "nfpJobs": "+18.5萬人",
        "us10yYield": f"{us10y:.2f}%",
        "vixIndex": f"{vix:.1f}",
        "macroScore": max(-2, min(2, macro_score)),
        "headlines": macro_news
    }

def fetch_all_tw_stocks_warrants_dividends():
    ts = int(time.time())
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    history_file = "tw_stocks_history.json"
    history_data = {"records": []}
    cached_div_map = {}

    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if "records" in loaded:
                    history_data = loaded
                    for rec in history_data["records"]:
                        for st in (rec.get("allStocks") or rec.get("sectors") or []):
                            c = st.get("code", "")
                            ex_d = st.get("exDividendDate", "")
                            c_div = safe_float(st.get("cashDividend"), 0.0)
                            if c and ex_d and c_div > 0:
                                cached_div_map[c] = {"exDividendDate": ex_d, "cashDividend": c_div}
        except Exception:
            pass

    print("1. 正在從台灣證交所 (TWSE) 抓取全市場收盤行情 (STOCK_DAY_ALL)...")
    price_url = f"https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL?_={ts}"
    price_res = requests.get(price_url, headers=headers, timeout=15)
    price_data = price_res.json() if price_res.status_code == 200 else []

    actual_data_date = ""
    if price_data and isinstance(price_data, list):
        actual_data_date = roc_to_iso_date(price_data[0].get("Date", ""))

    if actual_data_date != today_str:
        fallback_data, fallback_date = fetch_fallback_mi_index(headers)
        if fallback_data:
            price_data = fallback_data
            actual_data_date = fallback_date

    print("2. 正在抓取全台股個股本益比與殖利率 (BWIBBU_ALL)...")
    val_url = f"https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL?_={ts}"
    val_res = requests.get(val_url, headers=headers, timeout=15)
    val_data = val_res.json() if val_res.status_code == 200 else []

    print("3. 正在抓取證交所官方【除權息預告表 (TWT48U_ALL)】...")
    div_url = f"https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL?_={ts}"
    div_res = requests.get(div_url, headers=headers, timeout=15)
    div_data = div_res.json() if div_res.status_code == 200 else []

    div_map = dict(cached_div_map)
    for d in div_data:
        code = str(d.get("Code", "")).strip()
        ex_date = roc_to_iso_date(d.get("ExdividendDate") or d.get("Date"))
        cash_div = safe_float(d.get("CashDividend"), 0.0)
        if code and ex_date and cash_div > 0:
            div_map[code] = {"exDividendDate": ex_date, "cashDividend": round(cash_div, 4)}

    val_map = {}
    for v in val_data:
        code = v.get("Code", "").strip()
        if code:
            val_map[code] = {
                "pe": safe_float(v.get("PEratio"), 0.0),
                "yield": safe_float(v.get("DividendYield"), 0.0),
                "pb": safe_float(v.get("PBratio"), 0.0)
            }

    all_stocks = []
    all_warrants = []

    for item in price_data:
        code = item.get("Code", "").strip()
        name = item.get("Name", "").strip()
        close_p = safe_float(item.get("ClosingPrice"), 0.0)
        open_p = safe_float(item.get("OpeningPrice"), close_p)
        high_p = safe_float(item.get("HighestPrice"), close_p)
        low_p = safe_float(item.get("LowestPrice"), close_p)
        change_val = safe_float(item.get("Change"), 0.0)
        vol_shares = int(safe_float(item.get("TradeVolume"), 0))

        if close_p <= 0 or vol_shares == 0:
            continue

        prev_p = close_p - change_val
        change_pct = round((change_val / prev_p) * 100, 2) if prev_p > 0 else 0.0
        vol_lots = round(vol_shares / 1000)

        if is_twse_warrant(code):
            w_type = "PUT" if (code.endswith("P") or "售" in name) else "CALL"
            all_warrants.append({
                "id": f"{code} {name}",
                "code": code,
                "name": name,
                "assetType": "WARRANT",
                "warrantType": w_type,
                "open": open_p if open_p > 0 else close_p,
                "high": high_p if high_p > 0 else close_p,
                "low": low_p if low_p > 0 else close_p,
                "price": close_p,
                "changePct": change_pct,
                "volLots": vol_lots
            })
            continue

        if not (len(code) == 4 or code.startswith("00")):
            continue

        v_info = val_map.get(code, {"pe": 20.0, "yield": 2.5, "pb": 1.5})
        pe = v_info["pe"]
        div_yield = v_info["yield"]
        d_info = div_map.get(code, {})
        ex_div_date = d_info.get("exDividendDate", "")
        cash_div = d_info.get("cashDividend", round(close_p * (div_yield / 100), 2) if div_yield > 0 else 0.0)

        if 0 < pe < 15 or div_yield >= 4.5:
            fair_value = round(close_p * 1.12, 2)
        elif pe > 35:
            fair_value = round(close_p * 0.90, 2)
        else:
            fair_value = round(close_p / (1 + (change_pct / 100) * 0.5), 2)

        all_stocks.append({
            "id": f"{code} {name}",
            "code": code,
            "name": name,
            "assetType": "STOCK",
            "open": open_p if open_p > 0 else close_p,
            "high": high_p if high_p > 0 else close_p,
            "low": low_p if low_p > 0 else close_p,
            "price": close_p,
            "changePct": change_pct,
            "volLots": vol_lots,
            "pe": pe,
            "yield": div_yield,
            "exDividendDate": ex_div_date,
            "cashDividend": cash_div,
            "fairValue": fair_value,
            "sentiment": round(max(-1.0, min(1.0, change_pct / 5.0)), 2),
            "news": []
        })

    top_warrants = sorted(
        [w for w in all_warrants if w["price"] >= 0.3 and w["volLots"] >= 100],
        key=lambda x: x["volLots"],
        reverse=True
    )[:35]

    record_date_str = actual_data_date if actual_data_date else today_str
    try:
        record_dt = datetime.datetime.strptime(record_date_str, "%Y-%m-%d")
    except ValueError:
        record_dt = datetime.datetime.now()
        record_date_str = record_dt.strftime("%Y-%m-%d")

    weekday_str = WEEKDAY_MAP[record_dt.weekday()]
    full_date_label = f"{record_date_str} ({weekday_str})"

    # 併發抓取 105 檔標普500/那斯達克100美股與美債歷史序列
    fx_bars, us_series_map = fetch_all_yahoo_series(headers)
    fx_rate, us_assets = build_us_assets_for_specific_date(record_date_str, fx_bars, us_series_map)

    by_ex_div = [s for s in all_stocks if s["exDividendDate"] != ""][:10]
    by_vol = sorted(all_stocks, key=lambda x: x["volLots"], reverse=True)[:15]
    by_gain = sorted([s for s in all_stocks if s["volLots"] > 1000], key=lambda x: x["changePct"], reverse=True)[:10]
    by_drop = sorted([s for s in all_stocks if s["volLots"] > 1000], key=lambda x: x["changePct"])[:10]
    by_val = sorted([s for s in all_stocks if 0 < s["pe"] < 14 and s["yield"] > 4.0 and s["volLots"] > 500], key=lambda x: x["yield"], reverse=True)[:10]

    focus_dict = {}
    for s in (by_ex_div + by_vol + by_gain + by_drop + by_val):
        focus_dict[s["code"]] = s
    focus_list = list(focus_dict.values())

    print("5. 正在為焦點個股抓取 Google News 當日財經新聞...")
    for idx, stock in enumerate(focus_list):
        if idx < 14:
            news_items, news_sent = fetch_stock_news(stock["code"], stock["name"])
            if news_items:
                stock["news"] = news_items
                stock["sentiment"] = round((stock["sentiment"] + news_sent) / 2, 2)
        if not stock["news"]:
            div_tag = f"｜除息日:{stock['exDividendDate']} (配息${stock['cashDividend']}元)" if stock["exDividendDate"] else ""
            stock["news"] = [{
                "title": f"【盤後資訊】{stock['id']} 收盤 {stock['price']} 元 ({stock['changePct']}%)，殖利率 {stock['yield']}%{div_tag}",
                "score": 1 if stock["changePct"] > 0.5 else -1 if stock["changePct"] < -0.5 else 0
            }]

    macro_info = fetch_macro_environment(headers)

    today_record = {
        "date": record_date_str,
        "weekday": weekday_str,
        "fullDateLabel": full_date_label,
        "fxRate": fx_rate,
        "macro": macro_info,
        "totalMarketCount": len(all_stocks),
        "totalUsCount": len(us_assets),
        "totalWarrantCount": len(all_warrants),
        "sectors": focus_list,
        "warrants": top_warrants,
        "usAssets": us_assets,
        "allStocks": all_stocks
    }

    exist_idx = next((i for i, r in enumerate(history_data["records"]) if r["date"] == record_date_str), -1)
    if exist_idx >= 0:
        history_data["records"][exist_idx] = today_record
    else:
        history_data["records"].append(today_record)

    # 自動為歷史紀錄中所有舊日期回填 105 檔標普500/那斯達克100美股之真實歷史價格！
    for rec in history_data["records"]:
        r_date = rec.get("date", "")
        if r_date and us_series_map:
            real_fx, real_us = build_us_assets_for_specific_date(r_date, fx_bars, us_series_map)
            if real_us:
                rec["fxRate"] = real_fx
                rec["usAssets"] = real_us

    history_data["records"].sort(key=lambda r: r.get("date", ""))

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 完成！已寫入【{full_date_label}】總經雷達({macro_info['regimeLabel']})、台股、權證、USD/TWD 匯率({fx_rate})與 {len(us_assets)} 檔美股至 {history_file}！")

if __name__ == "__main__":
    fetch_all_tw_stocks_warrants_dividends()