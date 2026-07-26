"""The owner's saved post — a reference to ONE message the bot re-sends.

The owner uses /setpost (reply to a message) to save it. We only store the
message's location (chat_id + message_id); the actual content stays on
Telegram's servers, so we can re-send it verbatim (by file reference, no
re-upload) to any number of recipients — text, media, caption, premium emoji
and all.
"""
from __future__ import annotations

import json

import config


def save(chat_id: int, message_id: int) -> None:
    config.SAVED_POST_FILE.write_text(
        json.dumps({"chat_id": int(chat_id), "message_id": int(message_id)})
    )


def load() -> dict | None:
    if config.SAVED_POST_FILE.exists():
        try:
            data = json.loads(config.SAVED_POST_FILE.read_text())
            if "chat_id" in data and "message_id" in data:
                return data
        except (ValueError, OSError):
            return None
    return None


def clear() -> bool:
    """Remove the saved post. Returns True if there was one."""
    if config.SAVED_POST_FILE.exists():
        config.SAVED_POST_FILE.unlink()
        return True
    return False


def exists() -> bool:
    return load() is not None
