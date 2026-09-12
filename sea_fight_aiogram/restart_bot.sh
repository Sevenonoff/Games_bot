#!/bin/bash
# Скрипт полного перезапуска Sea Fight Bot

echo "🔄 Остановка бота..."
pkill -9 -f 'python3.*main.py'
pkill -9 screen
sleep 2

echo "✅ Запуск бота..."
cd /home/clawuser/projects/Games_bot/sea_fight_aiogram
screen -dmS seafight /usr/bin/python3 main.py

sleep 3
if pgrep -f 'python3.*main.py' > /dev/null; then
    echo "✅ Бот успешно запущен!"
    echo "   PID: $(pgrep -f 'python3.*main.py')"
else
    echo "❌ Ошибка запуска бота"
    exit 1
fi
