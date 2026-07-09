"""Inline URL buttons attached to the post / broadcast (set via /setbutton).

Stored in data/buttons.json as a list of rows, each row a list of
{"text": ..., "url": ...}. Example on Telegram:

    /setbutton
    Join Channel - https://t.me/yourchannel
    Website - https://example.com | Support - https://t.me/support

- each line is a ROW of buttons
- within a line, "|" separates buttons on the same row
- each button is  Label - https://url  (tg:// links are allowed too)
"""
from __future__ import annotations

import json

from telethon import Button

import config


def save(rows: list) -> None:
    config.BUTTONS_FILE.write_text(json.dumps(rows, ensure_ascii=False))


def load() -> list | None:
    if config.BUTTONS_FILE.exists():
        try:
            data = json.loads(config.BUTTONS_FILE.read_text())
            return data or None
        except (ValueError, OSError):
            return None
    return None


def clear() -> bool:
    if config.BUTTONS_FILE.exists():
        config.BUTTONS_FILE.unlink()
        return True
    return False


def count() -> int:
    rows = load() or []
    return sum(len(r) for r in rows)


def to_markup():
    """Build the Telethon button markup, or None if no buttons are set."""
    rows = load()
    if not rows:
        return None
    markup = []
    for row in rows:
        brow = [Button.url(b["text"], b["url"]) for b in row if b.get("url")]
        if brow:
            markup.append(brow)
    return markup or None


def parse(text: str):
    """Parse a /setbutton body into rows. Returns (rows, error_message)."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        row = []
        for part in line.split("|"):
            part = part.strip()
            if not part:
                continue
            label, sep, url = part.rpartition(" - ")
            label, url = label.strip(), url.strip()
            if not sep or not label or not url:
                return None, f"Bad button: {part!r}\nUse:  Label - https://url"
            if not url.startswith(("http://", "https://", "tg://")):
                return None, f"URL must start with http(s):// or tg://  ->  {url!r}"
            row.append({"text": label, "url": url})
        if row:
            rows.append(row)
    if not rows:
        return None, "No buttons found. Example:  Join - https://t.me/yourchannel"
    return rows, None
