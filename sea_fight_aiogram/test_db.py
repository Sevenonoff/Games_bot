#!/usr/bin/env python3
"""
Тест подключения к PostgreSQL
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
import asyncpg

load_dotenv()

async def test_db():
    try:
        conn = await asyncpg.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", 5432)),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )

        print("✅ Успешное подключение к PostgreSQL!")

        # Проверяем таблицы
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
        """)

        print(f"📊 Найдено таблиц: {len(tables)}")
        for table in tables:
            print(f"   - {table['table_name']}")

        # Проверяем количество пользователей
        user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        print(f"👥 Пользователей в базе: {user_count}")

        # Проверяем количество записей в лидерборде
        leaderboard_count = await conn.fetchval("SELECT COUNT(*) FROM leaderboard")
        print(f"🏆 Записей в лидерборде: {leaderboard_count}")

        await conn.close()
        print("\n✅ Тест базы данных пройден успешно!")

    except Exception as e:
        print(f"❌ Ошибка подключения к базе данных: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_db())
