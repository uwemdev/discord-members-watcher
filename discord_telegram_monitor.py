
import discord
from discord.ext import commands
import requests
import json
import os
import time
from datetime import datetime, timezone
import random
WELCOME_GIFS = [
    'https://media.giphy.com/media/OkJat1YNdoD3W/giphy.gif',
    'https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif',
    'https://media.giphy.com/media/xUPGcguWZHRC2HyBRS/giphy.gif',
    'https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif',
    'https://media.giphy.com/media/3o6Zt481isNVuQI1l6/giphy.gif',
]

# Multi-language support (add more as needed)
WELCOME_MESSAGES = {
    'en': "Welcome to the server! 🎊",
    'es': "¡Bienvenido al servidor! 🎊",
    'fr': "Bienvenue sur le serveur ! 🎊",
    'de': "Willkommen auf dem Server! 🎊",
}

# Log file for join events
JOIN_LOG_FILE = 'join_events.log'

# 1. Replace with your Discord user token (NOT your bot token)
DISCORD_TOKEN = 'MTQ4ODI0Mjg5NTQ0MTEwNDkxNg.GuNKuX.SjIDpLFDTgJyiUyqxolxIUCPnztupwQzxHLJls'

# 2. Replace with your Telegram bot token (from BotFather)
TELEGRAM_BOT_TOKEN = '8783172226:AAFjYu6Q3hYgJ3hYOCyFFz6OCiDhV-ylrBc'

# 3. Replace with your Telegram channel username (e.g., @yourchannel) or channel ID
TELEGRAM_CHANNEL = '@thediscordtelegram'

bot = commands.Bot(command_prefix='!', self_bot=True)

# File to store last known members
MEMBERS_FILE = 'last_members.json'

def load_last_members():
    if os.path.exists(MEMBERS_FILE):
        with open(MEMBERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_last_members(data):
    with open(MEMBERS_FILE, 'w') as f:
        json.dump(data, f)

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
        print(f"[Telegram Error] {e}")
        # Optionally, log to a file or ignore

# Send a test message on script start
send_telegram_message("Test message from my bot!")

# On startup, report new members since last run
@bot.event
async def on_ready():
    try:
        last_members = load_last_members()
        new_last_members = {}
        for guild in bot.guilds:
            # await guild.chunk()  # Removed: Not allowed for user/self-bots
            current_ids = set(str(m.id) for m in guild.members)
            new_last_members[str(guild.id)] = list(current_ids)
            prev_ids = set(last_members.get(str(guild.id), []))
            new_ids = current_ids - prev_ids
            if new_ids:
                new_users = [m for m in guild.members if str(m.id) in new_ids]
                invite_link = SERVER_INVITES.get(str(guild.id), None)
                msg = f"<b>New members since last run in {guild.name} (ID: {guild.id}):</b>\n"
                msg += '\n'.join(f"<code>{u.name}#{u.discriminator}</code>" for u in new_users)
                if invite_link:
                    msg += f"\nServer link: {invite_link}"
                else:
                    msg += f"\nServer ID: <code>{guild.id}</code> (no invite link set)"
                send_telegram_message(msg)
        save_last_members(new_last_members)
    except Exception as e:
        error_msg = f"<b>on_ready error:</b> {e}"
        print(error_msg)
        send_telegram_message(error_msg)

# Optional: Map server IDs to invite links
SERVER_INVITES = {
    # Example: '123456789012345678': 'https://discord.gg/yourinvite',
    # Add your server IDs and invite links here
}



@bot.event
async def on_member_join(member):
    server = member.guild
    server_name = server.name
    server_id = server.id
    user_tag = f"{member.name}#{member.discriminator}"
    avatar_url = member.avatar.url if member.avatar else ''
    account_created = member.created_at.strftime('%Y-%m-%d %H:%M UTC')
    member_count = server.member_count
    join_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    server_icon = server.icon.url if server.icon else ''
    suspicious = (datetime.now(timezone.utc) - member.created_at).days < 3
    roles = [role.name for role in member.roles if role.name != '@everyone']
    roles_str = ', '.join(roles) if roles else 'None'
    # Multi-language (default to English)
    lang = 'en'  # You could detect or set per-server
    welcome_text = WELCOME_MESSAGES.get(lang, WELCOME_MESSAGES['en'])
    gif_url = random.choice(WELCOME_GIFS)

    # Try to get or create an invite link
    invite_link = SERVER_INVITES.get(str(server_id), None)
    if not invite_link:
        try:
            for channel in server.text_channels:
                if channel.permissions_for(server.me).create_instant_invite:
                    invite = await channel.create_invite(max_age=0, max_uses=0, unique=False)
                    invite_link = invite.url
                    SERVER_INVITES[str(server_id)] = invite_link
                    break
        except Exception as e:
            invite_link = None

    # Try to get inviter (requires Audit Log permission)
    inviter = None
    try:
        async for entry in server.audit_logs(limit=10, action=discord.AuditLogAction.member_invite):
            if entry.target.id == member.id:
                inviter = entry.user
                break
    except Exception:
        pass

    # Suspicious account warning
    suspicious_msg = ''
    if suspicious:
        suspicious_msg = '\n⚠️ <b>Suspicious account (created recently!)</b>'

    # Moderation: auto-ban flagged accounts (example, not active)
    # if suspicious:
    #     await member.ban(reason="Auto-ban: suspicious account")
    #     suspicious_msg += '\n🚫 User auto-banned.'

    msg = f"🎉 <b>Welcome a new member!</b>\n"
    msg += f"👤 User: <code>{user_tag}</code>\n"
    msg += f"🆔 User ID: <code>{member.id}</code>\n"
    msg += f"📅 Account created: <b>{account_created}</b>\n"
    msg += f"🏠 Server: <b>{server_name}</b> (ID: <code>{server_id}</code>)\n"
    if server_icon:
        msg += f"<a href='{server_icon}'>Server Icon</a>\n"
    if avatar_url:
        msg += f"<a href='{avatar_url}'>User Avatar</a>\n"
    if invite_link:
        msg += f"🔗 <a href='{invite_link}'>Join Server</a>\n"
    else:
        msg += f"Server ID: <code>{server_id}</code> (no invite link set)\n"
    if inviter:
        msg += f"🙋 Invited by: <code>{inviter.name}#{inviter.discriminator}</code>\n"
    msg += f"👥 Member count: <b>{member_count}</b>\n"
    msg += f"⏰ Joined: <b>{join_time}</b>\n"
    msg += f"🏷️ Roles: <b>{roles_str}</b>\n"
    msg += suspicious_msg
    msg += f"\n{welcome_text}"
    msg += f"\n<a href='{gif_url}'>Welcome GIF</a>"
    print(msg)
    send_telegram_message(msg)

    # Log join event
    with open(JOIN_LOG_FILE, 'a', encoding='utf-8') as logf:
        logf.write(f"{datetime.now(timezone.utc).isoformat()} | {user_tag} | {member.id} | {server_name} | suspicious={suspicious}\n")

# Error handling and auto-restart
while True:
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        error_msg = f"<b>Bot crashed with error:</b> {e}\nRestarting in 10 seconds..."
        print(error_msg)
        send_telegram_message(error_msg)
        time.sleep(10)