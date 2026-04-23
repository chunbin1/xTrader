#!/usr/bin/env python3.11
"""
社交媒体监控 → 智谱翻译分析 → 飞书推送

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
from zhipuai import ZhipuAI

import analyzer
import sender
from fetchers import truthsocial
from fetchers import x as x_fetcher
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


def process_account(account: dict, zhipu_client, webhook: str,
                    secret: str, model: str, auth_token: str) -> bool:
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
            result = analyzer.analyze(zhipu_client, post["text"], model)
        except Exception as e:
            logger.error("[%s] 翻译分析完全失败，跳过推送: %s", name, e)
            continue
        sender.send(webhook, account, post, result, secret, model)
        time.sleep(1)

    return True


def run_once(zhipu_client, webhook: str, secret: str, model: str, auth_token: str):
    accounts = load_accounts()
    for account in accounts:
        process_account(account, zhipu_client, webhook, secret, model, auth_token)


def main():
    parser = argparse.ArgumentParser(description="社交媒体监控推送飞书")
    parser.add_argument("--watch", action="store_true", help="持续监控模式")
    parser.add_argument("--interval", type=int,
                        default=int(os.getenv("POLL_INTERVAL", "120")),
                        help="轮询间隔（秒），默认读取 .env 中的 POLL_INTERVAL")
    args = parser.parse_args()

    zhipu_key = os.getenv("ZHIPU_API_KEY")
    webhook = os.getenv("FEISHU_WEBHOOK_URL")
    secret = os.getenv("FEISHU_SECRET", "")
    model = os.getenv("ZHIPU_MODEL", "glm-4-flash")
    auth_token = os.getenv("X_AUTH_TOKEN", "")

    if not zhipu_key:
        raise SystemExit("❌ 请在 .env 中设置 ZHIPU_API_KEY")
    if not webhook:
        raise SystemExit("❌ 请在 .env 中设置 FEISHU_WEBHOOK_URL")

    zhipu_client = ZhipuAI(api_key=zhipu_key)

    quiet = os.getenv("QUIET_HOURS", "")

    if args.watch:
        logger.info("🚀 监控启动，间隔 %ds，共 %d 个账号%s",
                    args.interval, len(load_accounts()),
                    f"，免打扰时段 {quiet}" if quiet else "")
        while True:
            try:
                if in_quiet_hours(quiet):
                    logger.info("😴 当前处于免打扰时段（%s），跳过本轮", quiet)
                else:
                    run_once(zhipu_client, webhook, secret, model, auth_token)
            except Exception as e:
                logger.error("主循环异常: %s", e)
            time.sleep(args.interval)
    else:
        run_once(zhipu_client, webhook, secret, model, auth_token)


if __name__ == "__main__":
    main()
