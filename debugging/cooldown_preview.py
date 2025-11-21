#!/usr/bin/env python3
"""cooldown_preview.py – calculate and explain the cooldown for the latest RSS item.

Uses the same size/speed logic as ratioking: cooldown_seconds = ceil(size_bytes / (speed_MBps_bytes)).
Falls back to the legacy 2-hour cooldown if the size is unavailable or speed is zero.
"""
import math
import os
import sys
from dotenv import load_dotenv
import feedparser

load_dotenv()

RSS_URL = os.getenv("RSS_URL")
DOWNLOAD_SPEED_MBPS = float(os.getenv("DOWNLOAD_SPEED_MBPS", "10"))
DEFAULT_COOLDOWN = 2 * 60 * 60  # 2 h
SPEED_BYTES_PER_SEC = max(DOWNLOAD_SPEED_MBPS, 0) * 1024 * 1024

if not RSS_URL:
    print("❌ RSS_URL must be set (env or .env).")
    sys.exit(1)


def extract_torrent_size(entry):
    """Return content size in bytes, if present in feed entry."""
    candidates = [
        entry.get("contentlength"),
        entry.get("torrent", {}).get("contentlength") if entry.get("torrent") else None,
    ]
    for raw in candidates:
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def human_bytes(num):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num) < 1024:
            return f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} PB"


def main():
    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        print("⚠️ RSS feed empty or unreachable")
        sys.exit(2)

    entry = feed.entries[0]
    title = entry.get("title", "<no title>")
    size_bytes = extract_torrent_size(entry)

    print(f"Latest item: {title}")
    print(f"GUID: {entry.get('id') or entry.get('guid') or entry.get('link')}")

    if size_bytes:
        cooldown_seconds = math.ceil(size_bytes / SPEED_BYTES_PER_SEC) if SPEED_BYTES_PER_SEC > 0 else DEFAULT_COOLDOWN
        cooldown_minutes = cooldown_seconds / 60
        print("\nCooldown calculation:")
        print(f"  size = {human_bytes(size_bytes)} ({size_bytes} bytes)")
        print(f"  speed = {DOWNLOAD_SPEED_MBPS:.2f} MB/s → {SPEED_BYTES_PER_SEC:.0f} bytes/s")
        print(f"  formula: ceil(size_bytes / speed_bytes_per_sec)")
        print(f"  result: ceil({size_bytes} / {int(SPEED_BYTES_PER_SEC)}) = {cooldown_seconds} s ({cooldown_minutes:.1f} min)")
    else:
        print("\nCooldown calculation:")
        print("  size unavailable in feed → using fallback cooldown")
        print(f"  result: {DEFAULT_COOLDOWN} s ({DEFAULT_COOLDOWN/60:.1f} min)")


if __name__ == "__main__":
    main()
