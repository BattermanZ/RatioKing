#!/usr/bin/env python3
"""telegram_cooldown_test.py – send the full cooldown Telegram message for the latest RSS item."""
import html
import os
import sys
import time
from urllib.parse import urlparse

import feedparser
import requests
from dotenv import load_dotenv

load_dotenv()

RSS_URL = os.getenv("RSS_URL")
DOWNLOAD_SPEED_MBPS = float(os.getenv("DOWNLOAD_SPEED_MBPS", "10"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SPEED_BYTES_PER_SEC = max(DOWNLOAD_SPEED_MBPS, 0) * 1024 * 1024
DEFAULT_COOLDOWN = 2 * 60 * 60

if not RSS_URL:
    print("❌ RSS_URL must be set")
    sys.exit(1)


def bdecode(data: bytes, idx: int = 0):
    token = data[idx:idx+1]
    if not token:
        raise ValueError("unexpected end of data")
    if token == b"i":
        end = data.index(b"e", idx)
        return int(data[idx+1:end]), end + 1
    if token == b"l":
        idx += 1
        out = []
        while data[idx:idx+1] != b"e":
            val, idx = bdecode(data, idx)
            out.append(val)
        return out, idx + 1
    if token == b"d":
        idx += 1
        out = {}
        while data[idx:idx+1] != b"e":
            key, idx = bdecode(data, idx)
            val, idx = bdecode(data, idx)
            out[key] = val
        return out, idx + 1
    if token.isdigit():
        colon = data.index(b":", idx)
        length = int(data[idx:colon])
        start = colon + 1
        end = start + length
        return data[start:end], end
    raise ValueError(f"unexpected token at {idx}: {token!r}")


def parse_torrent_size(torrent_bytes: bytes):
    decoded, _ = bdecode(torrent_bytes, 0)
    if not isinstance(decoded, dict):
        return None
    info = decoded.get(b"info")
    if not isinstance(info, dict):
        return None
    if b"length" in info and isinstance(info[b"length"], int):
        return info[b"length"]
    files = info.get(b"files")
    if isinstance(files, list):
        total = 0
        for f in files:
            if isinstance(f, dict) and isinstance(f.get(b"length"), int):
                total += f[b"length"]
        return total if total > 0 else None
    return None


def human_bytes(num: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num)
    for unit in units:
        if abs(size) < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} EB"


def get_torrent_url(entry):
    for enc in entry.get("enclosures", []):
        href = enc.get("href")
        if href and ".torrent" in urlparse(href).path:
            return href
    for link in entry.get("links", []):
        if link.get("type") in ("application/x-bittorrent", "application/octet-stream"):
            return link.get("href")
    link = entry.get("link")
    return link if link and ".torrent" in urlparse(link).path else None


def notify_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")
        sys.exit(2)
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"❌ Telegram send failed: status {resp.status_code} body {resp.text!r}")
        sys.exit(3)


feed = feedparser.parse(RSS_URL)
if not feed.entries:
    print("⚠️ RSS feed empty or unreachable")
    sys.exit(4)

entry = feed.entries[0]
title = entry.get("title", "<no title>")
torrent_url = get_torrent_url(entry)
if not torrent_url:
    print("❌ No torrent URL found in latest entry")
    sys.exit(5)

resp = requests.get(torrent_url, timeout=30)
if resp.status_code != 200:
    print(f"❌ Torrent fetch failed: status {resp.status_code}")
    sys.exit(6)

size_bytes = parse_torrent_size(resp.content)
size_text = human_bytes(size_bytes) if size_bytes else "unknown size"

if size_bytes and SPEED_BYTES_PER_SEC > 0:
    cooldown_seconds = max(int((size_bytes + SPEED_BYTES_PER_SEC - 1) // SPEED_BYTES_PER_SEC), 0)
else:
    cooldown_seconds = DEFAULT_COOLDOWN
cooldown_minutes = cooldown_seconds / 60
ends_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + cooldown_seconds))

message = (
    f"<b>📥 Added torrent</b>\n\n"
    f"{html.escape(title)}\n\n"
    f"Size: {size_text}\n"
    f"Cooldown: {cooldown_minutes:.1f} min\n"
    f"Ends: {ends_at}"
)

print("Sending message:\n", message)
notify_telegram(message)
print("✅ Telegram message sent.")
