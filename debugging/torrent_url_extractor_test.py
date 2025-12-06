#!/usr/bin/env python3
"""torrent_url_extractor_test.py – extract torrent URLs and GUIDs from the latest feed items."""
import json
import os
import sys
from urllib.parse import urlparse

import feedparser
from dotenv import load_dotenv

load_dotenv()
RSS_URL = os.getenv("RSS_URL")

if not RSS_URL:
    print("❌ RSS_URL must be set")
    sys.exit(1)


def get_torrent_url(entry):
    # Prefer enclosures
    for enc in entry.get("enclosures", []):
        href = enc.get("href")
        if href and ".torrent" in urlparse(href).path:
            return href
    # Prefer typed links
    for link in entry.get("links", []):
        if link.get("type") in ("application/x-bittorrent", "application/octet-stream"):
            return link.get("href")
    # Fallback to main link if it looks like a torrent link even with query params
    link = entry.get("link")
    if link and ".torrent" in urlparse(link).path:
        return link
    return None


def get_guid(entry):
    guid = entry.get("id") or entry.get("guid") or entry.get("link")
    return guid


feed = feedparser.parse(RSS_URL)
if not feed.entries:
    print("⚠️ No entries found or feed unreachable")
    sys.exit(2)

output = []
for entry in feed.entries[:10]:
    output.append({
        "title": entry.get("title"),
        "guid": get_guid(entry),
        "torrent_url": get_torrent_url(entry),
        "enclosures": entry.get("enclosures"),
        "links_types": [{k: v for k, v in l.items() if k in ("href", "type")} for l in entry.get("links", [])],
    })

print(json.dumps(output, indent=2, default=str))
