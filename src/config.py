import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    discord_token: str
    app_id: str
    lastfm_username: str
    lastfm_api_key: str
    poll_interval: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        token = os.environ.get("DISCORD_TOKEN", "").strip()
        app_id = os.environ.get("APP_ID", "").strip() or "1108588077900898414"
        username = os.environ.get("LASTFM_USERNAME", "").strip()
        api_key = os.environ.get("LASTFM_API_KEY", "").strip()
        poll_interval = int(os.environ.get("POLL_INTERVAL", "30"))
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

        missing = []
        if not token:
            missing.append("DISCORD_TOKEN")
        if not username:
            missing.append("LASTFM_USERNAME")
        if not api_key:
            missing.append("LASTFM_API_KEY")

        if missing:
            print(f"[FATAL] Variabili d'ambiente mancanti: {', '.join(missing)}")
            print("Copia .env.example in .env e compila i valori.")
            sys.exit(1)

        return cls(
            discord_token=token,
            app_id=app_id,
            lastfm_username=username,
            lastfm_api_key=api_key,
            poll_interval=max(poll_interval, 10),
            log_level=log_level,
        )
