# BotFather launch pack

This is the canonical copy/paste profile for SPEC-0005. Record the final username and
verification date at the bottom; never record the token.

Telegram currently limits display names to 64 characters, usernames to 5-32 Latin
letters, numbers, or underscores ending in `bot`, About text to 120 characters, full
descriptions to 512 characters, command names to 1-32 characters, and command
descriptions to 1-256 characters. A privacy-policy URL must be publicly reachable over
HTTPS. Username availability must be checked live.

## Identity

Russian display name:

```text
Вслух — текст в голос
```

English display name:

```text
Vslukh — Text to Voice
```

Try usernames in this order:

1. `@VslukhBot`
2. `@VslukhVoiceBot`
3. `@TextVslukhBot`
4. `@VslukhTTSBot`

Alternative name families retained for future rebranding:

- `ПроЧти / Prochti`: `@ProchtiBot`, `@ProchtiVoiceBot`, `@ProchtiTTSBot`,
  `@ListenDontReadBot`
- `СловоЗвук / SlovoZvuk`: `@SlovoZvukBot`, `@SlovoVoiceBot`,
  `@RussianVoiceNoteBot`, `@TextToVoiceRuBot`

## About

Russian:

```text
Озвучиваю обычные и пересланные тексты локально. Этот бот не сохраняет сообщения и аудио.
```

English:

```text
Turns regular and forwarded text into voice notes. Local synthesis; this bot stores no messages or audio.
```

## Full description

Russian:

```text
Превращаю текст в голосовые сообщения прямо в Telegram. Лучше всего работаю с русским текстом; качество английских слов и фраз зависит от настроенного голоса. Озвучивание выполняется локально; бот не хранит сообщения или аудио.
```

English:

```text
I turn text into Telegram voice notes. Russian is strongest; English quality depends on the configured voice. Send or forward text and I will return ready-to-play audio. Speech generation runs locally; the bot stores neither messages nor audio.
```

## Privacy policy

The public page contains the full policy in Russian and English:

```text
https://vslukh-privacy.ihoruru.chatgpt.site
```

## Commands

Russian:

```text
start - Начать работу с ботом
help - Показать подробную справку
```

English:

```text
start - Start using the bot
help - Show detailed help
```

## Welcome message (`/start`)

Russian:

```text
Привет! Я "Вслух".

Я превращаю обычные и пересланные текстовые сообщения в голосовые заметки. В зависимости от настроенного голоса бот также может естественно читать английские слова и фразы.

Отправьте мне текст или перешлите текстовое сообщение — я отвечу готовой голосовой заметкой.

Озвучивание выполняется локально. Я не сохраняю сообщения и созданное аудио.

/help — подробная справка
```

English:

```text
Hello! I am Vslukh.

I turn regular and forwarded text messages into voice notes. Depending on the configured voice, the bot can also read English words and phrases naturally.

Send me text or forward a text message, and I will reply with a ready-to-play voice note.

Speech is generated locally. I do not store messages or generated audio.

/help — detailed help
```

## Runtime copy

### `/help`

Russian:

```text
Как пользоваться:

• Отправьте обычное текстовое сообщение.
• Или перешлите текстовое сообщение из другого чата.
• Получите голосовую заметку в ответ.

Бот работает только в личном чате. Лучше всего он работает с русским текстом; качество английских слов и фраз зависит от настроенного голоса. Озвучивается только текст сообщения, без имени автора и данных пересылки. Сообщения и готовое аудио не сохраняются. Если бот занят, попробуйте снова позже.

/start — показать приветствие
/help — показать эту справку
```

English:

```text
How to use the bot:

• Send a regular text message.
• Or forward a text message from another chat.
• Receive a voice note in reply.

The bot works only in private chats. It is strongest in Russian; the quality of English words and phrases depends on the configured voice. It reads only the message text, not the author name or forwarding details. Messages and generated audio are not stored. If the bot is busy, try again later.

/start — show the welcome message
/help — show this help
```

## Avatar

Upload `assets/vslukh-avatar.png`. Its editable source is
`assets/vslukh-avatar.svg`. The mark uses a deep navy background, white speech bubble
whose tail becomes a three-bar waveform, and one turquoise accent. It contains no text,
shadows, gradients, or tiny detail and stays inside the central 70% circle-safe area.

## Setup checklist

1. In BotFather, run `/newbot`, paste the recommended display name, and choose the first
   available username from the ordered list.
2. Store the issued token only in the runtime secret. Never paste it into this repository,
   specifications, logs, shell history, Docker build arguments, or committed CI settings.
3. Set the localized display names, About text, full descriptions, command lists, and
   welcome copy from this document.
4. Configure the privacy-policy URL from this document.
5. Run `/setuserpic` and upload `assets/vslukh-avatar.png`.
6. Run `/setjoingroups` and disable group joining.
7. Leave group privacy enabled and inline mode disabled. Do not configure domains,
   payments, Mini Apps, description media, or extra commands for v1.
8. In Russian and English Telegram clients, verify the profile, privacy-policy link,
   `/start`, `/help`, direct text, forwarded text, unsupported media guidance, and a
   returned voice note.

BotFather does not provide a friends-only private-message allowlist for this ordinary
bot. Anyone who discovers the username can send it messages.

## Verification record

- Final username: _not created yet_
- Verified on: _not verified yet_
- Verified by: _not verified yet_
