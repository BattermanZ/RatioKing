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
import math
import html
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
DOWNLOAD_SPEED_MBPS = float(os.getenv("DOWNLOAD_SPEED_MBPS", "10"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

# 🎯 User-tunable download parameters
SAVE_PATH            = os.getenv("SAVE_PATH", "/mnt/ratioking/avistaz")
CATEGORY             = os.getenv("CATEGORY", "avistaz")
TAGS                 = os.getenv("TAGS", "ratioking")
RATIO_LIMIT          = float(os.getenv("RATIO_LIMIT", "-1"))   # -1 = unlimited
SEEDING_TIME_LIMIT   = int(os.getenv("SEEDING_TIME_LIMIT", "-1"))  # -1 = unlimited

FRESH_WINDOW = 10 * 60      # 10 min
DEFAULT_COOLDOWN = 2 * 60 * 60  # 2 h fallback
SPEED_BYTES_PER_SEC = max(DOWNLOAD_SPEED_MBPS, 0) * 1024 * 1024

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
DEFAULT_STATE: Dict[str, Any] = {"last_guid": None, "last_dl_ts": 0, "cooldown_until": 0}

def load_state(path: str) -> Dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text())
        return {**DEFAULT_STATE, **data}
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_STATE.copy()

def save_state(path: str, state: Dict[str, Any]):
    Path(path).write_text(json.dumps(state, indent=2))

# ─── HELPERS ───────────────────────────────────────────────
def extract_torrent_size(entry) -> Optional[int]:
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


def calculate_cooldown_seconds(entry) -> int:
    size_bytes = extract_torrent_size(entry)
    if size_bytes and SPEED_BYTES_PER_SEC > 0:
        seconds = math.ceil(size_bytes / SPEED_BYTES_PER_SEC)
        return max(seconds, 0)
    return DEFAULT_COOLDOWN


def human_bytes(num: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num)
    for unit in units:
        if abs(size) < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} EB"


def notify_telegram(message: str):
    """Send a Telegram message if credentials are configured."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("⚠️ Telegram notify failed – status %s body %r", resp.status_code, resp.text)
    except Exception as exc:
        logger.warning("⚠️ Telegram notify raised %s", exc)

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
    cooldown_until = state.get("cooldown_until", last_dl_ts + DEFAULT_COOLDOWN)
    now = int(time.time())

    # Rule-3 ⏳ Cooldown
    if now < cooldown_until:
        remaining = (cooldown_until - now) // 60
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
    login_body = login.text.strip()
    if login.status_code != 200 or login_body != "Ok.":
        logger.error("❌ qBittorrent login failed – status %s body %r", login.status_code, login_body)
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

    add_body = (add.text or "").strip()
    if add.status_code == 200 and add_body in ("Ok.", "Ok"):
        logger.info("📥 Torrent added successfully!")
        cooldown_seconds = calculate_cooldown_seconds(entry)
        cooldown_minutes = cooldown_seconds / 60
        state["last_guid"] = guid
        state["last_dl_ts"] = now
        state["cooldown_until"] = now + cooldown_seconds
        save_state(STATE_FILE, state)
        if cooldown_seconds == DEFAULT_COOLDOWN:
            logger.info("💾 State saved – fallback cooldown %.1f min", DEFAULT_COOLDOWN / 60)
        else:
            size_bytes = extract_torrent_size(entry) or 0
            size_gb = size_bytes / (1024 ** 3)
            logger.info("💾 State saved – cooldown %.1f min for %.2f GB @ %.2f MB/s",
                        cooldown_minutes, size_gb, DOWNLOAD_SPEED_MBPS)
        size_bytes_msg = extract_torrent_size(entry)
        size_text = human_bytes(size_bytes_msg) if size_bytes_msg else "unknown size"
        title = html.escape(entry.get("title", "<no title>"))
        notify_telegram(f"<b>📥 Added torrent</b>\n\n{title}\n\nSize: {size_text}")
    else:
        logger.error("❌ Failed to add torrent – status %s body %r", add.status_code, add_body)

# ─── ENTRY POINT ──────────────────────────────────────────
if __name__ == "__main__":
    logger.info("🚀 Starting ratioking – interval %d min", INTERVAL_MIN)
    while True:
        try:
            run_once()
        except Exception as exc:
            logger.exception("💥 Unexpected error: %s", exc)
        time.sleep(INTERVAL_MIN * 60)
