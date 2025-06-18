#!/usr/bin/env python3
import os
import sys
import json
from dotenv import load_dotenv
import feedparser

# ─── LOAD ENV ──────────────────────────────────────────────
load_dotenv()
RSS_URL = os.getenv("RSS_URL")
if not RSS_URL:
    print("❌ Please set RSS_URL in your .env file.")
    sys.exit(1)

# ─── FETCH AND INSPECT RSS ─────────────────────────────────
feed = feedparser.parse(RSS_URL)
if feed.bozo:
    print(f"⚠️  Warning: feed parsing encountered issues: {feed.bozo_exception}")

output = []
for idx, entry in enumerate(feed.entries, start=1):
    item = {
        "index": idx,
        "id": entry.get("id"),
        "guid": entry.get("guid"),
        "link": entry.get("link"),
        "title": entry.get("title"),
        "published": entry.get("published"),
        "published_parsed": entry.get("published_parsed"),
        "updated": entry.get("updated", None),
        "updated_parsed": entry.get("updated_parsed", None),
        "enclosures": [{"href": e.get("href"), "type": e.get("type")} for e in entry.get("enclosures", [])],
        "links": [{"href": l.get("href"), "type": l.get("type")} for l in entry.get("links", [])],
    }
    output.append(item)

# Print JSON to stdout for inspection
print(json.dumps({"feed_title": feed.feed.get("title"), "entries": output}, indent=2, default=str))
