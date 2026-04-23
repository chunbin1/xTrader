#!/usr/bin/env python3.11
import feedparser
import re
import json
from datetime import datetime

RSS_URL = "https://trumpstruth.org/feed"

def clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()

def fetch_posts(limit: int = 10) -> list[dict]:
    feed = feedparser.parse(RSS_URL)
    posts = []
    for entry in feed.entries[:limit]:
        text = clean_html(entry.get("summary", ""))
        if not text:
            continue
        posts.append({
            "id": entry.get("id", ""),
            "text": text,
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
        })
    return posts

if __name__ == "__main__":
    print(f"正在抓取 Truth Social RSS...\n")
    posts = fetch_posts(limit=10)
    print(f"共获取 {len(posts)} 条帖子\n")
    for i, p in enumerate(posts, 1):
        print(f"{'='*60}")
        print(f"[{i}] {p['published']}")
        print(f"内容: {p['text'][:300]}")
        print(f"链接: {p['link']}")
    print(f"{'='*60}")
