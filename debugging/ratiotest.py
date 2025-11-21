#!/usr/bin/env python3
"""ratiotest.py – simulation script with three rules

Time handling fix: convert RSS published/updated times to **UTC** using
`calendar.timegm`, because `feedparser` already normalises the tz offset to
UTC but `time.mktime` mistakenly treats it as local time. This removes the
~2‑hour skew you observed.
"""
import os
import sys
import json
import time
import logging
import calendar
import math
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import feedparser

# ─── CONFIG ────────────────────────────────────────────────
QB_URL       = os.getenv("QB_URL", "http://127.0.0.1:8080")
RSS_URL      = os.getenv("RSS_URL")
STATE_FILE   = os.getenv("STATE_FILE", "./ratiotest.state.json")
INTERVAL_MIN = int(os.getenv("INTERVAL_MINUTES", "15"))
LOG_FILE     = os.getenv("LOG_FILE", "./ratiotest.log")
DOWNLOAD_SPEED_MBPS = float(os.getenv("DOWNLOAD_SPEED_MBPS", "10"))

FRESH_WINDOW = 10 * 60      # 10 min
DEFAULT_COOLDOWN = 2 * 60 * 60  # 2 h fallback
SPEED_BYTES_PER_SEC = max(DOWNLOAD_SPEED_MBPS, 0) * 1024 * 1024

if not RSS_URL:
    print("❌ RSS_URL must be set (env or .env).")
    sys.exit(1)

# ─── LOGGING ───────────────────────────────────────────────
Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("ratiotest")
logger.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")

fh = logging.FileHandler(LOG_FILE)
fh.setFormatter(fmt)
logger.addHandler(fh)

sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(fmt)
logger.addHandler(sh)

# ─── STATE HELPERS ─────────────────────────────────────────
DEFAULT_STATE: Dict[str, Any] = {"last_guid": None, "last_dl_ts": 0, "cooldown_until": 0}

def load_state(path: str) -> Dict[str, Any]:
    try:
        return {**DEFAULT_STATE, **json.loads(Path(path).read_text())}
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_STATE.copy()

def save_state(path: str, state: Dict[str, Any]):
    Path(path).write_text(json.dumps(state, indent=2))

# ─── UTILS ─────────────────────────────────────────────────
def extract_torrent_size(entry) -> Optional[int]:
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


def calculate_cooldown_seconds(entry) -> int:
    size_bytes = extract_torrent_size(entry)
    if size_bytes and SPEED_BYTES_PER_SEC > 0:
        return max(math.ceil(size_bytes / SPEED_BYTES_PER_SEC), 0)
    return DEFAULT_COOLDOWN

def get_torrent_url(entry) -> Optional[str]:
    for enc in entry.get("enclosures", []):
        href = enc.get("href")
        if href and href.endswith(".torrent"):
            return href
    for link in entry.get("links", []):
        if link.get("type") in ("application/x-bittorrent", "application/octet-stream"):
            return link.get("href")
    link = entry.get("link")
    return link if link and link.endswith(".torrent") else None


def get_entry_age_sec(entry) -> Optional[int]:
    """Return age in seconds by converting struct_time to UTC epoch."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    # feedparser normalises parsed struct_time to UTC already → use calendar.timegm
    entry_ts = calendar.timegm(parsed)
    return int(time.time() - entry_ts)

# ─── CORE LOGIC ────────────────────────────────────────────

def run_once():
    state = load_state(STATE_FILE)
    last_guid = state["last_guid"]
    last_dl_ts = state["last_dl_ts"]
    cooldown_until = state.get("cooldown_until", last_dl_ts + DEFAULT_COOLDOWN)
    now = int(time.time())

    # Rule 3: cooldown first
    if now < cooldown_until:
        remaining = (cooldown_until - now) // 60
        logger.info(f"Rule‑3 cooldown active ({remaining} min left) → skip")
        return

    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        logger.warning("RSS feed empty or unreachable")
        return

    entry = feed.entries[0]
    guid = entry.get("id") or entry.get("guid") or entry.get("link")

    # Rule 1: duplicate check
    if guid == last_guid:
        logger.info("Rule‑1 newest GUID already processed → skip")
        return

    # Rule 2: freshness
    age_sec = get_entry_age_sec(entry)
    if age_sec is None or age_sec > FRESH_WINDOW:
        logger.info(f"Rule‑2: Torrent age is {age_sec/60:.1f} min > 10 min → skip")
        return

    torrent_url = get_torrent_url(entry)
    if not torrent_url:
        logger.error("Failed to extract .torrent URL → skip")
        return

    # All rules passed – simulate
    logger.info("All rules passed – would download: %s", entry.get("title", "<no title>"))
    logger.info("[SIMULATION] Would POST to %s/api/v2/torrents/add with URL: %s", QB_URL, torrent_url)

    # Update state
    cooldown_seconds = calculate_cooldown_seconds(entry)
    state["last_guid"] = guid
    state["last_dl_ts"] = now
    state["cooldown_until"] = now + cooldown_seconds
    save_state(STATE_FILE, state)
    if cooldown_seconds == DEFAULT_COOLDOWN:
        logger.info("State updated → fallback cooldown %.1f min", DEFAULT_COOLDOWN / 60)
    else:
        size_bytes = extract_torrent_size(entry) or 0
        size_gb = size_bytes / (1024 ** 3)
        logger.info("State updated → cooldown %.1f min for %.2f GB @ %.2f MB/s",
                    cooldown_seconds / 60, size_gb, DOWNLOAD_SPEED_MBPS)

# ─── MAIN LOOP ─────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("Starting ratiotest (interval %d min)", INTERVAL_MIN)
    while True:
        try:
            run_once()
        except Exception as exc:
            logger.exception("Unexpected error: %s", exc)
        time.sleep(INTERVAL_MIN * 60)
