#!/usr/bin/env python3
"""torrent_size_test.py – download the latest torrent and report its size via bencode parsing."""
import os
import sys
import json
from urllib.parse import urlparse

import feedparser
import requests
from dotenv import load_dotenv

load_dotenv()

RSS_URL = os.getenv("RSS_URL")

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


feed = feedparser.parse(RSS_URL)
if not feed.entries:
    print("⚠️ RSS feed empty or unreachable")
    sys.exit(2)

entry = feed.entries[0]
title = entry.get("title", "<no title>")
torrent_url = get_torrent_url(entry)
if not torrent_url:
    print("❌ No torrent URL found in latest entry")
    sys.exit(3)

resp = requests.get(torrent_url, timeout=30)
if resp.status_code != 200:
    print(f"❌ Torrent fetch failed: status {resp.status_code}")
    sys.exit(4)

size_bytes = parse_torrent_size(resp.content)

print(json.dumps({
    "title": title,
    "torrent_url": torrent_url,
    "size_bytes": size_bytes,
    "size_gb": size_bytes / (1024 ** 3) if size_bytes else None,
}, indent=2))
