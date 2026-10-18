# Бот игр для Max. Сборка из корня репозитория (нужны games_core и max_bot):
#   docker compose -f max_bot/deploy/compose.yaml up -d --build
FROM python:3.12-slim
LABEL app=games-bot
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY max_bot/requirements.txt max_bot/requirements.txt
RUN pip install -r max_bot/requirements.txt
COPY games_core games_core
COPY max_bot max_bot
CMD ["python", "-m", "max_bot.main"]
