"""The BOT (long-running). Two jobs:

1. Welcome every NEW join requester automatically the instant they request to
   join — by sending them your SAVED POST (see /setpost). This is the "flawless"
   path: the bot sees the request live, so it can always reach the user. Each
   requester is also added to the broadcast audience.

2. Let the OWNER post to everyone with /broadcast.

The content is ONE saved post you set with /setpost — any message (video,
photo, text, premium emoji... everything lives in that post). No fixed
"new channel link" config is required; whatever you put in the post is what
gets sent.

Owner commands (DM the bot):
  /start              show help
  /setpost            reply to a message to save it as THE post
  /clearpost          forget the saved post
  /setbutton          set inline URL buttons for the post
  /clearbutton        remove the buttons
  /preview            send the saved post to yourself
  /stats              audience size + post/button status
  /broadcast          push the saved post (or a replied post) to everyone
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
import buttons
import config
import saved_post
from bot_dm import dm_user

_state = broadcast.BroadcastState()


def _is_owner(event) -> bool:
    return bool(config.OWNER_ID) and event.sender_id == config.OWNER_ID


def broadcast_targets() -> list[int]:
    """Everyone we can post to: saved audience unioned with the pending dump."""
    return audience.merged_with_pending()


def build_bot() -> TelegramClient:
    config.require("API_ID", "API_HASH", "BOT_TOKEN")
    bot = TelegramClient(config.BOT_SESSION, config.API_ID, config.API_HASH)

    async def welcome(peer, first_name: str | None) -> str:
        """Send the saved post to one user; fall back to the text template.

        `peer` is the resolved entity when we have it (carries the access hash
        so the send actually goes through), or the raw user id otherwise.
        """
        src = await broadcast.resolve_saved(bot)
        if src is not None:
            return await broadcast._copy_to(bot, peer, src)
        if config.has_text_template():
            uid = peer if isinstance(peer, int) else peer.id
            return await dm_user(bot, uid, first_name)
        return "no_post"  # nothing configured yet — just collected

    # --- 1. New join requests -> auto-welcome + remember for broadcasts ----
    @bot.on(events.Raw(UpdateBotChatInviteRequester))
    async def on_request(update: UpdateBotChatInviteRequester):
        uid = update.user_id
        peer = uid
        first_name = None
        try:
            # Resolving now also caches the access hash from the live update,
            # so the DM below can actually reach the user.
            entity = await bot.get_entity(uid)
            peer = entity
            first_name = getattr(entity, "first_name", None)
        except Exception:
            pass

        audience.add(uid)
        status = await welcome(peer, first_name)
        print(f"join request from {uid} -> {status}")

    # --- 2. Owner: /start ---------------------------------------------------
    @bot.on(events.NewMessage(pattern=r"^/start"))
    async def on_start(event):
        if not _is_owner(event):
            return
        await event.reply(
            "Owner panel\n\n"
            "/setpost     — reply to a post to save it (this is what gets sent)\n"
            "/clearpost   — forget the saved post\n"
            "/setbutton   — set inline URL buttons for the post\n"
            "/clearbutton — remove the buttons\n"
            "/preview     — send the saved post to yourself\n"
            "/broadcast   — push the saved post (or a replied post) to everyone\n"
            "/stats       — audience size + post/button status\n"
            "/cancel      — stop a running broadcast\n\n"
            "The post can be a video/photo/text with premium emoji or a spoiler "
            "image — everything in it is sent as-is."
        )

    # --- 2. Owner: /setpost -------------------------------------------------
    @bot.on(events.NewMessage(pattern=r"^/setpost"))
    async def on_setpost(event):
        if not _is_owner(event):
            return
        src = await event.get_reply_message()
        if src is None:
            await event.reply("Reply to the message you want to save with /setpost.")
            return
        saved_post.save(event.chat_id, src.id)
        await event.reply("Saved. This post will be sent to new joiners and on /broadcast.")

    # --- 2. Owner: /clearpost -----------------------------------------------
    @bot.on(events.NewMessage(pattern=r"^/clearpost"))
    async def on_clearpost(event):
        if not _is_owner(event):
            return
        removed = saved_post.clear()
        await event.reply("Saved post cleared." if removed else "No saved post to clear.")

    # --- 2. Owner: /setbutton -----------------------------------------------
    @bot.on(events.NewMessage(pattern=r"^/setbutton"))
    async def on_setbutton(event):
        if not _is_owner(event):
            return
        body = event.raw_text[len("/setbutton"):].strip()
        if not body:
            await event.reply(
                "Set inline buttons for the post.\n\n"
                "One button:\n/setbutton Join - https://t.me/yourchannel\n\n"
                "Multiple (| = same row, new line = new row):\n"
                "/setbutton\n"
                "Join - https://t.me/x | Chat - https://t.me/y\n"
                "Website - https://example.com"
            )
            return
        rows, err = buttons.parse(body)
        if err:
            await event.reply(err)
            return
        buttons.save(rows)
        total = sum(len(r) for r in rows)
        await event.reply(
            f"Saved {total} button(s) in {len(rows)} row(s). Use /preview to check."
        )

    # --- 2. Owner: /clearbutton ---------------------------------------------
    @bot.on(events.NewMessage(pattern=r"^/clearbutton"))
    async def on_clearbutton(event):
        if not _is_owner(event):
            return
        removed = buttons.clear()
        await event.reply("Buttons cleared." if removed else "No buttons set.")

    # --- 2. Owner: /preview -------------------------------------------------
    @bot.on(events.NewMessage(pattern=r"^/preview"))
    async def on_preview(event):
        if not _is_owner(event):
            return
        src = await broadcast.resolve_saved(bot)
        if src is None:
            await event.reply("No saved post. Use /setpost (reply to a message) first.")
            return
        status = await broadcast._copy_to(bot, event.sender_id, src)
        if status != "sent":
            await event.reply(f"Preview failed: {status}")

    # --- 2. Owner: /stats ---------------------------------------------------
    @bot.on(events.NewMessage(pattern=r"^/stats"))
    async def on_stats(event):
        if not _is_owner(event):
            return
        count = len(broadcast_targets())
        post = "set" if saved_post.exists() else "none"
        btns = buttons.count()
        running = "yes" if _state.running else "no"
        await event.reply(
            f"Audience: {count}\nSaved post: {post}\nButtons: {btns}\n"
            f"Broadcast running: {running}"
        )

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

        # Prefer a replied post; otherwise use the saved post.
        src = await event.get_reply_message()
        if src is None:
            src = await broadcast.resolve_saved(bot)
        if src is None:
            await event.reply(
                "Nothing to send. Reply to a post with /broadcast, or set one "
                "with /setpost first."
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


async def main() -> None:
    config.require("API_ID", "API_HASH", "BOT_TOKEN")
    if not config.OWNER_ID:
        print("WARNING: OWNER_ID is not set — owner commands are disabled. "
              "Run `python setup.py` or set OWNER_ID in .env.")

    bot = build_bot()
    await bot.start(bot_token=config.BOT_TOKEN)
    me = await bot.get_me()

    # Warm the entity cache for the source channel up front. The saved post is
    # fetched by numeric channel id, which needs the channel's access_hash in
    # the session cache; on a fresh session (new VPS) or right after a restart
    # that cache is cold, so the first welcome would otherwise silently fall
    # back to plain text and drop the post's premium/custom emoji.
    ident = config.channel_ident()
    if ident:
        try:
            chan = await bot.get_entity(ident)
            print(f"Source channel resolved: {getattr(chan, 'title', ident)}")
        except Exception as exc:  # noqa: BLE001
            print(f"Could not pre-resolve SOURCE_CHANNEL {ident!r} "
                  f"({type(exc).__name__}: {exc}). It will be warmed from the "
                  "first join-request update instead.")

    post = "set" if saved_post.exists() else "NOT set (use /setpost)"
    print(f"Live as @{me.username}. Saved post: {post}.")
    print(f"Waiting for join requests on {config.SOURCE_CHANNEL} ... (Ctrl+C to stop)")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
