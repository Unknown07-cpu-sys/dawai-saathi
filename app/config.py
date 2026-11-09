"""Settings for Dawai Saathi, read from environment variables and the .env file.

Why a file just for settings? So no other file needs to know where a setting or a
secret comes from. Every other module simply does:

    from app.config import settings
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# The project folder: the one that contains app/, tests/ and data/
BASE_DIR = Path(__file__).resolve().parent.parent

# Read the .env file if it exists. A real environment variable wins over .env.
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_url: str
    max_call_attempts: int
    sarvam_api_key: str


def load_settings() -> Settings:
    default_db_file = BASE_DIR / "data" / "dawai.db"
    return Settings(
        app_name="Dawai Saathi",
        # "or" (not a default argument) so an empty DATABASE_URL= line also falls back.
        # as_posix() writes forward slashes, which SQLAlchemy accepts on Windows too.
        database_url=os.getenv("DATABASE_URL") or f"sqlite:///{default_db_file.as_posix()}",
        # An initial attempt plus one retry: two attempts in total (project requirement).
        max_call_attempts=2,
        # Empty until Milestone 5. This value must never be printed or logged.
        sarvam_api_key=os.getenv("SARVAM_API_KEY", ""),
    )


settings = load_settings()
