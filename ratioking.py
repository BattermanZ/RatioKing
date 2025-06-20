#!/usr/bin/env python3
"""ratioking.py – production downloader with 3-rule logic.
Reads download parameters (save path, category, tags, share limits) from the
environment or .env file so you can tweak them without touching the code.
"""
import os
import sys
import json
import time
import logging
import calendar
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import feedparser
import requests

# ─── CONFIG ────────────────────────────────────────────────
QB_URL       = os.getenv("QB_URL", "http://127.0.0.1:8080")
QB_USER      = os.getenv("QB_USER", "admin")
QB_PASS      = os.getenv("QB_PASS", "adminadmin")
RSS_URL      = os.getenv("RSS_URL")
STATE_FILE   = os.getenv("STATE_FILE", "./ratioking.state.json")
INTERVAL_MIN = int(os.getenv("INTERVAL_MINUTES", "15"))
LOG_FILE     = os.getenv("LOG_FILE", "./ratioking.log")

# 🎯 User-tunable download parameters
SAVE_PATH            = os.getenv("SAVE_PATH", "/mnt/ratioking/avistaz")
CATEGORY             = os.getenv("CATEGORY", "avistaz")
TAGS                 = os.getenv("TAGS", "ratioking")
RATIO_LIMIT          = float(os.getenv("RATIO_LIMIT", "-1"))   # -1 = unlimited
SEEDING_TIME_LIMIT   = int(os.getenv("SEEDING_TIME_LIMIT", "-1"))  # -1 = unlimited

FRESH_WINDOW = 10 * 60      # 10 min
COOLDOWN     = 2 * 60 * 60  # 2 h

if not RSS_URL:
    print("❌ RSS_URL must be set (env or .env).")
    sys.exit(1)

# ─── LOGGING ───────────────────────────────────────────────
Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("ratioking")
logger.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")

fh = logging.FileHandler(LOG_FILE)
fh.setFormatter(fmt)
logger.addHandler(fh)

sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(fmt)
logger.addHandler(sh)

# ─── STATE ─────────────────────────────────────────────────
DEFAULT_STATE: Dict[str, Any] = {"last_guid": None, "last_dl_ts": 0}

def load_state(path: str) -> Dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text())
        return {**DEFAULT_STATE, **data}
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_STATE.copy()

def save_state(path: str, state: Dict[str, Any]):
    Path(path).write_text(json.dumps(state, indent=2))

# ─── HELPERS ───────────────────────────────────────────────

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
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return None if not parsed else int(time.time() - calendar.timegm(parsed))

# ─── CORE ─────────────────────────────────────────────────

def run_once():
    state = load_state(STATE_FILE)
    last_guid = state["last_guid"]
    last_dl_ts = state["last_dl_ts"]
    now = int(time.time())

    # Rule-3 ⏳ Cooldown
    if now - last_dl_ts < COOLDOWN:
        remaining = (COOLDOWN - (now - last_dl_ts)) // 60
        logger.info(f"⏳ Cooldown active – {remaining} min left → skip")
        return

    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        logger.warning("⚠️ RSS feed empty or unreachable")
        return

    entry = feed.entries[0]
    guid = entry.get("id") or entry.get("guid") or entry.get("link")

    # Rule-1 🆔 Duplicate
    if guid == last_guid:
        logger.info("🆔 Latest GUID already processed → skip")
        return

    # Rule-2 ⏱️ Freshness
    age_sec = get_entry_age_sec(entry)
    if age_sec is None or age_sec > FRESH_WINDOW:
        logger.info(f"⏱️ Age {age_sec/60:.1f} min > 10 min → skip")
        return

    torrent_url = get_torrent_url(entry)
    if not torrent_url:
        logger.error("❌ .torrent URL not found → skip")
        return

    # All rules passed – download
    logger.info("✅ Downloading: %s", entry.get("title", "<no title>"))

    session = requests.Session()
    login = session.post(
        f"{QB_URL}/api/v2/auth/login",
        data={"username": QB_USER, "password": QB_PASS},
        headers={"Referer": QB_URL}, timeout=10)
    if login.status_code != 200 or login.text.strip() != "Ok.":
        logger.error("❌ qBittorrent login failed (%s)", login.status_code)
        return
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
        headers={"Referer": QB_URL}, timeout=20)

    if add.status_code == 200:
        logger.info("📥 Torrent added successfully!")
        state["last_guid"] = guid
        state["last_dl_ts"] = now
        save_state(STATE_FILE, state)
        logger.info("💾 State saved – cooldown started (2 h)")
    else:
        logger.error("❌ Failed to add torrent (%s)", add.status_code)

# ─── ENTRY POINT ──────────────────────────────────────────
if __name__ == "__main__":
    logger.info("🚀 Starting ratioking – interval %d min", INTERVAL_MIN)
    while True:
        try:
            run_once()
        except Exception as exc:
            logger.exception("💥 Unexpected error: %s", exc)
        time.sleep(INTERVAL_MIN * 60)
