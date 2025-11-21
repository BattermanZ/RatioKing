#!/usr/bin/env python3
"""telegram_test.py – send the same Telegram notification RatioKing would emit for the latest RSS item.

Run this to verify your TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are working without touching qBittorrent.
"""
import os
import sys
import logging
import html
from dotenv import load_dotenv
import feedparser
import requests

load_dotenv()

RSS_URL = os.getenv("RSS_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

logger = logging.getLogger("telegram_test")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
logger.addHandler(handler)


def notify_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")
        sys.exit(2)
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
        timeout=10,
    )
    if resp.status_code != 200:
        logger.error("❌ Telegram notify failed – status %s body %r", resp.status_code, resp.text)
        sys.exit(3)
    logger.info("📨 Telegram message sent: %s", message)


def main():
    if not RSS_URL:
        logger.error("❌ RSS_URL must be set")
        sys.exit(1)

    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        logger.error("⚠️ RSS feed empty or unreachable")
        sys.exit(4)

    entry = feed.entries[0]
    title = entry.get("title", "<no title>")
    size_bytes = entry.get("contentlength")
    size_text = "unknown size"
    try:
        if size_bytes:
            size_int = int(size_bytes)
            units = ["B", "KB", "MB", "GB", "TB", "PB"]
            sz = float(size_int)
            for unit in units:
                if abs(sz) < 1024.0:
                    size_text = f"{sz:.2f} {unit}"
                    break
                sz /= 1024.0
    except Exception:
        pass

    message = f"<b>📥 Added torrent</b>\n\n{html.escape(title)}\n\nSize: {size_text}"
    logger.info("Latest RSS item: %s (size: %s)", title, size_text)
    notify_telegram(message)


if __name__ == "__main__":
    main()
