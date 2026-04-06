
import asyncio
import discord
from discord.ext import commands
import requests
import json
import os
import time
from datetime import datetime, timezone
import random
import html
WELCOME_GIFS = []

# Log file for join events
JOIN_LOG_FILE = 'join_events.log'

# Configure secrets via environment variables for local use and Render deployment.
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL = os.getenv('TELEGRAM_CHANNEL')

if not DISCORD_TOKEN or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL:
    raise RuntimeError(
        'Missing required environment variables: DISCORD_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL'
    )

bot = commands.Bot(command_prefix='!', self_bot=True)

# File to store last known members
MEMBERS_FILE = 'last_members.json'

def send_telegram_message(text):
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    data = {
        'chat_id': TELEGRAM_CHANNEL,
        'text': text,
        'parse_mode': 'HTML',
    }
    try:
        requests.post(url, data=data, timeout=10)
    except requests.exceptions.RequestException as e:
        pass

# Optional: Map server IDs to invite links
SERVER_INVITES = {
    # Example: '123456789012345678': 'https://discord.gg/yourinvite',
    # Add your server IDs and invite links here
}



@bot.event
async def on_member_join(member):
    user_tag = f"{member.name}#{member.discriminator}"
    server_name = member.guild.name
    server_id = member.guild.id
    user_link = f"https://discord.com/users/{member.id}"

    # Try to get inviter (requires Audit Log permission)
    inviter = None
    inviter_server = None
    try:
        async for entry in member.guild.audit_logs(limit=10, action=discord.AuditLogAction.member_invite):
            if entry.target.id == member.id:
                inviter = entry.user
                inviter_server = inviter.guild.name if inviter.guild else None
                break
    except Exception:
        pass

    msg = f"New user joined: <a href='{user_link}'>{html.escape(user_tag)}</a> (ID: {member.id}) in {html.escape(server_name)} (ID: {server_id})"
    if inviter:
        msg += f" - Invited by {html.escape(inviter.name)}#{inviter.discriminator}"
        if inviter_server and inviter_server != server_name:
            msg += f" from {html.escape(inviter_server)}"

    send_telegram_message(msg)
    await asyncio.sleep(60)  # Delay 1 minute to avoid rate limiting without blocking the bot
    with open(JOIN_LOG_FILE, 'a', encoding='utf-8') as logf:
        logf.write(f"{datetime.now(timezone.utc).isoformat()} | {user_tag} | {member.id} | {server_name} | {server_id}\n")

# Error handling and auto-restart
while True:
    print("Bot starting...")
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"Bot crashed: {e}. Restarting in 10 seconds...")
        time.sleep(10)