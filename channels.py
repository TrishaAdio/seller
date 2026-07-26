"""Registered channels — the chats whose join requests the bot acts on.

The owner manages the list at runtime from the bot:

    /add -1001234567890      (or @publicchannel)
    /remove -1001234567890
    /chats

Stored in data/channels.json as {"<chat_id>": "<title>"}. While the list is
empty the bot acts on join requests from EVERY chat it administers; as soon as
one chat is added, only registered chats are handled.
"""
from __future__ import annotations

import json

import config


def _load() -> dict[int, str]:
    if config.CHANNELS_FILE.exists():
        try:
            raw = json.loads(config.CHANNELS_FILE.read_text())
            return {int(k): (v or "") for k, v in raw.items()}
        except (ValueError, OSError, TypeError, AttributeError):
            return {}
    return {}


def _save(chats: dict[int, str]) -> None:
    config.CHANNELS_FILE.write_text(
        json.dumps({str(k): v for k, v in sorted(chats.items())}, ensure_ascii=False)
    )


def parse_ident(text: str):
    """Turn owner input into a chat id (int) or a public ident (str).

    Accepts  -1001234567890 , 1234567890 (bare channel id, normalised to the
    -100 form), @username , or a t.me link. Returns None if unusable.
    """
    t = (text or "").strip()
    if not t:
        return None
    if t.startswith("@") or "t.me/" in t:
        return t
    body = t[1:] if t.startswith("-") else t
    if not body.isdigit():
        return None
    n = int(t)
    if n > 0:  # bare channel id copied from a client — add the -100 prefix
        n = int(f"-100{n}")
    return n


def add(chat_id: int, title: str = "") -> bool:
    """Register a chat. Returns True if it was newly added."""
    chats = _load()
    chat_id = int(chat_id)
    new = chat_id not in chats
    if new or (title and not chats.get(chat_id)):
        chats[chat_id] = title or chats.get(chat_id, "")
        _save(chats)
    return new


def remove(chat_id: int) -> bool:
    """Unregister a chat. Returns True if it was there."""
    chats = _load()
    if int(chat_id) not in chats:
        return False
    chats.pop(int(chat_id))
    _save(chats)
    return True


def set_title(chat_id: int, title: str) -> None:
    chats = _load()
    if int(chat_id) in chats and title and chats[int(chat_id)] != title:
        chats[int(chat_id)] = title
        _save(chats)


def all_items() -> list[tuple[int, str]]:
    return sorted(_load().items())


def all_ids() -> list[int]:
    return sorted(_load())


def count() -> int:
    return len(_load())


def accepts(chat_id: int) -> bool:
    """True if join requests from this chat should be handled."""
    chats = _load()
    return not chats or int(chat_id) in chats
