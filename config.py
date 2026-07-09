"""Central config + tiny helpers shared by the bot and the userbot.

Everything is read from environment variables (see .env.example).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Telegram credentials -------------------------------------------------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Numeric user id of the OWNER — the only account allowed to run /broadcast.
# setup.py fills this in automatically from the userbot login.
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# --- Channel + message ----------------------------------------------------
SOURCE_CHANNEL = os.getenv("SOURCE_CHANNEL", "")

# NEW_CHANNEL_LINK and DM_MESSAGE are OPTIONAL. The primary content is the
# "saved post" the owner sets with /setpost (any message: video/photo/text,
# premium emoji — everything lives in that post). These two are only used as a
# fallback text template when NO saved post exists.
NEW_CHANNEL_LINK = os.getenv("NEW_CHANNEL_LINK", "")
# \n in the .env is literal; turn it into a real newline.
DM_MESSAGE = os.getenv("DM_MESSAGE", "").replace("\\n", "\n")

# --- Rate limiting --------------------------------------------------------
DM_DELAY_SECONDS = float(os.getenv("DM_DELAY_SECONDS", "4"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "25"))
BATCH_PAUSE_SECONDS = float(os.getenv("BATCH_PAUSE_SECONDS", "60"))

# --- Paths ----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Where the userbot dumps pending requesters, and where the bot tracks sends.
PENDING_FILE = DATA_DIR / "pending_users.json"
SENT_FILE = DATA_DIR / "sent.json"
FAILED_FILE = DATA_DIR / "failed.json"
# Accumulated set of everyone we can broadcast to (requesters, live joiners).
AUDIENCE_FILE = DATA_DIR / "audience.json"
# Reference to the owner's saved post (the thing that gets broadcast).
SAVED_POST_FILE = DATA_DIR / "saved_post.json"

# Session file names (created on first login).
USERBOT_SESSION = str(BASE_DIR / "userbot")
BOT_SESSION = str(BASE_DIR / "bot")


def channel_ident():
    """SOURCE_CHANNEL as an int id when numeric (e.g. -1004363487750), else the
    raw string (username / invite link). Passing an int makes Telethon treat it
    as a peer id instead of trying to resolve it as a username."""
    s = SOURCE_CHANNEL.strip()
    if not s:
        return s
    body = s[1:] if s.startswith("-") else s
    return int(s) if body.isdigit() else s


def has_text_template() -> bool:
    """True if a fallback DM text template is configured."""
    return bool(DM_MESSAGE.strip())


def render_message(first_name: str | None) -> str:
    """Fill the fallback DM template with the user's name and the invite link."""
    name = (first_name or "there").strip() or "there"
    return DM_MESSAGE.format(name=name, link=NEW_CHANNEL_LINK)


def require(*names: str) -> None:
    """Fail fast with a clear message if a required env var is missing."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise SystemExit(
            "Missing required config: "
            + ", ".join(missing)
            + "\nCopy .env.example to .env and fill it in."
        )
