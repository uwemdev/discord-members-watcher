from discord.ext import commands
import requests

# 1. Replace with your Discord user token (NOT your bot token)
DISCORD_TOKEN = 'YOUR_DISCORD_USER_TOKEN'

# 2. Replace with your Telegram bot token (from BotFather)
TELEGRAM_BOT_TOKEN = '8783172226:AAFjYu6Q3hYgJ3hYOCyFFz6OCiDhV-ylrBc'

# 3. Replace with your Telegram channel username (e.g., @yourchannel) or channel ID
TELEGRAM_CHANNEL = '@thediscordtelegram'

bot = commands.Bot(command_prefix='!', self_bot=True)

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