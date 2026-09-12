#!/bin/bash
# Скрипт установки systemd сервиса для автозапуска бота

SERVICE_FILE="/etc/systemd/system/seafight-bot.service"

# Копируем файл сервиса
sudo cp /home/clawuser/projects/Games_bot/sea_fight_aiogram/seafight-bot.service $SERVICE_FILE

# Перезагружаем systemd
sudo systemctl daemon-reload

# Включаем автозапуск
sudo systemctl enable seafight-bot.service

echo "✅ Сервис установлен и включён в автозапуск"
echo "   Команды управления:"
echo "   - Запуск: sudo systemctl start seafight-bot"
echo "   - Остановка: sudo systemctl stop seafight-bot"
echo "   - Перезапуск: sudo systemctl restart seafight-bot"
echo "   - Статус: sudo systemctl status seafight-bot"
echo "   - Логи: sudo journalctl -u seafight-bot -f"
