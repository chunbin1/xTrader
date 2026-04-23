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
    return os.path.join(base, f"seen_{handle}.json")


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

    feed = feedparser.parse(rss_url)
    new_posts = []

    for entry in feed.entries:
        pid = entry.get("id") or entry.get("link", "")
        if pid in seen:
            continue
        text = _clean(entry.get("summary", ""))
        # 过滤空帖、纯转帖链接、内容过短
        if not text or text.startswith("RT: https://") or len(text) < 20:
            seen.add(pid)
            continue
        try:
            pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)\
                .astimezone(CST).strftime("%Y-%m-%d %H:%M 北京时间")
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
        _save_seen(handle, seen)

    return list(reversed(new_posts))
