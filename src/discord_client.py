import asyncio
import json
import logging
import random

import aiohttp

log = logging.getLogger(__name__)

GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"

OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_PRESENCE_UPDATE = 3
OP_HEARTBEAT_ACK = 11


class DiscordClient:
    GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"

    def __init__(
        self,
        token: str,
        app_id: str = "1108588077900898414",
        lastfm_username: str = "",
        button_text: str = "",
        button_url: str = "",
    ):
        self._token = token
        self._app_id = app_id
        self._lastfm_username = lastfm_username
        self._button_text = button_text
        self._button_url = button_url
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._heartbeat_interval: float = 41.25
        self._heartbeat_task: asyncio.Task | None = None
        self._sequence: int | None = None
        self._connected = asyncio.Event()
        self._ready = asyncio.Event()
        self._session_id: str = ""
        self._other_sessions: set[str] = set()
        self._current_status: str = "offline"
        self._on_sessions_change: asyncio.Event | None = None

    def set_sessions_callback(self, event: asyncio.Event) -> None:
        self._on_sessions_change = event

    @property
    def has_other_sessions(self) -> bool:
        return len(self._other_sessions) > 0

    async def set_status(self, status: str) -> None:
        if status == self._current_status:
            return
        self._current_status = status
        if self._ready.is_set() and self._ws and not self._ws.closed:
            payload = {
                "op": OP_PRESENCE_UPDATE,
                "d": {
                    "since": None,
                    "activities": [],
                    "status": status,
                    "afk": False,
                },
            }
            try:
                await self._ws.send_json(payload)
            except Exception:
                pass

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession()
        while True:
            try:
                await self._run()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Gateway disconnesso: %s", e)
            self._connected.clear()
            self._ready.clear()
            self._other_sessions.clear()
            self._session_id = ""
            delay = min(2 ** (random.random() * 5), 60)
            log.info("Riconnessione tra %.1fs...", delay)
            await asyncio.sleep(delay)

    async def _run(self) -> None:
        self._ws = await self._session.ws_connect(GATEWAY_URL, max_msg_size=16 * 1024 * 1024)
        msg = await self._ws.receive()
        data = json.loads(msg.data)
        self._heartbeat_interval = data["d"]["heartbeat_interval"] / 1000.0
        await self._identify()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        try:
            await self._listen()
        finally:
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _identify(self) -> None:
        payload = {
            "op": OP_IDENTIFY,
            "d": {
                "token": self._token,
                "properties": {
                    "os": "linux",
                    "browser": "custom",
                    "device": "",
                },
                "presence": {
                    "status": "offline",
                    "afk": False,
                },
            },
        }
        await self._ws.send_json(payload)

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            try:
                await self._ws.send_json({
                    "op": OP_HEARTBEAT,
                    "d": self._sequence,
                })
            except Exception:
                break

    def _parse_sessions(self, sessions: list[dict]) -> None:
        self._other_sessions.clear()
        for s in sessions:
            sid = s.get("session_id", "")
            status = s.get("status", "offline")
            if sid and sid != self._session_id and status != "offline":
                self._other_sessions.add(sid)
        if self._on_sessions_change:
            self._on_sessions_change.set()

    async def _listen(self) -> None:
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                op = data.get("op")
                event = data.get("t")
                self._sequence = data.get("s", self._sequence)

                if op == 4:
                    log.error("INVALID SESSION (op 4)")
                    break
                elif op == OP_HEARTBEAT_ACK:
                    pass
                elif event == "READY":
                    d = data["d"]
                    self._session_id = d.get("session", "")
                    sessions = d.get("sessions", [])
                    self._parse_sessions(sessions)
                    log.info("Connesso (user: %s)", d.get("user", {}).get("id"))
                    self._ready.set()
                    self._connected.set()
                elif event == "SESSIONS_REPLACE":
                    sessions = data["d"]
                    self._parse_sessions(sessions)
                elif event == "RESUMED":
                    self._ready.set()
                    self._connected.set()
            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    async def set_presence(
        self,
        artist: str,
        title: str,
        album: str,
        url: str,
        start_time: float,
        duration: int,
    ) -> None:
        if not self._ready.is_set():
            return
        if self._ws.closed:
            return

        assets = {}
        if album:
            assets["large_text"] = album
            assets["small_text"] = artist

        buttons = ["Last.fm"]
        button_urls = [url]
        if self._button_text and self._button_url:
            buttons.append(self._button_text)
            button_urls.append(self._button_url)
        elif self._lastfm_username:
            buttons.append("Profile")
            button_urls.append(f"https://www.last.fm/user/{self._lastfm_username}")

        activity = {
            "application_id": self._app_id,
            "name": "some music",
            "type": 2,
            "state": artist,
            "details": title,
            "timestamps": {"start": int(start_time * 1000)},
            "assets": assets,
            "status_display_type": 1,
            "buttons": buttons,
            "metadata": {"button_urls": button_urls},
            "flags": 8,
        }

        payload = {
            "op": OP_PRESENCE_UPDATE,
            "d": {
                "since": None,
                "activities": [activity],
                "status": self._current_status,
                "afk": False,
            },
        }
        try:
            await self._ws.send_json(payload)
        except Exception as e:
            log.error("Errore invio presence: %s", e)

    async def clear_presence(self) -> None:
        if not self._ready.is_set():
            return
        payload = {
            "op": OP_PRESENCE_UPDATE,
            "d": {
                "since": None,
                "activities": [],
                "status": self._current_status,
                "afk": False,
            },
        }
        try:
            await self._ws.send_json(payload)
        except Exception as e:
            log.error("Errore pulizia presence: %s", e)

    async def close(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
