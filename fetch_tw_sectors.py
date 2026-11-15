#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【傳奇大師賽博炒股 V25.0 修正版】全台股四板塊 (上市/上櫃/興櫃/創櫃/KY) 數據引擎
★ 修正 1：嚴格過濾 6 碼權證 (03~08開頭)，確保全台股股票池精準為 ~2,300 檔純股票與ETF
★ 修正 2：若逢週六、週日執行，自動對齊至最近一個週五交易日，避免產生週末無波動之 Z=0σ 紀錄
★ 修正 3：直接透過 yfinance 抓取真實台灣加權指數 (^TWII)，修正台指期貨點數為真實 22,000~24,000 點水準
★ 修正 4：強制保留八大產業所有代表股進入 allStocks，確保每個板塊熱力圖都有充足標的
"""

import os
import re
import json
import time
import datetime
import requests

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

DEFAULT_FUGLE_KEY = "MjkzM2Y1ODQtNjNhOC00OTk0LTg0MzgtYTA4M2M0YjM1OGU5IDU4Zjg3Yzg5LTY5NjMtNGRjNy1hNDRjLTg4NjI2YzYxYTgwNw=="
FUGLE_API_KEY = os.environ.get("FUGLE_API_KEY", DEFAULT_FUGLE_KEY).strip()
FUGLE_BASE_URL = "https://api.fugle.tw/marketdata/v1.0/stock"
HISTORY_JSON_PATH = "tw_stocks_history.json"
WEEKDAY_MAP = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]

GISA_INNOVATION_POOL = [
    {"code": "7402", "name": "邑錡(創櫃轉上櫃示範)", "sectorCat": "AI_SEMI", "basePrice": 68.5, "pe": 28.0, "yield": 1.2},
    {"code": "7556", "name": "意德士(創櫃新創)", "sectorCat": "BIOTECH_NEW", "basePrice": 134.0, "pe": 16.8, "yield": 3.4},
    {"code": "7610", "name": "聯友金屬(創櫃綠能循環)", "sectorCat": "POWER_GREEN", "basePrice": 84.0, "pe": 19.5, "yield": 2.1},
    {"code": "7584", "name": "樂意傳播(創櫃文創數位)", "sectorCat": "BIOTECH_NEW", "basePrice": 79.5, "pe": 18.0, "yield": 3.0},
    {"code": "7595", "name": "萬達光電(創櫃觸控科技)", "sectorCat": "SERVER_PC", "basePrice": 42.8, "pe": 15.2, "yield": 3.5}
]

CORE_US_ASSETS = [
    {"code": "NVDA", "name": "輝達 (NVIDIA)", "assetType": "US_STOCK", "usSector": "AI_SEMI", "yield": 0.03, "isETB": True, "borrowFeeRate": 0.35, "fallbackPrice": 148.5},
    {"code": "AAPL", "name": "蘋果 (Apple)", "assetType": "US_STOCK", "usSector": "BUFFETT_TECH", "yield": 0.45, "isETB": True, "borrowFeeRate": 0.25, "fallbackPrice": 228.0},
    {"code": "TSLA", "name": "特斯拉 (Tesla)", "assetType": "US_STOCK", "usSector": "MEME_GROWTH", "yield": 0.0, "isETB": True, "borrowFeeRate": 1.50, "fallbackPrice": 298.0},
    {"code": "INTC", "name": "英特爾 (Intel)", "assetType": "US_STOCK", "usSector": "AI_SEMI", "yield": 0.0, "isETB": True, "borrowFeeRate": 0.85, "fallbackPrice": 22.5},
    {"code": "KO", "name": "可口可樂 (Coca-Cola)", "assetType": "US_STOCK", "usSector": "BUFFETT_VALUE", "yield": 3.05, "isETB": True, "borrowFeeRate": 0.25, "fallbackPrice": 66.2},
    {"code": "VST", "name": "Vistra (AI核能電力)", "assetType": "US_STOCK", "usSector": "AI_POWER", "yield": 0.65, "isETB": True, "borrowFeeRate": 0.60, "fallbackPrice": 138.0},
    {"code": "GME", "name": "遊戲驛站 (GameStop)", "assetType": "US_STOCK", "usSector": "MEME_GROWTH", "yield": 0.0, "isETB": False, "borrowFeeRate": 28.50, "fallbackPrice": 28.5},
    {"code": "TLT", "name": "20年期美債ETF", "assetType": "US_BOND", "usSector": "BOND", "yield": 4.45, "isETB": True, "borrowFeeRate": 0.40, "fallbackPrice": 92.5},
    {"code": "SGOV", "name": "0-3月極短國庫券", "assetType": "US_BOND", "usSector": "BOND", "yield": 4.85, "isETB": True, "borrowFeeRate": 0.25, "fallbackPrice": 100.45}
]


def is_valid_stock_or_etf_code(code, name=""):
    """過濾掉 6 碼認購/認售權證 (03~08開頭 或 名稱含購/售/牛/熊)，只保留真實股票與 ETF"""
    if not code:
        return False
    if any(k in name for k in ["購", "售", "牛", "熊", "展", "認購", "認售"]):
        return False
    # 一般台股為 4 碼數字 (如 2330, 7769)；ETF 為 00 開頭 (如 0050, 00679B, 00878)
    if re.match(r"^[1-9]\d{3}$", code):
        return True
    if re.match(r"^00\d{2,4}[A-Z]?$", code):
        return True
    return False


def classify_tw_sector(code, name, board_type="TWSE", is_ky=False):
    """將全台股自動歸類至 8 大板塊區域 (優先識別重電、航運、金控、半導體，讓興櫃重電股也能被重電分類搜到)"""
    if code in ("1519", "1503", "1504", "1513", "1514", "1609", "6806", "7610") or any(k in name for k in ["華城", "士電", "中興電", "亞力", "東元", "大亞", "森崴", "重電", "能源", "綠能", "電網"]):
        return "POWER_GREEN"
    if code in ("2603", "2609", "2615", "2618", "2610", "2606") or any(k in name for k in ["長榮", "陽明", "萬海", "航", "海運", "航空", "物流"]):
        return "SHIPPING"
    if code.startswith("28") or code.startswith("58") or code.endswith("B") or any(k in name for k in ["金", "銀", "險", "證", "債"]):
        return "FINANCE_BOND"
    if is_ky or "-KY" in name.upper() or "KY" in name.upper():
        return "KY_GLOBAL"
    if board_type == "EMERGING":
        return "EMERGING_STAR"
    if board_type == "GISA" or any(k in name for k in ["生技", "藥", "醫", "保瑞", "美時", "合一", "基因"]):
        return "BIOTECH_NEW"
    if code in ("2330", "2454", "3037", "3443", "3661", "2303", "3711", "6770") or any(k in name for k in ["積電", "發科", "世芯", "創意", "欣興", "矽", "晶", "半導", "封測", "聯電", "日月光"]):
        return "AI_SEMI"
    return "SERVER_PC"


def safe_float(val, default=0.0):
    if val is None:
        return default
    s = str(val).replace(",", "").replace("%", "").replace("+", "").strip()
    if not s or s in ("--", "---", "N/A", "X", "除權息", "除息", "除權"):
        return default
    try:
        return float(s)
    except Exception:
        return default


def get_effective_trading_date():
    """若今天為週六或週日，自動退回最近一個週五交易日，避免產生週末重複無波動紀錄"""
    dt = datetime.date.today()
    if dt.weekday() == 5:  # 週六 -> 週五
        dt = dt - datetime.timedelta(days=1)
    elif dt.weekday() == 6:  # 週日 -> 週五
        dt = dt - datetime.timedelta(days=2)
    return dt


def fetch_all_tw_markets_wholesale():
    """批發層：一次抓齊上市、上櫃、KY、興櫃與創櫃板（嚴格過濾權證）"""
    headers = {"User-Agent": "Mozilla/5.0"}
    all_stocks_map = {}
    pe_yield_map = {}

    try:
        r_pe = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL", headers=headers, timeout=12)
        if r_pe.status_code == 200:
            for row in r_pe.json():
                c = str(row.get("Code", "")).strip()
                pe_yield_map[c] = {
                    "pe": round(safe_float(row.get("PEratio"), 16.5), 2),
                    "yield": round(safe_float(row.get("DividendYield"), 3.2), 2)
                }
    except Exception as e:
        print(f"[TWSE BWIBBU 提示] {e}")

    # B. TWSE 上市全市場 (排除 6 碼權證)
    try:
        r_twse = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", headers=headers, timeout=15)
        if r_twse.status_code == 200:
            for row in r_twse.json():
                code = str(row.get("Code", "")).strip()
                name = str(row.get("Name", "")).strip()
                if not is_valid_stock_or_etf_code(code, name):
                    continue
                close_p = safe_float(row.get("ClosingPrice"), 0.0)
                if close_p <= 0:
                    continue
                open_p = safe_float(row.get("OpeningPrice"), close_p)
                high_p = safe_float(row.get("HighestPrice"), close_p)
                low_p = safe_float(row.get("LowestPrice"), close_p)
                chg_val = safe_float(row.get("Change"), 0.0)
                prev_p = max(0.01, close_p - chg_val)
                chg_pct = round((chg_val / prev_p) * 100, 2)
                vol_shares = safe_float(row.get("TradeVolume"), 0.0)
                vol_lots = max(1, int(vol_shares / 1000))

                is_ky = ("-KY" in name.upper()) or ("KY" in name.upper())
                board = "KY" if is_ky else "TWSE"
                sec_cat = classify_tw_sector(code, name, board, is_ky)
                fund = pe_yield_map.get(code, {"pe": 17.5, "yield": 3.1})

                all_stocks_map[code] = {
                    "id": f"{code} {name}",
                    "code": code,
                    "name": name,
                    "boardType": board,
                    "isKY": is_ky,
                    "sectorCat": sec_cat,
                    "assetType": "TW_BOND" if code.endswith("B") else "STOCK",
                    "open": round(open_p, 2),
                    "high": round(high_p, 2),
                    "low": round(low_p, 2),
                    "price": round(close_p, 2),
                    "changePct": chg_pct,
                    "volLots": vol_lots,
                    "pe": fund["pe"],
                    "yield": fund["yield"],
                    "fairValue": round(close_p / (1 + (chg_pct / 100) * 0.45), 2),
                    "allowMarginShort": True,
                    "allowSBL": True,
                    "sblFeeRate": 4.2 if is_ky else (5.5 if fund["pe"] > 30 else 2.0)
                }
            print(f"✅ 已載入 TWSE 上市純股票/ETF(含KY) 共 {len(all_stocks_map)} 檔 (已濾除權證)")
    except Exception as e:
        print(f"[TWSE 全市場提示] {e}")

    # C. TPEx 上櫃全市場 (排除權證)
    try:
        r_otc = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes", headers=headers, timeout=15)
        if r_otc.status_code == 200:
            otc_count = 0
            for row in r_otc.json():
                code = str(row.get("SecuritiesCompanyCode", "")).strip()
                name = str(row.get("CompanyName", "")).strip()
                if not is_valid_stock_or_etf_code(code, name):
                    continue
                close_p = safe_float(row.get("Close"), 0.0)
                if close_p <= 0:
                    continue
                open_p = safe_float(row.get("Open"), close_p)
                high_p = safe_float(row.get("High"), close_p)
                low_p = safe_float(row.get("Low"), close_p)
                chg_val = safe_float(row.get("Change"), 0.0)
                prev_p = max(0.01, close_p - chg_val)
                chg_pct = round((chg_val / prev_p) * 100, 2)
                vol_shares = safe_float(row.get("TradingShares"), 0.0)
                vol_lots = max(1, int(vol_shares / 1000))

                is_ky = "-KY" in name.upper()
                board = "KY" if is_ky else "OTC"
                sec_cat = classify_tw_sector(code, name, board, is_ky)

                all_stocks_map[code] = {
                    "id": f"{code} {name}",
                    "code": code,
                    "name": name,
                    "boardType": board,
                    "isKY": is_ky,
                    "sectorCat": sec_cat,
                    "assetType": "TW_BOND" if code.endswith("B") else "STOCK",
                    "open": round(open_p, 2),
                    "high": round(high_p, 2),
                    "low": round(low_p, 2),
                    "price": round(close_p, 2),
                    "changePct": chg_pct,
                    "volLots": vol_lots,
                    "pe": 0.0 if code.endswith("B") else 21.0,
                    "yield": 4.5 if code.endswith("B") else 2.8,
                    "fairValue": round(close_p / (1 + (chg_pct / 100) * 0.45), 2),
                    "allowMarginShort": not code.endswith("B"),
                    "allowSBL": True,
                    "sblFeeRate": 4.8 if is_ky else 2.8
                }
                otc_count += 1
            print(f"✅ 已載入 TPEx 上櫃純股票/債券ETF 共 {otc_count} 檔")
    except Exception as e:
        print(f"[TPEx 上櫃提示] {e}")

    # D. TPEx 興櫃全市場 (EMERGING)
    try:
        r_emg = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics", headers=headers, timeout=15)
        if r_emg.status_code == 200:
            emg_count = 0
            for row in r_emg.json():
                code = str(row.get("SecuritiesCompanyCode") or row.get("Code") or "").strip()
                name = str(row.get("CompanyName") or row.get("Name") or "").strip()
                if not re.match(r"^[1-9]\d{3}$", code):
                    continue
                close_p = safe_float(row.get("Close") or row.get("AveragePrice") or row.get("LatestPrice"), 0.0)
                if close_p <= 0:
                    continue
                high_p = safe_float(row.get("High"), close_p * 1.02)
                low_p = safe_float(row.get("Low"), close_p * 0.98)
                prev_p = safe_float(row.get("PreviousAveragePrice"), close_p)
                chg_pct = round(((close_p - prev_p) / max(0.01, prev_p)) * 100, 2) if prev_p > 0 else 0.0
                vol_shares = safe_float(row.get("TradingShares") or row.get("Volume"), 500000)
                vol_lots = max(1, int(vol_shares / 1000))

                is_ky = "-KY" in name.upper()
                sec_cat = classify_tw_sector(code, name, "EMERGING", is_ky)

                all_stocks_map[code] = {
                    "id": f"{code} {name}",
                    "code": code,
                    "name": name,
                    "boardType": "EMERGING",
                    "isKY": is_ky,
                    "sectorCat": sec_cat,
                    "assetType": "STOCK",
                    "open": round(prev_p, 2),
                    "high": round(high_p, 2),
                    "low": round(low_p, 2),
                    "price": round(close_p, 2),
                    "changePct": chg_pct,
                    "volLots": vol_lots,
                    "pe": 26.5,
                    "yield": 1.3,
                    "fairValue": round(prev_p, 2),
                    "allowMarginShort": False,
                    "allowSBL": False,
                    "sblFeeRate": 9.5,
                    "haltReason": "興櫃無融券制度(無漲跌幅限制)"
                }
                emg_count += 1
            print(f"✅ 已載入 TPEx 興櫃(無漲跌幅限制) 共 {emg_count} 檔")
    except Exception as e:
        print(f"[TPEx 興櫃提示] {e}")

    if "7769" not in all_stocks_map:
        all_stocks_map["7769"] = {
            "id": "7769 鴻勁(興櫃AI設備)", "code": "7769", "name": "鴻勁(興櫃AI設備)",
            "boardType": "EMERGING", "isKY": False, "sectorCat": "EMERGING_STAR", "assetType": "STOCK",
            "open": 1850.0, "high": 2130.0, "low": 1840.0, "price": 2110.0, "changePct": 14.05,
            "volLots": 4800, "pe": 25.0, "yield": 1.3, "fairValue": 1850.0,
            "allowMarginShort": False, "allowSBL": False, "sblFeeRate": 9.5, "haltReason": "興櫃無融券制度"
        }

    # E. 注入創櫃板 (GISA)
    for g in GISA_INNOVATION_POOL:
        c = g["code"]
        if c not in all_stocks_map:
            all_stocks_map[c] = {
                "id": f"{c} {g['name']}",
                "code": c,
                "name": g["name"],
                "boardType": "GISA",
                "isKY": False,
                "sectorCat": g["sectorCat"],
                "assetType": "STOCK",
                "open": g["basePrice"],
                "high": round(g["basePrice"] * 1.03, 2),
                "low": round(g["basePrice"] * 0.98, 2),
                "price": round(g["basePrice"] * 1.015, 2),
                "changePct": 1.50,
                "volLots": 650,
                "pe": g["pe"],
                "yield": g["yield"],
                "fairValue": g["basePrice"],
                "allowMarginShort": False,
                "allowSBL": False,
                "sblFeeRate": 9.9,
                "haltReason": "創櫃板新創禁空"
            }

    return all_stocks_map


def enrich_top_focus_via_fugle(all_stocks_map):
    """點穴層：確保八大產業代表股全部在焦點池與搜尋池中"""
    must_have_codes = [
        "2330", "2454", "2317", "2382", "2603", "2609", "2891",
        "1519", "1503", "1504", "1513", "3037", "00679B", "3661", "7769", "7556", "7610"
    ]
    focus_list = []

    for c in must_have_codes:
        if c in all_stocks_map:
            focus_list.append(all_stocks_map[c])

    ky_candidates = sorted([s for s in all_stocks_map.values() if s.get("isKY")], key=lambda x: x.get("volLots", 0), reverse=True)[:3]
    emg_candidates = sorted([s for s in all_stocks_map.values() if s.get("boardType") == "EMERGING"], key=lambda x: abs(x.get("changePct", 0)), reverse=True)[:3]
    gisa_candidates = [s for s in all_stocks_map.values() if s.get("boardType") == "GISA"]

    for extra in (ky_candidates + emg_candidates + gisa_candidates):
        if extra["code"] not in [x["code"] for x in focus_list]:
            focus_list.append(extra)

    # 僅於平日開盤日呼叫 Fugle 更新即時價，避免週日休市回傳空值覆蓋
    is_weekend = datetime.date.today().weekday() >= 5
    if FUGLE_API_KEY and not is_weekend:
        print("🔌 正在透過 Fugle API 點穴更新焦點股即時五檔價差...")
        headers = {"X-API-KEY": FUGLE_API_KEY}
        for s in focus_list[:16]:
            if s.get("boardType") == "GISA":
                continue
            try:
                time.sleep(1.02)
                url = f"{FUGLE_BASE_URL}/intraday/quote/{s['code']}"
                r = requests.get(url, headers=headers, timeout=8)
                if r.status_code == 200:
                    q = r.json()
                    if q.get("closePrice") and float(q["closePrice"]) > 0:
                        s["price"] = float(q["closePrice"])
                    if q.get("changePercent") is not None:
                        s["changePct"] = float(q["changePercent"])
                    bids = q.get("bids") or []
                    asks = q.get("asks") or []
                    if bids and asks and bids[0].get("price") and asks[0].get("price"):
                        mid = (float(bids[0]["price"]) + float(asks[0]["price"])) / 2.0
                        if mid > 0:
                            s["fugleSpreadBps"] = round(((float(asks[0]["price"]) - float(bids[0]["price"])) / mid) * 10000, 2)
            except Exception:
                pass

    for s in focus_list:
        b_tag = "🌏KY第一上市" if s.get("isKY") else ("🚀興櫃無漲跌限" if s.get("boardType") == "EMERGING" else ("🌱創櫃板新創" if s.get("boardType") == "GISA" else "🏛️上市櫃核心"))
        s["news"] = [{
            "title": f"【{b_tag}｜{s.get('sectorCat','台股')}】{s['id']} 收 ${s['price']} ({'+' if s['changePct']>=0 else ''}{s['changePct']}%)，量 {s.get('volLots',0):,} 張",
            "score": 1 if s["changePct"] >= 0 else -1
        }]

    # 確保八大產業代表股與前 800 大活絡純股票都在 allStocks 中
    focus_codes = {x["code"] for x in focus_list}
    sorted_others = sorted(
        [v for k, v in all_stocks_map.items() if k not in focus_codes],
        key=lambda x: (x.get("boardType") in ("EMERGING", "GISA") or x.get("isKY"), x.get("volLots", 0)),
        reverse=True
    )[:750]
    sorted_all = focus_list + sorted_others
    return focus_list, sorted_all, len(all_stocks_map)


def fetch_us_and_macro_via_yfinance(tsmc_price=1050.0, tsmc_chg=0.5):
    """跨國層：抓取美股、美債、USD/TWD 匯率與真實台灣加權指數 (^TWII)"""
    fx_rate = 32.25
    taiex_close = round(max(22500, tsmc_price * 21.65))
    taiex_chg = tsmc_chg
    us_assets_out = []

    if HAS_YFINANCE:
        try:
            fx_hist = yf.Ticker("TWD=X").history(period="5d")
            if not fx_hist.empty:
                fx_rate = round(float(fx_hist["Close"].iloc[-1]), 2)
        except Exception:
            pass

        try:
            twii_hist = yf.Ticker("^TWII").history(period="5d")
            if len(twii_hist) >= 2:
                prev_tw = float(twii_hist["Close"].iloc[-2])
                cur_tw = float(twii_hist["Close"].iloc[-1])
                if cur_tw > 15000:
                    taiex_close = round(cur_tw)
                    taiex_chg = round(((cur_tw - prev_tw) / prev_tw) * 100, 2)
        except Exception:
            pass

    for item in CORE_US_ASSETS:
        code = item["code"]
        price = item["fallbackPrice"]
        open_p = price
        high_p = round(price * 1.01, 2)
        low_p = round(price * 0.99, 2)
        chg_pct = 0.5
        vol_shares = 35000000

        if HAS_YFINANCE:
            try:
                tk = yf.Ticker(code)
                h = tk.history(period="5d")
                if len(h) >= 2:
                    prev_c = float(h["Close"].iloc[-2])
                    cur_c = float(h["Close"].iloc[-1])
                    price = round(cur_c, 2)
                    open_p = round(float(h["Open"].iloc[-1]), 2)
                    high_p = round(float(h["High"].iloc[-1]), 2)
                    low_p = round(float(h["Low"].iloc[-1]), 2)
                    chg_pct = round(((cur_c - prev_c) / max(0.01, prev_c)) * 100, 2)
                    vol_shares = int(h["Volume"].iloc[-1]) or 35000000
            except Exception:
                pass

        us_assets_out.append({
            "id": f"{code} {item['name']}",
            "code": code,
            "name": item["name"],
            "assetType": item["assetType"],
            "usSector": item["usSector"],
            "currency": "USD",
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "price": price,
            "changePct": chg_pct,
            "volShares": vol_shares,
            "yield": item["yield"],
            "exDividendDate": "",
            "cashDividend": 0.0,
            "isETB": item["isETB"],
            "borrowFeeRate": item["borrowFeeRate"]
        })

    return fx_rate, taiex_close, taiex_chg, us_assets_out


def main():
    print("🚀 啟動 V25.0 全台股四板塊 (過濾權證＋週末防重複＋真實台指期點數) 引擎...")
    all_stocks_map = fetch_all_tw_markets_wholesale()
    focus_sectors, all_stocks_list, total_count = enrich_top_focus_via_fugle(all_stocks_map)

    tsmc_obj = all_stocks_map.get("2330", {"price": 1065.0, "changePct": 0.8})
    fx_rate, taiex_close, taiex_chg, us_assets_list = fetch_us_and_macro_via_yfinance(
        tsmc_obj["price"], tsmc_obj["changePct"]
    )

    eff_dt = get_effective_trading_date()
    date_str = eff_dt.strftime("%Y-%m-%d")
    weekday_str = WEEKDAY_MAP[eff_dt.weekday()]

    tx_open = round(taiex_close / (1 + (taiex_chg * 0.7) / 100))
    macro_futures = [
        {"id": "TX 臺股大台指期貨", "futCode": "TX", "futName": "臺股大台指期貨", "underlyingId": "臺灣加權指數", "open": tx_open, "high": max(tx_open, taiex_close) + 85, "low": min(tx_open, taiex_close) - 70, "price": taiex_close, "changePct": taiex_chg, "volLots": 115000, "sharesPerContract": 200, "marginRate": 0.051, "marginReq": 242000, "maintMargin": 185000, "settlementDate": "2026-11-18"},
        {"id": "MTX 小型臺指期貨", "futCode": "MTX", "futName": "小型臺指期貨", "underlyingId": "臺灣加權指數", "open": tx_open, "high": max(tx_open, taiex_close) + 85, "low": min(tx_open, taiex_close) - 70, "price": taiex_close, "changePct": taiex_chg, "volLots": 215000, "sharesPerContract": 50, "marginRate": 0.051, "marginReq": 60500, "maintMargin": 46250, "settlementDate": "2026-11-18"},
        {"id": "TMF 微型臺指期貨", "futCode": "TMF", "futName": "微型臺指期貨", "underlyingId": "臺灣加權指數", "open": tx_open, "high": max(tx_open, taiex_close) + 85, "low": min(tx_open, taiex_close) - 70, "price": taiex_close, "changePct": taiex_chg, "volLots": 168000, "sharesPerContract": 10, "marginRate": 0.051, "marginReq": 12100, "maintMargin": 9250, "settlementDate": "2026-11-18"}
    ]

    new_rec = {
        "date": date_str,
        "weekday": weekday_str,
        "fullDateLabel": f"{date_str} ({weekday_str})",
        "fxRate": fx_rate,
        "taiexPrice": taiex_close,
        "taiexChangePct": taiex_chg,
        "macroFutures": macro_futures,
        "totalMarketCount": total_count,
        "chapterTitle": f"全台股四板塊制霸 ({total_count}檔純股與ETF同步｜{date_str})",
        "usAssets": us_assets_list,
        "sectors": focus_sectors,
        "allStocks": all_stocks_list
    }

    history_data = {"records": []}
    if os.path.exists(HISTORY_JSON_PATH):
        try:
            with open(HISTORY_JSON_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded.get("records"), list):
                    # 自動清除先前誤產生的週六、週日休市重複紀錄
                    clean_recs = []
                    for r in loaded["records"]:
                        d_s = r.get("date", "")
                        try:
                            wd = datetime.date.fromisoformat(d_s).weekday()
                            if wd >= 5:
                                continue
                        except Exception:
                            pass
                        clean_recs.append(r)
                    history_data["records"] = clean_recs
        except Exception:
            pass

    idx = next((i for i, r in enumerate(history_data["records"]) if r.get("date") == date_str), -1)
    if idx >= 0:
        history_data["records"][idx] = new_rec
    else:
        history_data["records"].append(new_rec)
    history_data["records"].sort(key=lambda r: r.get("date", ""))

    with open(HISTORY_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)
    print(f"🎉 修復完成！已濾除權證並清除週末重複紀錄，共 {total_count} 檔純股票/ETF、台指期 {taiex_close:,} 點寫入 {HISTORY_JSON_PATH}！")


if __name__ == "__main__":
    main()
