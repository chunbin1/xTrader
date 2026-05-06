import re
import json
import os
import logging
import feedparser
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

logger = logging.getLogger(__name__)


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _seen_file(handle: str) -> str:
    base = os.path.dirname(os.path.dirname(__file__))
    data_dir = os.path.join(base, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, f"seen_{handle}.json")


def _load_seen(handle: str) -> set:
    path = _seen_file(handle)
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        return set(json.load(f))


def _save_seen(handle: str, seen: set):
    with open(_seen_file(handle), "w") as f:
        json.dump(list(seen), f)


def fetch(account: dict) -> list[dict]:
    """抓取 Truth Social RSS，返回新帖列表。"""
    handle = account["handle"]
    rss_url = account.get("rss_url", f"https://truthsocial.com/@{handle}.rss")
    seen = _load_seen(handle)
    seen_file = _seen_file(handle)

    logger.debug("[%s] 已读取 seen 文件: %s（%d 条记录）", handle, seen_file, len(seen))

    feed = feedparser.parse(rss_url)
    logger.debug("[%s] RSS 返回 %d 条条目", handle, len(feed.entries))

    new_posts = []
    skipped_seen = 0
    skipped_empty = 0

    for entry in feed.entries:
        pid = entry.get("id") or entry.get("link", "")
        if pid in seen:
            skipped_seen += 1
            continue
        text = _clean(entry.get("summary", ""))
        if not text or text.startswith("RT: https://") or len(text) < 20:
            logger.debug("[%s] 跳过空/转帖: %s", handle, pid)
            seen.add(pid)
            skipped_empty += 1
            continue
        try:
            pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)\
                .astimezone(CST).strftime("%Y-%m-%d %H:%M 北京时间")
        except Exception:
            pub = entry.get("published", "")

        logger.info("[%s] 新帖 ID=%s 时间=%s 内容=%s...",
                    handle, pid, pub, text[:40])
        new_posts.append({
            "id": pid,
            "text": text,
            "link": entry.get("link", ""),
            "published": pub,
        })
        seen.add(pid)

    logger.info("[%s] 本轮结果：新帖 %d 条，已读跳过 %d 条，空帖跳过 %d 条",
                handle, len(new_posts), skipped_seen, skipped_empty)

    if new_posts:
        _save_seen(handle, seen)
        logger.debug("[%s] seen 文件已更新，当前共 %d 条", handle, len(seen))

    return list(reversed(new_posts))
