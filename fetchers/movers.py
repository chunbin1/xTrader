"""
美股热点数据：涨幅榜、跌幅榜、成交量榜（via yfinance screener）
"""
import logging
import time

logger = logging.getLogger(__name__)

_cache: dict = {}
_CACHE_TTL = 300  # 5分钟，避免同一轮次重复拉取


def fetch(count: int = 5) -> dict:
    """返回三个榜单，任何失败返回 {} 静默降级。

    结构：
    {
      "gainers":  [{"symbol": "TXN", "name": "Texas Instruments", "price": 282.23, "change_pct": 19.43, "volume": 25620382}, ...],
      "losers":   [...],
      "actives":  [...],
    }
    """
    now = time.time()
    if _cache and now - _cache.get("ts", 0) < _CACHE_TTL:
        logger.debug("热点数据命中缓存 (age=%.0fs)", now - _cache["ts"])
        return _cache["data"]

    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance 未安装，热点数据不可用")
        return {}

    result = {}
    try:
        for screen, key in [("day_gainers", "gainers"),
                             ("day_losers",  "losers"),
                             ("most_actives", "actives")]:
            sc = yf.screen(screen, count=count)
            result[key] = [
                {
                    "symbol":     r.get("symbol", ""),
                    "name":       r.get("shortName", ""),
                    "price":      r.get("regularMarketPrice", 0),
                    "change_pct": round(r.get("regularMarketChangePercent", 0), 2),
                    "volume":     r.get("regularMarketVolume", 0),
                }
                for r in sc.get("quotes", [])
            ]

        # 为涨跌幅超过 5% 的个股拉取最新新闻（最多 3 条标题）
        notable = {r["symbol"] for lst in result.values()
                   for r in lst if abs(r["change_pct"]) >= 5}
        news_map = _fetch_news(yf, notable)
        for lst in result.values():
            for r in lst:
                r["news"] = news_map.get(r["symbol"], [])

        _cache.update({"data": result, "ts": now})
        logger.info("热点数据已刷新: 涨幅榜%d条 跌幅榜%d条 成交量榜%d条",
                    len(result.get("gainers", [])),
                    len(result.get("losers", [])),
                    len(result.get("actives", [])))
        return result

    except Exception as e:
        logger.warning("热点数据获取失败: %s", e)
        return {}


def _fetch_news(yf, symbols: set, max_per: int = 3) -> dict:
    """为指定 symbols 拉取最新新闻标题，返回 {symbol: [title, ...]}。"""
    result = {}
    for sym in symbols:
        try:
            raw = yf.Ticker(sym).news or []
            titles = []
            for item in raw:
                title = (item.get("content") or {}).get("title") or item.get("title")
                if title:
                    titles.append(title)
                if len(titles) >= max_per:
                    break
            if titles:
                result[sym] = titles
                logger.debug("[%s] 新闻: %s", sym, titles)
        except Exception as e:
            logger.debug("[%s] 新闻获取失败: %s", sym, e)
    return result


def is_market_open() -> bool:
    """判断当前是否在美股正式交易时段（09:30–16:00 ET，周一至周五）。"""
    from datetime import datetime, timezone, timedelta
    ET = timezone(timedelta(hours=-4))  # 夏令时 EDT；冬令时改为 -5
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:  # 周六、周日
        return False
    market_open  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)
    return market_open <= now_et < market_close
