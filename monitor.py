#!/usr/bin/env python3.11
"""
社交媒体监控 → MiMo 翻译分析 → 飞书推送

支持平台：
  truthsocial  - Truth Social RSS（无需 key）
  x            - X/Twitter（需要 X_AUTH_TOKEN）

添加监控账号：编辑 accounts.json 即可，无需改代码。

用法：
  单次运行：python3.11 monitor.py
  持续监控：python3.11 monitor.py --watch
  指定间隔：python3.11 monitor.py --watch --interval 120
"""
import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from zhipuai import ZhipuAI
except ImportError:
    ZhipuAI = None

import analyzer
import sender
from fetchers import truthsocial
from fetchers import x as x_fetcher
from fetchers import market as market_fetcher
from fetchers import movers as movers_fetcher
from fetchers.x import CookieExpiredError

load_dotenv()

_log_level = logging.DEBUG if os.getenv("DEBUG") else logging.INFO
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

ACCOUNTS_FILE = os.path.join(os.path.dirname(__file__), "accounts.json")


def in_quiet_hours(quiet: str) -> bool:
    """判断当前北京时间是否在免打扰时段内。
    quiet 格式：'23:00-07:00'，支持跨午夜。
    """
    if not quiet:
        return False
    try:
        start_str, end_str = quiet.strip().split("-")
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
    except Exception:
        logger.warning("QUIET_HOURS 格式错误，应为 HH:MM-HH:MM，当前值: %s", quiet)
        return False

    now = datetime.now(CST)
    cur = now.hour * 60 + now.minute
    start = sh * 60 + sm
    end = eh * 60 + em

    if start <= end:          # 同日，如 09:00-18:00
        return start <= cur < end
    else:                     # 跨午夜，如 23:00-07:00
        return cur >= start or cur < end


def load_accounts() -> list[dict]:
    with open(ACCOUNTS_FILE) as f:
        return json.load(f)


def process_account(account: dict, llm_client, webhook: str,
                    secret: str, models: list[str], auth_token: str,
                    market_context: str = "", market_snapshot: dict = None) -> bool:
    """处理单个账号，返回 False 表示 Cookie 失效需停止该账号。"""
    name = account.get("name", account["handle"])
    platform = account["platform"]

    try:
        if platform == "truthsocial":
            posts = truthsocial.fetch(account)
        elif platform == "x":
            if not auth_token:
                logger.warning("[%s] 未配置 X_AUTH_TOKEN，跳过", name)
                return True
            posts = x_fetcher.fetch(account, auth_token)
        else:
            logger.warning("[%s] 未知平台: %s，跳过", name, platform)
            return True
    except CookieExpiredError:
        sender.send_cookie_alert(webhook, account, secret)
        return False
    except Exception as e:
        logger.error("[%s] 抓取失败: %s", name, e)
        return True

    if not posts:
        logger.info("[%s] 没有新内容", name)
        return True

    logger.info("[%s] 发现 %d 条新内容，开始分析推送...", name, len(posts))
    for post in posts:
        logger.info("[%s] 分析: %s...", name, post["text"][:60])
        try:
            result = analyzer.analyze(llm_client, post["text"], models,
                                      market_context=market_context)
        except Exception as e:
            logger.error("[%s] AI 服务不可用，推送原文: %s", name, e)
            result = {"_raw": True}
        sender.send(webhook, account, post, result, secret, models[0],
                    market_snapshot=market_snapshot)
        time.sleep(1)

    return True


def run_once(llm_client, webhook: str, secret: str, models: list[str], auth_token: str):
    market_context, market_snapshot = market_fetcher.fetch()
    accounts = load_accounts()
    for account in accounts:
        process_account(account, llm_client, webhook, secret, models, auth_token,
                        market_context, market_snapshot)


