"""Shared BOT helpers: build the bot client and safely DM a single user.

The bot is allowed to message a user ONLY because that user has a pending
join request in a channel where the bot is an admin. For historical
requesters (fetched by the userbot) we address them by raw id via
InputPeerUser(user_id, 0) — bots may use access_hash 0 for such peers.
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
from telethon.tl.types import InputPeerUser

import buttons as buttons_store
import config


def build_bot() -> TelegramClient:
    config.require("API_ID", "API_HASH", "BOT_TOKEN")
    return TelegramClient(config.BOT_SESSION, config.API_ID, config.API_HASH)


async def _resolve_peer(bot: TelegramClient, user_id: int):
    """Real access hash from cache if known, else access_hash 0 as a fallback."""
    try:
        return await bot.get_input_entity(user_id)
    except (ValueError, TypeError):
        return InputPeerUser(user_id, 0)


async def dm_user(bot: TelegramClient, user_id: int, first_name: str | None) -> str:
    """Send the fallback text DM to one user.

    Returns a status string: "sent", "blocked", "invalid", "deleted",
    "is_bot", or "flood:<seconds>". Raises nothing for expected failures.
    """
    peer = await _resolve_peer(bot, user_id)
    text = config.render_message(first_name)
    try:
        await bot.send_message(peer, text, link_preview=False,
                               buttons=buttons_store.to_markup())
        return "sent"
    except FloodWaitError as e:
        return f"flood:{e.seconds}"
    except PeerFloodError:
        # Telegram flagged the bot for too many messages — must cool down.
        return "peerflood"
    except UserIsBlockedError:
        return "blocked"
    except (InputUserDeactivatedError,):
        return "deleted"
    except UserIsBotError:
        return "is_bot"
    except (PeerIdInvalidError, ValueError):
        # Usually means the user has no pending request the bot can reach.
        return "invalid"


async def dm_user_with_flood_retry(
    bot: TelegramClient, user_id: int, first_name: str | None, max_wait: int = 300
) -> str:
    """Same as dm_user but transparently waits out short FloodWaitErrors."""
    while True:
        status = await dm_user(bot, user_id, first_name)
        if status.startswith("flood:"):
            wait = int(status.split(":", 1)[1])
            if wait > max_wait:
                return status  # too long — let the caller decide
            print(f"    flood wait {wait}s (user {user_id}) — sleeping")
            await asyncio.sleep(wait + 1)
            continue
        return status
