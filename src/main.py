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
                    log.info("Fine riproduzione: %s", state["track"].display)
                    await discord.clear_presence()
                    state["track"] = None
                    state["start"] = 0.0
                    state["id"] = None
            else:
                track_id = f"{track.artist}:{track.title}"
                if track_id != state["id"]:
                    log.info("Now playing: %s [%s]", track.display, track.album or "N/A")
                    state["start"] = time.time()
                    state["id"] = track_id
                    state["track"] = track

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


async def dnd_watcher(discord: DiscordClient, state: dict) -> None:
    event = asyncio.Event()
    discord.set_dnd_callback(event)
    while True:
        await event.clear()
        await event.wait()
        log.info("Cambio status -> %s", "DND" if discord.is_dnd else "online")
        track = state["track"]
        if track:
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
    log.info("Avvio Last.fm -> Discord RPC per %s", config.lastfm_username)

    async with aiohttp.ClientSession() as session:
        discord = DiscordClient(config.discord_token, config.app_id, config.lastfm_username)
        lastfm = LastFMClient(config.lastfm_api_key, config.lastfm_username, session)

        state: dict = {"track": None, "start": 0.0, "id": None}

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

        discord_task = asyncio.create_task(discord.connect())
        poll_task = asyncio.create_task(poll_loop(config, discord, lastfm, state))
        dnd_task = asyncio.create_task(dnd_watcher(discord, state))

        log.info("In attesa di connessione Discord Gateway...")
        await discord._connected.wait()
        log.info("Gateway connesso. Status iniziale: %s", "DND" if discord.is_dnd else "online")
        log.info("Avvio polling Last.fm...")

        await stop.wait()
        log.info("Shutdown in corso...")
        poll_task.cancel()
        dnd_task.cancel()
        discord_task.cancel()
        await discord.close()
        try:
            await discord_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
