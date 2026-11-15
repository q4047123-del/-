#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【傳奇大師賽博炒股 V25.0 終極完整版】update_stocks.py
1. 批發層：一次抓齊 TWSE 上市、TPEx 上櫃、KY 股、TPEx 興櫃與 GISA 創櫃板（嚴格過濾權證混入股票池）
2. 點穴層：透過 Fugle API 更新焦點股即時五檔委買委賣價差 (fugleSpreadBps)
3. 權證層 (NEW!)：根據各期現股價格與交易日期，自動生成具備「雙月季度輪動換約、動態履約價對齊、Theta時間衰減、真實槓桿連動」之 6 碼權證池，杜絕過期權證或價格脫鉤！
4. 跨國與總經層：yfinance 同步真實 ^VIX、^TNX (10Y美債)、^IRX、^TWII (加權指數)、TWD=X 匯率與 Google News 台股即時 RSS 頭條
"""

import os
import re
import math
import json
import time
import datetime
import xml.etree.ElementTree as ET
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

# TWSE 6碼權證發行基準規格表 (會隨各期交易日自動輪動合約月份與對齊當期履約價)
TWSE_WARRANT_TEMPLATES = [
    {"code": "081524", "baseName": "台積電元大5B購01", "warrantType": "CALL", "underlyingCode": "2330", "underlyingId": "2330 台積電", "targetMult": 1.02, "cr": 0.02, "isDeepOtm": False},
    {"code": "042891", "baseName": "鴻海凱基5B購02", "warrantType": "CALL", "underlyingCode": "2317", "underlyingId": "2317 鴻海", "targetMult": 1.02, "cr": 0.15, "isDeepOtm": False},
    {"code": "053108", "baseName": "華城群益5C購01", "warrantType": "CALL", "underlyingCode": "1519", "underlyingId": "1519 華城", "targetMult": 1.03, "cr": 0.05, "isDeepOtm": False},
    {"code": "061882", "baseName": "華城中信5B購01(深度價外)", "warrantType": "CALL", "underlyingCode": "1519", "underlyingId": "1519 華城", "targetMult": 1.18, "cr": 0.05, "isDeepOtm": True},
    {"code": "072341", "baseName": "長榮元富5B購01", "warrantType": "CALL", "underlyingCode": "2603", "underlyingId": "2603 長榮", "targetMult": 1.02, "cr": 0.15, "isDeepOtm": False},
    {"code": "038912", "baseName": "中信金永豐5B購01", "warrantType": "CALL", "underlyingCode": "2891", "underlyingId": "2891 中信金", "targetMult": 1.02, "cr": 0.50, "isDeepOtm": False},
    {"code": "04192P", "baseName": "欣興凱基5B售01", "warrantType": "PUT", "underlyingCode": "3037", "underlyingId": "3037 欣興", "targetMult": 0.95, "cr": 0.15, "isDeepOtm": False}
]


def is_valid_stock_or_etf_code(code, name=""):
    """過濾掉 6 碼認購/認售權證，只保留真實 4 碼股票與 00 開頭 ETF"""
    if not code:
        return False
    if any(k in name for k in ["購", "售", "牛", "熊", "展", "認購", "認售"]):
        return False
    if re.match(r"^[1-9]\d{3}$", code):
        return True
    if re.match(r"^00\d{2,4}[A-Z]?$", code):
        return True
    return False


def classify_tw_sector(code, name, board_type="TWSE", is_ky=False):
    """將全台股自動歸類至 8 大板塊區域"""
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
    """若逢週六或週日，自動對齊至最近一個週五交易日"""
    dt = datetime.date.today()
    if dt.weekday() == 5:
        dt = dt - datetime.timedelta(days=1)
    elif dt.weekday() == 6:
        dt = dt - datetime.timedelta(days=2)
    return dt


def build_dynamic_warrants_for_date(stocks_list, current_date_str):
    """
    ★ V25.0 Python 端權證自動定價與雙月季度輪動引擎：
    1. 依 current_date_str 自動計算當期雙月合約到期日 (每月 28 號到期，過期自動換掛下一期新合約)
    2. 依當期標的現股真實價格動態錨定履約價 (杜絕台積電漲到 $2350 履約價還停在 $1050 的問題)
    3. 依剩餘天數計算 Theta 時間價值衰減、內含價值、合理市價、真實有效槓桿與聯動漲跌幅
    """
    try:
        cur_dt = datetime.date.fromisoformat(current_date_str)
    except Exception:
        cur_dt = datetime.date.today()

    cur_year = cur_dt.year
    cur_month = cur_dt.month
    cur_day = cur_dt.day

    # 每 2 個月為一輪權證合約週期；若超過當月 28 號結算日，立即下市並換掛下一個雙月新合約
    mat_year = cur_year
    mat_month = cur_month + 1 if (cur_month % 2 == 1) else cur_month
    if cur_month == mat_month and cur_day > 28:
        mat_month += 2
        if mat_month > 12:
            mat_month -= 12
            mat_year += 1

    maturity_date_str = f"{mat_year}-{mat_month:02d}-28"
    last_trading_date_str = f"{mat_year}-{mat_month:02d}-24"

    roc_year_digit = (mat_year - 1911) % 10
    month_code = "A" if mat_month == 10 else ("B" if mat_month == 11 else ("C" if mat_month == 12 else str(mat_month)))

    try:
        mat_dt = datetime.date.fromisoformat(maturity_date_str)
        days_to_maturity = max(0, (mat_dt - cur_dt).days)
    except Exception:
        days_to_maturity = 30

    is_matured_today = (current_date_str == maturity_date_str)
    is_halted = (current_date_str > last_trading_date_str and current_date_str < maturity_date_str)

    stock_map = {s.get("code"): s for s in (stocks_list or []) if s.get("code")}
    warrants_out = []

    for tpl in TWSE_WARRANT_TEMPLATES:
        u_code = tpl["underlyingCode"]
        st_obj = stock_map.get(u_code)
        u_price = float(st_obj["price"]) if (st_obj and st_obj.get("price", 0) > 0) else 200.0
        u_chg = float(st_obj.get("changePct", 0.0)) if st_obj else 0.0
        u_high = float(st_obj.get("high", u_price)) if st_obj else u_price
        u_low = float(st_obj.get("low", u_price)) if st_obj else u_price
        u_vol = int(st_obj.get("volLots", 15000)) if st_obj else 15000

        # 自動將權證名稱中的民國年與月份代號更新為當期活躍合約
        dyn_name = re.sub(r"[0-9][1-9ABCabc]([購售])", f"{roc_year_digit}{month_code}\\1", tpl["baseName"])
        w_id = f"{tpl['code']} {dyn_name}"
        w_type = tpl["warrantType"]
        is_deep_otm = tpl["isDeepOtm"]

        # 根據當期現股價格動態對齊合理履約價
        raw_strike = u_price * tpl["targetMult"]
        if u_price >= 500:
            strike_price = round(raw_strike / 10.0) * 10.0
        else:
            strike_price = round(raw_strike, 1)

        cr = tpl["cr"]
        if u_price >= 1500 and cr > 0.025:
            cr = 0.02

        settle_p_60m = round((u_high + u_low + u_price * 2.0) / 4.0, 2)

        if w_type == "CALL":
            intrinsic_val = max(0.0, (u_price - strike_price) * cr)
            settle_intrinsic_val = max(0.0, (settle_p_60m - strike_price) * cr)
            moneyness_pct = round(((u_price - strike_price) / max(1.0, strike_price)) * 100.0, 1)
        else:
            intrinsic_val = max(0.0, (strike_price - u_price) * cr)
            settle_intrinsic_val = max(0.0, (strike_price - settle_p_60m) * cr)
            moneyness_pct = round(((strike_price - u_price) / max(1.0, strike_price)) * 100.0, 1)

        is_itm = moneyness_pct > 0

        # 計算隨到期天數衰減之時間價值 (Theta Decay)
        theta_factor = math.sqrt(min(60.0, float(days_to_maturity)) / 45.0)
        base_time_rate = 0.018 if is_deep_otm else (0.032 if is_itm else 0.045)
        theo_time_val = 0.0 if is_matured_today else max(
            0.05,
            u_price * cr * base_time_rate * theta_factor * math.exp(-max(0.0, -moneyness_pct) / 18.0)
        )

        if is_matured_today:
            w_price = round(settle_intrinsic_val, 2) if settle_intrinsic_val > 0 else 0.01
        else:
            w_price = round(max(0.15, intrinsic_val + theo_time_val), 2)

        approx_delta = min(0.88, 0.55 + moneyness_pct / 40.0) if is_itm else max(0.18, 0.48 + moneyness_pct / 35.0)
        eff_leverage = round(min(12.5, max(1.5, (u_price * cr / max(0.05, w_price)) * approx_delta)), 1)

        dir_sign = -1.0 if w_type == "PUT" else 1.0
        w_chg_pct = round(max(-45.0, min(85.0, u_chg * dir_sign * eff_leverage * 0.85)), 2)

        prev_w_close = max(0.05, round(w_price / (1.0 + w_chg_pct / 100.0), 2))
        w_open = round(prev_w_close * (1.0 + (w_chg_pct * 0.3) / 100.0), 2)
        w_high = round(max(w_open, w_price) * 1.02, 2)
        w_low = round(min(w_open, w_price) * 0.98, 2)
        w_vol_lots = max(1500, int(u_vol * 0.32))

        warrants_out.append({
            "id": w_id,
            "code": tpl["code"],
            "name": dyn_name,
            "warrantType": w_type,
            "underlyingCode": u_code,
            "underlyingId": st_obj["id"] if st_obj else tpl["underlyingId"],
            "underlyingPrice": u_price,
            "strikePrice": strike_price,
            "exerciseRatio": cr,
            "lastTradingDate": last_trading_date_str,
            "maturityDate": maturity_date_str,
            "daysToMaturity": days_to_maturity,
            "settlementPrice60m": settle_p_60m,
            "intrinsicUnitVal": round(intrinsic_val, 3),
            "settleIntrinsicUnitVal": round(settle_intrinsic_val, 3),
            "moneynessPct": moneyness_pct,
            "isITM": is_itm,
            "effLeverage": eff_leverage,
            "isHaltedBeforeMaturity": is_halted,
            "isMaturedToday": is_matured_today,
            "open": w_open,
            "high": w_high,
            "low": w_low,
            "price": w_price,
            "changePct": w_chg_pct,
            "volLots": w_vol_lots
        })

    return warrants_out


def fetch_live_tw_financial_news_rss(max_items=4):
    """從 Google News 抓取最新台灣股市/台積電/總經真實新聞頭條"""
    headlines = []
    try:
        url = "https://news.google.com/rss/search?q=%E5%8F%B0%E8%82%A1+OR+%E5%8F%B0%E7%A9%8D%E9%9B%BB+OR+%E8%88%88%E6%AB%83&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            for item in root.findall("./channel/item")[:max_items]:
                title = (item.findtext("title") or "").strip()
                if title:
                    score = 2 if any(w in title for w in ["漲", "創高", "利多", "買超", "噴", "強", "降息"]) else (-2 if any(w in title for w in ["跌", "重挫", "賣超", "恐慌", "通膨", "殺"]) else 1)
                    headlines.append({
                        "tag": "📰台股即時頭條",
                        "title": title,
                        "score": score
                    })
    except Exception as e:
        print(f"[新聞 RSS 提示] {e}")
    return headlines


def generate_upgraded_stock_news(s):
    """根據個股四板塊屬性、漲跌幅、量能、本益比、殖利率與五檔滑價，生成專業級多維度情報新聞"""
    code = s.get("code", "")
    name = s.get("name", "")
    price = s.get("price", 0)
    chg = s.get("changePct", 0)
    vol = s.get("volLots", 0)
    pe = s.get("pe", 16.0)
    yld = s.get("yield", 3.0)
    board = s.get("boardType", "TWSE")
    is_ky = s.get("isKY", False)
    sec_cat = s.get("sectorCat", "SERVER_PC")
    spread_bps = s.get("fugleSpreadBps")

    b_tag = "🌏KY第一上市" if is_ky else ("🚀興櫃無漲跌限" if board == "EMERGING" else ("🌱創櫃板新創" if board == "GISA" else ("🏛️上櫃" if board == "OTC" else "🏛️上市")))
    sign = "+" if chg >= 0 else ""
    spread_str = f"｜Fugle五檔價差 {spread_bps}bps" if spread_bps else ""

    news_items = []

    if board == "EMERGING":
        if chg >= 5.0:
            news_items.append({
                "title": f"🚀【興櫃無漲跌停限制飆股】{code} {name} 推薦券商造市買盤湧入，單日狂飆 {sign}{chg}% 收 ${price}（量 {vol:,} 張），觸發李佛摩箱型突破金字塔加碼信號！",
                "score": 2
            })
        elif chg <= -4.0:
            news_items.append({
                "title": f"⚠️【興櫃高波動拉回】{code} {name} 盤中議價賣壓出籠回檔 {chg}% 收 ${price}（興櫃無融券制度不可放空，宜留意造市商買賣價差）",
                "score": -2
            })
        else:
            news_items.append({
                "title": f"🚀【興櫃戰略觀察】{code} {name} 收 ${price} ({sign}{chg}%)，成交量 {vol:,} 張，機構與散戶關注轉上市櫃潛力",
                "score": 1 if chg >= 0 else -1
            })
    elif board == "GISA":
        news_items.append({
            "title": f"🌱【創櫃板微小型新創】{code} {name} 最新參考價 ${price} ({sign}{chg}%)，PE={pe}倍、殖利率 {yld}%，籌碼無信用融資浮額，獲咆哮小貓 Deep Value 底倉鎖定！",
            "score": 2 if chg >= 0 else 1
        })
    elif is_ky:
        if abs(chg) >= 3.0:
            news_items.append({
                "title": f"🌏【KY海外第一上市高Beta異動】{code} {name} 今日劇烈波動 {sign}{chg}% 收 ${price}（量 {vol:,} 張，PE={pe}倍），西蒙斯大獎章模型啟動橫截面 Z-Score 掃描！",
                "score": 2 if chg > 0 else -2
            })
        else:
            news_items.append({
                "title": f"🌏【KY跨國供應鏈】{code} {name} 收 ${price} ({sign}{chg}%)，PE={pe}倍、殖利率 {yld}%{spread_str}",
                "score": 1 if chg >= 0 else -1
            })
    else:
        if chg >= 3.5:
            news_items.append({
                "title": f"🔥【{b_tag}帶量突破】{code} {name} 法人買盤點火強攻 {sign}{chg}% 收 ${price}（爆量 {vol:,} 張{spread_str}），動量因子 Z-Score 顯著轉正！",
                "score": 2
            })
        elif chg <= -2.5:
            news_items.append({
                "title": f"📉【{b_tag}回測均線】{code} {name} 隨盤勢修正 {chg}% 收 ${price}（量 {vol:,} 張，PE={pe}倍、殖利率 {yld}%），巴菲特與西蒙斯評估超跌低接安全邊際",
                "score": -2
            })
        else:
            news_items.append({
                "title": f"🏛️【{b_tag}盤後微結構】{code} {name} 收 ${price} ({sign}{chg}%)，成交量 {vol:,} 張｜PE={pe}倍、殖利率 {yld}%{spread_str}",
                "score": 1 if chg >= 0 else -1
            })

    if yld >= 4.5 and pe > 0 and pe <= 16.0:
        news_items.append({
            "title": f"🛡️【波克夏價值護城河】{code} {name} 具備高現金殖利率 ({yld}%) 與低本益比 ({pe}倍) 雙重安全墊，長線防禦價值浮現",
            "score": 2
        })
    elif sec_cat in ("AI_SEMI", "SERVER_PC", "POWER_GREEN") and chg >= 1.5:
        news_items.append({
            "title": f"⚡【AI算力與電力基建咽喉】{code} {name} 受惠北美 CSP 雲端資本支出與電網升級需求，阿申 (Situational Awareness) 納入核心算力輪動池",
            "score": 2
        })

    return news_items


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
            print(f"✅ 已載入 TWSE 上市純股票/ETF(含KY) 共 {len(all_stocks_map)} 檔")
    except Exception as e:
        print(f"[TWSE 全市場提示] {e}")

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

    for s in all_stocks_map.values():
        s["news"] = generate_upgraded_stock_news(s)

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
                    s["news"] = generate_upgraded_stock_news(s)
            except Exception:
                pass

    focus_codes = {x["code"] for x in focus_list}
    sorted_others = sorted(
        [v for k, v in all_stocks_map.items() if k not in focus_codes],
        key=lambda x: (x.get("boardType") in ("EMERGING", "GISA") or x.get("isKY"), x.get("volLots", 0)),
        reverse=True
    )[:750]
    sorted_all = focus_list + sorted_others
    return focus_list, sorted_all, len(all_stocks_map)


def fetch_us_and_macro_via_yfinance(tsmc_price=1050.0, tsmc_chg=0.5, focus_sectors=None):
    """跨國層：抓取真實 ^VIX、^TNX (10Y美債)、^IRX、^TWII 與 Google News 即時頭條"""
    fx_rate = 32.50
    taiex_close = round(max(22500, tsmc_price * 21.65))
    taiex_chg = tsmc_chg
    vix_val = 16.5
    vix_chg = 0.0
    us10y_val = 4.35
    us10y_chg = 0.0
    irx_val = 4.50
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

        try:
            vix_hist = yf.Ticker("^VIX").history(period="5d")
            if len(vix_hist) >= 2:
                vix_val = round(float(vix_hist["Close"].iloc[-1]), 2)
                vix_chg = round(vix_val - float(vix_hist["Close"].iloc[-2]), 2)
        except Exception:
            pass

        try:
            tnx_hist = yf.Ticker("^TNX").history(period="5d")
            if len(tnx_hist) >= 2:
                us10y_val = round(float(tnx_hist["Close"].iloc[-1]), 2)
                us10y_chg = round(us10y_val - float(tnx_hist["Close"].iloc[-2]), 2)
        except Exception:
            pass

        try:
            irx_hist = yf.Ticker("^IRX").history(period="5d")
            if not irx_hist.empty:
                irx_val = round(float(irx_hist["Close"].iloc[-1]), 2)
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

    is_stress = vix_val >= 20.0
    if is_stress or taiex_chg <= -0.8:
        regime = "HAWKISH_INFLATION"
        regime_label = f"🔴 VIX={vix_val} 避險升溫・ERC風控防禦" if is_stress else f"🔴 殖利率{us10y_val}%壓抑・震盪防禦"
        regime_color = "#ff8a80"
        macro_score = -2
        borrow_heat = f"{round(1.35 + max(0, (vix_val - 15) * 0.05), 2)}x▲(搶券)"
    elif taiex_chg >= 0.8 and vix_val <= 17.5:
        regime = "RATE_CUT_RALLY"
        regime_label = f"🚀 台股+{taiex_chg}%・VIX={vix_val}多頭擴張"
        regime_color = "#ffd54f"
        macro_score = 2
        borrow_heat = "0.95x▼(回補)"
    else:
        regime = "GOLDILOCKS"
        regime_label = f"🟢 台股盤整({taiex_chg:+.2f}%)・四板塊輪動"
        regime_color = "#76c888"
        macro_score = 1
        borrow_heat = "1.10x(溫和)"

    vix_arrow = "▲" if vix_chg > 0.05 else ("▼" if vix_chg < -0.05 else "")
    y10_arrow = "▲" if us10y_chg > 0.02 else ("▼" if us10y_chg < -0.02 else "")

    rss_headlines = fetch_live_tw_financial_news_rss(max_items=4)
    top_gainer = sorted(focus_sectors or [], key=lambda x: x.get("changePct", 0), reverse=True)[0] if focus_sectors else None
    nvda_obj = next((u for u in us_assets_out if u["code"] == "NVDA"), None)

    auto_headlines = [
        {
            "tag": "🌐真實總經與台指期實盤",
            "title": f"【台美實盤同步】加權指數收 {taiex_close:,} 點 ({taiex_chg:+.2f}%)｜VIX 恐慌指數 {vix_val}{vix_arrow}｜10Y 美債殖利率 {us10y_val}%{y10_arrow}｜USD/TWD 匯率 {fx_rate}",
            "score": 2 if taiex_chg >= 0 else -2
        }
    ]
    if top_gainer:
        auto_headlines.append({
            "tag": "🔥四板塊最強領頭羊",
            "title": f"【當日強勢焦點】{top_gainer['id']} 領漲 +{top_gainer['changePct']}% 收 ${top_gainer['price']}（成交量 {top_gainer.get('volLots',0):,} 張），吸引動量資金進駐！",
            "score": 2
        })
    if nvda_obj:
        auto_headlines.append({
            "tag": "🇺🇸美股AI算力連動",
            "title": f"【跨國算力風向球】輝達 (NVDA) 最新收 US${nvda_obj['price']} ({nvda_obj['changePct']:+.2f}%)，牽動台積電、世芯-KY 與興櫃 AI 檢測設備族群表現",
            "score": 1 if nvda_obj["changePct"] >= 0 else -1
        })

    macro_obj = {
        "regime": regime,
        "regimeLabel": regime_label,
        "regimeColor": regime_color,
        "fedRate": f"{irx_val:.2f}%",
        "us10yYield": f"{us10y_val:.2f}%{y10_arrow}",
        "vixIndex": f"{vix_val:.2f}{vix_arrow}",
        "stressMultText": "1.40x🚨(VIX壓力)" if is_stress else "1.00x🟢(正常)",
        "borrowHeatText": borrow_heat,
        "macroScore": macro_score,
        "headlines": rss_headlines + auto_headlines
    }

    return fx_rate, taiex_close, taiex_chg, us_assets_out, macro_obj


def clean_and_upgrade_existing_record(r):
    """清理舊歷史紀錄中誤混入的 6 碼權證、補齊升級版新聞，並為每一期重新計算當期動態掛牌權證"""
    d_str = r.get("date", "2026-11-10")
    if isinstance(r.get("allStocks"), list):
        r["allStocks"] = [
            s for s in r["allStocks"]
            if is_valid_stock_or_etf_code(str(s.get("code", "")), str(s.get("name", "")))
        ]
        r["totalMarketCount"] = max(len(r["allStocks"]), 2320)

    if isinstance(r.get("sectors"), list):
        r["sectors"] = [
            s for s in r["sectors"]
            if is_valid_stock_or_etf_code(str(s.get("code", "")), str(s.get("name", "")))
        ]
        for s in r["sectors"]:
            s["news"] = generate_upgraded_stock_news(s)
        # ★ 為每一筆歷史交易日生成對齊當期現股價格與當期雙月合約到期日的 6 碼權證
        r["warrants"] = build_dynamic_warrants_for_date(r["sectors"], d_str)
    return r


def main():
    print("🚀 啟動 V25.0 全台股四板塊 + 6碼權證季度動態換約 + 真實總經與即時新聞引擎...")
    all_stocks_map = fetch_all_tw_markets_wholesale()
    focus_sectors, all_stocks_list, total_count = enrich_top_focus_via_fugle(all_stocks_map)

    tsmc_obj = all_stocks_map.get("2330", {"price": 1065.0, "changePct": 0.8})
    fx_rate, taiex_close, taiex_chg, us_assets_list, macro_obj = fetch_us_and_macro_via_yfinance(
        tsmc_obj["price"], tsmc_obj["changePct"], focus_sectors
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

    # 生成當期動態掛牌與合理定價之 6 碼權證清單
    dynamic_warrants = build_dynamic_warrants_for_date(focus_sectors, date_str)

    new_rec = {
        "date": date_str,
        "weekday": weekday_str,
        "fullDateLabel": f"{date_str} ({weekday_str})",
        "fxRate": fx_rate,
        "taiexPrice": taiex_close,
        "taiexChangePct": taiex_chg,
        "macro": macro_obj,
        "macroFutures": macro_futures,
        "totalMarketCount": total_count,
        "chapterTitle": f"全台股四板塊實盤 ({total_count}檔同步｜台指 {taiex_close:,} 點｜VIX {macro_obj['vixIndex']})",
        "usAssets": us_assets_list,
        "sectors": focus_sectors,
        "warrants": dynamic_warrants,
        "allStocks": all_stocks_list
    }

    history_data = {"records": []}
    if os.path.exists(HISTORY_JSON_PATH):
        try:
            with open(HISTORY_JSON_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded.get("records"), list):
                    clean_recs = []
                    for r in loaded["records"]:
                        d_s = r.get("date", "")
                        try:
                            wd = datetime.date.fromisoformat(d_s).weekday()
                            if wd >= 5:
                                continue
                        except Exception:
                            pass
                        clean_recs.append(clean_and_upgrade_existing_record(r))
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
    print(f"🎉 全面升級完成！已將 {total_count} 檔純股票/ETF、{len(dynamic_warrants)} 檔動態換約權證、台指期 {taiex_close:,} 點與即時新聞寫入 {HISTORY_JSON_PATH}！")


if __name__ == "__main__":
    main()
