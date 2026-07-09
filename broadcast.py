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
import json

from telethon import TelegramClient, utils
from telethon.errors import (
    FloodWaitError,
    InputUserDeactivatedError,
    PeerFloodError,
    PeerIdInvalidError,
    UserIsBlockedError,
    UserIsBotError,
)
from telethon.tl.types import InputPeerUser, Message, MessageMediaWebPage

import buttons as buttons_store
import config
import saved_post

# Non-premium bots can attach at most this many UTF-16 units as a media caption.
# Longer text is sent as a separate follow-up so nothing (e.g. URLs) is dropped.
CAPTION_LIMIT = 1024


def _utf16_len(text: str) -> int:
    """Telegram counts caption length in UTF-16 code units, not code points."""
    return len(text.encode("utf-16-le")) // 2


def pending_username_map() -> dict:
    """Map of user_id -> @username from the fetched backlog (usernames only)."""
    if not config.PENDING_FILE.exists():
        return {}
    try:
        data = json.loads(config.PENDING_FILE.read_text())
        return {u["user_id"]: u["username"] for u in data if u.get("username")}
    except Exception:
        return {}


async def _resolve_send_peer(bot: TelegramClient, target, username: str | None = None):
    """Turn a target into a sendable peer, trying hardest to get a REAL peer.

    Order:
      1) already an entity/InputPeer -> use as-is
      2) cached access hash (live join requesters, seen via update)
      3) resolve the public @username (the only way to reach an OLD requester
         the bot never saw — works only if the user has a username)
      4) last resort access_hash 0 (usually rejected for uncached users)
    """
    if not isinstance(target, int):
        return target
    try:
        return await bot.get_input_entity(target)
    except (ValueError, TypeError):
        pass
    if username:
        try:
            return await bot.get_input_entity(username)
        except Exception:
            pass
    return InputPeerUser(target, 0)


async def resolve_saved(bot: TelegramClient) -> Message | None:
    """Fetch the owner's saved-post Message, or None if unset/deleted."""
    info = saved_post.load()
    if not info:
        return None
    try:
        msg = await bot.get_messages(info["chat_id"], ids=info["message_id"])
    except Exception:
        return None
    return msg  # None if the message was deleted


class BroadcastState:
    """Shared flag object so /cancel can stop an in-flight broadcast."""

    def __init__(self) -> None:
        self.running = False
        self.cancel = False


async def _copy_to(bot: TelegramClient, target, src: Message, markup="__default__",
                   username: str | None = None) -> str:
    """Send a copy of `src` to one target (user id or entity).

    Preserves media, caption, all formatting (incl. premium/custom emoji), and
    the spoiler flag. If the caption is too long for the bot's media-caption
    limit, the media is sent first and the full text follows as its own message
    so no URLs/text are lost. `markup` defaults to the configured /setbutton
    buttons; pass None to force no buttons. `username` lets old requesters be
    resolved by @username when the bot has no cached access hash.
    """
    if markup == "__default__":
        markup = buttons_store.to_markup()

    peer = await _resolve_send_peer(bot, target, username)
    entities = src.entities or None
    text = src.message or ""
    try:
        has_media = src.media is not None and not isinstance(src.media, MessageMediaWebPage)
        if has_media:
            # Re-send existing media by reference (no re-upload) and carry over
            # the spoiler flag — send_file has no spoiler kwarg in this build,
            # so we set it on the InputMedia directly.
            input_media = utils.get_input_media(src.media)
            if getattr(src.media, "spoiler", False) and hasattr(input_media, "spoiler"):
                input_media.spoiler = True
            if _utf16_len(text) <= CAPTION_LIMIT:
                await bot.send_file(
                    peer,
                    input_media,
                    caption=text,
                    formatting_entities=entities,
                    buttons=markup,
                )
            else:
                # Caption exceeds the bot caption limit — send media, then the
                # full text (with all links) as a separate message.
                await bot.send_file(peer, input_media, caption="")
                await bot.send_message(
                    peer,
                    text,
                    formatting_entities=entities,
                    link_preview=True,
                    buttons=markup,
                )
        else:
            await bot.send_message(
                peer,
                text,
                formatting_entities=entities,
                link_preview=isinstance(src.media, MessageMediaWebPage),
                buttons=markup,
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
    usernames: dict | None = None,
) -> dict:
    """Copy `src` to every id in `targets`, paced and cancellable.

    `progress` (optional) is an async callable(done, stats) invoked periodically.
    `usernames` (optional) maps user_id -> @username so old requesters the bot
    never saw can still be resolved. Returns a stats dict. Stops early on
    PeerFloodError (hard rate limit).
    """
    state.running = True
    state.cancel = False
    stats = _new_stats(len(targets))
    done = 0
    markup = buttons_store.to_markup()  # resolve once for the whole run
    if usernames is None:
        usernames = pending_username_map()
    try:
        for user_id in targets:
            if state.cancel:
                break

            uname = usernames.get(user_id)
            status = await _copy_to(bot, user_id, src, markup=markup, username=uname)

            # Wait out short flood requests once, then retry the same user.
            if status.startswith("flood:"):
                wait = int(status.split(":", 1)[1])
                if wait <= 300:
                    await asyncio.sleep(wait + 1)
                    status = await _copy_to(bot, user_id, src, markup=markup, username=uname)

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
