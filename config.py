"""Central config for the bot. Everything comes from .env (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Telegram credentials -------------------------------------------------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Numeric user id of the OWNER — the only account the bot takes commands from.
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# --- Rate limiting --------------------------------------------------------
DM_DELAY_SECONDS = float(os.getenv("DM_DELAY_SECONDS", "4"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "25"))
BATCH_PAUSE_SECONDS = float(os.getenv("BATCH_PAUSE_SECONDS", "60"))

# --- Paths ----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Everyone the bot may broadcast to (collected from join requests).
AUDIENCE_FILE = DATA_DIR / "audience.json"
# Channels whose join requests the bot answers (managed with /add and /remove).
CHANNELS_FILE = DATA_DIR / "channels.json"
# Reference to the owner's saved post (the thing that gets sent/broadcast).
SAVED_POST_FILE = DATA_DIR / "saved_post.json"
# Inline URL buttons attached to the post / broadcast (set via /setbutton).
BUTTONS_FILE = DATA_DIR / "buttons.json"

# Session file name (created on first login).
BOT_SESSION = str(BASE_DIR / "bot")


def require(*names: str) -> None:
    """Fail fast with a clear message if a required env var is missing."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise SystemExit(
            "Missing required config: "
            + ", ".join(missing)
            + "\nCopy .env.example to .env and fill it in."
        )
