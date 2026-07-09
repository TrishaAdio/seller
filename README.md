# Channel Migration + Broadcast Bot (Telethon)

Reach everyone who requested to join your channel and move them to a new/backup
channel — and keep posting to them afterwards with a single `/broadcast`
command.

- **Bot** does all the DMing (it's allowed to message pending join-requesters).
- **Userbot** (your own account) lists the existing backlog, which the Bot API
  can't do.

## Why a bot *and* a userbot?

Telegram lets a bot message a user **only** when that user has a *pending join
request* in a channel where the bot is an admin. That's the whole trick — it's
why this reaches people who never messaged the bot first.

|                              | Bot | Userbot (your account) |
|------------------------------|-----|------------------------|
| DM a pending requester       | ✅  | ❌ (would be spam/ban) |
| Get live "new request" event | ✅  | —                      |
| **List** existing pending requests | ❌ (no Bot API method) | ✅ |

So: the **userbot enumerates** the backlog → the **bot DMs** them. New requests
after that are handled live by the bot, which also collects everyone into a
**broadcast audience** you can post to any time.

## Quick start

```bash
pip install -r requirements.txt
python setup.py          # interactive: asks for everything + logs you in
```

`setup.py` prompts for `API_ID` / `API_HASH` (from https://my.telegram.org),
the bot token (from [@BotFather](https://t.me/BotFather)), your channel + invite
link, then logs in your **userbot** (asks your phone number → the **OTP** code
Telegram sends → your **2FA** password if set) and the **bot**. It auto-detects
your `OWNER_ID`, writes `.env`, and creates the session files.

> Before running the bot: make the **bot an admin** of the source channel with
> the **"Add users"** right, ensure **your own account is an admin** there too,
> and turn on **"Approve new members"** (that's what creates join requests).

## Usage

**1) List the existing backlog** (userbot):
```bash
python fetch_pending.py
```
→ writes `data/pending_users.json` and seeds `data/audience.json`.

**2) DM the backlog the invite** (bot, paced + resume-safe):
```bash
python dm_backlog.py
```

**3) Run the bot** (keep it running):
```bash
python live_bot.py
```
- Auto-DMs every **new** join requester your invite, and adds them to the audience.
- Gives **you** (the owner) broadcast controls in the bot's DM.

## Owner commands (DM the bot)

| Command       | What it does                                                        |
|---------------|---------------------------------------------------------------------|
| `/start`      | Show the owner help panel                                           |
| `/stats`      | Audience size + whether a broadcast is running                      |
| `/broadcast`  | **Reply** to any post to send it to the whole audience              |
| `/cancel`     | Stop a running broadcast after the current message                  |

**How to broadcast:** send (or forward) the post you want — a **video with a
caption, a photo, plain text, anything** — to the bot, then **reply to it** with
`/broadcast`. The bot copies that exact message to everyone (no "forwarded from"
tag) and edits a live progress message as it goes.

### Premium / custom emoji

Custom (premium) emoji are part of the message as `MessageEntityCustomEmoji`
entities. `/broadcast` copies those entities verbatim, so premium emoji in your
post render for all recipients. Bots gained the right to send custom emoji in
**Bot API 9.4** (Feb 2026) — see the
[Bot API changelog](https://core.telegram.org/bots/api-changelog).
*Content rephrased for compliance with licensing restrictions.*

## Files

| File               | Role                                                          |
|--------------------|---------------------------------------------------------------|
| `setup.py`         | Interactive setup: creds + userbot OTP login + writes `.env`  |
| `config.py`        | Loads `.env`, message template, paths                         |
| `fetch_pending.py` | **Userbot**: dumps all pending requesters + seeds audience    |
| `bot_dm.py`        | Shared bot client + flood-safe single-DM helper               |
| `dm_backlog.py`    | **Bot**: DMs the backlog with pacing + resume                 |
| `live_bot.py`      | **Bot**: auto-DMs new requesters + owner `/broadcast` etc.    |
| `broadcast.py`     | Copies any message (media/caption/emoji) to the audience      |
| `audience.py`      | Persistent recipient set (`data/audience.json`)               |

## Important notes

- **Pace it.** DMing/broadcasting to thousands fast will trip `PeerFloodError`
  and can limit the bot. Defaults are conservative; slower is safer. Broadcasts
  stop cleanly on a hard rate limit — just re-run later.
- **Only messages people who requested to join / already got a DM.** That's the
  one case Telegram permits, which keeps this legitimate rather than spam.
- **Userbots are real accounts driven by the API** (a gray area in Telegram's
  ToS). Use a dedicated account and keep its role limited to just listing.
- **Never commit `.env` or `*.session`** — they're your logins. `.gitignore`
  already excludes them.
