from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from app.services.coaching.llm_client import OpenAICompatibleClient
from app.services.coaching.prompt_builder import PromptBuilder


class CallSummary(BaseModel):
    recap: str
    strengths: list[str]
    weaknesses: list[str]
    flagged_moments: list[str]


class SummaryService:
    async def build(
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
        completion = await llm_client.complete(prompt=prompt)
        try:
            return CallSummary.model_validate_json(completion["message"])
        except (KeyError, TypeError, ValidationError):
            return None
