"""Проверка initData Telegram Mini App (core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).

Mini App получает от Telegram строку initData (query string) с полем hash — подписью
HMAC-SHA256 остальных полей. Ключ подписи — HMAC-SHA256(ключ "WebAppData", токен бота).
Без aiogram: модуль проверяется тестами ядра.
"""
import hashlib
import hmac
import json
from typing import Optional
from urllib.parse import parse_qsl

MAX_AGE = 24 * 3600


def secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def sign(fields: dict, bot_token: str) -> str:
    """Подпись полей, как её считает Telegram (нужна и тестам, чтобы собрать верный initData)."""
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    return hmac.new(secret_key(bot_token), check.encode(), hashlib.sha256).hexdigest()


def verify(init_data: str, bot_token: str, now: float, max_age: float = MAX_AGE) -> Optional[dict]:
    """Пользователь из initData ({"id", "username", "first_name", …}) или None, если подпись не сошлась,
    данные устарели или испорчены."""
    if not init_data or not bot_token:
        return None
    try:
        fields = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    received = fields.pop("hash", None)
    if not received or not hmac.compare_digest(sign(fields, bot_token), received):
        return None
    try:
        auth_date = int(fields.get("auth_date", ""))
        user = json.loads(fields.get("user", ""))
    except ValueError:
        return None
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        return None
    if now - auth_date > max_age or auth_date - now > 300:
        return None
    return user
