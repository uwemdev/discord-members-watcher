
import hashlib
import html
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

if os.name == 'nt':
    import msvcrt
else:
    import fcntl

import discord
import requests
from discord.ext import commands

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv(dotenv_path=Path(__file__).with_name('.env'))

JOIN_LOG_FILE = 'join_events.log'
LAST_MEMBERS_FILE = Path(__file__).with_name('last_members.json')
LAST_MEMBERS_LOCK_FILE = Path(__file__).with_name('last_members.lock')
MESSAGE_CACHE_FILE = Path(__file__).with_name('sent_messages.json')
BOT_INSTANCE_LOCK_FILE = Path(__file__).with_name('bot.instance.lock')
JOIN_DEDUPE_WINDOW_SECONDS = 10 * 60
TELEGRAM_DEDUPE_WINDOW_SECONDS = 60 * 60
RECENT_JOIN_CACHE_LIMIT = 200
RECENT_MESSAGE_CACHE_LIMIT = 500
join_state_lock = Lock()
instance_lock_handle = None


DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL = os.getenv('TELEGRAM_CHANNEL')

if not DISCORD_TOKEN or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL:
    raise RuntimeError(
        'Missing required environment variables: DISCORD_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL'
    )

bot_options = {'self_bot': True}

# `discord.py-self` does not expose `discord.Intents`, while standard
# `discord.py` does. Keep the bot runnable in both environments.
if hasattr(discord, 'Intents'):
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    bot_options['intents'] = intents

bot = commands.Bot(command_prefix='!', **bot_options)


def ensure_lockfile_seeded(handle):
    handle.seek(0)
    if not handle.read(1):
        handle.write('0')
        handle.flush()
    handle.seek(0)


@contextmanager
def last_members_file_lock():
    LAST_MEMBERS_LOCK_FILE.touch(exist_ok=True)
    with LAST_MEMBERS_LOCK_FILE.open('r+', encoding='utf-8') as handle:
        ensure_lockfile_seeded(handle)
        if os.name == 'nt':
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def acquire_instance_lock():
    global instance_lock_handle

    BOT_INSTANCE_LOCK_FILE.touch(exist_ok=True)
    handle = BOT_INSTANCE_LOCK_FILE.open('r+', encoding='utf-8')
    ensure_lockfile_seeded(handle)

    try:
        if os.name == 'nt':
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False

    instance_lock_handle = handle
    return True


def load_last_members():
    if not LAST_MEMBERS_FILE.exists():
        return {}

    try:
        with LAST_MEMBERS_FILE.open('r', encoding='utf-8') as handle:
            raw_data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}

    normalized = {}

    for guild_id, entries in raw_data.items():
        if isinstance(entries, dict):
            member_times = {}
            for member_id, seen_at in entries.items():
                try:
                    member_times[str(member_id)] = int(seen_at)
                except (TypeError, ValueError):
                    continue
        elif isinstance(entries, list):
            member_times = {str(member_id): 0 for member_id in entries}
        else:
            continue

        if member_times:
            normalized[str(guild_id)] = member_times

    return normalized


def save_last_members(data):
    try:
        temp_file = LAST_MEMBERS_FILE.with_suffix('.json.tmp')
        with temp_file.open('w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False)
        temp_file.replace(LAST_MEMBERS_FILE)
    except OSError as exc:
        print(f'Failed to save recent join cache: {exc}')


def is_already_seen(guild_id, member_id):
    now = int(time.time())
    guild_key = str(guild_id)
    member_key = str(member_id)

    with join_state_lock:
        with last_members_file_lock():
            recent_join_cache = load_last_members()

            for cached_guild_id in list(recent_join_cache):
                member_times = recent_join_cache.get(cached_guild_id, {})
                fresh_member_times = {
                    cached_member_id: int(seen_at)
                    for cached_member_id, seen_at in member_times.items()
                    if int(seen_at) and now - int(seen_at) < JOIN_DEDUPE_WINDOW_SECONDS
                }
                if fresh_member_times:
                    recent_join_cache[cached_guild_id] = fresh_member_times
                else:
                    recent_join_cache.pop(cached_guild_id, None)

            guild_entries = recent_join_cache.setdefault(guild_key, {})
            last_seen = int(guild_entries.get(member_key, 0))
            if last_seen and now - last_seen < JOIN_DEDUPE_WINDOW_SECONDS:
                save_last_members(recent_join_cache)
                return True

            guild_entries[member_key] = now
            if len(guild_entries) > RECENT_JOIN_CACHE_LIMIT:
                recent_items = sorted(guild_entries.items(), key=lambda item: item[1], reverse=True)[:RECENT_JOIN_CACHE_LIMIT]
                recent_join_cache[guild_key] = dict(recent_items)

            save_last_members(recent_join_cache)
            return False


def load_message_cache():
    if not MESSAGE_CACHE_FILE.exists():
        return {}

    try:
        with MESSAGE_CACHE_FILE.open('r', encoding='utf-8') as handle:
            raw_data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}

    normalized = {}
    for fingerprint, seen_at in raw_data.items():
        try:
            normalized[str(fingerprint)] = int(seen_at)
        except (TypeError, ValueError):
            continue

    return normalized


