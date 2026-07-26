"""The BOT (long-running). Everything lives here now:

1. Welcome every NEW join requester automatically the instant they request to
   join one of the REGISTERED channels — by sending them your SAVED POST (see
   /setpost). The bot sees the request live, so it can always reach the user.
   Each requester is also added to the broadcast audience.

2. Manage the channels it watches at runtime with /add and /remove, so one bot
   can serve any number of channels without touching .env.

3. Let the OWNER post to everyone with /broadcast (alias /bcast).

The content is ONE saved post you set with /setpost — any message (video,
photo, text, premium emoji... everything lives in that post).

Owner commands (DM the bot):
  /start              show help
  /add <chat_id>      watch a channel's join requests
  /remove <chat_id>   stop watching a channel
  /chats              list watched channels
  /setpost            reply to a message to save it as THE post
  /clearpost          forget the saved post
  /setbutton          set inline URL buttons for the post
  /clearbutton        remove the buttons
  /preview            send the saved post to yourself
  /stats              audience size + channel/post/button status
  /broadcast          push the saved post (or a replied post) to everyone
  /cancel             stop a running broadcast

Requirements:
  - The bot is an ADMIN of each watched channel with the "Add users" right.
  - Each channel has "Approve new members" (join requests) turned on.
  - OWNER_ID is set in .env.

Run:  python live_bot.py     (Ctrl+C to stop)
"""
from __future__ import annotations

import asyncio

from telethon import TelegramClient, events, utils
from telethon.tl.types import UpdateBotChatInviteRequester

import audience
import broadcast
import buttons
import channels
import config
import saved_post

_state = broadcast.BroadcastState()

HELP = (
    "Owner panel\n\n"
    "/add <chat_id>    — watch a channel's join requests\n"
    "/remove <chat_id> — stop watching a channel\n"
    "/chats            — list watched channels\n"
    "/setpost          — reply to a post to save it (this is what gets sent)\n"
    "/clearpost        — forget the saved post\n"
    "/setbutton        — set inline URL buttons for the post\n"
    "/clearbutton      — remove the buttons\n"
    "/preview          — send the saved post to yourself\n"
    "/broadcast        — push the saved post (or a replied post) to everyone\n"
    "/stats            — audience + channels + post status\n"
    "/cancel           — stop a running broadcast"
)


def _is_owner(event) -> bool:
    return bool(config.OWNER_ID) and event.sender_id == config.OWNER_ID


def _cmd(name: str, *aliases: str) -> str:
    """Regex for a bot command, tolerating the /cmd@botname form."""
    names = "|".join((name, *aliases))
    return rf"^/(?:{names})(?:@\w+)?(?:\s|$)"


def _args(event) -> str:
    """Everything after the command word (newlines preserved)."""
    parts = (event.raw_text or "").split(None, 1)
    return parts[1].strip() if len(parts) > 1 else ""


def broadcast_targets() -> list[int]:
    return audience.all_ids()


def _fmt_chat(chat_id: int, title: str) -> str:
    return f"{chat_id} — {title}" if title else str(chat_id)


