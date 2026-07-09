"""The BOT (long-running). Two jobs:

1. Auto-DM every NEW join requester the invite to your new channel, the instant
   they request to join. This is the "flawless" path — the bot sees the request
   live so it can always reach the user. Each requester is also added to the
   broadcast audience.

2. Let the OWNER post to everyone with /broadcast (reply to any message).

Owner commands (DM the bot):
  /start              show help
  /stats              show audience size + broadcast state
  /broadcast          reply to a post to send it to the whole audience
                      (any format: video, photo, text... premium emoji kept)
  /cancel             stop a running broadcast

Requirements:
  - The bot is an ADMIN of the source channel with the "Add users" right.
  - The channel has "Approve new members" (join requests) turned on.
  - OWNER_ID is set (setup.py does this for you).

Run:  python live_bot.py     (Ctrl+C to stop)
"""
from __future__ import annotations

import asyncio

from telethon import TelegramClient, events
from telethon.tl.types import UpdateBotChatInviteRequester

import audience
import broadcast
import config
from bot_dm import dm_user

_state = broadcast.BroadcastState()


def _is_owner(event) -> bool:
    return config.OWNER_ID and event.sender_id == config.OWNER_ID


def build_bot() -> TelegramClient:
    config.require("API_ID", "API_HASH", "BOT_TOKEN")
    bot = TelegramClient(config.BOT_SESSION, config.API_ID, config.API_HASH)

    # --- 1. New join requests -> auto-DM + remember for broadcasts ---------
    @bot.on(events.Raw(UpdateBotChatInviteRequester))
    async def on_request(update: UpdateBotChatInviteRequester):
        uid = update.user_id
        first_name = None
        try:
            entity = await bot.get_entity(uid)
            first_name = getattr(entity, "first_name", None)
        except Exception:
            pass

        audience.add(uid)
        status = await dm_user(bot, uid, first_name)
        print(f"join request from {uid} -> DM {status}")

    # --- 2. Owner: /start ---------------------------------------------------
    @bot.on(events.NewMessage(pattern=r"^/start"))
    async def on_start(event):
        if not _is_owner(event):
            return
        await event.reply(
            "Owner panel\n\n"
            "/broadcast  — reply to any post to send it to everyone\n"
            "/stats      — audience size + status\n"
            "/cancel     — stop a running broadcast\n\n"
            "Tip: reply to a video/photo/text (premium emoji supported)."
        )

    # --- 2. Owner: /stats ---------------------------------------------------
    @bot.on(events.NewMessage(pattern=r"^/stats"))
    async def on_stats(event):
        if not _is_owner(event):
            return
        count = len(broadcast_targets())
        running = "yes" if _state.running else "no"
        await event.reply(f"Audience: {count}\nBroadcast running: {running}")

    # --- 2. Owner: /cancel --------------------------------------------------
    @bot.on(events.NewMessage(pattern=r"^/cancel"))
    async def on_cancel(event):
        if not _is_owner(event):
            return
        if _state.running:
            _state.cancel = True
            await event.reply("Cancelling after the current message.")
        else:
            await event.reply("Nothing is broadcasting.")

    # --- 2. Owner: /broadcast ----------------------------------------------
    @bot.on(events.NewMessage(pattern=r"^/broadcast"))
    async def on_broadcast(event):
        if not _is_owner(event):
            return
        if _state.running:
            await event.reply("A broadcast is already running. Use /cancel first.")
            return

        src = await event.get_reply_message()
        if src is None:
            await event.reply(
                "Reply to the post you want to send (video, photo, text...) "
                "with /broadcast."
            )
            return

        targets = broadcast_targets()
        if not targets:
            await event.reply(
                "Audience is empty. Run `python fetch_pending.py` first, or wait "
                "for new join requests."
            )
            return

        status_msg = await event.reply(f"Broadcasting to {len(targets)} users...")

        async def progress(done, stats):
            try:
                await status_msg.edit(
                    f"Broadcasting... {done}/{stats['total']}\n"
                    + broadcast.format_stats(stats)
                )
            except Exception:
                pass

        async def runner():
            stats = await broadcast.run_broadcast(
                bot, src, targets, _state, progress=progress
            )
            try:
                await status_msg.edit("Broadcast finished.\n" + broadcast.format_stats(stats))
            except Exception:
                pass
            print("broadcast finished:", stats)

        asyncio.create_task(runner())

    return bot


def broadcast_targets() -> list[int]:
    """Everyone we can post to: saved audience unioned with the pending dump."""
    return audience.merged_with_pending()


async def main() -> None:
    config.require("API_ID", "API_HASH", "BOT_TOKEN", "NEW_CHANNEL_LINK")
    if not config.OWNER_ID:
        print("WARNING: OWNER_ID is not set — /broadcast will be disabled. "
              "Run `python setup.py` or set OWNER_ID in .env.")

    bot = build_bot()
    await bot.start(bot_token=config.BOT_TOKEN)
    me = await bot.get_me()
    print(f"Live as @{me.username}. Waiting for join requests on "
          f"{config.SOURCE_CHANNEL} ... (Ctrl+C to stop)")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
