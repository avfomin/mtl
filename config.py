# -*- coding: utf-8 -*-
import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "sonar")
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "credentials.json")
# Альтернатива для облачного хостинга без файловой системы для секретов:
# вставить содержимое JSON-ключа сервис-аккаунта целиком в эту переменную окружения.
GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT", "")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Results")

ASSESSMENT_DEADLINE = os.getenv("ASSESSMENT_DEADLINE", "не указан")

# Максимально параллельных запросов к LLM при проверке Части 1 (15 обоснований)
LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "5"))
