from discord.ext import commands
import requests
import json
import os

# 1. Replace with your Discord user token (NOT your bot token)
DISCORD_TOKEN = 'YOUR_DISCORD_USER_TOKEN'

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
    requests.post(url, data=data)

# Send a test message on script start
send_telegram_message("Test message from my bot!")

# On startup, report new members since last run
@bot.event
async def on_ready():
    last_members = load_last_members()
    new_last_members = {}
    for guild in bot.guilds:
        await guild.chunk()  # Ensure all members are loaded
        current_ids = set(str(m.id) for m in guild.members)
        new_last_members[str(guild.id)] = list(current_ids)
        prev_ids = set(last_members.get(str(guild.id), []))
        new_ids = current_ids - prev_ids
        if new_ids:
            new_users = [m for m in guild.members if str(m.id) in new_ids]
            msg = f"<b>New members since last run in {guild.name}:</b>\n"
            msg += '\n'.join(f"<code>{u.name}#{u.discriminator}</code>" for u in new_users)
            send_telegram_message(msg)
    save_last_members(new_last_members)

# Optional: Map server IDs to invite links
SERVER_INVITES = {
    # Example: '123456789012345678': 'https://discord.gg/yourinvite',
    # Add your server IDs and invite links here
}

@bot.event
async def on_member_join(member):
    server_name = member.guild.name
    user_tag = f"{member.name}#{member.discriminator}"
    invite_link = SERVER_INVITES.get(str(member.guild.id), None)
    msg = f"👤 <b>New member joined</b>\n" \
          f"User: <code>{user_tag}</code>\n" \
          f"Server: <b>{server_name}</b>"
    if invite_link:
        msg += f"\nInvite: {invite_link}"
    print(msg)
    send_telegram_message(msg)

bot.run(DISCORD_TOKEN)