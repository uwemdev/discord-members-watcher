
import html
import os
import time
from datetime import datetime, timezone
from pathlib import Path

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


def send_telegram_message(text, image_url=None):
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
    while True:
        print('Bot starting...')
        try:
            bot.run(DISCORD_TOKEN)
        except Exception as exc:
            print(f'Bot crashed: {exc}. Restarting in 10 seconds...')
            time.sleep(10)


if __name__ == '__main__':
    main()
