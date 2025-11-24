#!/usr/bin/env python3
"""rss_info_report.py – summarize fields provided for each torrent in the RSS feed."""
import json
import sys
from typing import Any, Dict, List

import feedparser
from dotenv import load_dotenv
import os

load_dotenv()
RSS_URL = os.getenv("RSS_URL")
if not RSS_URL:
    print("❌ Please set RSS_URL in your .env file.")
    sys.exit(1)


def prune(entry: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    return {k: entry.get(k) for k in keys if entry.get(k) is not None}


feed = feedparser.parse(RSS_URL)
if feed.bozo:
    print(f"⚠️  Warning: feed parsing encountered issues: {feed.bozo_exception}")

summary = {
    "feed_title": feed.feed.get("title"),
    "entries": [],
}

for idx, entry in enumerate(feed.entries, start=1):
    enclosures = [
        {"href": e.get("href"), "type": e.get("type"), "length": e.get("length")}
        for e in entry.get("enclosures", [])
    ]
    # Gather common torrent-related fields if present
    torrent_meta = prune(entry.get("torrent", {}) if entry.get("torrent") else {}, [
        "contentlength", "infohash", "filename", "magneturi"
    ])
    summary["entries"].append({
        "index": idx,
        "title": entry.get("title"),
        "id": entry.get("id"),
        "guid": entry.get("guid"),
        "link": entry.get("link"),
        "contentlength": entry.get("contentlength"),
        "infohash": entry.get("infohash"),
        "published": entry.get("published"),
        "enclosures": enclosures,
        "torrent": torrent_meta,
        "keys_present": sorted(entry.keys()),
    })

print(json.dumps(summary, indent=2, default=str))
