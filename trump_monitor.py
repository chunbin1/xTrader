#!/usr/bin/env python3.11
"""
川普 Truth Social 监控 → 智谱翻译 → 飞书推送
用法：
  单次运行：python3.11 trump_monitor.py
  持续监控：python3.11 trump_monitor.py --watch
"""
import argparse
import hashlib
import hmac
import base64
import json
import logging
import os
import re
import time
from datetime import datetime

import feedparser
import requests
from dotenv import load_dotenv
from zhipuai import ZhipuAI

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

RSS_URL = "https://trumpstruth.org/feed"
SEEN_FILE = os.path.join(os.path.dirname(__file__), "seen_trump.json")


# ── RSS 抓取 ──────────────────────────────────────────────

def clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def load_seen() -> set:
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE) as f:
        return set(json.load(f))


def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def fetch_new_posts() -> list[dict]:
    seen = load_seen()
    feed = feedparser.parse(RSS_URL)
    new_posts = []

    for entry in feed.entries:
        pid = entry.get("id", entry.get("link", ""))
        if pid in seen:
            continue
        text = clean_html(entry.get("summary", ""))
        # 过滤空帖、纯链接转帖、内容过短
        if not text or text.startswith("RT: https://") or len(text) < 20:
            seen.add(pid)
            continue
        try:
            pub = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            pub = entry.get("published", "")

        new_posts.append({
            "id": pid,
            "text": text,
            "link": entry.get("link", ""),
            "published": pub,
        })
        seen.add(pid)

    if new_posts:
        save_seen(seen)
    return list(reversed(new_posts))  # 按时间正序


# ── 智谱翻译 + 市场分析 ───────────────────────────────────

SYSTEM_PROMPT = """你是专业的政治新闻翻译兼金融市场分析师。
用户给你川普的帖子，请完成两件事：
1. 翻译成简体中文（保留原文语气，人名保留英文）
2. 分析对以下三类资产的影响：美股、原油、利率（美债）

严格输出以下 JSON，不要有任何多余文字：
{
  "translation": "中文译文",
  "market": {
    "stocks": {"signal": "利好|利空|中性", "reason": "一句话理由"},
    "oil":    {"signal": "利好|利空|中性", "reason": "一句话理由"},
    "rates":  {"signal": "利好|利空|中性", "reason": "一句话理由"}
  },
  "irrelevant": true/false
}

irrelevant=true 表示帖子与市场完全无关（如纯人身攻击、转发文章等），此时 market 各项填中性即可。"""

SIGNAL_EMOJI = {"利好": "📈", "利空": "📉", "中性": "➡️"}


def analyze(client: ZhipuAI, text: str, model: str = "glm-4-flash") -> dict:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.3,
    )
    raw = resp.choices[0].message.content.strip()
    start, end = raw.find("{"), raw.rfind("}") + 1
    return json.loads(raw[start:end])


# ── 飞书推送 ──────────────────────────────────────────────

def feishu_sign(secret: str) -> tuple[str, str]:
    ts = str(int(time.time()))
    msg = f"{ts}\n{secret}"
    sig = base64.b64encode(
        hmac.new(msg.encode(), digestmod=hashlib.sha256).digest()
    ).decode()
    return ts, sig


def send_feishu(webhook: str, post: dict, result: dict, secret: str = ""):
    original = post["text"]
    if len(original) > 400:
        original = original[:400] + "..."

    translation = result.get("translation", "")
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

    # 卡片标题颜色：有利好=绿，有利空=红，否则蓝
    signals = [market.get(k, {}).get("signal", "中性") for k in ("stocks", "oil", "rates")]
    if not irrelevant and "利空" in signals:
        color = "red"
    elif not irrelevant and "利好" in signals:
        color = "green"
    else:
        color = "blue"

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "🇺🇸 川普新帖"},
                "template": color,
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**🕐 {post['published']}**"},
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**📝 原文**\n{original}"},
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**🈶 译文**\n{translation}"},
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**📊 市场影响**\n{market_text}"},
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看原帖"},
                            "url": post["link"],
                            "type": "default",
                        }
                    ],
                },
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": "🤖 智谱 GLM 自动翻译分析 · 仅供参考"}
                    ],
                },
            ],
        },
    }

    if secret:
        ts, sig = feishu_sign(secret)
        card["timestamp"] = ts
        card["sign"] = sig

    resp = requests.post(
        webhook,
        json=card,
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    data = resp.json()
    ok = data.get("code") == 0 or data.get("StatusCode") == 0
    if ok:
        logger.info("飞书推送成功")
    else:
        logger.error("飞书推送失败: %s", data)
    return ok


# ── 主流程 ────────────────────────────────────────────────

def run_once(zhipu_client: ZhipuAI, webhook: str, secret: str, model: str):
    posts = fetch_new_posts()
    if not posts:
        logger.info("没有新帖子")
        return

    logger.info("发现 %d 条新帖，开始翻译分析推送... (模型: %s)", len(posts), model)
    for post in posts:
        logger.info("分析: %s...", post["text"][:60])
        try:
            result = analyze(zhipu_client, post["text"], model)
        except Exception as e:
            logger.error("分析失败: %s", e)
            result = {"translation": post["text"], "market": {}, "irrelevant": True}
        send_feishu(webhook, post, result, secret)
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true", help="持续监控模式")
    parser.add_argument("--interval", type=int, default=60, help="轮询间隔（秒）")
    args = parser.parse_args()

    zhipu_key = os.getenv("ZHIPU_API_KEY")
    webhook = os.getenv("FEISHU_WEBHOOK_URL")
    secret = os.getenv("FEISHU_SECRET", "")
    model = os.getenv("ZHIPU_MODEL", "glm-4-flash")

    if not zhipu_key:
        raise SystemExit("❌ 请在 .env 中设置 ZHIPU_API_KEY")
    if not webhook:
        raise SystemExit("❌ 请在 .env 中设置 FEISHU_WEBHOOK_URL")

    client = ZhipuAI(api_key=zhipu_key)

    if args.watch:
        logger.info("🚀 持续监控模式启动，间隔 %ds，模型 %s", args.interval, model)
        while True:
            try:
                run_once(client, webhook, secret, model)
            except Exception as e:
                logger.error("异常: %s", e)
            time.sleep(args.interval)
    else:
        run_once(client, webhook, secret, model)


if __name__ == "__main__":
    main()
