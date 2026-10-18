import logging

from max_bot import config
from max_bot.main import SecretFilter


def test_webhook_secret_masked_in_log(monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_SECRET", "s3cret-abc")
    record = logging.LogRecord("maxapi", logging.INFO, __file__, 1,
                               "Webhook сервер запущен на %s", ("http://0.0.0.0:8445/hooks/games/s3cret-abc",), None)
    assert SecretFilter().filter(record)
    assert record.getMessage() == "Webhook сервер запущен на http://0.0.0.0:8445/hooks/games/***"
