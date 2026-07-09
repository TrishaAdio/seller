"""Persistent broadcast audience — the set of user ids the bot can post to.

Grows over time: seeded from the pending-request backlog and topped up with
every new live join-requester. Stored as a plain JSON array in
data/audience.json.
"""
from __future__ import annotations

import json
from typing import Iterable

import config


def load_ids() -> set[int]:
    if config.AUDIENCE_FILE.exists():
        try:
            return set(json.loads(config.AUDIENCE_FILE.read_text()))
        except (ValueError, OSError):
            return set()
    return set()


def _save(ids: set[int]) -> None:
    config.AUDIENCE_FILE.write_text(json.dumps(sorted(ids)))


def add(user_id: int) -> bool:
    """Add one user. Returns True if newly added."""
    ids = load_ids()
    if user_id in ids:
        return False
    ids.add(user_id)
    _save(ids)
    return True


def add_many(user_ids: Iterable[int]) -> int:
    """Add many users. Returns how many were newly added."""
    ids = load_ids()
    before = len(ids)
    ids.update(int(u) for u in user_ids)
    _save(ids)
    return len(ids) - before


def all_ids() -> list[int]:
    return sorted(load_ids())


def merged_with_pending() -> list[int]:
    """Audience unioned with the raw pending-request dump (belt and braces)."""
    ids = load_ids()
    if config.PENDING_FILE.exists():
        try:
            pending = json.loads(config.PENDING_FILE.read_text())
            ids.update(u["user_id"] for u in pending)
        except (ValueError, OSError, KeyError, TypeError):
            pass
    return sorted(ids)