def save_message_cache(data):
    try:
        temp_file = MESSAGE_CACHE_FILE.with_suffix('.json.tmp')
        with temp_file.open('w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False)
        temp_file.replace(MESSAGE_CACHE_FILE)
    except OSError as exc:
        print(f'Failed to save Telegram dedupe cache: {exc}')


def is_duplicate_telegram_message(text, image_url=None):
    now = int(time.time())
    fingerprint = hashlib.sha256(f'{text}\n{image_url or ""}'.encode('utf-8')).hexdigest()

    with join_state_lock:
        with last_members_file_lock():
            message_cache = load_message_cache()
            message_cache = {
                cached_fingerprint: int(seen_at)
                for cached_fingerprint, seen_at in message_cache.items()
                if now - int(seen_at) < TELEGRAM_DEDUPE_WINDOW_SECONDS
            }

            if fingerprint in message_cache:
                save_message_cache(message_cache)
                return True

            message_cache[fingerprint] = now
            if len(message_cache) > RECENT_MESSAGE_CACHE_LIMIT:
                recent_items = sorted(message_cache.items(), key=lambda item: item[1], reverse=True)[:RECENT_MESSAGE_CACHE_LIMIT]
                message_cache = dict(recent_items)

            save_message_cache(message_cache)
            return False


def send_telegram_message(text, image_url=None):
    if is_duplicate_telegram_message(text, image_url=image_url):
        print('Skipping duplicate Telegram notification with matching content.')
        return

    base_url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}'
    try:
        if image_url:
            photo_data = {
                'chat_id': TELEGRAM_CHANNEL,
                'photo': image_url,
                'caption': text[:1024],
                'parse_mode': 'HTML',
            }
            response = requests.post(f'{base_url}/sendPhoto', data=photo_data, timeout=20)
            if response.ok:
                return

        message_data = {
            'chat_id': TELEGRAM_CHANNEL,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True,
        }
        requests.post(f'{base_url}/sendMessage', data=message_data, timeout=20).raise_for_status()
    except requests.exceptions.RequestException as exc:
        print(f'Telegram send failed: {exc}')


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')


@bot.event
async def on_member_join(member):
    if is_already_seen(member.guild.id, member.id):
        print(f'Duplicate join event for {member} in {member.guild.name}, skipping.')
        return

    user_tag = str(member)
    server_name = member.guild.name
    server_id = member.guild.id
    user_link = f'https://discord.com/users/{member.id}'

    inviter = None
    try:
        async for entry in member.guild.audit_logs(limit=10, action=discord.AuditLogAction.member_invite):
            if entry.target and entry.target.id == member.id:
                inviter = entry.user
                break
    except Exception:
        inviter = None

    image_url = member.guild.icon.url if member.guild.icon else getattr(member.display_avatar, 'url', None)

    lines = [
        '🎉 <b>New member joined</b>',
        f"👤 <a href='{user_link}'>{html.escape(user_tag)}</a> (ID: <code>{member.id}</code>)",
        f"🏠 {html.escape(server_name)} (ID: <code>{server_id}</code>)",
    ]
    if inviter:
        lines.append(f'📨 Invited by {html.escape(str(inviter))}')

    send_telegram_message('\n'.join(lines), image_url=image_url)

    with open(JOIN_LOG_FILE, 'a', encoding='utf-8') as logf:
        logf.write(
            f"{datetime.now(timezone.utc).isoformat()} | {user_tag} | {member.id} | {server_name} | {server_id}\n"
        )


def main():
    if not acquire_instance_lock():
        print('Another bot instance is already running; exiting to prevent duplicate Telegram alerts.')
        return

    while True:
        print('Bot starting...')
        try:
            bot.run(DISCORD_TOKEN)
        except Exception as exc:
            print(f'Bot crashed: {exc}. Restarting in 10 seconds...')
            time.sleep(10)


if __name__ == '__main__':
    main()
