import base64
import hashlib
import hmac
import logging
import time

import requests

logger = logging.getLogger(__name__)

SIGNAL_EMOJI = {"利好": "📈", "利空": "📉", "中性": "➡️"}
PLATFORM_EMOJI = {"truthsocial": "🇺🇸", "x": "🚀"}


def _sign(secret: str) -> tuple[str, str]:
    ts = str(int(time.time()))
    sig = base64.b64encode(
        hmac.new(f"{ts}\n{secret}".encode(), digestmod=hashlib.sha256).digest()
    ).decode()
    return ts, sig


def send(webhook: str, account: dict, post: dict, result: dict, secret: str = "", model: str = "") -> bool:
    """发送分析结果到飞书。

    account: accounts.json 中的单条配置
    post:    fetcher 返回的帖子字典
    result:  analyzer 返回的分析结果
    """
    name = account.get("name", account.get("handle", "未知"))
    platform = account.get("platform", "x")
    emoji = PLATFORM_EMOJI.get(platform, "📢")

    translation = result.get("translation", "")
    summary = result.get("summary") or ""
    market = result.get("market", {})
    irrelevant = result.get("irrelevant", False)

    def market_line(label: str, key: str) -> str:
        item = market.get(key, {})
        sig = item.get("signal", "中性")
        reason = item.get("reason", "—")
        return f"{SIGNAL_EMOJI.get(sig, '➡️')} **{label}** {sig}｜{reason}"

    if irrelevant:
        market_text = "与市场无直接关联"
    else:
        market_text = "\n".join([
            market_line("美股", "stocks"),
            market_line("原油", "oil"),
            market_line("美债利率", "rates"),
        ])

    signals = [market.get(k, {}).get("signal", "中性") for k in ("stocks", "oil", "rates")]
    if not irrelevant and "利空" in signals:
        color = "red"
    elif not irrelevant and "利好" in signals:
        color = "green"
    else:
        color = "blue"

    original = post["text"]
    if len(original) > 400:
        original = original[:400] + "..."

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"{emoji} {name} 新帖"},
                "template": color,
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**🕐 {post['published']}**"}},
                *([{"tag": "div", "text": {"tag": "lark_md", "content": f"**💡 概要** {summary}"}}] if summary else []),
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**📝 原文**\n{original}"}},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**🈶 译文**\n{translation}"}},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**📊 市场影响**\n{market_text}"}},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "查看原帖"},
                     "url": post["link"], "type": "default"}
                ]},
                {"tag": "note", "elements": [
                    {"tag": "plain_text", "content": f"🤖 {model or 'GLM'} 自动翻译分析 · 仅供参考"}
                ]},
            ],
        },
    }

    if secret:
        ts, sig = _sign(secret)
        card["timestamp"] = ts
        card["sign"] = sig

    try:
        resp = requests.post(webhook, json=card, timeout=10)
        data = resp.json()
        ok = data.get("code") == 0 or data.get("StatusCode") == 0
        if ok:
            logger.info("[%s] 飞书推送成功", name)
        else:
            logger.error("[%s] 飞书推送失败: %s", name, data)
        return ok
    except Exception as e:
        logger.error("[%s] 飞书推送异常: %s", name, e)
        return False


def send_cookie_alert(webhook: str, account: dict, secret: str = ""):
    """Cookie 失效时发送飞书告警。"""
    name = account.get("name", account.get("handle", "未知"))
    handle = account.get("handle", "")

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"⚠️ {name} 监控 Cookie 已失效"},
                "template": "red",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"X 账号 Cookie 已过期，**{name}**（@{handle}）监控已暂停。\n\n"
                            "**请按以下步骤更新：**\n"
                            "1. 浏览器登录 x.com\n"
                            "2. 按 F12 → 应用 → Cookie → x.com\n"
                            "3. 复制 `auth_token` 和 `ct0`\n"
                            "4. 更新 `.env` 中对应的值\n"
                            "5. 重启服务：`bash start.sh`"
                        ),
                    },
                },
            ],
        },
    }

    if secret:
        ts, sig = _sign(secret)
        card["timestamp"] = ts
        card["sign"] = sig

    try:
        requests.post(webhook, json=card, timeout=10)
        logger.error("[%s] Cookie 失效，已发送飞书告警", name)
    except Exception as e:
        logger.error("告警推送失败: %s", e)
