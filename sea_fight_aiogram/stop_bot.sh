#!/bin/bash
# Скрипт остановки Sea Fight Bot

if screen -list | grep -q "seafight"; then
    screen -S seafight -X quit
    echo "✅ Бот остановлен"
else
    echo "⚠️  Бот не запущен"
fi
