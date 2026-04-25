from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from app.services.coaching.llm_client import OpenAICompatibleClient
from app.services.coaching.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


class CallSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recap: str
    strengths: list[str]
    weaknesses: list[str]
    flagged_moments: list[str]


class SummaryService:
    def build(
        self,
        transcript: list[dict[str, Any]] | None = None,
        *,
        flags: list[dict[str, Any]] | None = None,
        prompt_builder: PromptBuilder | None = None,
        llm_client: OpenAICompatibleClient | None = None,
    ) -> Awaitable[CallSummary | None] | None:
        if transcript is not None and flags is None and prompt_builder is None and llm_client is None:
            return None

        if transcript is None or flags is None or prompt_builder is None or llm_client is None:
            raise TypeError(
                "SummaryService.build() requires transcript, flags, prompt_builder, and llm_client"
            )

        return self._build_async(
            transcript=transcript,
            flags=flags,
            prompt_builder=prompt_builder,
            llm_client=llm_client,
        )

    async def _build_async(
        self,
        *,
        transcript: list[dict[str, Any]],
        flags: list[dict[str, Any]],
        prompt_builder: PromptBuilder,
        llm_client: OpenAICompatibleClient,
    ) -> CallSummary | None:
        prompt = prompt_builder.build_after_call_summary(
            transcript=transcript,
            flags=flags,
        )
        try:
            completion = await self._request_completion(
                prompt=prompt,
                llm_client=llm_client,
            )
            return CallSummary.model_validate_json(completion["message"])
        except Exception:
            logger.exception("after-call summary generation failed")
            return None

    @staticmethod
    def _response_format() -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "after_call_summary",
                "strict": True,
                "schema": CallSummary.model_json_schema(),
            },
        }

    async def _request_completion(
        self,
        *,
        prompt: str,
        llm_client: OpenAICompatibleClient,
    ) -> dict[str, Any]:
        try:
            return await llm_client.complete(
                prompt=prompt,
                response_format=self._response_format(),
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {400, 404, 422}:
                raise

            logger.warning(
                "after-call summary structured output unsupported: status=%s; retrying without response_format",
                exc.response.status_code,
            )
            return await llm_client.complete(prompt=prompt)
