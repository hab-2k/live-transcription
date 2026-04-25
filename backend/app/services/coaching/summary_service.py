from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from pydantic import BaseModel

from app.services.coaching.llm_client import OpenAICompatibleClient
from app.services.coaching.prompt_builder import PromptBuilder


class CallSummary(BaseModel):
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
            completion = await llm_client.complete(prompt=prompt)
            return CallSummary.model_validate_json(completion["message"])
        except Exception:
            return None
