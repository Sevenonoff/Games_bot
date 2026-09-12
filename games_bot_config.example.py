# screen -S games_bot -d -m python3 /home/bot-user/games_bot/games_bot.py

API_TOKEN = 'your_telegram_bot_token_here' #@games_telegram_robot

# Database configuration (PostgreSQL)
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'seafight_user',
    'password': 'your_password_here',
    'database': 'seafight_bot'
}

BOT_SETTINGS = {
    'API_TOKEN': '',
    'ADMINS_API_TOKEN': '',
    'users_table': 'users',
    'regs_table': None,
    'conversation_table': None,
    'calendary_table': None,
    'services_table': None,
    'admins_chat_ids': [],
    'mode': ''
}

