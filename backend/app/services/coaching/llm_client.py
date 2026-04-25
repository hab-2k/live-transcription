from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, transport=transport, timeout=timeout)
        self._api_key = api_key
        self._model = model

    async def complete(
        self,
        *,
        prompt: str,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if response_format is not None:
            payload["response_format"] = response_format
        started_at = time.perf_counter()
        logger.info(
            "llm request started: base_url=%s model=%s prompt_chars=%d",
            self._base_url,
            self._model,
            len(prompt),
        )
        try:
            response = await self._client.post(
                "/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
        except Exception:
            logger.exception(
                "llm request failed: base_url=%s model=%s elapsed_ms=%.1f",
                self._base_url,
                self._model,
                (time.perf_counter() - started_at) * 1000,
            )
            raise

        response_payload = response.json()
        logger.info(
            "llm request completed: base_url=%s model=%s status=%s elapsed_ms=%.1f",
            self._base_url,
            self._model,
            response.status_code,
            (time.perf_counter() - started_at) * 1000,
        )
        return {"message": response_payload["choices"][0]["message"]["content"]}
