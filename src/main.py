import asyncio
import logging
import signal
import time

import aiohttp

from .config import Config
from .lastfm import LastFMClient
from .discord_client import DiscordClient

log = logging.getLogger("lastfm-rpc")


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if level == "DEBUG":
        logging.getLogger("httpx").setLevel(logging.DEBUG)
        logging.getLogger("pylast").setLevel(logging.DEBUG)
    else:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("pylast").setLevel(logging.WARNING)


def _resolve_status(is_playing: bool) -> str:
    return "dnd" if is_playing else "offline"


async def poll_loop(
    config: Config,
    discord: DiscordClient,
    lastfm: LastFMClient,
    state: dict,
) -> None:
    while True:
        try:
            track = await lastfm.get_now_playing()

            if track is None:
                if state["track"] is not None:
                    log.info("Stop: %s", state["track"].display)
                    state["track"] = None
                    state["start"] = 0.0
                    state["id"] = None
                    if not discord.has_other_sessions:
                        await discord.clear_presence()
                        await discord.set_status(_resolve_status(False))
            else:
                track_id = f"{track.artist}:{track.title}"
                if track_id != state["id"]:
                    log.info("Playing: %s [%s]", track.display, track.album or "N/A")
                    state["start"] = time.time()
                    state["id"] = track_id
                    state["track"] = track
                    if not discord.has_other_sessions:
                        await discord.set_status("dnd")

                if not discord.has_other_sessions:
                    await discord.set_presence(
                        artist=track.artist,
                        title=track.title,
                        album=track.album,
                        url=track.url,
                        start_time=state["start"],
                        duration=track.duration,
                    )

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("Poll error: %s", e)

        await asyncio.sleep(config.poll_interval)


async def session_watcher(discord: DiscordClient, state: dict) -> None:
    event = asyncio.Event()
    discord.set_sessions_callback(event)
    while True:
        await event.clear()
        await event.wait()

        if discord.has_other_sessions:
            await discord.set_status("offline")
            await discord.clear_presence()
            continue

        is_playing = state["track"] is not None
        await discord.set_status(_resolve_status(is_playing))
        if is_playing:
            track = state["track"]
            await discord.set_presence(
                artist=track.artist,
                title=track.title,
                album=track.album,
                url=track.url,
                start_time=state["start"],
                duration=track.duration,
            )
        else:
            await discord.clear_presence()


async def main() -> None:
    config = Config.from_env()
    setup_logging(config.log_level)

    async with aiohttp.ClientSession() as session:
        discord = DiscordClient(
            config.discord_token,
            config.app_id,
            config.lastfm_username,
            config.button_text,
            config.button_url,
        )
        lastfm = LastFMClient(config.lastfm_api_key, config.lastfm_username, session)

        state: dict = {"track": None, "start": 0.0, "id": None}

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

        discord_task = asyncio.create_task(discord.connect())
        poll_task = asyncio.create_task(poll_loop(config, discord, lastfm, state))
        session_task = asyncio.create_task(session_watcher(discord, state))

        await discord._connected.wait()
        await discord.set_status(_resolve_status(False))
        log.info("In ascolto su Last.fm (%s)...", config.lastfm_username)

        await stop.wait()
        poll_task.cancel()
        session_task.cancel()
        discord_task.cancel()
        await discord.close()
        try:
            await discord_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