def main():
    parser = argparse.ArgumentParser(description="社交媒体监控推送飞书")
    parser.add_argument("--watch", action="store_true", help="持续监控模式")
    parser.add_argument("--interval", type=int,
                        default=int(os.getenv("POLL_INTERVAL", "120")),
                        help="轮询间隔（秒），默认读取 .env 中的 POLL_INTERVAL")
    args = parser.parse_args()

    provider = os.getenv("LLM_PROVIDER", "mimo")
    model = os.getenv("LLM_MODEL", "")
    auth_token = os.getenv("X_AUTH_TOKEN", "")
    webhook = os.getenv("FEISHU_WEBHOOK_URL")
    secret = os.getenv("FEISHU_SECRET", "")

    if not webhook:
        raise SystemExit("❌ 请在 .env 中设置 FEISHU_WEBHOOK_URL")

    # 根据 provider 读取对应的 API Key 和 base_url，并选择 SDK
    PROVIDER_CONFIG = {
        "mimo":   {"key_env": "MIMO_API_KEY",  "base_url": "https://api.xiaomimimo.com/v1"},
        "zhipu":  {"key_env": "ZHIPU_API_KEY", "base_url": "https://open.bigmodel.cn/api/paas/v4"},
        "openai": {"key_env": "OPENAI_API_KEY", "base_url": "https://api.openai.com/v1"},
    }
    cfg = PROVIDER_CONFIG.get(provider, PROVIDER_CONFIG["mimo"])
    api_key = os.getenv(cfg["key_env"])
    if not api_key:
        raise SystemExit(f"❌ 请在 .env 中设置 {cfg['key_env']}（当前 provider={provider}）")

    models = analyzer.get_model_list(provider, model)
    logger.info("📡 LLM provider=%s, models=%s", provider, models)

    # 创建 LLM 客户端：优先用 openai SDK（通用），不可用时降级到 zhipuai SDK
    if OpenAI is not None:
        llm_client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
    elif ZhipuAI is not None:
        logger.info("openai SDK 不可用，使用 zhipuai SDK")
        llm_client = ZhipuAI(api_key=api_key)
    else:
        raise SystemExit("❌ 请安装 openai 或 zhipuai SDK: pip install openai")

    quiet = os.getenv("QUIET_HOURS", "")

    MARKET_PUSH_DELAY = 15 * 60  # 开盘后等待 15 分钟再推送
    MARKET_PUSH_INTERVAL = 30 * 60  # 之后每 30 分钟一次

    if args.watch:
        logger.info("🚀 监控启动，间隔 %ds，共 %d 个账号%s",
                    args.interval, len(load_accounts()),
                    f"，免打扰时段 {quiet}" if quiet else "")
        last_market_push = 0.0
        market_open_since = 0.0
        while True:
            try:
                # 社交媒体监控（受免打扰时段控制）
                if in_quiet_hours(quiet):
                    logger.info("😴 当前处于免打扰时段（%s），跳过本轮", quiet)
                else:
                    run_once(llm_client, webhook, secret, models, auth_token)

                # 美股热点推送（开盘后 15 分钟开始推送，不受免打扰限制）
                now = time.time()
                if movers_fetcher.is_market_open():
                    if market_open_since == 0.0:
                        market_open_since = now
                    if now - market_open_since >= MARKET_PUSH_DELAY and (
                            last_market_push == 0.0 or
                            now - last_market_push >= MARKET_PUSH_INTERVAL):
                        try:
                            logger.info("📊 美股开盘中，推送热点榜单...")
                            movers = movers_fetcher.fetch(count=5)
                            if movers:
                                analysis = analyzer.analyze_movers(llm_client, movers, models)
                                sender.send_market_movers(webhook, movers, analysis, secret)
                                last_market_push = now
                        except Exception as e:
                            logger.error("美股热点推送异常: %s", e)
                else:
                    market_open_since = 0.0
                    last_market_push = 0.0

            except Exception as e:
                logger.error("主循环异常: %s", e)
            time.sleep(args.interval)
    else:
        run_once(llm_client, webhook, secret, models, auth_token)


if __name__ == "__main__":
    main()
