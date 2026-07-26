# Join-Request Welcome + Broadcast Bot (Telethon)

One long-running bot. It watches the channels you register, DMs every new join
requester your saved post, collects them into a broadcast audience, and lets you
push any post to that audience later.

The content is a single **saved post** you set once with `/setpost`. It can be a
video with caption, a photo, plain text, anything — including **premium emoji**
and spoilers — and the bot sends that exact post as-is.

## Why this works

Telegram lets a bot message a user **only** when that user has a *pending join
request* in a channel where the bot is an admin. That's the whole trick — it's
why this reaches people who never messaged the bot first. The bot gets the
request as a live update, so it can always reach that user, and it remembers
them for future broadcasts.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env      # fill in API_ID, API_HASH, BOT_TOKEN, OWNER_ID
python live_bot.py
```

Then, in each channel you want to serve:

1. Make the bot an **admin** with the **"Add users"** right.
2. Turn on **"Approve new members"** (that's what creates join requests).
3. DM the bot `/add <chat_id>` (e.g. `/add -1001234567890`, or `/add @channel`).

Finally, DM the bot the post you want to send and **reply to it with
`/setpost`**. Use `/preview` to see exactly what recipients will get.

## Owner commands (DM the bot)

| Command             | What it does                                             |
|---------------------|----------------------------------------------------------|
| `/start`            | Show the owner panel                                     |
| `/add <chat_id>`    | Watch that channel's join requests                        |
| `/remove <chat_id>` | Stop watching that channel                                |
| `/chats`            | List watched channels                                     |
| `/setpost`          | **Reply** to a message to save it as THE post             |
| `/clearpost`        | Forget the saved post                                     |
| `/setbutton`        | Inline URL buttons for the post                           |
| `/clearbutton`      | Remove the buttons                                        |
| `/preview`          | Send the saved post to yourself                           |
| `/broadcast`        | Push the saved post (or a replied post) to the audience    |
| `/bcast`            | Alias of `/broadcast`                                     |
| `/stats`            | Audience + channels + post/button status                  |
| `/cancel`           | Stop a running broadcast after the current message         |

`/add` accepts a `-100…` id, a bare channel id, an `@username`, or a t.me link.
While no channel is registered the bot handles join requests from **every** chat
it administers; once one is added, only registered chats are handled.

The bot copies the post (no "forwarded from" tag) and edits a live progress
message as a broadcast runs.

### Buttons

```
/setbutton
Join - https://t.me/x | Chat - https://t.me/y
Website - https://example.com
```

Each line is a row; `|` splits buttons within a row.

### Premium / custom emoji

Custom (premium) emoji are part of the message as `MessageEntityCustomEmoji`
entities. Because the post is re-sent by reference, those entities are preserved
and render for all recipients. Bots gained the right to send custom emoji in
**Bot API 9.4** — see the
[Bot API changelog](https://core.telegram.org/bots/api-changelog).
*Content rephrased for compliance with licensing restrictions.*

## Files

| File            | Role                                                        |
|-----------------|-------------------------------------------------------------|
| `live_bot.py`   | The bot: auto-welcome, channel registry, owner commands      |
| `config.py`     | Loads `.env`, paths                                          |
| `channels.py`   | Watched channels (`data/channels.json`, `/add` + `/remove`)  |
| `audience.py`   | Persistent recipient set (`data/audience.json`)              |
| `broadcast.py`  | Copies any message (media/caption/emoji) to the audience     |
| `saved_post.py` | Stores the reference to the owner's saved post               |
| `buttons.py`    | Inline URL buttons (`data/buttons.json`)                     |

## Notes

- **Pace it.** Sending to thousands fast will trip `PeerFloodError` and can
  limit the bot. Defaults are conservative; slower is safer. Broadcasts stop
  cleanly on a hard rate limit — just re-run later.
- **Only reaches people who requested to join.** That's the one case Telegram
  permits, which keeps this legitimate rather than spam.
- Old join requests made *before* the bot was added can't be enumerated by a
  bot (the Bot API has no method to list them) — only live requests are caught.
- **Never commit `.env` or `*.session`** — they're your logins. `.gitignore`
  already excludes them.
