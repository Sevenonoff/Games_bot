#!/bin/bash
# Скрипт проверки статуса Sea Fight Bot

if screen -list | grep -q "seafight"; then
    echo "✅ Бот запущен"
    echo "   PID: $(pgrep -f 'python3.*main.py')"
    echo "   Память: $(ps -o pid,rss,vsz,cmd -p $(pgrep -f 'python3.*main.py') | tail -1 | awk '{print "RSS: " $2/1024 " MB, VSZ: " $3/1024 " MB"}')"
else
    echo "❌ Бот не запущен"
    exit 1
fi
