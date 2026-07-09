"""USERBOT step — enumerate every pending join request on the source channel.

Why the userbot does this and not the bot:
The Bot API can only APPROVE or DECLINE join requests, it has no way to *list*
them. So we log in with your own account (which must be an admin of the source
channel) and page through the full pending list, dumping the user ids to
data/pending_users.json. The bot then reads that file to DM everyone.

Run:  python fetch_pending.py
On first run it will ask for your phone number + login code.
"""
from __future__ import annotations

import asyncio
import json

from telethon import TelegramClient
from telethon.errors import ChatAdminRequiredError
from telethon.tl.functions.messages import GetChatInviteImportersRequest
from telethon.tl.types import InputUserEmpty

import audience
import config

PAGE = 100  # max the API returns per call


async def resolve_channel(client: TelegramClient, ident):
    """Resolve the source channel, even a PRIVATE one referenced by numeric id.

    Telethon can't look up a private channel by bare id unless it's already in
    the account's entity cache. So if the direct lookup fails, we warm the cache
    by loading the account's dialogs (the channel you admin is in there) and
    retry.
    """
    try:
        return await client.get_entity(ident)
    except (ValueError, TypeError):
        pass

    print("Channel not cached yet — loading your dialogs to find it...")
    target = None
    async for dialog in client.iter_dialogs():
        if dialog.id == ident or getattr(dialog.entity, "id", None) == ident:
            target = dialog.entity
            break

    if target is not None:
        return target
    # One more direct attempt now that the cache is warm.
    return await client.get_entity(ident)


async def fetch_all_pending() -> list[dict]:
    config.require("API_ID", "API_HASH", "SOURCE_CHANNEL")

    client = TelegramClient(config.USERBOT_SESSION, config.API_ID, config.API_HASH)
    await client.start()  # prompts for phone + code on first run

    me = await client.get_me()
    print(f"Logged in as {me.first_name} (id {me.id})")

    try:
        channel = await resolve_channel(client, config.channel_ident())
    except (ValueError, TypeError):
        await client.disconnect()
        raise SystemExit(
            f"Could not find the channel {config.SOURCE_CHANNEL!r}.\n"
            "Check that:\n"
            "  - SOURCE_CHANNEL in .env is correct (id like -100..., @username, "
            "or invite link)\n"
            f"  - this account ({me.first_name}, id {me.id}) is a MEMBER/ADMIN "
            "of that channel."
        )
    print(f"Reading pending join requests for: {getattr(channel, 'title', channel.id)}")

    importers: list[dict] = []
    seen: set[int] = set()
    offset_date = None
    offset_user = InputUserEmpty()

    while True:
        try:
            result = await client(
                GetChatInviteImportersRequest(
                    peer=channel,
                    limit=PAGE,
                    offset_date=offset_date,
                    offset_user=offset_user,
                    requested=True,  # only users with a *pending* join request
                )
            )
        except ChatAdminRequiredError:
            await client.disconnect()
            raise SystemExit(
                f"This account ({me.first_name}) must be an ADMIN of the channel "
                "with the 'Add users' right to read join requests."
            )

        # Telegram returns an empty page only when there's nothing left. It may
        # return FEWER than `limit` while more still remain, so we must NOT stop
        # just because a page was short.
        if not result.importers:
            break

        users_by_id = {u.id: u for u in result.users}
        new_count = 0
        for imp in result.importers:
            if imp.user_id in seen:
                continue
            seen.add(imp.user_id)
            new_count += 1
            u = users_by_id.get(imp.user_id)
            importers.append(
                {
                    "user_id": imp.user_id,
                    "first_name": getattr(u, "first_name", None) if u else None,
                    "username": getattr(u, "username", None) if u else None,
                    "date": imp.date.isoformat() if imp.date else None,
                }
            )

        print(f"  ...collected {len(importers)} so far")

        # If a full page brought nothing new, the offset isn't advancing —
        # stop rather than loop forever.
        if new_count == 0:
            break

        last = result.importers[-1]
        offset_date = last.date
        offset_user = await client.get_input_entity(users_by_id[last.user_id])

        await asyncio.sleep(0.5)  # be gentle between pages

    await client.disconnect()
    return importers


async def main() -> None:
    pending = await fetch_all_pending()
    config.PENDING_FILE.write_text(json.dumps(pending, indent=2, ensure_ascii=False))

    # Seed the broadcast audience so the bot can post to these people later.
    added = audience.add_many(u["user_id"] for u in pending)

    print(f"\nDone. {len(pending)} pending requesters saved to {config.PENDING_FILE}")
    print(f"Audience updated: +{added} new (total {len(audience.all_ids())}).")


if __name__ == "__main__":
    asyncio.run(main())
