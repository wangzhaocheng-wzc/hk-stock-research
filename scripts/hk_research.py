#!/usr/bin/env python3
"""Generate a compact Hong Kong stock research brief from public data."""

from __future__ import annotations

import argparse
import contextlib
import html
import io
import json
import numbers
import re
import sys
import warnings
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

warnings.filterwarnings("ignore")

import pandas as pd
import requests


@dataclass
class FetchResult:
    name: str
    ok: bool
    data: Any = None
    error: Optional[str] = None


def normalize_hk_symbol(raw: str) -> str:
    """Normalize HK tickers like HK:700, 700.HK, or 00700 to 5 digits."""
    match = re.search(r"(\d{1,5})", raw)
    if not match:
        raise ValueError(f"Cannot find a Hong Kong stock code in: {raw}")
    return match.group(1).zfill(5)


def safe_fetch(name: str, func: Any, *args: Any, **kwargs: Any) -> FetchResult:
    """Run a data fetch and return a structured error instead of raising."""
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return FetchResult(name=name, ok=True, data=func(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001 - preserve upstream endpoint failures.
        return FetchResult(name=name, ok=False, error=f"{type(exc).__name__}: {exc}")


def normalize_history_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize AkShare HK history frames from different providers."""
    if df.empty:
        return df
    renamed = df.rename(
        columns={
            "date": "日期",
            "open": "开盘",
            "close": "收盘",
            "high": "最高",
            "low": "最低",
            "volume": "成交量",
            "amount": "成交额",
        }
    ).copy()
    if "日期" in renamed.columns:
        renamed["日期"] = pd.to_datetime(renamed["日期"], errors="coerce").dt.strftime("%Y-%m-%d")
    if "涨跌幅" not in renamed.columns and "收盘" in renamed.columns:
        close = pd.to_numeric(renamed["收盘"], errors="coerce")
        renamed["涨跌幅"] = (close.pct_change() * 100).round(2)
    return renamed


def latest_history_date(df: pd.DataFrame) -> Optional[date]:
    """Return the latest date available in a normalized history frame."""
    if df.empty or "日期" not in df.columns:
        return None
    dates = pd.to_datetime(df["日期"], errors="coerce").dropna()
    if dates.empty:
        return None
    return dates.max().date()


def fetch_history(ak: Any, symbol: str, start: date, end: date, required_date: Optional[date] = None) -> FetchResult:
    """Fetch daily history from multiple providers and choose the freshest usable frame."""
    results = []
    eastmoney = safe_fetch(
        "history:eastmoney",
        ak.stock_hk_hist,
        symbol=symbol,
        period="daily",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="",
    )
    sina = safe_fetch("history:sina", ak.stock_hk_daily, symbol=symbol, adjust="")

    for result in [eastmoney, sina]:
        if not result.ok or result.data.empty:
            results.append(result)
            continue
        hist = normalize_history_frame(result.data)
        if "日期" in hist.columns:
            dates = pd.to_datetime(hist["日期"], errors="coerce")
            hist = hist[(dates.dt.date >= start) & (dates.dt.date <= end)]
        result.data = hist
        results.append(result)

    candidates = [result for result in results if result.ok and not result.data.empty]
    if candidates:
        if required_date:
            exact = [
                result
                for result in candidates
                if latest_history_date(result.data) == required_date
                or required_date in set(pd.to_datetime(result.data["日期"], errors="coerce").dt.date.dropna())
            ]
            if exact:
                chosen = max(exact, key=lambda item: latest_history_date(item.data) or date.min)
                chosen.data = chosen.data[
                    pd.to_datetime(chosen.data["日期"], errors="coerce").dt.date <= required_date
                ]
                return chosen
        return max(candidates, key=lambda item: latest_history_date(item.data) or date.min)

    errors = []
    for result in results:
        if not result.ok:
            errors.append(f"{result.name}: {result.error}")
    return FetchResult(name="history", ok=False, error="; ".join(errors) or "No history data returned")


def pct_change(values: pd.Series, periods: int) -> Optional[float]:
    """Return percentage change across a period if enough data exists."""
    series = pd.to_numeric(values, errors="coerce").dropna()
    if len(series) <= periods:
        return None
    base = series.iloc[-periods - 1]
    if base == 0:
        return None
    return round((series.iloc[-1] / base - 1) * 100, 2)


def latest_pct_change(values: pd.Series) -> Optional[float]:
    """Return percentage change from first to last numeric item."""
    series = pd.to_numeric(values, errors="coerce").dropna()
    if len(series) < 2:
        return None
    base = series.iloc[0]
    if base == 0:
        return None
    return round((series.iloc[-1] / base - 1) * 100, 2)


def series_percentile(series: pd.Series, value: float) -> Optional[float]:
    """Return percentile rank of a value within a numeric series."""
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    return round(float((clean <= value).sum() / len(clean) * 100), 2)


def latest_number(df: pd.DataFrame, column: str) -> Optional[float]:
    """Extract the latest numeric value from a column."""
    if column not in df.columns or df.empty:
        return None
    series = pd.to_numeric(df[column], errors="coerce").dropna()
    if series.empty:
        return None
    return float(series.iloc[-1])


def safe_round(value: Any, digits: int = 2) -> Optional[float]:
    """Round a numeric value if it is finite."""
    number = pd.to_numeric(pd.Series([value]), errors="coerce").dropna()
    if number.empty:
        return None
    return round(float(number.iloc[0]), digits)


def score_label(score: Optional[int]) -> str:
    """Convert a technical score into a readable state label."""
    if score is None:
        return "数据不足"
    if score >= 85:
        return "强势"
    if score >= 70:
        return "偏强"
    if score >= 50:
        return "中性"
    if score >= 35:
        return "偏弱"
    return "弱势"


def rsi_state(value: Optional[float]) -> str:
    """Describe a 14-period RSI value."""
    if value is None:
        return "N/A"
    if value >= 70:
        return "偏热"
    if value <= 30:
        return "偏冷"
    if value >= 55:
        return "偏强"
    if value <= 45:
        return "偏弱"
    return "中性"


def technical_snapshot(hist: pd.DataFrame) -> Dict[str, Any]:
    """Compute a simple technical dashboard from daily OHLCV data."""
    if hist.empty or "收盘" not in hist.columns:
        return {}

    close = pd.to_numeric(hist.get("收盘", pd.Series(dtype=float)), errors="coerce")
    high = pd.to_numeric(hist.get("最高", pd.Series(dtype=float)), errors="coerce")
    low = pd.to_numeric(hist.get("最低", pd.Series(dtype=float)), errors="coerce")
    volume = pd.to_numeric(hist.get("成交量", pd.Series(dtype=float)), errors="coerce")
    clean_close = close.dropna()
    if len(clean_close) < 20:
        return {"score": None, "state": "数据不足", "notes": ["日线数据少于20条，暂不生成技术面评分。"]}

    latest_close = float(clean_close.iloc[-1])
    ma_5 = clean_close.rolling(5).mean().iloc[-1] if len(clean_close) >= 5 else None
    ma_10 = clean_close.rolling(10).mean().iloc[-1] if len(clean_close) >= 10 else None
    ma_20 = clean_close.rolling(20).mean().iloc[-1] if len(clean_close) >= 20 else None
    ma_60 = clean_close.rolling(60).mean().iloc[-1] if len(clean_close) >= 60 else None

    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    dif = ema_12 - ema_26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd_hist = (dif - dea) * 2

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi_14 = 100 - (100 / (1 + rs))

    support_20d = low.tail(20).min() if not low.tail(20).dropna().empty else None
    resistance_20d = high.tail(20).max() if not high.tail(20).dropna().empty else None
    volume_avg_20d = volume.tail(20).mean() if len(volume.dropna()) >= 20 else None
    latest_volume = volume.dropna().iloc[-1] if not volume.dropna().empty else None
    volume_ratio = (
        (float(latest_volume) / float(volume_avg_20d) - 1) * 100
        if latest_volume is not None and volume_avg_20d is not None and volume_avg_20d != 0
        else None
    )
    volatility_20d = clean_close.pct_change().tail(20).std() * (252 ** 0.5) * 100 if len(clean_close) >= 21 else None

    trend_score = 0
    trend_notes: List[str] = []
    if ma_5 is not None and ma_20 is not None:
        if latest_close >= ma_5 >= ma_20:
            trend_score += 30
            trend_notes.append("收盘价站上MA5且MA5高于MA20。")
        elif latest_close >= ma_20:
            trend_score += 22
            trend_notes.append("收盘价仍在MA20上方。")
        elif latest_close >= ma_5:
            trend_score += 14
            trend_notes.append("收盘价站上MA5，但仍需观察MA20压力。")
        else:
            trend_score += 6
            trend_notes.append("收盘价低于MA5，短线趋势偏弱。")
    if ma_60 is not None:
        trend_score += 10 if latest_close >= ma_60 else 2

    momentum_score = 0
    rsi_value = safe_round(rsi_14.iloc[-1]) if not rsi_14.dropna().empty else None
    macd_value = safe_round(macd_hist.iloc[-1]) if not macd_hist.dropna().empty else None
    macd_prev = safe_round(macd_hist.dropna().iloc[-2]) if len(macd_hist.dropna()) >= 2 else None
    dif_value = safe_round(dif.iloc[-1]) if not dif.dropna().empty else None
    dea_value = safe_round(dea.iloc[-1]) if not dea.dropna().empty else None
    if macd_value is not None and dif_value is not None and dea_value is not None:
        if dif_value > dea_value and macd_value > 0:
            momentum_score += 25
        elif dif_value > dea_value:
            momentum_score += 18
        elif macd_prev is not None and macd_value > macd_prev:
            momentum_score += 12
        else:
            momentum_score += 5
    if rsi_value is not None:
        if 45 <= rsi_value <= 65:
            momentum_score += 15
        elif 35 <= rsi_value < 45 or 65 < rsi_value <= 75:
            momentum_score += 10
        else:
            momentum_score += 4

    volume_score = 0
    if volume_ratio is not None:
        if 10 <= volume_ratio <= 80 and latest_close >= (ma_20 if ma_20 is not None else latest_close):
            volume_score = 15
        elif -30 <= volume_ratio < 10:
            volume_score = 10
        elif volume_ratio > 80:
            volume_score = 8
        else:
            volume_score = 5

    risk_score = 5
    if volatility_20d is not None:
        if volatility_20d <= 35:
            risk_score = 10
        elif volatility_20d <= 60:
            risk_score = 7
        else:
            risk_score = 3

    total_score = int(max(0, min(100, round(trend_score + momentum_score + volume_score + risk_score))))
    distance_to_support = (
        (latest_close / float(support_20d) - 1) * 100 if support_20d is not None and support_20d != 0 else None
    )
    distance_to_resistance = (
        (float(resistance_20d) / latest_close - 1) * 100 if resistance_20d is not None and latest_close != 0 else None
    )

    return {
        "score": total_score,
        "state": score_label(total_score),
        "trend_score": int(trend_score),
        "momentum_score": int(momentum_score),
        "volume_score": int(volume_score),
        "risk_score": int(risk_score),
        "ma": {
            "ma_5": safe_round(ma_5),
            "ma_10": safe_round(ma_10),
            "ma_20": safe_round(ma_20),
            "ma_60": safe_round(ma_60),
        },
        "price_vs_ma20_pct": safe_round((latest_close / ma_20 - 1) * 100 if ma_20 else None),
        "price_vs_ma60_pct": safe_round((latest_close / ma_60 - 1) * 100 if ma_60 else None),
        "macd": {
            "dif": dif_value,
            "dea": dea_value,
            "histogram": macd_value,
            "histogram_change": safe_round(macd_value - macd_prev) if macd_value is not None and macd_prev is not None else None,
        },
        "rsi_14": rsi_value,
        "rsi_state": rsi_state(rsi_value),
        "volume_vs_20d_avg_pct": safe_round(volume_ratio),
        "support_20d": safe_round(support_20d),
        "resistance_20d": safe_round(resistance_20d),
        "distance_to_support_pct": safe_round(distance_to_support),
        "distance_to_resistance_pct": safe_round(distance_to_resistance),
        "volatility_20d_pct": safe_round(volatility_20d),
        "notes": trend_notes,
    }


def fmt_value(value: Any, suffix: str = "") -> str:
    """Format display values consistently."""
    if value is None:
        return "N/A"
    if not isinstance(value, str) and pd.isna(value):
        return "N/A"
    if isinstance(value, numbers.Number):
        number = float(value)
        if number.is_integer():
            return f"{int(number):,}{suffix}" if abs(number) >= 1000 else f"{int(number)}{suffix}"
        if abs(value) >= 100:
            return f"{number:,.2f}{suffix}"
        return f"{number:.2f}{suffix}"
    return f"{value}{suffix}"


def clean_text(value: Any) -> str:
    """Remove lightweight HTML fragments and normalize whitespace."""
    text = html.unescape(str(value or ""))
    text = re.sub(r"<br\\s*/?>", " / ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def frame_records(df: pd.DataFrame, columns: List[str], limit: int) -> List[Dict[str, Any]]:
    """Return selected DataFrame rows as clean dictionaries."""
    if df.empty:
        return []
    rows: List[Dict[str, Any]] = []
    for _, row in df.head(limit).iterrows():
        item = {}
        for column in columns:
            item[column] = clean_text(row.get(column, ""))
        rows.append(item)
    return rows


def financial_highlights(profit_df: pd.DataFrame) -> Dict[str, Any]:
    """Extract common profit statement rows from AkShare HK financial data."""
    if profit_df.empty or "STD_ITEM_NAME" not in profit_df.columns:
        return {}

    report_date = None
    if "REPORT_DATE" in profit_df.columns:
        report_date = str(profit_df["REPORT_DATE"].iloc[0])[:10]

    wanted = {
        "营业额": "revenue",
        "毛利": "gross_profit",
        "经营溢利": "operating_profit",
        "股东应占溢利": "shareholder_profit",
        "每股基本盈利": "basic_eps",
        "每股股息": "dividend_per_share",
    }
    output: Dict[str, Any] = {"report_date": report_date}
    for cn_name, key in wanted.items():
        rows = profit_df[profit_df["STD_ITEM_NAME"].astype(str) == cn_name]
        if rows.empty or "AMOUNT" not in rows.columns:
            continue
        output[key] = rows["AMOUNT"].iloc[0]
    return output


def financial_trend(profit_df: pd.DataFrame) -> Dict[str, Any]:
    """Extract annual revenue/profit trend from HK profit statement rows."""
    if profit_df.empty or "REPORT_DATE" not in profit_df.columns or "STD_ITEM_NAME" not in profit_df.columns:
        return {}

    wanted = {
        "营业额": "revenue",
        "毛利": "gross_profit",
        "经营溢利": "operating_profit",
        "股东应占溢利": "shareholder_profit",
    }
    frames = []
    for cn_name, key in wanted.items():
        rows = profit_df[profit_df["STD_ITEM_NAME"].astype(str) == cn_name].copy()
        if rows.empty or "AMOUNT" not in rows.columns:
            continue
        rows["report_date"] = pd.to_datetime(rows["REPORT_DATE"], errors="coerce").dt.strftime("%Y-%m-%d")
        rows[key] = pd.to_numeric(rows["AMOUNT"], errors="coerce")
        frames.append(rows[["report_date", key]])
    if not frames:
        return {}

    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="report_date", how="outer")
    merged = merged.dropna(subset=["report_date"]).sort_values("report_date", ascending=False)
    if merged.empty:
        return {}

    latest = merged.iloc[0].to_dict()
    previous = merged.iloc[1].to_dict() if len(merged) > 1 else {}
    output: Dict[str, Any] = {
        "latest_report_date": latest.get("report_date"),
        "previous_report_date": previous.get("report_date"),
        "latest": latest,
        "previous": previous,
    }

    for key in wanted.values():
        latest_value = latest.get(key)
        previous_value = previous.get(key)
        if pd.notna(latest_value) and pd.notna(previous_value) and previous_value:
            output[f"{key}_yoy_pct"] = round((latest_value / previous_value - 1) * 100, 2)

    revenue = latest.get("revenue")
    if revenue and pd.notna(revenue):
        for key, label in [("gross_profit", "gross_margin_pct"), ("operating_profit", "operating_margin_pct")]:
            value = latest.get(key)
            if pd.notna(value):
                output[label] = round(value / revenue * 100, 2)
    return output


def selected_record(df: pd.DataFrame, columns: List[str]) -> Dict[str, Any]:
    """Return the first row with selected columns as plain values."""
    if df.empty:
        return {}
    row = df.iloc[0].to_dict()
    return {column: row.get(column) for column in columns if column in row}


def valuation_snapshot(ak: Any, symbol: str) -> Dict[str, FetchResult]:
    """Fetch a compact set of valuation series."""
    indicators = ["总市值", "市盈率(TTM)", "市净率"]
    return {
        indicator: safe_fetch(
            f"valuation:{indicator}",
            ak.stock_hk_valuation_baidu,
            symbol=symbol,
            indicator=indicator,
            period="近一年",
        )
        for indicator in indicators
    }


def fetch_realtime_quote(ak: Any, symbol: str) -> FetchResult:
    """Fetch delayed real-time quote snapshot from Sina HK spot data."""
    result = safe_fetch("realtime:sina", ak.stock_hk_spot)
    if not result.ok:
        return result
    df = result.data
    if df.empty or "代码" not in df.columns:
        return FetchResult(name=result.name, ok=False, error="No quote table returned")
    matched = df[df["代码"].astype(str).str.zfill(5) == symbol]
    if matched.empty:
        return FetchResult(name=result.name, ok=False, error=f"No realtime row found for {symbol}")
    row = matched.iloc[0].to_dict()
    return FetchResult(
        name=result.name,
        ok=True,
        data=selected_record(
            pd.DataFrame([row]),
            ["日期时间", "代码", "中文名称", "英文名称", "最新价", "涨跌额", "涨跌幅", "昨收", "今开", "最高", "最低", "成交量", "成交额", "买一", "卖一"],
        ),
    )


def fetch_southbound_holding(ak: Any, symbol: str, max_lookback_days: int = 7) -> FetchResult:
    """Fetch latest available stock-specific southbound holding, usually T+1."""
    errors = []
    for offset in range(max_lookback_days + 1):
        day = date.today() - timedelta(days=offset)
        date_key = day.strftime("%Y%m%d")
        result = safe_fetch(
            f"southbound:holding:{date_key}",
            ak.stock_hsgt_stock_statistics_em,
            symbol="南向持股",
            start_date=date_key,
            end_date=date_key,
        )
        if not result.ok:
            errors.append(f"{date_key}: {result.error}")
            continue
        df = result.data
        if df is None or df.empty or "股票代码" not in df.columns:
            errors.append(f"{date_key}: empty")
            continue
        matched = df[df["股票代码"].astype(str).str.zfill(5) == symbol]
        if matched.empty:
            errors.append(f"{date_key}: no row")
            continue
        return FetchResult(name="southbound:holding", ok=True, data=matched.iloc[0].to_dict())
    return FetchResult(name="southbound:holding", ok=False, error="; ".join(errors[-3:]) or "No holding data")


def fetch_southbound_holding_trend(ak: Any, symbol: str, days: int = 20) -> FetchResult:
    """Fetch recent southbound holding history for one HK stock."""
    end = date.today()
    start = end - timedelta(days=max(days * 2, days + 10))
    result = safe_fetch(
        "southbound:holding-trend",
        ak.stock_hsgt_stock_statistics_em,
        symbol="南向持股",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
    )
    if not result.ok:
        return result
    df = result.data
    if df is None or df.empty or "股票代码" not in df.columns:
        return FetchResult(name="southbound:holding-trend", ok=False, error="No holding trend data")
    matched = df[df["股票代码"].astype(str).str.zfill(5) == symbol].copy()
    if matched.empty:
        return FetchResult(name="southbound:holding-trend", ok=False, error=f"No holding trend row found for {symbol}")
    date_col = "持股日期" if "持股日期" in matched.columns else matched.columns[0]
    matched[date_col] = pd.to_datetime(matched[date_col], errors="coerce")
    matched = matched.dropna(subset=[date_col]).sort_values(date_col).tail(days)
    if matched.empty:
        return FetchResult(name="southbound:holding-trend", ok=False, error="Holding trend rows have no dates")
    quantity = pd.to_numeric(matched.get("持股数量", pd.Series(dtype=float)), errors="coerce")
    market_value = pd.to_numeric(matched.get("持股市值", pd.Series(dtype=float)), errors="coerce")
    ratio = pd.to_numeric(matched.get("持股数量占发行股百分比", pd.Series(dtype=float)), errors="coerce")
    latest = matched.iloc[-1].to_dict()
    first = matched.iloc[0].to_dict()
    return FetchResult(
        name="southbound:holding-trend",
        ok=True,
        data={
            "days": int(days),
            "start_date": str(first.get(date_col, ""))[:10],
            "latest_date": str(latest.get(date_col, ""))[:10],
            "latest": latest,
            "holding_quantity_change_pct": latest_pct_change(quantity),
            "holding_market_value_change_pct": latest_pct_change(market_value),
            "holding_ratio_change_pct_point": (
                round(float(ratio.dropna().iloc[-1] - ratio.dropna().iloc[0]), 4)
                if len(ratio.dropna()) >= 2
                else None
            ),
            "tail": matched.tail(5).to_dict(orient="records"),
        },
    )


def fetch_index_context(ak: Any, stock_return_5d: Optional[float], stock_return_20d: Optional[float]) -> FetchResult:
    """Fetch Hong Kong index performance and compare stock returns with benchmarks."""
    indexes = {"HSI": "恒生指数", "HSCEI": "恒生中国企业指数", "HSTECH": "恒生科技指数"}
    items = []
    errors = []
    for code, name in indexes.items():
        result = safe_fetch(f"index:{code}", ak.stock_hk_index_daily_sina, symbol=code)
        if not result.ok:
            errors.append({"section": result.name, "error": result.error})
            continue
        df = result.data.copy()
        if df.empty or "close" not in df.columns:
            errors.append({"section": result.name, "error": "No index close data"})
            continue
        close = pd.to_numeric(df["close"], errors="coerce")
        latest = df.iloc[-1].to_dict()
        item = {
            "code": code,
            "name": name,
            "latest_date": str(latest.get("date", "")),
            "close": latest.get("close"),
            "return_5d_pct": pct_change(close, 5),
            "return_20d_pct": pct_change(close, 20),
        }
        if stock_return_5d is not None and item["return_5d_pct"] is not None:
            item["stock_excess_5d_pct"] = round(stock_return_5d - item["return_5d_pct"], 2)
        if stock_return_20d is not None and item["return_20d_pct"] is not None:
            item["stock_excess_20d_pct"] = round(stock_return_20d - item["return_20d_pct"], 2)
        items.append(item)
    if not items:
        return FetchResult(name="index:context", ok=False, error="; ".join(item["error"] for item in errors) or "No index data")
    data: Dict[str, Any] = {"items": items}
    if errors:
        data["errors"] = errors
    return FetchResult(name="index:context", ok=True, data=data)


def fetch_short_selling(symbol: str, turnover: Optional[Any] = None) -> FetchResult:
    """Fetch current HKEX short selling turnover text report for one stock."""
    url = "https://www.hkex.com.hk/eng/stat/smstat/ssturnover/ncms/MSHTMAIN.HTM"
    try:
        response = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        text = response.text
        report_title = ""
        trade_date = ""
        for line in text.splitlines():
            clean = re.sub(r"\s+", " ", clean_text(line)).strip()
            if not report_title and "Short Selling Turnover" in clean and "Total Value" not in clean:
                report_title = clean
            if "TRADING DATE" in clean:
                trade_date = clean.split("TRADING DATE", 1)[-1].replace(":", "").strip()
        target_code = str(int(symbol))
        for line in text.splitlines():
            match = re.match(r"^\s*(\d{1,5})\s+(.+?)\s+([\d,]+)\s+([\d,]+)\s*$", clean_text(line))
            if not match or match.group(1) != target_code:
                continue
            short_shares = int(match.group(3).replace(",", ""))
            short_turnover = int(match.group(4).replace(",", ""))
            total_turnover = pd.to_numeric(pd.Series([turnover]), errors="coerce").dropna()
            ratio = (
                round(float(short_turnover / total_turnover.iloc[0] * 100), 2)
                if not total_turnover.empty and total_turnover.iloc[0] != 0
                else None
            )
            return FetchResult(
                name="short-selling:hkex",
                ok=True,
                data={
                    "source": url,
                    "report_title": report_title,
                    "trade_date": trade_date,
                    "code": symbol,
                    "name": match.group(2).strip(),
                    "short_shares": short_shares,
                    "short_turnover": short_turnover,
                    "short_turnover_ratio_pct": ratio,
                },
            )
        return FetchResult(name="short-selling:hkex", ok=False, error=f"No short selling row found for {symbol}")
    except Exception as exc:  # noqa: BLE001 - report upstream failures.
        return FetchResult(name="short-selling:hkex", ok=False, error=f"{type(exc).__name__}: {exc}")


def parse_jsonp(text: str) -> Dict[str, Any]:
    """Parse HKEX JSONP responses."""
    match = re.search(r"^[^(]*\((.*)\);?\s*$", text.strip(), flags=re.DOTALL)
    if not match:
        raise ValueError("Response is not JSONP")
    return json.loads(match.group(1))


def fetch_hkex_stock_id(symbol: str) -> FetchResult:
    """Resolve a HKEXnews stockId for a Hong Kong stock code."""
    url = "https://www1.hkexnews.hk/search/prefix.do"
    params = {"callback": "callback", "lang": "EN", "type": "A", "name": symbol, "market": "SEHK"}
    try:
        response = requests.get(
            url,
            params=params,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en",
            },
        )
        response.raise_for_status()
        data = parse_jsonp(response.text)
        for item in data.get("stockInfo", []):
            if str(item.get("code", "")).zfill(5) == symbol:
                return FetchResult(name="hkex:stock-id", ok=True, data=item)
        return FetchResult(name="hkex:stock-id", ok=False, error=f"No HKEX stockId found for {symbol}")
    except Exception as exc:  # noqa: BLE001 - report upstream failures.
        return FetchResult(name="hkex:stock-id", ok=False, error=f"{type(exc).__name__}: {exc}")


def fetch_hkex_announcements(symbol: str, days: int, limit: int) -> FetchResult:
    """Fetch latest HKEXnews announcements for one stock."""
    stock_id = fetch_hkex_stock_id(symbol)
    if not stock_id.ok:
        return FetchResult(name="hkex:announcements", ok=False, error=stock_id.error)

    end = date.today()
    start = end - timedelta(days=days)
    params = {
        "sortDir": "0",
        "sortByOptions": "DateTime",
        "category": "0",
        "market": "SEHK",
        "stockId": str(stock_id.data["stockId"]),
        "documentType": "-1",
        "fromDate": start.strftime("%Y%m%d"),
        "toDate": end.strftime("%Y%m%d"),
        "title": "",
        "searchType": "0",
        "t1code": "-2",
        "t2Gcode": "-2",
        "t2code": "-2",
        "rowRange": str(limit),
        "lang": "E",
    }
    try:
        response = requests.get(
            "https://www1.hkexnews.hk/search/titleSearchServlet.do",
            params=params,
            timeout=25,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en",
                "Accept": "application/json,text/javascript,*/*;q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        response.raise_for_status()
        data = response.json()
        raw_result = data.get("result")
        if not raw_result or raw_result == "null":
            rows: List[Dict[str, Any]] = []
        else:
            rows = json.loads(raw_result)
        announcements = []
        for row in rows[:limit]:
            link = clean_text(row.get("FILE_LINK"))
            if link.startswith("/"):
                link = f"https://www1.hkexnews.hk{link}"
            announcements.append(
                {
                    "date_time": clean_text(row.get("DATE_TIME")),
                    "stock_code": clean_text(row.get("STOCK_CODE")),
                    "stock_name": clean_text(row.get("STOCK_NAME")),
                    "title": clean_text(row.get("TITLE")),
                    "category": clean_text(row.get("LONG_TEXT") or row.get("SHORT_TEXT")),
                    "file_type": clean_text(row.get("FILE_TYPE")),
                    "file_info": clean_text(row.get("FILE_INFO")),
                    "link": link,
                }
            )
        return FetchResult(
            name="hkex:announcements",
            ok=True,
            data={
                "stock_id": stock_id.data,
                "days": days,
                "record_count": int(data.get("recordCnt", len(announcements)) or 0),
                "items": announcements,
            },
        )
    except Exception as exc:  # noqa: BLE001 - report upstream failures.
        return FetchResult(name="hkex:announcements", ok=False, error=f"{type(exc).__name__}: {exc}")


def summarize_announcements(announcements: Dict[str, Any]) -> Dict[str, Any]:
    """Create structured corporate-action and risk summaries from HKEX announcement titles."""
    items = announcements.get("items", []) if isinstance(announcements, dict) else []
    category_keywords = {
        "buyback": ["buyback", "repurchase"],
        "monthly_return": ["monthly return"],
        "financial_results": ["results", "financial", "annual report", "interim report"],
        "general_meeting": ["agm", "annual general meeting", "notice of general meeting"],
        "director_change": ["director", "appointment", "resignation"],
        "financing_or_placing": ["placing", "subscription", "issue shares", "convertible"],
        "dividend": ["dividend", "distribution"],
    }
    risk_keywords = {
        "suspension": ["suspension", "trading halt"],
        "profit_warning": ["profit warning", "loss warning"],
        "litigation_or_investigation": ["litigation", "legal proceedings", "investigation"],
        "regulatory": ["disciplinary", "sanction", "regulatory"],
        "auditor_or_results_delay": ["auditor", "delay in publication", "inside information"],
    }
    categories = {name: [] for name in category_keywords}
    risks = {name: [] for name in risk_keywords}
    for item in items:
        text = f"{item.get('title', '')} {item.get('category', '')}".lower()
        compact = {
            "date_time": item.get("date_time"),
            "title": item.get("title"),
            "category": item.get("category"),
            "link": item.get("link"),
        }
        for name, keywords in category_keywords.items():
            if any(keyword in text for keyword in keywords):
                categories[name].append(compact)
        for name, keywords in risk_keywords.items():
            if any(keyword in text for keyword in keywords):
                risks[name].append(compact)
    return {
        "category_counts": {name: len(rows) for name, rows in categories.items()},
        "risk_counts": {name: len(rows) for name, rows in risks.items()},
        "buybacks": categories["buyback"][:10],
        "financing_or_placing": categories["financing_or_placing"][:10],
        "risk_hits": {name: rows[:10] for name, rows in risks.items() if rows},
    }


def fetch_news(ak: Any, symbol: str, limit: int) -> FetchResult:
    """Fetch recent stock news from Eastmoney via AkShare."""
    result = safe_fetch("news:eastmoney", ak.stock_news_em, symbol=symbol)
    if not result.ok:
        return result
    rows = frame_records(result.data, ["发布时间", "文章来源", "新闻标题", "新闻内容", "新闻链接"], limit)
    return FetchResult(name=result.name, ok=True, data=rows)


def fetch_dividends(ak: Any, symbol: str, limit: int = 5) -> FetchResult:
    """Fetch recent dividend and payout records."""
    result = safe_fetch("dividends:eastmoney", ak.stock_hk_dividend_payout_em, symbol=symbol)
    if not result.ok:
        return result
    rows = frame_records(result.data, ["最新公告日期", "财政年度", "分红方案", "分配类型", "除净日", "截至过户日", "发放日"], limit)
    return FetchResult(name=result.name, ok=True, data=rows)


def fetch_southbound(ak: Any) -> FetchResult:
    """Fetch market-level southbound Stock Connect data."""
    summary = safe_fetch("southbound:summary", ak.stock_hsgt_fund_flow_summary_em)
    hist_sh = safe_fetch("southbound:hist:港股通沪", ak.stock_hsgt_hist_em, symbol="港股通沪")
    hist_sz = safe_fetch("southbound:hist:港股通深", ak.stock_hsgt_hist_em, symbol="港股通深")

    if not any(item.ok for item in [summary, hist_sh, hist_sz]):
        return FetchResult(
            name="southbound",
            ok=False,
            error="; ".join(item.error or "" for item in [summary, hist_sh, hist_sz] if item.error),
        )

    data: Dict[str, Any] = {}
    errors = []
    if summary.ok:
        df = summary.data.copy()
        south = df[df.get("资金方向", pd.Series(dtype=str)).astype(str) == "南向"] if "资金方向" in df.columns else df
        data["summary"] = south.to_dict(orient="records")
    else:
        errors.append({"section": summary.name, "error": summary.error})

    history_items = []
    for label, result in [("港股通沪", hist_sh), ("港股通深", hist_sz)]:
        if result.ok and not result.data.empty:
            tail = result.data.tail(5).copy()
            history_items.append({"channel": label, "latest": tail.iloc[-1].to_dict(), "tail": tail.to_dict(orient="records")})
        elif not result.ok:
            errors.append({"section": result.name, "error": result.error})
    data["history"] = history_items
    if errors:
        data["errors"] = errors
    return FetchResult(name="southbound", ok=True, data=data)


def build_payload(
    symbol: str,
    lookback_days: int,
    required_date: Optional[date] = None,
    news_limit: int = 5,
    announcement_days: int = 31,
    announcement_limit: int = 5,
    dividend_limit: int = 5,
    southbound_trend_days: int = 20,
    include_short_selling: bool = True,
    include_index_context: bool = True,
) -> Dict[str, Any]:
    """Fetch and compute the research payload."""
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("AkShare is not installed. Install with: python3 -m pip install akshare") from exc

    end = date.today()
    start = end - timedelta(days=lookback_days)

    history_result = fetch_history(ak, symbol, start, end, required_date=required_date)
    profile_result = safe_fetch("profile", ak.stock_hk_company_profile_em, symbol=symbol)
    profit_result = safe_fetch(
        "financial:profit",
        ak.stock_financial_hk_report_em,
        stock=symbol,
        symbol="利润表",
        indicator="年度",
    )
    valuations = valuation_snapshot(ak, symbol)
    realtime_result = fetch_realtime_quote(ak, symbol)
    indicator_result = safe_fetch("financial:latest-indicators", ak.stock_hk_financial_indicator_em, symbol=symbol)
    security_result = safe_fetch("security:profile", ak.stock_hk_security_profile_em, symbol=symbol)
    dividend_result = fetch_dividends(ak, symbol, dividend_limit)
    news_result = fetch_news(ak, symbol, news_limit)
    announcements_result = fetch_hkex_announcements(symbol, announcement_days, announcement_limit)
    southbound_result = fetch_southbound(ak)
    southbound_holding_result = fetch_southbound_holding(ak, symbol)
    southbound_trend_result = fetch_southbound_holding_trend(ak, symbol, southbound_trend_days)

    payload: Dict[str, Any] = {
        "symbol": symbol,
        "generated_on": end.isoformat(),
        "lookback_days": lookback_days,
        "sources": {
            "history": "AkShare stock_hk_hist / Eastmoney, fallback stock_hk_daily / Sina",
            "realtime": "AkShare stock_hk_spot / Sina HK spot quote, may be delayed",
            "profile": "AkShare stock_hk_company_profile_em / Eastmoney HK F10",
            "valuation": "AkShare stock_hk_valuation_baidu / Baidu stock data",
            "financials": "AkShare stock_financial_hk_report_em / Eastmoney HK F10",
            "latest_indicators": "AkShare stock_hk_financial_indicator_em / Eastmoney HK F10",
            "security_profile": "AkShare stock_hk_security_profile_em / Eastmoney HK F10",
            "dividends": "AkShare stock_hk_dividend_payout_em / Eastmoney HK F10",
            "news": "AkShare stock_news_em / Eastmoney stock news search",
            "announcements": "HKEXnews titleSearchServlet.do official listed company announcements",
            "southbound": "AkShare stock_hsgt_fund_flow_summary_em and stock_hsgt_hist_em / Eastmoney HSGT",
            "southbound_holding": "AkShare stock_hsgt_stock_statistics_em / Eastmoney southbound holding, usually T+1",
            "southbound_holding_trend": "AkShare stock_hsgt_stock_statistics_em / Eastmoney recent southbound holding history",
            "index_context": "AkShare stock_hk_index_daily_sina / Sina HK index history",
            "short_selling": "HKEX Short Selling Turnover report, current main-board report",
        },
        "errors": [],
        "data_quality": {
            "required_price_date": required_date.isoformat() if required_date else None,
            "price_date_matched": None,
            "notes": [
                "All numeric fields are fetched from upstream public data endpoints; the script does not infer missing market prices.",
                "Public endpoints may be delayed, revised, throttled, or temporarily unavailable.",
            ],
        },
    }

    if history_result.ok:
        hist = history_result.data.copy()
        close = pd.to_numeric(hist.get("收盘", pd.Series(dtype=float)), errors="coerce")
        volume = pd.to_numeric(hist.get("成交量", pd.Series(dtype=float)), errors="coerce")
        latest = hist.iloc[-1].to_dict() if not hist.empty else {}
        turnover = pd.to_numeric(hist.get("成交额", pd.Series(dtype=float)), errors="coerce")
        high = pd.to_numeric(hist.get("最高", pd.Series(dtype=float)), errors="coerce")
        low = pd.to_numeric(hist.get("最低", pd.Series(dtype=float)), errors="coerce")
        payload["price"] = {
            "latest_date": str(latest.get("日期", "")),
            "open": latest.get("开盘"),
            "high": latest.get("最高"),
            "low": latest.get("最低"),
            "close": latest.get("收盘"),
            "change_pct": latest.get("涨跌幅"),
            "amplitude_pct": latest.get("振幅"),
            "turnover_rate_pct": latest.get("换手率"),
            "turnover": latest.get("成交额"),
            "volume": latest.get("成交量"),
            "return_5d_pct": pct_change(close, 5),
            "return_20d_pct": pct_change(close, 20),
            "return_60d_pct": pct_change(close, 60),
            "return_period_pct": pct_change(close, len(close.dropna()) - 1) if len(close.dropna()) > 1 else None,
            "ma_5": round(close.tail(5).mean(), 2) if len(close.dropna()) >= 5 else None,
            "ma_20": round(close.tail(20).mean(), 2) if len(close.dropna()) >= 20 else None,
            "ma_60": round(close.tail(60).mean(), 2) if len(close.dropna()) >= 60 else None,
            "period_high": round(float(high.max()), 2) if not high.dropna().empty else None,
            "period_low": round(float(low.min()), 2) if not low.dropna().empty else None,
            "avg_turnover_20d": round(float(turnover.tail(20).mean()), 2) if len(turnover.dropna()) >= 20 else None,
            "volatility_20d_pct": round(float(close.pct_change().tail(20).std() * (252 ** 0.5) * 100), 2)
            if len(close.dropna()) >= 21
            else None,
            "latest_volume_vs_20d_avg_pct": (
                round((volume.iloc[-1] / volume.tail(20).mean() - 1) * 100, 2)
                if len(volume.dropna()) >= 20 and volume.tail(20).mean() != 0
                else None
            ),
        }
        payload["technical"] = technical_snapshot(hist)
        latest_date = str(payload["price"]["latest_date"])
        payload["data_quality"]["price_date_matched"] = (
            latest_date == required_date.isoformat() if required_date else None
        )
        if required_date and latest_date != required_date.isoformat():
            payload["errors"].append(
                {
                    "section": "strict-date-check",
                    "error": f"Latest price date is {latest_date}, required {required_date.isoformat()}",
                }
            )
        payload["history_tail"] = hist.tail(5).to_dict(orient="records")
    else:
        payload["errors"].append({"section": history_result.name, "error": history_result.error})

    if include_index_context:
        index_result = fetch_index_context(
            ak,
            payload.get("price", {}).get("return_5d_pct"),
            payload.get("price", {}).get("return_20d_pct"),
        )
        if index_result.ok:
            payload["index_context"] = index_result.data
            for item in index_result.data.get("errors", []):
                payload["errors"].append(item)
        else:
            payload["errors"].append({"section": index_result.name, "error": index_result.error})

    if include_short_selling:
        short_result = fetch_short_selling(symbol, payload.get("price", {}).get("turnover"))
        if short_result.ok:
            payload["short_selling"] = short_result.data
        else:
            payload["errors"].append({"section": short_result.name, "error": short_result.error})

    if profile_result.ok and not profile_result.data.empty:
        row = profile_result.data.iloc[0].to_dict()
        payload["company"] = {
            "name": row.get("公司名称"),
            "english_name": row.get("英文名称"),
            "industry": row.get("所属行业"),
            "chairman": row.get("董事长"),
            "employees": row.get("员工人数"),
            "website": row.get("公司网址"),
            "introduction": row.get("公司介绍"),
        }
    else:
        payload["errors"].append({"section": profile_result.name, "error": profile_result.error})

    payload["valuation"] = {}
    for indicator, result in valuations.items():
        if result.ok:
            latest = latest_number(result.data, "value")
            latest_date = str(result.data["date"].iloc[-1]) if not result.data.empty and "date" in result.data.columns else ""
            first = latest_number(result.data.head(1), "value")
            change_pct = round((latest / first - 1) * 100, 2) if latest is not None and first not in (None, 0) else None
            percentile = series_percentile(result.data["value"], latest) if latest is not None and "value" in result.data.columns else None
            payload["valuation"][indicator] = {
                "date": latest_date,
                "value": latest,
                "one_year_change_pct": change_pct,
                "one_year_percentile_pct": percentile,
            }
        else:
            payload["errors"].append({"section": result.name, "error": result.error})

    if profit_result.ok:
        payload["financial_highlights"] = financial_highlights(profit_result.data)
        payload["financial_trend"] = financial_trend(profit_result.data)
    else:
        payload["errors"].append({"section": profit_result.name, "error": profit_result.error})

    if realtime_result.ok:
        payload["realtime_quote"] = realtime_result.data
    else:
        payload["errors"].append({"section": realtime_result.name, "error": realtime_result.error})

    if indicator_result.ok:
        payload["latest_indicators"] = selected_record(
            indicator_result.data,
            [
                "基本每股收益(元)",
                "每股净资产(元)",
                "每手股",
                "每股股息TTM(港元)",
                "派息比率(%)",
                "已发行股本(股)",
                "每股经营现金流(元)",
                "股息率TTM(%)",
                "总市值(港元)",
                "营业总收入",
                "销售净利率(%)",
                "净利润",
                "股东权益回报率(%)",
                "市盈率",
                "市净率",
                "总资产回报率(%)",
            ],
        )
    else:
        payload["errors"].append({"section": indicator_result.name, "error": indicator_result.error})

    if security_result.ok:
        payload["security_profile"] = selected_record(
            security_result.data,
            [
                "证券代码",
                "证券简称",
                "上市日期",
                "证券类型",
                "发行价",
                "发行量(股)",
                "每手股数",
                "每股面值",
                "交易所",
                "板块",
                "年结日",
                "ISIN（国际证券识别编码）",
                "是否沪港通标的",
                "是否深港通标的",
            ],
        )
    else:
        payload["errors"].append({"section": security_result.name, "error": security_result.error})

    if dividend_result.ok:
        payload["dividends"] = dividend_result.data
    else:
        payload["errors"].append({"section": dividend_result.name, "error": dividend_result.error})

    if news_result.ok:
        payload["news"] = news_result.data
    else:
        payload["errors"].append({"section": news_result.name, "error": news_result.error})

    if announcements_result.ok:
        payload["announcements"] = announcements_result.data
        payload["corporate_actions"] = summarize_announcements(announcements_result.data)
    else:
        payload["errors"].append({"section": announcements_result.name, "error": announcements_result.error})

    if southbound_result.ok:
        payload["southbound"] = southbound_result.data
        for item in southbound_result.data.get("errors", []):
            payload["errors"].append(item)
    else:
        payload["errors"].append({"section": southbound_result.name, "error": southbound_result.error})

    if southbound_holding_result.ok:
        payload["southbound_holding"] = southbound_holding_result.data
    else:
        payload["errors"].append({"section": southbound_holding_result.name, "error": southbound_holding_result.error})

    if southbound_trend_result.ok:
        payload["southbound_holding_trend"] = southbound_trend_result.data
    else:
        payload["errors"].append({"section": southbound_trend_result.name, "error": southbound_trend_result.error})

    return payload


def markdown_table(rows: Iterable[Dict[str, Any]], columns: List[str]) -> str:
    """Render a minimal Markdown table."""
    rows = list(rows)
    if not rows:
        return "N/A"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join([header, sep, *body])


def render_interpretation(payload: Dict[str, Any]) -> List[str]:
    """Create a compact rules-based interpretation from fetched metrics."""
    price = payload.get("price", {})
    valuation = payload.get("valuation", {})
    lines: List[str] = []

    return_20d = price.get("return_20d_pct")
    return_5d = price.get("return_5d_pct")
    volume_delta = price.get("latest_volume_vs_20d_avg_pct")
    close = price.get("close")
    ma_20 = price.get("ma_20")

    if return_20d is not None and return_5d is not None:
        if return_20d < 0 <= return_5d:
            lines.append("近20日仍为回撤状态，但5日表现转强，短线有修复迹象。")
        elif return_20d > 0 and return_5d > 0:
            lines.append("5日和20日收益同为正，价格趋势偏强，需继续观察量能是否配合。")
        elif return_20d < 0 and return_5d < 0:
            lines.append("5日和20日收益同为负，短线仍偏弱，先关注是否企稳。")
        else:
            lines.append("短线表现弱于近20日走势，可能处在获利回吐或震荡阶段。")

    if close is not None and ma_20 is not None:
        if close >= ma_20:
            lines.append("最新收盘价位于20日均价上方，技术面暂未跌破中短期均线。")
        else:
            lines.append("最新收盘价低于20日均价，技术面需要留意均线压力。")

    if volume_delta is not None:
        if volume_delta > 30:
            lines.append("成交量明显高于20日均量，说明当前波动有资金参与。")
        elif volume_delta < -30:
            lines.append("成交量明显低于20日均量，当前价格变化的确认度偏弱。")
        else:
            lines.append("成交量接近20日均量，暂未出现极端放量或缩量。")

    pe = valuation.get("市盈率(TTM)", {}).get("value") if valuation else None
    pb = valuation.get("市净率", {}).get("value") if valuation else None
    if pe is not None and pb is not None:
        lines.append(f"估值层面，TTM市盈率约{pe:.2f}倍，市净率约{pb:.2f}倍，适合继续和同业及自身历史区间对比。")

    technical = payload.get("technical", {})
    if technical.get("score") is not None:
        lines.append(
            f"技术面评分为{technical.get('score')}/100，状态为{technical.get('state')}；"
            "该评分仅基于日线趋势、MACD/RSI、量能和波动率。"
        )

    if not lines:
        lines.append("可用数据不足，建议先补充行情、估值或财报数据后再判断。")
    return lines


def first_item(items: Any) -> Dict[str, Any]:
    """Return the first item from a list-like value."""
    return items[0] if isinstance(items, list) and items else {}


def render_executive_brief(payload: Dict[str, Any]) -> List[str]:
    """Render a Feishu-friendly narrative summary before the detailed report."""
    symbol = payload.get("symbol", "N/A")
    company = payload.get("company", {})
    price = payload.get("price", {})
    realtime = payload.get("realtime_quote", {})
    technical = payload.get("technical", {})
    valuation = payload.get("valuation", {})
    financials = payload.get("financial_highlights", {})
    trend = payload.get("financial_trend", {})
    news_items = payload.get("news", []) if isinstance(payload.get("news", []), list) else []
    news = first_item(news_items)
    announcements = payload.get("announcements", {})
    announcement_items = announcements.get("items", []) if isinstance(announcements, dict) else []
    latest_announcement = first_item(announcement_items)
    corporate_actions = payload.get("corporate_actions", {})
    category_counts = corporate_actions.get("category_counts", {}) if isinstance(corporate_actions, dict) else {}
    risk_counts = corporate_actions.get("risk_counts", {}) if isinstance(corporate_actions, dict) else {}
    short_selling = payload.get("short_selling", {})
    index_context = payload.get("index_context", {})
    index_items = index_context.get("items", []) if isinstance(index_context, dict) else []
    holding = payload.get("southbound_holding", {})
    holding_trend = payload.get("southbound_holding_trend", {})
    southbound = payload.get("southbound", {})
    southbound_summary = southbound.get("summary", []) if isinstance(southbound, dict) else []
    southbound_history = southbound.get("history", []) if isinstance(southbound, dict) else []

    name = company.get("name") or realtime.get("中文名称") or "N/A"
    english_name = company.get("english_name") or realtime.get("英文名称") or "N/A"
    pe = valuation.get("市盈率(TTM)", {}).get("value") if valuation else None
    pb = valuation.get("市净率", {}).get("value") if valuation else None
    market_cap = valuation.get("总市值", {}).get("value") if valuation else None
    summary_lines = render_interpretation(payload)

    lines = [
        "",
        "## 核心解析",
        f"{symbol} 港股资讯已查到。",
        "",
        "### 核心快照",
        f"- 公司：{name} / {english_name}",
        f"- 代码：{symbol}.HK",
        f"- 行业：{company.get('industry', 'N/A')}",
        f"- 最新日线交易日：{price.get('latest_date', 'N/A')}",
        f"- 收盘价：{fmt_value(price.get('close'), ' HKD')}",
        f"- 当日涨跌幅：{fmt_value(price.get('change_pct'), '%')}",
    ]
    if realtime:
        lines.extend(
            [
                f"- 盘中快照：{realtime.get('日期时间', 'N/A')}",
                f"- 盘中现价：{fmt_value(realtime.get('最新价'), ' HKD')}",
                f"- 盘中涨跌幅：{fmt_value(realtime.get('涨跌幅'), '%')}",
                f"- 今日高/低：{fmt_value(realtime.get('最高'))} / {fmt_value(realtime.get('最低'))}",
                f"- 今日成交额：{fmt_value(realtime.get('成交额'), ' 港元')}",
            ]
        )

    lines.extend(
        [
            "",
            "### 走势与交易",
            f"- 5日/20日/60日涨跌幅：{fmt_value(price.get('return_5d_pct'), '%')} / {fmt_value(price.get('return_20d_pct'), '%')} / {fmt_value(price.get('return_60d_pct'), '%')}",
            f"- 当前收盘 {fmt_value(price.get('close'))}，20日均价 {fmt_value(price.get('ma_20'))}",
            f"- 最新成交量较20日均量：{fmt_value(price.get('latest_volume_vs_20d_avg_pct'), '%')}",
            f"- 20日年化波动率：{fmt_value(price.get('volatility_20d_pct'), '%')}",
        ]
    )
    if technical:
        lines.extend(
            [
                f"- 技术面评分：{fmt_value(technical.get('score'))}/100，状态：{technical.get('state', 'N/A')}",
                f"- MA5/10/20/60：{fmt_value(technical.get('ma', {}).get('ma_5'))} / {fmt_value(technical.get('ma', {}).get('ma_10'))} / {fmt_value(technical.get('ma', {}).get('ma_20'))} / {fmt_value(technical.get('ma', {}).get('ma_60'))}",
                f"- RSI14：{fmt_value(technical.get('rsi_14'))}，{technical.get('rsi_state', 'N/A')}",
            ]
        )
    if summary_lines:
        lines.append(f"- 结论：{summary_lines[0]}")

    if index_items:
        lines.extend(["", "### 相对指数表现"])
        for item in index_items:
            if item.get("code") in {"HSI", "HSTECH"}:
                lines.append(
                    f"- 相对{item.get('name', item.get('code'))}：5日超额 {fmt_value(item.get('stock_excess_5d_pct'), '%')}，"
                    f"20日超额 {fmt_value(item.get('stock_excess_20d_pct'), '%')}"
                )

    if short_selling:
        lines.extend(
            [
                "",
                "### 沽空情况",
                f"- HKEX 沽空报告：{short_selling.get('trade_date', 'N/A')}",
                f"- 沽空金额：{fmt_value(short_selling.get('short_turnover'), ' HKD')}",
                f"- 沽空成交占当日成交额：{fmt_value(short_selling.get('short_turnover_ratio_pct'), '%')}",
            ]
        )

    lines.extend(
        [
            "",
            "### 估值与财务",
            f"- 总市值：{fmt_value(market_cap)}",
            f"- TTM 市盈率/市净率：{fmt_value(pe)} / {fmt_value(pb)}",
            f"- 营业额：{fmt_value(financials.get('revenue'))}",
            f"- 股东应占溢利：{fmt_value(financials.get('shareholder_profit'))}",
            f"- 营收/股东应占溢利同比：{fmt_value(trend.get('revenue_yoy_pct'), '%')} / {fmt_value(trend.get('shareholder_profit_yoy_pct'), '%')}",
            f"- 毛利率/经营利润率：{fmt_value(trend.get('gross_margin_pct'), '%')} / {fmt_value(trend.get('operating_margin_pct'), '%')}",
        ]
    )

    lines.extend(["", "### 最新新闻"])
    if news_items:
        for index, item in enumerate(news_items[:3], start=1):
            content = clean_text(item.get("新闻内容", ""))
            brief = f"｜摘要：{content[:90]}..." if content else ""
            lines.append(
                f"{index}. {item.get('发布时间', 'N/A')}｜{item.get('文章来源', 'N/A')}｜"
                f"{item.get('新闻标题', 'N/A')}{brief}"
            )
            if item.get("新闻链接"):
                lines.append(f"   链接：{item.get('新闻链接')}")
    else:
        lines.append("- N/A")

    lines.extend(["", "### 港交所公告"])
    if latest_announcement:
        risk_total = sum(int(value or 0) for value in risk_counts.values())
        active_categories = [
            f"{name} {count}条"
            for name, count in [
                ("回购", category_counts.get("buyback", 0)),
                ("业绩/财报", category_counts.get("financial_results", 0)),
                ("融资/配售", category_counts.get("financing_or_placing", 0)),
                ("董事变动", category_counts.get("director_change", 0)),
                ("分红", category_counts.get("dividend", 0)),
            ]
            if count
        ]
        lines.extend(
            [
                f"- 近 {announcements.get('days', 'N/A')} 天共 {announcements.get('record_count', 'N/A')} 条公告。",
                f"- 分类命中：{'; '.join(active_categories) if active_categories else '未识别到重点分类'}",
                f"- 风险关键词：{risk_total} 条。",
            ]
        )
        for index, item in enumerate(announcement_items[:5], start=1):
            lines.append(
                f"{index}. {item.get('date_time', 'N/A')}｜{item.get('title', 'N/A')}｜"
                f"{item.get('category', 'N/A')}｜{item.get('file_type', 'N/A')} {item.get('file_info', '')}"
            )
            if item.get("link"):
                lines.append(f"   链接：{item.get('link')}")
    else:
        lines.append("- N/A")

    lines.extend(["", "### 南向资金/持仓"])
    if southbound_summary:
        net_values = pd.to_numeric(pd.Series([item.get("成交净买额") for item in southbound_summary]), errors="coerce").dropna()
        net_total = round(float(net_values.sum()), 2) if not net_values.empty else None
        lines.append(f"- 市场级港股通净买额合计字段：{fmt_value(net_total)}（单位沿用上游接口）。")
        for item in southbound_summary:
            lines.append(
                f"- {item.get('交易日', 'N/A')}｜{item.get('板块', 'N/A')}｜"
                f"成交净买额：{fmt_value(item.get('成交净买额'))}｜"
                f"相关指数：{item.get('相关指数', 'N/A')} {fmt_value(item.get('指数涨跌幅'), '%')}"
            )
    if southbound_history:
        for channel in southbound_history:
            latest = channel.get("latest", {})
            lines.append(
                f"- 历史最新：{channel.get('channel', 'N/A')}｜{latest.get('日期', 'N/A')}｜"
                f"成交净买额：{fmt_value(latest.get('当日成交净买额'))}｜"
                f"买入/卖出：{fmt_value(latest.get('买入成交额'))} / {fmt_value(latest.get('卖出成交额'))}"
            )
    if holding:
        lines.append(
            f"- 个股持仓：{holding.get('持股日期', 'N/A')}｜持股数量 {fmt_value(holding.get('持股数量'))}｜"
            f"持股市值 {fmt_value(holding.get('持股市值'))}｜占发行股比例 {fmt_value(holding.get('持股数量占发行股百分比'), '%')}｜"
            f"1日/5日/10日市值变化：{fmt_value(holding.get('持股市值变化-1日'))} / "
            f"{fmt_value(holding.get('持股市值变化-5日'))} / {fmt_value(holding.get('持股市值变化-10日'))}"
        )
    if holding_trend:
        lines.append(
            f"- 近{holding_trend.get('days', 'N/A')}日趋势（{holding_trend.get('start_date', 'N/A')} 至 {holding_trend.get('latest_date', 'N/A')}）："
            f"持股数量 {fmt_value(holding_trend.get('holding_quantity_change_pct'), '%')}｜"
            f"持股市值 {fmt_value(holding_trend.get('holding_market_value_change_pct'), '%')}｜"
            f"占比变化 {fmt_value(holding_trend.get('holding_ratio_change_pct_point'), 'pct')}"
        )

    final_observation = "；".join(str(item).rstrip("。") for item in summary_lines[:3]) if summary_lines else "数据不足，暂不做方向判断"
    lines.extend(
        [
            "",
            "### 一句话总结",
            f"{name}当前状态：{final_observation}。以上为公开数据整理，不构成投资建议。",
        ]
    )
    return lines


def render_information_brief(payload: Dict[str, Any]) -> List[str]:
    """Render collected news, announcements, and southbound flow as a readable brief."""
    news = payload.get("news", [])
    announcements = payload.get("announcements", {})
    announcement_items = announcements.get("items", []) if isinstance(announcements, dict) else []
    southbound = payload.get("southbound", {})
    summary = southbound.get("summary", []) if isinstance(southbound, dict) else []
    history = southbound.get("history", []) if isinstance(southbound, dict) else []
    buyback_items = [
        item
        for item in announcement_items
        if "buyback" in f"{item.get('title', '')} {item.get('category', '')}".lower()
    ]
    category_keywords = {
        "回购": ["buyback", "repurchase"],
        "月报表": ["monthly return"],
        "业绩/财报": ["results", "financial", "annual report", "interim report"],
        "股东大会": ["agm", "annual general meeting", "notice of general meeting"],
        "董事变动": ["director", "appointment", "resignation"],
        "融资/配售": ["placing", "subscription", "issue shares"],
    }
    category_counts = {name: 0 for name in category_keywords}
    risk_keywords = {
        "停牌": ["suspension", "trading halt"],
        "盈利预警": ["profit warning", "loss warning"],
        "诉讼/调查": ["litigation", "legal proceedings", "investigation"],
        "监管/处罚": ["disciplinary", "sanction", "regulatory"],
    }
    risk_hits: Dict[str, List[str]] = {name: [] for name in risk_keywords}
    for item in announcement_items:
        text = f"{item.get('title', '')} {item.get('category', '')}".lower()
        for name, keywords in category_keywords.items():
            if any(keyword in text for keyword in keywords):
                category_counts[name] += 1
        for name, keywords in risk_keywords.items():
            if any(keyword in text for keyword in keywords):
                risk_hits[name].append(item.get("title", "N/A"))

    lines = ["", "## 资讯整理", "", "### 信息概览"]
    if news:
        latest_news = news[0]
        lines.append(
            f"- 最新新闻：{latest_news.get('发布时间', 'N/A')}，"
            f"{latest_news.get('文章来源', 'N/A')} 报道「{latest_news.get('新闻标题', 'N/A')}」。"
        )
    else:
        lines.append("- 最新新闻：N/A。")

    if announcement_items:
        latest_announcement = announcement_items[0]
        lines.append(
            f"- 最新官方公告：{latest_announcement.get('date_time', 'N/A')}，"
            f"{latest_announcement.get('title', 'N/A')}，类别为 {latest_announcement.get('category', 'N/A')}。"
        )
        if buyback_items:
            lines.append(f"- 回购相关公告：当前展示范围内识别到 {len(buyback_items)} 条包含 Share Buyback / buyback 的公告。")
        risk_count = sum(len(items) for items in risk_hits.values())
        lines.append(f"- 风险提示关键词：当前展示范围内识别到 {risk_count} 条停牌/盈利预警/诉讼/监管类关键词命中。")
    else:
        lines.append("- 最新官方公告：N/A。")

    if summary:
        net_values = pd.to_numeric(pd.Series([item.get("成交净买额") for item in summary]), errors="coerce").dropna()
        net_total = round(float(net_values.sum()), 2) if not net_values.empty else None
        trade_date = summary[0].get("交易日", "N/A")
        lines.append(
            f"- 南向资金：{trade_date} 港股通沪/深合计成交净买额字段值为 {fmt_value(net_total)}"
            "（单位沿用上游接口）。"
        )
    else:
        lines.append("- 南向资金：N/A。")

    lines.extend(["", "### 公司相关新闻", "来源：东方财富个股新闻搜索，经 AkShare `stock_news_em` 收集。"])
    if news:
        for index, item in enumerate(news, start=1):
            content = item.get("新闻内容", "")
            brief = f" 摘要：{content[:120]}..." if content else ""
            lines.append(
                f"{index}. {item.get('发布时间', 'N/A')}｜{item.get('文章来源', 'N/A')}｜"
                f"{item.get('新闻标题', 'N/A')}{brief}"
            )
            if item.get("新闻链接"):
                lines.append(f"   链接：{item['新闻链接']}")
    else:
        lines.append("- N/A")

    lines.extend(
        [
            "",
            "### 港交所公告",
            "来源：HKEXnews 官方公告标题搜索；这里只展示公告元数据和 PDF 链接，未解析 PDF 正文。",
        ]
    )
    if announcement_items:
        lines.append(
            f"- 检索范围：近 {announcements.get('days', 'N/A')} 天；"
            f"HKEX stockId={announcements.get('stock_id', {}).get('stockId', 'N/A')}；"
            f"总记录数={announcements.get('record_count', 'N/A')}。"
        )
        for index, item in enumerate(announcement_items, start=1):
            lines.append(
                f"{index}. {item.get('date_time', 'N/A')}｜{item.get('title', 'N/A')}｜"
                f"{item.get('category', 'N/A')}｜{item.get('file_type', 'N/A')} {item.get('file_info', '')}"
            )
            if item.get("link"):
                lines.append(f"   链接：{item['link']}")
        active_categories = [f"{name} {count}条" for name, count in category_counts.items() if count]
        lines.append(f"- 公告分类统计：{'; '.join(active_categories) if active_categories else '未识别到重点分类'}")
        active_risks = [f"{name} {len(items)}条" for name, items in risk_hits.items() if items]
        lines.append(f"- 风险提示关键词：{'; '.join(active_risks) if active_risks else '未识别到停牌/盈利预警/诉讼/监管处罚关键词'}")
    else:
        lines.append("- N/A")

    corporate_actions = payload.get("corporate_actions", {})
    if corporate_actions:
        lines.extend(["", "### 公司行动雷达"])
        category_counts = corporate_actions.get("category_counts", {})
        risk_counts = corporate_actions.get("risk_counts", {})
        lines.append(
            "- 分类命中："
            f"回购 {category_counts.get('buyback', 0)}｜"
            f"业绩/财报 {category_counts.get('financial_results', 0)}｜"
            f"融资/配售 {category_counts.get('financing_or_placing', 0)}｜"
            f"董事变动 {category_counts.get('director_change', 0)}｜"
            f"分红 {category_counts.get('dividend', 0)}"
        )
        risk_total = sum(int(value or 0) for value in risk_counts.values())
        lines.append(f"- 风险类命中：{risk_total} 条。")
        buybacks = corporate_actions.get("buybacks", [])
        if buybacks:
            latest = buybacks[0]
            lines.append(
                f"- 最新回购相关：{latest.get('date_time', 'N/A')}｜{latest.get('title', 'N/A')}｜{latest.get('link', 'N/A')}"
            )
        risk_hits = corporate_actions.get("risk_hits", {})
        if risk_hits:
            for name, rows in risk_hits.items():
                latest = rows[0] if rows else {}
                lines.append(f"- {name}：{latest.get('date_time', 'N/A')}｜{latest.get('title', 'N/A')}")

    lines.extend(
        [
            "",
            "### 南向资金背景",
            "来源：东方财富沪深港通资金流，经 AkShare `stock_hsgt_fund_flow_summary_em` 和 `stock_hsgt_hist_em` 收集。此处为市场级数据，不代表个股专属资金流。",
        ]
    )
    if summary:
        for item in summary:
            lines.append(
                f"- 当日汇总：{item.get('交易日', 'N/A')}｜{item.get('板块', 'N/A')}｜"
                f"成交净买额：{fmt_value(item.get('成交净买额'))}｜"
                f"相关指数：{item.get('相关指数', 'N/A')} {fmt_value(item.get('指数涨跌幅'), '%')}"
            )
    else:
        lines.append("- 当日汇总：N/A")

    for channel in history:
        latest = channel.get("latest", {})
        lines.append(
            f"- 历史最新：{channel.get('channel', 'N/A')}｜{latest.get('日期', 'N/A')}｜"
            f"成交净买额：{fmt_value(latest.get('当日成交净买额'))}｜"
            f"买入/卖出：{fmt_value(latest.get('买入成交额'))} / {fmt_value(latest.get('卖出成交额'))}"
        )

    holding = payload.get("southbound_holding", {})
    if holding:
        lines.extend(["", "### 南向个股持仓"])
        lines.append("来源：东方财富南向持股每日个股统计，经 AkShare `stock_hsgt_stock_statistics_em` 收集；通常为 T+1 数据。")
        lines.append(
            f"- {holding.get('持股日期', 'N/A')}｜{holding.get('股票简称', 'N/A')}｜"
            f"持股数量：{fmt_value(holding.get('持股数量'))}｜"
            f"持股市值：{fmt_value(holding.get('持股市值'))}｜"
            f"占发行股比例：{fmt_value(holding.get('持股数量占发行股百分比'), '%')}｜"
            f"1日/5日/10日市值变化：{fmt_value(holding.get('持股市值变化-1日'))} / "
            f"{fmt_value(holding.get('持股市值变化-5日'))} / {fmt_value(holding.get('持股市值变化-10日'))}"
        )

    holding_trend = payload.get("southbound_holding_trend", {})
    if holding_trend:
        lines.extend(["", "### 南向持仓趋势"])
        lines.append("来源：东方财富南向持股每日个股统计；此处为最近可得日期的趋势对比，通常为 T+1 数据。")
        latest = holding_trend.get("latest", {})
        lines.append(
            f"- 区间：{holding_trend.get('start_date', 'N/A')} 至 {holding_trend.get('latest_date', 'N/A')}｜"
            f"最新持股数量：{fmt_value(latest.get('持股数量'))}｜"
            f"最新持股市值：{fmt_value(latest.get('持股市值'))}｜"
            f"占发行股比例：{fmt_value(latest.get('持股数量占发行股百分比'), '%')}"
        )
        lines.append(
            f"- 区间变化：持股数量 {fmt_value(holding_trend.get('holding_quantity_change_pct'), '%')}｜"
            f"持股市值 {fmt_value(holding_trend.get('holding_market_value_change_pct'), '%')}｜"
            f"占比变化 {fmt_value(holding_trend.get('holding_ratio_change_pct_point'), 'pct')}"
        )

    return lines


def render_market_context(payload: Dict[str, Any]) -> List[str]:
    """Render market-relative strength and short-selling context."""
    index_context = payload.get("index_context", {})
    short_selling = payload.get("short_selling", {})
    lines = ["", "## 市场相对强弱与交易情绪"]

    lines.extend(["", "### 指数相对强弱"])
    items = index_context.get("items", []) if isinstance(index_context, dict) else []
    if items:
        lines.append("来源：新浪港股指数历史行情，经 AkShare `stock_hk_index_daily_sina` 收集。")
        for item in items:
            lines.append(
                f"- {item.get('name', item.get('code', 'N/A'))}（{item.get('latest_date', 'N/A')}）："
                f"5日/20日涨跌幅 {fmt_value(item.get('return_5d_pct'), '%')} / {fmt_value(item.get('return_20d_pct'), '%')}；"
                f"个股超额 {fmt_value(item.get('stock_excess_5d_pct'), '%')} / {fmt_value(item.get('stock_excess_20d_pct'), '%')}"
            )
    else:
        lines.append("- N/A")

    lines.extend(["", "### 沽空成交"])
    if short_selling:
        lines.append("来源：HKEX Short Selling Turnover 当前主板报告；盘中报告可能只覆盖至午间收市。")
        lines.append(
            f"- 报告：{short_selling.get('report_title', 'N/A')}｜交易日：{short_selling.get('trade_date', 'N/A')}"
        )
        lines.append(
            f"- 沽空股数/金额：{fmt_value(short_selling.get('short_shares'))} / "
            f"{fmt_value(short_selling.get('short_turnover'), ' HKD')}｜"
            f"占当日成交额：{fmt_value(short_selling.get('short_turnover_ratio_pct'), '%')}"
        )
    else:
        lines.append("- N/A")

    return lines


def render_technical_dashboard(payload: Dict[str, Any]) -> List[str]:
    """Render the technical indicator dashboard."""
    technical = payload.get("technical", {})
    lines = ["", "## 技术面看板"]
    if not technical:
        lines.append("- N/A")
        return lines

    ma = technical.get("ma", {})
    macd = technical.get("macd", {})
    notes = technical.get("notes", [])
    lines.extend(
        [
            "来源：基于日线 OHLCV 计算；评分只用于研究辅助，不代表买卖建议。",
            f"- 综合评分：{fmt_value(technical.get('score'))}/100｜状态：{technical.get('state', 'N/A')}",
            f"- 子评分：趋势 {fmt_value(technical.get('trend_score'))}｜动量 {fmt_value(technical.get('momentum_score'))}｜量能 {fmt_value(technical.get('volume_score'))}｜波动 {fmt_value(technical.get('risk_score'))}",
            f"- MA5/10/20/60：{fmt_value(ma.get('ma_5'))} / {fmt_value(ma.get('ma_10'))} / {fmt_value(ma.get('ma_20'))} / {fmt_value(ma.get('ma_60'))}",
            f"- 价格相对 MA20/MA60：{fmt_value(technical.get('price_vs_ma20_pct'), '%')} / {fmt_value(technical.get('price_vs_ma60_pct'), '%')}",
            f"- MACD DIF/DEA/柱：{fmt_value(macd.get('dif'))} / {fmt_value(macd.get('dea'))} / {fmt_value(macd.get('histogram'))}｜柱变化：{fmt_value(macd.get('histogram_change'))}",
            f"- RSI14：{fmt_value(technical.get('rsi_14'))}｜状态：{technical.get('rsi_state', 'N/A')}",
            f"- 成交量较20日均量：{fmt_value(technical.get('volume_vs_20d_avg_pct'), '%')}｜20日年化波动率：{fmt_value(technical.get('volatility_20d_pct'), '%')}",
            f"- 20日支撑/压力：{fmt_value(technical.get('support_20d'))} / {fmt_value(technical.get('resistance_20d'))}",
            f"- 距支撑/压力空间：{fmt_value(technical.get('distance_to_support_pct'), '%')} / {fmt_value(technical.get('distance_to_resistance_pct'), '%')}",
        ]
    )
    if notes:
        lines.append(f"- 观察：{' '.join(notes)}")
    return lines


def render_market_snapshot(payload: Dict[str, Any]) -> List[str]:
    """Render price, trading, security, financial, and dividend display items."""
    price = payload.get("price", {})
    realtime = payload.get("realtime_quote", {})
    security = payload.get("security_profile", {})
    indicators = payload.get("latest_indicators", {})
    dividends = payload.get("dividends", [])

    lines = ["", "## 价格与交易"]
    if realtime:
        lines.extend(
            [
                "### 实时/盘中快照",
                "来源：新浪港股实时行情，经 AkShare `stock_hk_spot` 收集；免费源可能延迟，以数据时间为准。",
                f"- 数据时间：{realtime.get('日期时间', 'N/A')}",
                f"- 现价/涨跌幅：{fmt_value(realtime.get('最新价'), ' HKD')} / {fmt_value(realtime.get('涨跌幅'), '%')}",
                f"- 买一/卖一：{fmt_value(realtime.get('买一'))} / {fmt_value(realtime.get('卖一'))}",
                f"- 今日高/低：{fmt_value(realtime.get('最高'))} / {fmt_value(realtime.get('最低'))}",
                f"- 成交量/成交额：{fmt_value(realtime.get('成交量'))} / {fmt_value(realtime.get('成交额'))}",
                f"- 昨收/今开：{fmt_value(realtime.get('昨收'))} / {fmt_value(realtime.get('今开'))}",
            ]
        )
    else:
        lines.extend(["### 实时/盘中快照", "- N/A"])

    lines.extend(["", "### 日线与K线趋势"])
    lines.extend(
        [
            f"- 最新交易日：{price.get('latest_date', 'N/A')}",
            f"- 开/高/低/收：{fmt_value(price.get('open'))} / {fmt_value(price.get('high'))} / {fmt_value(price.get('low'))} / {fmt_value(price.get('close'), ' HKD')}",
            f"- 当日涨跌幅/振幅：{fmt_value(price.get('change_pct'), '%')} / {fmt_value(price.get('amplitude_pct'), '%')}",
            f"- 换手率：{fmt_value(price.get('turnover_rate_pct'), '%')}",
            f"- 成交量/成交额：{fmt_value(price.get('volume'))} / {fmt_value(price.get('turnover'))}",
            f"- 5日/20日/60日/区间涨跌幅：{fmt_value(price.get('return_5d_pct'), '%')} / {fmt_value(price.get('return_20d_pct'), '%')} / {fmt_value(price.get('return_60d_pct'), '%')} / {fmt_value(price.get('return_period_pct'), '%')}",
            f"- 5日/20日/60日均价：{fmt_value(price.get('ma_5'))} / {fmt_value(price.get('ma_20'))} / {fmt_value(price.get('ma_60'))}",
            f"- 当前回看区间高/低：{fmt_value(price.get('period_high'))} / {fmt_value(price.get('period_low'))}",
            f"- 20日平均成交额：{fmt_value(price.get('avg_turnover_20d'))}",
            f"- 20日年化波动率：{fmt_value(price.get('volatility_20d_pct'), '%')}",
            f"- 最新成交量较20日均量：{fmt_value(price.get('latest_volume_vs_20d_avg_pct'), '%')}",
        ]
    )

    lines.extend(["", "## 证券资料"])
    if security:
        lines.extend(
            [
                f"- 证券简称/代码：{security.get('证券简称', 'N/A')} / {security.get('证券代码', 'N/A')}",
                f"- 上市日期/板块：{str(security.get('上市日期', 'N/A'))[:10]} / {security.get('板块', 'N/A')}",
                f"- 每手股数/发行价：{fmt_value(security.get('每手股数'))} / {fmt_value(security.get('发行价'), ' HKD')}",
                f"- 是否沪港通/深港通标的：{security.get('是否沪港通标的', 'N/A')} / {security.get('是否深港通标的', 'N/A')}",
                f"- ISIN：{security.get('ISIN（国际证券识别编码）', 'N/A')}",
            ]
        )
    else:
        lines.append("- N/A")

    lines.extend(["", "## 最新财务指标"])
    if indicators:
        lines.extend(
            [
                f"- 基本每股收益/每股净资产：{fmt_value(indicators.get('基本每股收益(元)'))} / {fmt_value(indicators.get('每股净资产(元)'))}",
                f"- 每股经营现金流：{fmt_value(indicators.get('每股经营现金流(元)'))}",
                f"- 每股股息TTM/股息率TTM：{fmt_value(indicators.get('每股股息TTM(港元)'), ' HKD')} / {fmt_value(indicators.get('股息率TTM(%)'), '%')}",
                f"- 派息比率：{fmt_value(indicators.get('派息比率(%)'), '%')}",
                f"- 总市值：{fmt_value(indicators.get('总市值(港元)'), ' HKD')}",
                f"- 市盈率/市净率：{fmt_value(indicators.get('市盈率'))} / {fmt_value(indicators.get('市净率'))}",
                f"- 销售净利率/ROE/ROA：{fmt_value(indicators.get('销售净利率(%)'), '%')} / {fmt_value(indicators.get('股东权益回报率(%)'), '%')} / {fmt_value(indicators.get('总资产回报率(%)'), '%')}",
            ]
        )
    else:
        lines.append("- N/A")

    lines.extend(["", "## 分红派息"])
    if dividends:
        for index, item in enumerate(dividends, start=1):
            lines.append(
                f"{index}. 公告日：{item.get('最新公告日期', 'N/A')}｜财政年度：{item.get('财政年度', 'N/A')}｜"
                f"{item.get('分红方案', 'N/A')}｜类型：{item.get('分配类型', 'N/A')}｜"
                f"除净日：{item.get('除净日', 'N/A')}｜发放日：{item.get('发放日', 'N/A')}"
            )
    else:
        lines.append("- N/A")

    return lines


def render_markdown(payload: Dict[str, Any]) -> str:
    """Render the research payload as a concise Markdown brief."""
    company = payload.get("company", {})
    price = payload.get("price", {})
    valuation = payload.get("valuation", {})
    financials = payload.get("financial_highlights", {})
    trend = payload.get("financial_trend", {})

    lines = [
        f"# 港股研究快照：{payload['symbol']}",
        "",
        f"- 生成日期：{payload['generated_on']}",
        f"- 公司：{company.get('name', 'N/A')} / {company.get('english_name', 'N/A')}",
        f"- 行业：{company.get('industry', 'N/A')}",
        f"- 最新交易日：{price.get('latest_date', 'N/A')}",
        f"- 收盘价：{fmt_value(price.get('close'), ' HKD')}",
        f"- 当日涨跌幅：{fmt_value(price.get('change_pct'), '%')}",
        f"- 5日/20日涨跌幅：{fmt_value(price.get('return_5d_pct'), '%')} / {fmt_value(price.get('return_20d_pct'), '%')}",
        f"- 5日/20日均价：{fmt_value(price.get('ma_5'))} / {fmt_value(price.get('ma_20'))}",
        f"- 最新成交额：{fmt_value(price.get('turnover'))}",
        f"- 最新成交量较20日均量：{fmt_value(price.get('latest_volume_vs_20d_avg_pct'), '%')}",
    ]

    lines.extend(render_executive_brief(payload))
    lines.extend(["", "## 初步解读"])
    lines.extend(f"- {item}" for item in render_interpretation(payload))

    lines.extend(render_market_snapshot(payload))
    lines.extend(render_technical_dashboard(payload))
    lines.extend(render_market_context(payload))
    lines.extend(
        [
            "",
        "## 估值快照",
        ]
    )

    if valuation:
        for name, item in valuation.items():
            lines.append(
                f"- {name}（{item.get('date', 'N/A')}）：{fmt_value(item.get('value'))}｜"
                f"近一年变化：{fmt_value(item.get('one_year_change_pct'), '%')}｜"
                f"近一年分位：{fmt_value(item.get('one_year_percentile_pct'), '%')}"
            )
    else:
        lines.append("- N/A")

    lines.extend(["", "## 财务摘要"])
    if financials:
        labels = {
            "report_date": "报告期",
            "revenue": "营业额",
            "gross_profit": "毛利",
            "operating_profit": "经营溢利",
            "shareholder_profit": "股东应占溢利",
            "basic_eps": "每股基本盈利",
            "dividend_per_share": "每股股息",
        }
        for key, label in labels.items():
            if key in financials:
                lines.append(f"- {label}：{fmt_value(financials[key])}")
        if trend:
            lines.extend(["", "### 财务趋势"])
            lines.append(f"- 对比期：{trend.get('latest_report_date', 'N/A')} vs {trend.get('previous_report_date', 'N/A')}")
            lines.append(
                f"- 营收/股东应占溢利同比：{fmt_value(trend.get('revenue_yoy_pct'), '%')} / "
                f"{fmt_value(trend.get('shareholder_profit_yoy_pct'), '%')}"
            )
            lines.append(
                f"- 毛利/经营溢利同比：{fmt_value(trend.get('gross_profit_yoy_pct'), '%')} / "
                f"{fmt_value(trend.get('operating_profit_yoy_pct'), '%')}"
            )
            lines.append(
                f"- 毛利率/经营利润率：{fmt_value(trend.get('gross_margin_pct'), '%')} / "
                f"{fmt_value(trend.get('operating_margin_pct'), '%')}"
            )
    else:
        lines.append("- N/A")

    lines.extend(["", "## 最近5个交易日"])
    tail = payload.get("history_tail", [])
    lines.append(markdown_table(tail, ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "涨跌幅"]))

    lines.extend(render_information_brief(payload))

    if company.get("introduction"):
        intro = str(company["introduction"]).strip()
        lines.extend(["", "## 公司简介", intro[:500] + ("..." if len(intro) > 500 else "")])

    if payload.get("errors"):
        lines.extend(["", "## 数据获取提示"])
        for item in payload["errors"]:
            lines.append(f"- {item['section']}: {item['error']}")

    quality = payload.get("data_quality", {})
    if quality:
        lines.extend(["", "## 数据真实性检查"])
        if quality.get("required_price_date"):
            status = "通过" if quality.get("price_date_matched") else "未通过"
            lines.append(f"- 要求行情日期：{quality['required_price_date']}，检查结果：{status}")
        for note in quality.get("notes", []):
            lines.append(f"- {note}")

    lines.extend(
        [
            "",
            "## 免责声明",
            "以上为公开数据整理和研究辅助，不构成任何投资建议或交易指令。",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Generate a Hong Kong stock research brief.")
    parser.add_argument("symbols", nargs="*", help="Hong Kong stock codes, e.g. 00700 03690 HK:9988")
    parser.add_argument("--symbols", dest="symbols_csv", help="Comma-separated Hong Kong stock codes, e.g. 00700,03690,09988.")
    parser.add_argument("--watchlist-file", help="Text file with one stock code per line. Lines after # are ignored.")
    parser.add_argument("--output-dir", help="Write one report file per stock into this directory instead of printing to stdout.")
    parser.add_argument("--lookback-days", type=int, default=120, help="Calendar days of recent history to fetch.")
    parser.add_argument("--require-today", action="store_true", help="Fail if latest price date is not today's local date.")
    parser.add_argument("--require-date", help="Fail if latest price date is not this YYYY-MM-DD date.")
    parser.add_argument("--news-limit", type=int, default=5, help="Number of Eastmoney news items to include.")
    parser.add_argument("--announcement-days", type=int, default=31, help="Days of HKEX announcements to search.")
    parser.add_argument("--announcement-limit", type=int, default=5, help="Number of HKEX announcement items to include.")
    parser.add_argument("--dividend-limit", type=int, default=5, help="Number of dividend/payout records to include.")
    parser.add_argument("--southbound-trend-days", type=int, default=20, help="Recent southbound holding trend rows to inspect.")
    parser.add_argument("--skip-short-selling", action="store_true", help="Skip HKEX short selling turnover lookup.")
    parser.add_argument("--skip-index-context", action="store_true", help="Skip Hong Kong index-relative strength lookup.")
    parser.add_argument("--json", action="store_true", help="Print JSON payload instead of Markdown.")
    return parser.parse_args(argv)


def collect_symbols(args: argparse.Namespace) -> List[str]:
    """Collect symbols from positional args, CSV args, and watchlist files."""
    raw_symbols: List[str] = []
    raw_symbols.extend(args.symbols or [])
    if args.symbols_csv:
        raw_symbols.extend(item.strip() for item in args.symbols_csv.split(","))
    if args.watchlist_file:
        path = Path(args.watchlist_file).expanduser()
        for line in path.read_text(encoding="utf-8").splitlines():
            cleaned = line.split("#", 1)[0].strip()
            if cleaned:
                raw_symbols.append(cleaned)

    symbols: List[str] = []
    seen = set()
    for raw in raw_symbols:
        if not raw:
            continue
        symbol = normalize_hk_symbol(raw)
        if symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    if not symbols:
        raise ValueError("Provide at least one Hong Kong stock code.")
    return symbols


def write_report(output_dir: Path, symbol: str, content: str, is_json: bool = False) -> Path:
    """Write a report file for one symbol."""
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "json" if is_json else "md"
    path = output_dir / f"{symbol}.{suffix}"
    path.write_text(content, encoding="utf-8")
    return path


def main(argv: List[str]) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    try:
        symbols = collect_symbols(args)
        required_date = None
        if args.require_today and args.require_date:
            raise ValueError("Use either --require-today or --require-date, not both.")
        if args.require_today:
            required_date = date.today()
        elif args.require_date:
            required_date = date.fromisoformat(args.require_date)
    except Exception as exc:  # noqa: BLE001 - CLI should return a readable failure.
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir).expanduser() if args.output_dir else None
    index_lines = [f"# 港股资讯报告索引", "", f"- 生成日期：{date.today().isoformat()}", ""]
    had_failure = False
    strict_failed = False

    for symbol in symbols:
        try:
            payload = build_payload(
                symbol,
                args.lookback_days,
                required_date=required_date,
                news_limit=args.news_limit,
                announcement_days=args.announcement_days,
                announcement_limit=args.announcement_limit,
                dividend_limit=args.dividend_limit,
                southbound_trend_days=args.southbound_trend_days,
                include_short_selling=not args.skip_short_selling,
                include_index_context=not args.skip_index_context,
            )
            strict_failed = strict_failed or any(
                item.get("section") == "strict-date-check" for item in payload.get("errors", [])
            )
            content = json.dumps(payload, ensure_ascii=False, indent=2, default=str) if args.json else render_markdown(payload)
            if output_dir:
                path = write_report(output_dir, symbol, content, is_json=args.json)
                index_lines.append(f"- {symbol}: {path.name}")
            else:
                if len(symbols) > 1:
                    print(f"\n\n<!-- report: {symbol} -->\n")
                print(content)
        except Exception as exc:  # noqa: BLE001 - keep batch jobs running.
            had_failure = True
            message = f"{type(exc).__name__}: {exc}"
            if output_dir:
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / f"{symbol}.error.txt").write_text(message, encoding="utf-8")
                index_lines.append(f"- {symbol}: FAILED - {message}")
            else:
                print(f"Error for {symbol}: {message}", file=sys.stderr)

    if output_dir and not args.json:
        (output_dir / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    if had_failure:
        return 1
    return 2 if strict_failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
