import json
import os
import logging
from datetime import datetime, timezone, timedelta

from Scweet.client import Scweet
from Scweet.config import ScweetConfig
from Scweet.exceptions import AuthError, AccountSessionAuthError, AccountPoolExhausted

logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8))


class CookieExpiredError(Exception):
    """X Cookie 失效，需要重新登录。"""


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


def fetch(account: dict, auth_token: str, limit: int = 20) -> list[dict]:
    """抓取 X 用户推文，返回新推文列表。Cookie 失效时抛 CookieExpiredError。"""
    handle = account["handle"]
    seen = _load_seen(handle)

    try:
        client = Scweet(
            auth_token=auth_token,
            config=ScweetConfig(
                daily_requests_limit=500,
                daily_tweets_limit=5000,
            ),
        )
        tweets = client.get_profile_tweets(handle, limit=limit)
    except (AuthError, AccountSessionAuthError, AccountPoolExhausted) as e:
        raise CookieExpiredError(str(e)) from e

    new_tweets = []
    for t in tweets:
        tid = t.get("id") or t.get("tweet_id") or t.get("url", "")
        if tid in seen:
            continue
        text = t.get("text") or t.get("full_text", "")
        text = " ".join(text.split())  # 折叠换行/多余空白为单个空格
        if not text or len(text) < 10:
            seen.add(tid)
            continue
        raw_time = t.get("timestamp") or t.get("created_at", "")
        try:
            pub = datetime.strptime(raw_time, "%a %b %d %H:%M:%S +0000 %Y")\
                .replace(tzinfo=timezone.utc).astimezone(CST)\
                .strftime("%Y-%m-%d %H:%M 北京时间")
        except Exception:
            pub = raw_time
        new_tweets.append({
            "id": tid,
            "text": text,
            "link": t.get("tweet_url") or t.get("url") or f"https://x.com/{handle}/status/{tid}",
            "published": pub,
        })
        seen.add(tid)

    if new_tweets:
        _save_seen(handle, seen)

    return list(reversed(new_tweets))
