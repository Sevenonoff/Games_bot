"""Проверка подписи initData Telegram Mini App."""
import json
from urllib.parse import urlencode

from sea_fight_aiogram import initdata

TOKEN = "123456:TEST-token"
NOW = 1_800_000_000


def make_init_data(user=None, auth_date=NOW, token=TOKEN, **extra) -> str:
    """initData, как его собирает Telegram: поля, подпись в hash."""
    fields = {"auth_date": str(auth_date), "query_id": "AAE",
              "user": json.dumps(user or {"id": 42, "first_name": "Тестер", "username": "tester"},
                                 ensure_ascii=False, separators=(",", ":")), **extra}
    return urlencode({**fields, "hash": initdata.sign(fields, token)})


def test_valid_signature_gives_user():
    user = initdata.verify(make_init_data(), TOKEN, NOW + 60)
    assert user == {"id": 42, "first_name": "Тестер", "username": "tester"}


def test_known_vector_from_telegram_algorithm():
    """Подпись — HMAC-SHA256 строки «ключ=значение» по алфавиту, ключ — HMAC("WebAppData", токен)."""
    fields = {"auth_date": "1", "user": '{"id":1}'}
    import hashlib
    import hmac
    key = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(key, b'auth_date=1\nuser={"id":1}', hashlib.sha256).hexdigest()
    assert initdata.sign(fields, TOKEN) == expected


def test_tampered_field_rejected():
    data = make_init_data().replace("tester", "admin")
    assert initdata.verify(data, TOKEN, NOW) is None


def test_other_bot_token_rejected():
    assert initdata.verify(make_init_data(token="999:other"), TOKEN, NOW) is None


def test_expired_and_future_rejected():
    assert initdata.verify(make_init_data(auth_date=NOW - 25 * 3600), TOKEN, NOW) is None
    assert initdata.verify(make_init_data(auth_date=NOW + 3600), TOKEN, NOW) is None


def test_garbage_rejected():
    for bad in ("", "hash=", "not a query", "user=%7B%7D&hash=abc", make_init_data(user={"id": "x"})):
        assert initdata.verify(bad, TOKEN, NOW) is None, bad
    assert initdata.verify(make_init_data(), "", NOW) is None
