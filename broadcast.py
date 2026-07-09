"""Broadcast engine — replicate ONE message (any format) to the whole audience.

The owner replies to a post with /broadcast; we copy that exact message to
every recipient. "Copy" (not forward) means no "forwarded from" header.

Format support: text, photo, video, document, audio, voice, sticker, GIF —
whatever the owner sent. Captions and all text formatting are preserved,
including PREMIUM / custom emoji: those live in the message as
MessageEntityCustomEmoji entities, and Bot API 9.4+ lets bots re-send them,
so we simply pass the original entities straight through.
"""
from __future__ import annotations

import asyncio

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    InputUserDeactivatedError,
    PeerFloodError,
    PeerIdInvalidError,
    UserIsBlockedError,
    UserIsBotError,
)
from telethon.tl.types import InputPeerUser, Message, MessageMediaWebPage

import config


class BroadcastState:
    """Shared flag object so /cancel can stop an in-flight broadcast."""

    def __init__(self) -> None:
        self.running = False
        self.cancel = False


async def _copy_to(bot: TelegramClient, user_id: int, src: Message) -> str:
    """Send a copy of `src` to one user. Returns a status string."""
    peer = InputPeerUser(user_id, 0)
    entities = src.entities or None
    text = src.message or ""
    try:
        has_media = src.media is not None and not isinstance(src.media, MessageMediaWebPage)
        if has_media:
            await bot.send_file(
                peer,
                file=src.media,
                caption=text,
                formatting_entities=entities,
            )
        else:
            await bot.send_message(
                peer,
                text,
                formatting_entities=entities,
                link_preview=isinstance(src.media, MessageMediaWebPage),
            )
        return "sent"
    except FloodWaitError as e:
        return f"flood:{e.seconds}"
    except PeerFloodError:
        return "peerflood"
    except UserIsBlockedError:
        return "blocked"
    except InputUserDeactivatedError:
        return "deleted"
    except UserIsBotError:
        return "is_bot"
    except (PeerIdInvalidError, ValueError):
        return "invalid"
    except Exception as e:  # noqa: BLE001 - never let one bad user kill the run
        return f"error:{type(e).__name__}"


def _new_stats(total: int) -> dict:
    return {
        "total": total,
        "sent": 0,
        "blocked": 0,
        "deleted": 0,
        "is_bot": 0,
        "invalid": 0,
        "error": 0,
        "flood_skipped": 0,
    }


async def run_broadcast(
    bot: TelegramClient,
    src: Message,
    targets: list[int],
    state: BroadcastState,
    progress=None,
) -> dict:
    """Copy `src` to every id in `targets`, paced and cancellable.

    `progress` (optional) is an async callable(done, stats) invoked periodically.
    Returns a stats dict. Stops early on PeerFloodError (hard rate limit).
    """
    state.running = True
    state.cancel = False
    stats = _new_stats(len(targets))
    done = 0
    try:
        for user_id in targets:
            if state.cancel:
                break

            status = await _copy_to(bot, user_id, src)

            # Wait out short flood requests once, then retry the same user.
            if status.startswith("flood:"):
                wait = int(status.split(":", 1)[1])
                if wait <= 300:
                    await asyncio.sleep(wait + 1)
                    status = await _copy_to(bot, user_id, src)

            if status == "sent":
                stats["sent"] += 1
            elif status == "peerflood":
                # Telegram is throttling the bot hard; stop and let the owner retry.
                stats["peerflood_stop"] = True
                break
            elif status.startswith("flood:"):
                stats["flood_skipped"] += 1
            elif status.startswith("error:"):
                stats["error"] += 1
            else:
                stats[status] = stats.get(status, 0) + 1

            done += 1
            if progress and done % 25 == 0:
                await progress(done, stats)

            await asyncio.sleep(config.DM_DELAY_SECONDS)
            if config.BATCH_SIZE and done % config.BATCH_SIZE == 0:
                await asyncio.sleep(config.BATCH_PAUSE_SECONDS)
    finally:
        state.running = False

    stats["done"] = done
    return stats


def format_stats(stats: dict) -> str:
    """Human-readable one-liner (+extras) for a status message."""
    lines = [
        f"Sent {stats.get('sent', 0)}/{stats.get('total', 0)}",
    ]
    extras = []
    for key in ("blocked", "deleted", "invalid", "is_bot", "error", "flood_skipped"):
        if stats.get(key):
            extras.append(f"{key}: {stats[key]}")
    if stats.get("peerflood_stop"):
        extras.append("STOPPED (Telegram rate limit — retry later)")
    if extras:
        lines.append(" | ".join(extras))
    return "\n".join(lines)
