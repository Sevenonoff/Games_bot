#!/bin/bash
# Скрипт запуска Sea Fight Bot

cd /home/clawuser/projects/Games_bot/sea_fight_aiogram

# Проверяем, запущен ли уже бот
if pgrep -f 'python3.*main.py' > /dev/null; then
    echo "⚠️  Бот уже запущен (PID: $(pgrep -f 'python3.*main.py'))"
    echo "   Для перезапуска используйте: ./restart_bot.sh"
    exit 1
fi

# Запускаем бота в новой screen сессии
screen -dmS seafight /usr/bin/python3 main.py

sleep 3

if pgrep -f 'python3.*main.py' > /dev/null; then
    echo "✅ Бот запущен в фоновом режиме"
    echo "   PID: $(pgrep -f 'python3.*main.py')"
    echo "   Просмотр логов: screen -r seafight"
    echo "   Отключение от логов: Ctrl+A, затем D"
    echo "   Завершение бота: ./stop_bot.sh"
else
    echo "❌ Ошибка запуска бота"
    exit 1
fi
