#!/usr/bin/env python3
"""rss_force_download.py – inject the newest RSS item directly into qBittorrent.

Useful for debugging qBittorrent responses without the RatioKing rule engine.
"""
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import feedparser
import requests
from dotenv import load_dotenv

load_dotenv()

QB_URL = os.getenv("QB_URL")
QB_USER = os.getenv("QB_USER")
QB_PASS = os.getenv("QB_PASS")
RSS_URL = os.getenv("RSS_URL")
SAVE_PATH = os.getenv("SAVE_PATH", "/mnt/ratioking/avistaz")
CATEGORY = os.getenv("CATEGORY", "avistaz")
TAGS = os.getenv("TAGS", "ratioking")
RATIO_LIMIT = float(os.getenv("RATIO_LIMIT", "-1"))
SEEDING_TIME_LIMIT = int(os.getenv("SEEDING_TIME_LIMIT", "-1"))

REQUIRED = {
    "QB_URL": QB_URL,
    "QB_USER": QB_USER,
    "QB_PASS": QB_PASS,
    "RSS_URL": RSS_URL,
}

missing = [key for key, value in REQUIRED.items() if not value]
if missing:
    print(f"❌ Missing required env vars: {', '.join(missing)}")
    sys.exit(1)

logger = logging.getLogger("rss_force_download")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
logger.addHandler(handler)

LOG_FILE = Path(os.getenv("FORCE_LOG_FILE", "./logs/rss_force_download.log"))
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
logger.addHandler(file_handler)


def get_torrent_url(entry) -> Optional[str]:
    for enclosure in entry.get("enclosures", []):
        href = enclosure.get("href")
        if href and href.endswith(".torrent"):
            return href
    for link in entry.get("links", []):
        if link.get("type") in ("application/x-bittorrent", "application/octet-stream"):
            return link.get("href")
    link = entry.get("link")
    return link if link and link.endswith(".torrent") else None


def main():
    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        logger.error("⚠️ RSS feed empty or unreachable")
        sys.exit(2)

    entry = feed.entries[0]
    title = entry.get("title", "<no title>")
    guid = entry.get("id") or entry.get("guid") or entry.get("link")
    torrent_url = get_torrent_url(entry)
    if not torrent_url:
        logger.error("❌ Could not find .torrent URL in feed entry")
        sys.exit(3)

    logger.info("Attempting to download latest item: %s", title)
    logger.info("GUID: %s", guid)
    logger.info("Torrent URL: %s", torrent_url)

    session = requests.Session()
    login = session.post(
        f"{QB_URL}/api/v2/auth/login",
        data={"username": QB_USER, "password": QB_PASS},
        headers={"Referer": QB_URL},
        timeout=10,
    )
    login_body = login.text.strip()
    if login.status_code != 200 or login_body != "Ok.":
        logger.error("❌ qBittorrent login failed – status %s body %r", login.status_code, login_body)
        sys.exit(4)
    logger.info("🔑 Authenticated to qBittorrent")

    add = session.post(
        f"{QB_URL}/api/v2/torrents/add",
        data={
            "urls": torrent_url,
            "savepath": SAVE_PATH,
            "category": CATEGORY,
            "tags": TAGS,
            "ratioLimit": RATIO_LIMIT,
            "seedingTimeLimit": SEEDING_TIME_LIMIT,
        },
        headers={"Referer": QB_URL},
        timeout=20,
    )
    add_body = (add.text or "").strip()
    if add.status_code == 200 and add_body in ("Ok.", "Ok"):
        logger.info("📥 Torrent accepted by qBittorrent (body=%r)", add_body)
    else:
        logger.error("❌ qBittorrent rejected torrent – status %s body %r", add.status_code, add_body)
        sys.exit(5)


if __name__ == "__main__":
    main()