def build_bot() -> TelegramClient:
    config.require("API_ID", "API_HASH", "BOT_TOKEN")
    bot = TelegramClient(config.BOT_SESSION, config.API_ID, config.API_HASH)

    async def welcome(peer) -> str:
        """Send the saved post to one user.

        `peer` is the resolved entity when we have it (carries the access hash
        so the send actually goes through), or the raw user id otherwise.
        """
        src = await broadcast.resolve_saved(bot)
        if src is None:
            return "no_post"  # nothing configured yet — user just collected
        return await broadcast._copy_to(bot, peer, src)

    # --- 1. New join requests -> auto-welcome + remember for broadcasts ----
    @bot.on(events.Raw(UpdateBotChatInviteRequester))
    async def on_request(update: UpdateBotChatInviteRequester):
        chat_id = utils.get_peer_id(update.peer)
        if not channels.accepts(chat_id):
            print(f"join request in {chat_id} ignored (not registered)")
            return

        uid = update.user_id
        peer = uid
        try:
            # Resolving now also caches the access hash from the live update,
            # so the DM below can actually reach the user.
            peer = await bot.get_entity(uid)
        except Exception:
            pass

        # Learn the channel title the first time we see traffic from it.
        try:
            chat = await bot.get_entity(update.peer)
            channels.set_title(chat_id, getattr(chat, "title", "") or "")
        except Exception:
            pass

        audience.add(uid)
        status = await welcome(peer)
        print(f"join request from {uid} in {chat_id} -> {status}")

    # --- 2. Owner: /start ---------------------------------------------------
    @bot.on(events.NewMessage(pattern=_cmd("start", "help")))
    async def on_start(event):
        if not _is_owner(event):
            return
        await event.reply(HELP)

    # --- 2. Owner: /add -----------------------------------------------------
    @bot.on(events.NewMessage(pattern=_cmd("add")))
    async def on_add(event):
        if not _is_owner(event):
            return
        ident = channels.parse_ident(_args(event))
        if ident is None:
            await event.reply("Usage: /add -1001234567890")
            return

        chat_id, title = None, ""
        try:
            chat = await bot.get_entity(ident)
            chat_id = utils.get_peer_id(chat)
            title = getattr(chat, "title", "") or ""
        except Exception as exc:  # noqa: BLE001
            if not isinstance(ident, int):
                await event.reply(f"Could not resolve {ident} ({type(exc).__name__}).")
                return
            # A bare channel id can't be resolved until the bot has seen the
            # chat; register it anyway and pick the title up on first request.
            chat_id = ident

        added = channels.add(chat_id, title)
        label = _fmt_chat(chat_id, title)
        await event.reply(
            (f"Added {label}" if added else f"Already watching {label}")
            + f"\nChannels: {channels.count()}"
        )

    # --- 2. Owner: /remove --------------------------------------------------
    @bot.on(events.NewMessage(pattern=_cmd("remove", "del")))
    async def on_remove(event):
        if not _is_owner(event):
            return
        ident = channels.parse_ident(_args(event))
        if ident is None:
            await event.reply("Usage: /remove -1001234567890")
            return

        chat_id = ident
        if not isinstance(ident, int):
            try:
                chat_id = utils.get_peer_id(await bot.get_entity(ident))
            except Exception as exc:  # noqa: BLE001
                await event.reply(f"Could not resolve {ident} ({type(exc).__name__}).")
                return

        removed = channels.remove(chat_id)
        await event.reply(
            (f"Removed {chat_id}" if removed else f"{chat_id} was not registered")
            + f"\nChannels: {channels.count()}"
        )

    # --- 2. Owner: /chats ---------------------------------------------------
    @bot.on(events.NewMessage(pattern=_cmd("chats", "channels", "list")))
    async def on_chats(event):
        if not _is_owner(event):
            return
        items = channels.all_items()
        if not items:
            await event.reply(
                "No channels registered — join requests from every chat the bot "
                "administers are handled."
            )
            return
        lines = "\n".join(_fmt_chat(cid, title) for cid, title in items)
        await event.reply(f"Watching {len(items)} channel(s):\n{lines}")

    # --- 2. Owner: /setpost -------------------------------------------------
    @bot.on(events.NewMessage(pattern=_cmd("setpost")))
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
    @bot.on(events.NewMessage(pattern=_cmd("clearpost")))
    async def on_clearpost(event):
        if not _is_owner(event):
            return
        removed = saved_post.clear()
        await event.reply("Saved post cleared." if removed else "No saved post to clear.")

    # --- 2. Owner: /setbutton -----------------------------------------------
    @bot.on(events.NewMessage(pattern=_cmd("setbutton")))
    async def on_setbutton(event):
        if not _is_owner(event):
            return
        body = _args(event)
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
        await event.reply(f"Saved {total} button(s) in {len(rows)} row(s).")

    # --- 2. Owner: /clearbutton ---------------------------------------------
    @bot.on(events.NewMessage(pattern=_cmd("clearbutton")))
    async def on_clearbutton(event):
        if not _is_owner(event):
            return
        removed = buttons.clear()
        await event.reply("Buttons cleared." if removed else "No buttons set.")

    # --- 2. Owner: /preview -------------------------------------------------
    @bot.on(events.NewMessage(pattern=_cmd("preview")))
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
    @bot.on(events.NewMessage(pattern=_cmd("stats")))
    async def on_stats(event):
        if not _is_owner(event):
            return
        await event.reply(
            f"Audience: {audience.count()}\n"
            f"Channels: {channels.count()}\n"
            f"Saved post: {'set' if saved_post.exists() else 'none'}\n"
            f"Buttons: {buttons.count()}\n"
            f"Broadcast running: {'yes' if _state.running else 'no'}"
        )

    # --- 2. Owner: /cancel --------------------------------------------------
    @bot.on(events.NewMessage(pattern=_cmd("cancel")))
    async def on_cancel(event):
        if not _is_owner(event):
            return
        if _state.running:
            _state.cancel = True
            await event.reply("Cancelling after the current message.")
        else:
            await event.reply("Nothing is broadcasting.")

    # --- 3. Owner: /broadcast ----------------------------------------------
    @bot.on(events.NewMessage(pattern=_cmd("broadcast", "bcast")))
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
            await event.reply("Audience is empty. Nobody has requested to join yet.")
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
              "Set OWNER_ID in .env.")

    bot = build_bot()
    await bot.start(bot_token=config.BOT_TOKEN)
    me = await bot.get_me()

    # Warm the entity cache for every watched channel up front. The saved post
    # is fetched by numeric chat id, which needs that chat's access_hash in the
    # session cache; on a fresh session (new VPS) or right after a restart the
    # cache is cold, so the first welcome could otherwise fail to find the post.
    watched = channels.all_items()
    for chat_id, title in watched:
        try:
            chat = await bot.get_entity(chat_id)
            name = getattr(chat, "title", "") or title
            channels.set_title(chat_id, name)
            print(f"watching {chat_id} — {name}")
        except Exception as exc:  # noqa: BLE001
            print(f"watching {chat_id} (could not pre-resolve: "
                  f"{type(exc).__name__}: {exc}; will warm on first request)")
    if not watched:
        print("No channels registered — handling join requests from every chat "
              "the bot administers. Use /add <chat_id> to restrict.")

    post = "set" if saved_post.exists() else "NOT set (use /setpost)"
    print(f"Live as @{me.username}. Saved post: {post}. "
          f"Audience: {audience.count()}.")
    print("Waiting for join requests... (Ctrl+C to stop)")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
