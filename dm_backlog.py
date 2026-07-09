"""BOT step — DM everyone the userbot found in data/pending_users.json.

Safe to stop and re-run: it tracks who was already messaged in data/sent.json
and skips them, so you never double-DM anyone.

Run:  python dm_backlog.py
On first run the bot logs in from its token (no phone code needed).
"""
import asyncio
import json

import config
from bot_dm import build_bot, dm_user_with_flood_retry


def _load(path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


def _save(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False))


async def main() -> None:
    if not config.PENDING_FILE.exists():
        raise SystemExit(
            f"{config.PENDING_FILE} not found. Run `python fetch_pending.py` first."
        )
    config.require("NEW_CHANNEL_LINK")

    pending = _load(config.PENDING_FILE, [])
    sent = set(_load(config.SENT_FILE, []))
    failed = _load(config.FAILED_FILE, {})

    todo = [u for u in pending if u["user_id"] not in sent]
    print(f"{len(pending)} total, {len(sent)} already done, {len(todo)} to go.\n")

    bot = build_bot()
    await bot.start(bot_token=config.BOT_TOKEN)

    processed = 0
    try:
        for user in todo:
            uid = user["user_id"]
            status = await dm_user_with_flood_retry(bot, uid, user.get("first_name"))

            if status == "sent":
                sent.add(uid)
                print(f"  [sent]    {uid}")
            elif status == "peerflood":
                # Telegram is throttling the bot hard — stop and let it rest.
                print("\n! PeerFloodError: Telegram is rate-limiting the bot.")
                print("  Stopping now. Wait a few hours, then re-run to resume.")
                break
            elif status.startswith("flood:"):
                wait = status.split(":", 1)[1]
                print(f"\n! Long flood wait ({wait}s) requested. Stopping; re-run later.")
                break
            else:
                failed[str(uid)] = status
                print(f"  [{status}]  {uid}")

            processed += 1

            # Persist progress every message so a crash never loses state.
            _save(config.SENT_FILE, sorted(sent))
            _save(config.FAILED_FILE, failed)

            # Gentle pacing.
            await asyncio.sleep(config.DM_DELAY_SECONDS)
            if config.BATCH_SIZE and processed % config.BATCH_SIZE == 0:
                print(f"  -- batch of {config.BATCH_SIZE} done, pausing "
                      f"{config.BATCH_PAUSE_SECONDS}s --")
                await asyncio.sleep(config.BATCH_PAUSE_SECONDS)
    finally:
        _save(config.SENT_FILE, sorted(sent))
        _save(config.FAILED_FILE, failed)
        await bot.disconnect()

    print(f"\nRun finished. sent={len(sent)} failed={len(failed)}")
    print(f"Details: {config.SENT_FILE} / {config.FAILED_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
