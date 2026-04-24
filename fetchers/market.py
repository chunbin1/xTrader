import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

SYMBOLS = {
    "SPY": {"label": "SPY",      "type": "stock"},
    "QQQ": {"label": "QQQ",      "type": "stock"},
    "USO": {"label": "原油(USO)", "type": "stock"},
    "TLT": {"label": "美债(TLT)", "type": "bond"},
}

_cache: dict = {}
_CACHE_TTL = 300  # 5分钟


def fetch() -> tuple[str, dict]:
    """返回 (prompt_block, snapshot)，任何失败返回 ("", {}) 静默降级。"""
    api_key = os.getenv("TWELVEDATA_API_KEY", "")
    if not api_key:
        logger.debug("未配置 TWELVEDATA_API_KEY，跳过行情获取")
        return "", {}

    now = time.time()
    if _cache and now - _cache.get("ts", 0) < _CACHE_TTL:
        logger.debug("行情命中缓存 (age=%.0fs)", now - _cache["ts"])
        return _cache["data"], _cache["snapshot"]

    try:
        symbols_str = ",".join(SYMBOLS.keys())
        resp = requests.get(
            "https://api.twelvedata.com/quote",
            params={"symbol": symbols_str, "apikey": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        snapshot = {}
        for sym, meta in SYMBOLS.items():
            item = data.get(sym, {})
            if item.get("status") == "error" or "close" not in item:
                logger.warning("行情数据异常 [%s]: %s", sym, item.get("message", "无数据"))
                continue
            price = float(item["close"])
            prev = float(item["previous_close"])
            pct = (price - prev) / prev * 100 if prev else 0.0
            snapshot[sym] = {
                "label": meta["label"],
                "price": price,
                "change_pct": pct,
                "type": meta["type"],
            }

        if not snapshot:
            logger.warning("所有行情数据获取失败")
            return "", {}

        lines = ["【当前市场快照（Twelve Data 实时）】"]
        for d in snapshot.values():
            sign = "+" if d["change_pct"] >= 0 else ""
            suffix = "，价格与利率反向" if d["type"] == "bond" else ""
            lines.append(f"  {d['label']}: ${d['price']:.2f} ({sign}{d['change_pct']:.2f}%{suffix})")
        block = "\n".join(lines)

        _cache.update({"data": block, "snapshot": snapshot, "ts": now})
        logger.info("行情已刷新: %s",
                    " | ".join(f"{d['label']} {d['change_pct']:+.2f}%" for d in snapshot.values()))
        return block, snapshot

    except Exception as e:
        logger.warning("行情获取失败: %s", e)
        return "", {}
