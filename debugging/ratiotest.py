#!/usr/bin/env python3
import os
import json
import sys
import time
import logging
from pathlib import Path

from dotenv import load_dotenv
import feedparser

# ─── LOAD ENV ──────────────────────────────────────────────
load_dotenv()

QB_URL       = os.getenv("QB_URL")
QB_USER      = os.getenv("QB_USER")
QB_PASS      = os.getenv("QB_PASS")
RSS_URL      = os.getenv("RSS_URL")
STATE_FILE   = os.getenv("STATE_FILE", "./ratiotest.state.json")
INTERVAL_MIN = int(os.getenv("INTERVAL_MINUTES", "15"))
LOG_FILE     = os.getenv("LOG_FILE", "./ratiotest.log")

# ─── VALIDATE CONFIG ───────────────────────────────────────
if not all([QB_URL, QB_USER, QB_PASS, RSS_URL]):
    print("❌ Please set QB_URL, QB_USER, QB_PASS and RSS_URL in your .env")
    sys.exit(1)

# ─── ENSURE LOG DIRECTORY ──────────────────────────────────
log_path = Path(LOG_FILE)
if log_path.parent and not log_path.parent.exists():
    log_path.parent.mkdir(parents=True, exist_ok=True)

# ─── SETUP LOGGING ─────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)
stream_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
stream_handler.setFormatter(stream_formatter)
logger.addHandler(stream_handler)

# ─── STATE HANDLING ────────────────────────────────────────
def load_state(path):
    if Path(path).is_file():
        try:
            return json.loads(Path(path).read_text())
        except json.JSONDecodeError:
            pass
    return {"last_guid": None}

def save_state(path, state):
    Path(path).write_text(json.dumps(state, indent=2))

# ─── RSS & SIMULATION LOGIC ───────────────────────────────
def run_once():
    state = load_state(STATE_FILE)
    last_guid = state.get("last_guid")

    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        logger.warning("RSS feed empty or unreachable")
        return

    # Only consider the newest entry
    entry = feed.entries[0]
    guid = entry.get("id") or entry.get("guid") or entry.get("link")

    if guid == last_guid:
        logger.info(f"No new torrents since last GUID: {last_guid}")
        return

    # extract torrent URL
    def get_torrent_url(e):
        for enc in e.get("enclosures", []):
            href = enc.get("href")
            if href and href.endswith(".torrent"):
                return href
        for link in e.get("links", []):
            if link.get("type") in ("application/x-bittorrent", "application/octet-stream"):
                return link.get("href")
        url = e.get("link")
        if url and url.endswith(".torrent"):
            return url
        return None

    torrent_url = get_torrent_url(entry)
    if not torrent_url:
        logger.error("Could not find a .torrent URL in the latest RSS entry")
        return

    logger.info(f"[SIMULATION] Found new torrent: {entry.title}")
    logger.info(f"[SIMULATION] Would send to qBittorrent API at {QB_URL}/api/v2/torrents/add with URL: {torrent_url}")

    # Simulate success and update state
    state["last_guid"] = guid
    save_state(STATE_FILE, state)
    logger.info("[SIMULATION] State updated, no actual download performed")

# ─── MAIN LOOP ─────────────────────────────────────────────
if __name__ == "__main__":
    logger.info(f"Starting ratiotest: interval {INTERVAL_MIN} min, logging to {LOG_FILE}")
    while True:
        try:
            run_once()
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
        time.sleep(INTERVAL_MIN * 60)
