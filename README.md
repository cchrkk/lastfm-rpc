# lastfm-rpc

Discord Rich Presence from Last.fm, with automatic DND status management. Runs as a Docker container on a VPS/server that's always on.

## Features

- **Rich Presence** — shows artist, track, album, progress bar, and Last.fm link on your Discord profile
- **Auto DND** — sets your status to Do Not Disturb when no other Discord device is online, switches back to Online when you connect from PC/phone
- **Lightweight** — Python + Alpine Docker image, ~50MB
- **Resilient** — auto-reconnect on disconnect, exponential backoff, log rotation

## How it works

```
Last.fm API  ──polling──>  Python  ──WebSocket──>  Discord Gateway
                             │                        │
                             └── session tracking ────┘
                                 (DND auto-switch)
```

The service connects to the Discord Gateway as **your user account** (self-bot) and directly updates your presence. It tracks your active sessions via the `SESSIONS_REPLACE` event to know when to switch between DND and Online.

## Requirements

- A **VPS or server** that's always on (Docker)
- A **Discord account**
- A **Last.fm account**
- A **Last.fm API key** — create one at https://www.last.fm/api/account/create

## Setup

### 1. Get your Discord User Token

1. Open Discord in your browser (https://discord.com/app)
2. Open DevTools (`F12` or `Ctrl+Shift+I`)
3. Go to **Network** tab
4. Filter by `gateway`
5. Refresh the page
6. Click any WebSocket request
7. Find the `Authorization` header in the request headers
8. Copy the token value

> **Warning:** This is a user token (self-bot). Discord's ToS technically prohibit automated user accounts. Use at your own risk.

### 2. Create a Last.fm API key

1. Go to https://www.last.fm/api/account/create
2. Fill in any app name/description
3. Copy the generated API key

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
DISCORD_TOKEN=your_discord_user_token
LASTFM_USERNAME=your_lastfm_username
LASTFM_API_KEY=your_lastfm_api_key
POLL_INTERVAL=30
LOG_LEVEL=INFO
```

### 4. Deploy

```bash
docker compose up -d --build
```

### 5. Check logs

```bash
docker compose logs -f
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | yes | — | Discord user token |
| `LASTFM_USERNAME` | yes | — | Last.fm username |
| `LASTFM_API_KEY` | yes | — | Last.fm API key |
| `POLL_INTERVAL` | no | `30` | Seconds between Last.fm polls |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## DND Logic

The service watches your Discord sessions:

| State | Your Status |
|---|---|
| No device connected (all PCs off) | **DND** |
| PC/phone connected | **Online** |

The music presence is always shown regardless of DND/Online status. When you're in DND, the "Listening to" activity still appears on your profile but with the DND indicator.

## Commands

```bash
# Start
docker compose up -d --build

# Stop
docker compose down

# Restart
docker compose restart

# Logs (follow)
docker compose logs -f

# Rebuild after code changes
docker compose up -d --build --force-recreate

# Check status
docker compose ps
```

## Project Structure

```
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── requirements.txt
├── README.md
└── src/
    ├── main.py            # entry point, orchestrates everything
    ├── config.py          # env var loading + validation
    ├── lastfm.py          # Last.fm API polling via pylast
    └── discord_client.py  # Discord Gateway WebSocket client
```

## License

MIT
