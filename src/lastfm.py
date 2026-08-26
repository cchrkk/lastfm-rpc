import asyncio
import logging
from dataclasses import dataclass

import aiohttp
import pylast

log = logging.getLogger(__name__)


@dataclass
class Track:
    artist: str
    title: str
    album: str
    duration: int
    url: str

    @property
    def display(self) -> str:
        return f"{self.artist} - {self.title}"


class LastFMClient:
    def __init__(self, api_key: str, username: str, session: aiohttp.ClientSession):
        self._api_key = api_key
        self._username = username
        self._network = pylast.LastFMNetwork(api_key=api_key)
        self._user = self._network.get_user(username)
        self._session = session

    def _get_track_sync(self) -> Track | None:
        track = self._user.get_now_playing()
        if track is None:
            return None

        duration = 0
        try:
            duration = int(track.duration / 1000) if track.duration else 0
        except Exception:
            pass

        album_name = ""
        try:
            album_name = track.album.name if track.album else ""
        except Exception:
            pass

        return Track(
            artist=track.artist.name,
            title=track.title,
            album=album_name,
            duration=duration,
            url=track.get_url(),
        )

    async def get_now_playing(self) -> Track | None:
        try:
            return await asyncio.to_thread(self._get_track_sync)
        except Exception as e:
            log.error("Last.fm poll error: %s", e)
            return None
