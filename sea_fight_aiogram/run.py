#!/usr/bin/env python3
"""
Скрипт запуска бота Sea Fight
"""

import asyncio
import sys
from pathlib import Path

# Добавляем текущую директорию в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот остановлен")
    except Exception as e:
        print(f"Ошибка при запуске бота: {e}")
        sys.exit(1)
