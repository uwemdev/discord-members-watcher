import hashlib
import html
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import discord
import requests
from discord.ext import commands

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv(dotenv_path=Path(__file__).with_name('.env'))

# FILES
JOIN_LOG_FILE = 'join_events.log'
LAST_MEMBERS_FILE = Path(__file__).with_name('last_members.json')
MESSAGE_CACHE_FILE = Path(__file__).with_name('sent_messages.json')
ROUND_ROBIN_FILE = Path(__file__).with_name('channel_index.json')

# SETTINGS
JOIN_DEDUPE_WINDOW_SECONDS = 10 * 60
TELEGRAM_DEDUPE_WINDOW_SECONDS = 60 * 60
RECENT_JOIN_CACHE_LIMIT = 200
RECENT_MESSAGE_CACHE_LIMIT = 500

lock = Lock()

# ENV
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL = os.getenv('TELEGRAM_CHANNEL')
TELEGRAM_CHANNEL_1 = os.getenv('TELEGRAM_CHANNEL_1')
TELEGRAM_CHANNEL_2 = os.getenv('TELEGRAM_CHANNEL_2')

TELEGRAM_CHANNELS = list(dict.fromkeys(
    channel
    for channel in [TELEGRAM_CHANNEL_1, TELEGRAM_CHANNEL_2, TELEGRAM_CHANNEL]
    if channel
))

if not DISCORD_TOKEN or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNELS:
    raise RuntimeError("Missing environment variables")

# BOT SETUP
bot_options = {'self_bot': True}

if hasattr(discord, 'Intents'):
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    bot_options['intents'] = intents

try:
    bot = commands.Bot(command_prefix='!', **bot_options)
except TypeError:
    bot_options.pop('self_bot', None)
    bot = commands.Bot(command_prefix='!', **bot_options)


# JSON HELPERS
def load_json(file):
    if not file.exists():
        return {}
    try:
        with file.open('r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}


def save_json(file, data):
    try:
        with file.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        print(f'Error saving {file}: {e}')


# JOIN DEDUPE
def is_already_seen(guild_id, member_id):
    now = int(time.time())

    with lock:
        data = load_json(LAST_MEMBERS_FILE)

        guild = data.setdefault(str(guild_id), {})
        last_seen = int(guild.get(str(member_id), 0))

        if last_seen and now - last_seen < JOIN_DEDUPE_WINDOW_SECONDS:
            return True

        guild[str(member_id)] = now

        if len(guild) > RECENT_JOIN_CACHE_LIMIT:
            sorted_items = sorted(guild.items(), key=lambda x: x[1], reverse=True)[:RECENT_JOIN_CACHE_LIMIT]
            data[str(guild_id)] = dict(sorted_items)

        save_json(LAST_MEMBERS_FILE, data)
        return False


# TELEGRAM GLOBAL DEDUPE
def is_duplicate_telegram_message(text, image_url=None):
    now = int(time.time())
    fingerprint = hashlib.sha256(f'{text}{image_url or ""}'.encode()).hexdigest()

    with lock:
        data = load_json(MESSAGE_CACHE_FILE)

        data = {
            k: v for k, v in data.items()
            if now - int(v) < TELEGRAM_DEDUPE_WINDOW_SECONDS
        }

        if fingerprint in data:
            return True

        data[fingerprint] = now

        if len(data) > RECENT_MESSAGE_CACHE_LIMIT:
            sorted_items = sorted(data.items(), key=lambda x: x[1], reverse=True)[:RECENT_MESSAGE_CACHE_LIMIT]
            data = dict(sorted_items)

        save_json(MESSAGE_CACHE_FILE, data)
        return False


def get_next_channel():
    with lock:
        data = {"index": 0}

        if ROUND_ROBIN_FILE.exists():
            try:
                with ROUND_ROBIN_FILE.open('r', encoding='utf-8') as f:
                    data = json.load(f)
            except:
                data = {"index": 0}

        index = int(data.get("index", 0)) % len(TELEGRAM_CHANNELS)
        next_index = (index + 1) % len(TELEGRAM_CHANNELS)

        data["index"] = next_index

        try:
            with ROUND_ROBIN_FILE.open('w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Channel index save error: {e}")

        return TELEGRAM_CHANNELS[index]


def format_message_for_channel(text, channel):
    if channel != TELEGRAM_CHANNEL_2:
        return text

    lines = text.splitlines()
    if not lines:
        return text

    alt_lines = ["⚡ <b>Member Update</b>"]

    for line in lines[1:]:
        cleaned = line.lstrip("🎉👤🏠 ")
        alt_lines.append(f"• {cleaned}")

    return "\n".join(alt_lines)


# SEND TELEGRAM
def send_telegram_message(text, image_url=None):
    if is_duplicate_telegram_message(text, image_url):
        print("Duplicate skipped globally")
        return

    base_url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}'
    channel = get_next_channel()
    formatted_text = format_message_for_channel(text, channel)

    try:
        if image_url:
            r = requests.post(
                f'{base_url}/sendPhoto',
                data={
                    'chat_id': channel,
                    'photo': image_url,
                    'caption': formatted_text[:1024],
                    'parse_mode': 'HTML'
                },
                timeout=20
            )
            if r.ok:
                print(f"Sent to {channel}")
                return

        requests.post(
            f'{base_url}/sendMessage',
            data={
                'chat_id': channel,
                'text': formatted_text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            },
            timeout=20
        )

        print(f"Sent to {channel}")

    except Exception as e:
        print(f"Telegram error for {channel}: {e}")


# EVENTS
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')


@bot.event
async def on_member_join(member):
    if is_already_seen(member.guild.id, member.id):
        print("Duplicate join skipped")
        return

    user_tag = str(member)
    server_name = member.guild.name
    user_link = f'https://discord.com/users/{member.id}'

    image_url = member.guild.icon.url if member.guild.icon else None

    message = (
        f"🎉 <b>New member joined</b>\n"
        f"👤 <a href='{user_link}'>{html.escape(user_tag)}</a>\n"
        f"🏠 {html.escape(server_name)}"
    )

    send_telegram_message(message, image_url=image_url)

    with open(JOIN_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{datetime.now(timezone.utc)} | {user_tag}\n")


# MAIN LOOP
def main():
    while True:
        try:
            print("Bot starting...")
            bot.run(DISCORD_TOKEN)
        except Exception as e:
            print(f"Crash: {e}, restarting in 10s...")
            time.sleep(10)


if __name__ == '__main__':
    main()