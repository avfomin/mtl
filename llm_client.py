# -*- coding: utf-8 -*-
"""Тонкий асинхронный клиент к Perplexity Chat Completions API."""
import asyncio
import logging
import random

import httpx

import config

logger = logging.getLogger(__name__)

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 4


class LLMError(Exception):
    pass


async def ask_llm(prompt: str, temperature: float = 0.0, max_tokens: int = 500) -> str:
    if not config.PERPLEXITY_API_KEY:
        raise LLMError("PERPLEXITY_API_KEY не задан в .env")

    headers = {
        "Authorization": f"Bearer {config.PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.PERPLEXITY_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_error = None
    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(MAX_RETRIES + 1):
            resp = await client.post(config.PERPLEXITY_API_URL, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                try:
                    return data["choices"][0]["message"]["content"].strip()
                except (KeyError, IndexError) as exc:
                    raise LLMError(f"Неожиданный формат ответа Perplexity: {data}") from exc

            last_error = f"Perplexity API вернул {resp.status_code}: {resp.text[:300]}"
            if resp.status_code not in RETRYABLE_STATUSES or attempt == MAX_RETRIES:
                logger.error("Perplexity API error (attempt %d/%d): %s", attempt + 1, MAX_RETRIES + 1, last_error)
                raise LLMError(last_error)

            delay = (2 ** attempt) + random.uniform(0, 1)
            logger.warning(
                "Perplexity API %s, retry %d/%d in %.1fs",
                resp.status_code, attempt + 1, MAX_RETRIES, delay,
            )
            await asyncio.sleep(delay)

    raise LLMError(last_error or "Unknown Perplexity API error")
