#!/bin/bash
# Скрипт запуска Sea Fight Bot

cd /home/clawuser/projects/Games_bot/sea_fight_aiogram

# Проверяем, запущен ли уже бот
if pgrep -f 'python3.*main.py' > /dev/null; then
    echo "⚠️  Бот уже запущен!"
    exit 1
fi

# Запускаем бота напрямую
exec /usr/bin/python3 main.py >> /tmp/bot_clean.log 2>&1
