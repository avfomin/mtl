# -*- coding: utf-8 -*-
"""Тонкий асинхронный клиент к Perplexity Chat Completions API."""
import logging

import httpx

import config

logger = logging.getLogger(__name__)


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

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(config.PERPLEXITY_API_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            logger.error("Perplexity API error %s: %s", resp.status_code, resp.text)
            raise LLMError(f"Perplexity API вернул {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Неожиданный формат ответа Perplexity: {data}") from exc
