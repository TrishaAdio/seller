# Channel Migration + Broadcast Bot (Telethon)

Reach everyone who requested to join your channel and move them to a new/backup
channel — and keep posting to them afterwards.

The content is a single **saved post** you set once with `/setpost`. It can be a
**video with caption, a photo, plain text, anything** — with **premium emoji** —
and the bot sends that exact post as-is. There is **no mandatory "new channel
link" setting**; whatever you put in the post is what people receive.

- **Bot** does all the sending (it's allowed to message pending join-requesters).
- **Userbot** (your own account) lists the existing backlog, which the Bot API
  can't do.

## Why a bot *and* a userbot?

Telegram lets a bot message a user **only** when that user has a *pending join
request* in a channel where the bot is an admin. That's the whole trick — it's
why this reaches people who never messaged the bot first.

|                              | Bot | Userbot (your account) |
|------------------------------|-----|------------------------|
| Send to a pending requester  | ✅  | ❌ (would be spam/ban) |
| Get live "new request" event | ✅  | —                      |
| **List** existing pending requests | ❌ (no Bot API method) | ✅ |

So: the **userbot enumerates** the backlog → the **bot sends** the post. New
requests after that are welcomed live by the bot, which also collects everyone
into a **broadcast audience** you can post to any time.

## Quick start

```bash
pip install -r requirements.txt
python setup.py          # interactive: asks for creds + logs you in
```

`setup.py` prompts for `API_ID` / `API_HASH` (from https://my.telegram.org) and
the bot token (from [@BotFather](https://t.me/BotFather)), then logs in your
**userbot** (phone → **OTP** code → **2FA** password if set) and the **bot**. It
auto-detects your `OWNER_ID` and writes `.env`. The channel link / message
prompts are **optional** — you'll set the real content with `/setpost`.

> Before running the bot: make the **bot an admin** of the source channel with
> the **"Add users"** right, ensure **your own account is an admin** there too,
> and turn on **"Approve new members"** (that's what creates join requests).

## Usage

**1) Start the bot and save your post:**
```bash
python live_bot.py
```
Then DM the bot: send the post you want (video/photo/text + premium emoji) and
**reply to it with `/setpost`**. Use `/preview` to see exactly what recipients
will get. From now on every **new** join requester is auto-sent that post.

**2) List the existing backlog** (userbot):
```bash
python fetch_pending.py
```
→ writes `data/pending_users.json` and seeds `data/audience.json`.

**3) Send the saved post to the backlog** (bot, paced + resume-safe):
```bash
python dm_backlog.py
```

Or skip step 3 and just use `/broadcast` from the bot — it targets the whole
audience (backlog included).

## Owner commands (DM the bot)

| Command       | What it does                                                        |
|---------------|---------------------------------------------------------------------|
| `/start`      | Show the owner help panel                                           |
| `/setpost`    | **Reply** to a message to save it as THE post                       |
| `/clearpost`  | Forget the saved post                                               |
| `/preview`    | Send the saved post to yourself                                     |
| `/broadcast`  | Push the saved post (or a replied post) to the whole audience       |
| `/stats`      | Audience size + whether a post is set + broadcast state             |
| `/cancel`     | Stop a running broadcast after the current message                  |

The bot copies the post (no "forwarded from" tag) and edits a live progress
message as it goes.

### Premium / custom emoji

Custom (premium) emoji are part of the message as `MessageEntityCustomEmoji`
entities. Because we re-send the post by reference, those entities are preserved
and render for all recipients. Bots gained the right to send custom emoji in
**Bot API 9.4** (Feb 2026) — see the
[Bot API changelog](https://core.telegram.org/bots/api-changelog).
*Content rephrased for compliance with licensing restrictions.*

## Files

| File               | Role                                                          |
|--------------------|---------------------------------------------------------------|
| `setup.py`         | Interactive setup: creds + userbot OTP login + writes `.env`  |
| `config.py`        | Loads `.env`, optional text fallback, paths                   |
| `fetch_pending.py` | **Userbot**: dumps all pending requesters + seeds audience    |
| `bot_dm.py`        | Shared bot client + flood-safe single-DM helper (fallback)    |
| `dm_backlog.py`    | **Bot**: sends the saved post to the backlog, paced + resume  |
| `live_bot.py`      | **Bot**: auto-welcome new requesters + owner commands         |
| `broadcast.py`     | Copies any message (media/caption/emoji) to the audience      |
| `saved_post.py`    | Stores the reference to the owner's saved post                |
| `audience.py`      | Persistent recipient set (`data/audience.json`)               |

## Important notes

- **Pace it.** Sending to thousands fast will trip `PeerFloodError` and can
  limit the bot. Defaults are conservative; slower is safer. Broadcasts stop
  cleanly on a hard rate limit — just re-run later.
- **Only reaches people who requested to join / already got the post.** That's
  the one case Telegram permits, which keeps this legitimate rather than spam.
- **Userbots are real accounts driven by the API** (a gray area in Telegram's
  ToS). Use a dedicated account and keep its role limited to just listing.
- **Never commit `.env` or `*.session`** — they're your logins. `.gitignore`
  already excludes them.
