# RatioKing

**Automated RSS‑to‑qBittorrent downloader** with three-rule logic, containerised in a lightweight multi-stage Alpine Docker image.

---

## Table of Contents

* [Features](#features)
* [Architecture](#architecture)
* [Requirements](#requirements)
* [Configuration](#configuration)
* [Setup & Installation](#setup--installation)
* [Running Locally](#running-locally)
* [Docker](#docker)

  * [Building the Image](#building-the-image)
  * [docker-compose](#docker-compose)
* [Logging & State](#logging--state)
* [Customization](#customization)
* [Troubleshooting](#troubleshooting)

---

## Features

* Polls a torrent RSS feed at configurable intervals.
* Applies three rules before downloading:

  1. ✅ Skip if the torrent GUID was already processed.
  2. ⏱️ Skip if the torrent is older than 10 minutes.
  3. ⏳ Skip if a download occurred too recently (cooldown derived from torrent size ÷ configured download speed, fallback 2 h).
* Optional Telegram notification when a torrent is added.
* Downloads new torrents via the qBittorrent WebAPI with custom parameters (save path, category, tags, share ratio, seeding time).
* Logs actions and reasons for skips with emojis for clarity.
* Persists state in a JSON file (last GUID and timestamp).
* Configurable entirely via environment variables or a `.env` file.
* Containerised using a minimal multi-stage Alpine Docker image (\~40 MB).

---

## Architecture

```
+--------------+           +-----------------+                    +-------------+
|              |   HTTP    |                 |   qBittorrent API  |             |
|  ratioking   | --------> | qBittorrent Web | <----------------- | qBittorrent |
|   script     |           |     API         |                    |   daemon    |
|   (Python)   |           |                 |                    |             |
+--------------+           +-----------------+                    +-------------+
        ^                                                         /
        |                                                        /
        | cron / loop                                          RSS
        v                                                      /
    state.json  <----  RSS Feed XML  <------------------------
```

1. The script runs in a loop (every X minutes).
2. It loads `state.json` to check last download GUID and timestamp.
3. It fetches the RSS feed, picks the newest entry, and applies the three rules.
4. If all pass, it calls the qBittorrent WebAPI to add the torrent with configured options.
5. It updates `state.json` to record the download.
6. All actions and skips are logged to stdout and a log file.

---

## Requirements

* Python 3.12+
* `feedparser` (RSS parsing)
* `requests` (HTTP client)
* `python-dotenv` (optional, for `.env` loading)

*On Docker, everything is packaged—no host Python needed.*

---

## Configuration

Copy the provided `.env.example` to `.env` and fill in your values:

```dotenv
# qBittorrent API endpoint
QB_URL=http://localhost:8080

# qBittorrent WebUI credentials
QB_USER=user
QB_PASS=password

# Your torrent RSS feed
RSS_URL=https://url.com

# Script options
INTERVAL_MINUTES=5
LOG_FILE=./logs/ratioking.log
# STATE_FILE=./ratioking.state.json   # optional custom path
DOWNLOAD_SPEED_MBPS=10               # Size / speed = cooldown duration
TELEGRAM_BOT_TOKEN=                  # Optional: send alerts via Telegram
TELEGRAM_CHAT_ID=                    # Optional: recipient chat ID

# Download parameters
SAVE_PATH=/mnt/path/
CATEGORY=category
TAGS=tags
RATIO_LIMIT=-1           # -1 = unlimited ratio
SEEDING_TIME_LIMIT=-1    # -1 = no time limit
```

Each variable has a sensible default if not set.

---

## Setup & Installation

1. **Clone** the repository:

   ```bash
   git clone https://.../ratioking.git
   cd ratioking
   ```
2. **Create** a Python virtual environment (optional for local runs):

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Generate** `requirements.txt` automatically:

   ```bash
   pip install feedparser requests python-dotenv
   pip freeze --local > requirements.txt
   ```
4. **Copy** configuration:

   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

---

## Running Locally

```bash
# Activate venv if used
source .venv/bin/activate

# Install deps
pip install -r requirements.txt

# Run the downloader
python ratioking.py
```

Logs appear on stdout and in `LOG_FILE`. Press `Ctrl+C` to stop.

---

## Docker

### Building the Image

```bash
docker build -t ratioking:v101.0.0 .
```

### docker-compose

Use the provided `docker-compose.yml`:

```yaml
version: "3.8"
services:
  ratioking:
    image: ratioking:v101.0.0
    env_file:
      - .env
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
    networks:
      - docker_default

networks:
  docker_default:
    external: true
```

Launch:

```bash
docker-compose up -d
```

---

## Logging & State

* **Logs:** stdout (captured by Docker logs) and file (`LOG_FILE`).
* **State:** JSON in `STATE_FILE`:

  ```json
  { "last_guid": "<torrent GUID>", "last_dl_ts": 168XYZ }
  ```

---

## Customization

* Change timing constants in code for different intervals.
* Tweak download options via `.env` without code changes.
* Use a different RSS feed by updating `RSS_URL`.

---

## Troubleshooting

* **Skipping too much?** Check logs for which rule is firing (🆔, ⏱️, ⏳).
* **API errors?** Validate credentials & test `curl` against `QB_URL`.
* **Feed issues?** Run `rss_debug.py` to inspect feed structure.
* **Docker build fails?** Ensure `requirements.txt` is up to date.

---

Enjoy your automated downloads! 📥🚀
