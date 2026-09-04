# BotFather launch pack

This is the canonical copy/paste profile retained by SPEC-0019. Record the final username and
verification date at the bottom; never record the token.

Telegram currently limits display names to 64 characters, usernames to 5-32 Latin
letters, numbers, or underscores ending in `bot`, About text to 120 characters, full
descriptions to 512 characters, command names to 1-32 characters, and command
descriptions to 1-256 characters. A privacy-policy URL must be publicly reachable over
HTTPS. Username availability must be checked live.

## Identity

Default and English display name:

```text
Read Aloud - Text to Voice
```

Russian display name:

```text
Read Aloud - озвучивание текста
```

Existing username: `@TextToVoiceRuBot`. Telegram does not permit changing an existing
bot's primary username, so retain it. The username is descriptive and contains no retired
brand reference.

## About

Russian:

```text
Озвучиваю текст и подписи к медиа локально. Этот бот не сохраняет сообщения и аудио.
```

English:

```text
Turns text and media captions into voice notes. Local synthesis; this bot stores no messages or audio.
```

## Full description

Russian:

```text
Отправьте или перешлите текст либо добавьте подпись к медиа, и Read Aloud вернет голосовую заметку в Telegram. Лучше всего бот работает с русским текстом; качество английской речи зависит от настроенного голоса. Озвучивание выполняется локально; бот не хранит сообщения и аудио.
```

English:

```text
Send or forward text, or add a caption to media, and Read Aloud will return a Telegram voice note. Russian is strongest; English quality depends on the configured voice. Speech is generated locally, and the bot stores neither messages nor audio.
```

## Privacy policy

The public page contains the full policy in Russian and English:

```text
https://telegram-tts-bot.iho.su/
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
Привет! Это Read Aloud.

Я превращаю обычные и пересланные текстовые сообщения, включая подписи к медиа, в голосовые заметки. В зависимости от настроенного голоса бот также может естественно читать английские слова и фразы.

Отправьте мне текст или медиа с подписью — я отвечу готовой голосовой заметкой.

Озвучивание выполняется локально. Я не сохраняю сообщения и созданное аудио.

/help — подробная справка

Политика конфиденциальности: http://telegram-tts-bot.iho.su/
```

English:

```text
Hi! This is Read Aloud.

I turn regular and forwarded text messages, including media captions, into voice notes. Depending on the configured voice, the bot can also read English words and phrases naturally.

Send me text or media with a caption, and I will reply with a ready-to-play voice note.

Speech is generated locally. I do not store messages or generated audio.

/help — detailed help

Privacy policy: http://telegram-tts-bot.iho.su/
```

## Runtime copy

### `/help`

Russian:

```text
Как пользоваться:

• Отправьте обычное текстовое сообщение.
• Или перешлите текстовое сообщение из другого чата.
• Текст в подписи к фото, видео или файлу тоже можно озвучить.
• Получите голосовую заметку в ответ.

Бот работает только в личном чате. Лучше всего он работает с русским текстом; качество английских слов и фраз зависит от настроенного голоса. Озвучивается только текст сообщения или подписи, без самого медиа, имени автора и данных пересылки. Сообщения и готовое аудио не сохраняются. Если бот занят, запросы ожидают в ограниченной очереди.

/start — показать приветствие
/help — показать эту справку

Репозиторий: https://github.com/ihoru/telegram-tts-bot

Политика конфиденциальности: http://telegram-tts-bot.iho.su/
```

English:

```text
How to use the bot:

• Send a regular text message.
• Or forward a text message from another chat.
• Text in a photo, video, or file caption can be voiced too.
• Receive a voice note in reply.

The bot works only in private chats. It is strongest in Russian; the quality of English words and phrases depends on the configured voice. It reads only the message text or caption, not the media, author name, or forwarding details. Messages and generated audio are not stored. If the bot is busy, requests wait in a bounded queue.

/start — show the welcome message
/help — show this help

Repository: https://github.com/ihoru/telegram-tts-bot

Privacy policy: http://telegram-tts-bot.iho.su/
```

## Avatar

Upload `assets/read-aloud-avatar.png`. Its editable source is
`assets/read-aloud-avatar.svg`. The mark uses a deep navy background, white speech bubble
whose tail becomes a three-bar waveform, and one turquoise accent. It contains no text,
shadows, gradients, or tiny detail and stays inside the central 70% circle-safe area.

## Setup checklist

1. In BotFather, select the existing `@TextToVoiceRuBot`; do not create a replacement bot
   or rotate its token for this rebrand.
2. Set the default, English, and Russian display names, About text, full descriptions,
   and command lists from this document. `/start` and `/help` are runtime responses and
   update when the new bot code is deployed; they are not pasted into BotFather.
3. Keep the existing privacy-policy URL from this document; no URL change is required.
4. The existing avatar artwork contains no text and does not need to be uploaded again.
   If it is missing, run `/setuserpic` and upload `assets/read-aloud-avatar.png`.
5. Keep group joining disabled.
6. Leave group privacy enabled and inline mode disabled. Do not configure domains,
   payments, Mini Apps, description media, or extra commands for v1.
7. In Russian and English Telegram clients, verify the profile, privacy-policy link,
   `/start`, `/help`, direct text, forwarded text, unsupported media guidance, and a
   returned voice note.

BotFather does not provide a friends-only private-message allowlist for this ordinary
bot. Anyone who discovers the username can send it messages.

## Verification record

- Final username: `@TextToVoiceRuBot`
- Verified on: _not verified yet_
- Verified by: _not verified yet_
