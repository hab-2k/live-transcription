import pytest

from app.services.coaching.prompt_builder import PromptBuilder
from app.services.coaching.summary_service import SummaryService


class FakeLLMClient:
    async def complete(self, *, prompt: str) -> dict[str, str]:
        assert "Return valid JSON" in prompt
        return {
            "message": """
            {
              "recap": "The caller queried a payment and received a partial explanation.",
              "strengths": ["Polite and calm tone throughout the call."],
              "weaknesses": ["Could confirm the next step more clearly."],
              "flagged_moments": ["The caller still sounded unsure about the payment outcome."]
            }
            """
        }


@pytest.mark.asyncio
async def test_summary_service_builds_structured_llm_summary() -> None:
    service = SummaryService()
    prompt_builder = PromptBuilder(
        persona={
            "name": "colleague_contact",
            "system_prompt": "You coach a retail banking colleague in real time.",
            "after_call_summary_prompt": "Write an after-call coaching summary.",
        }
    )

    summary = await service.build(
        transcript=[
            {"role": "colleague", "text": "Thanks for calling, I can help with that."},
            {"role": "customer", "text": "I still do not understand the payment."},
        ],
        flags=[{"code": "ownership", "message": "Ownership was not explicit."}],
        prompt_builder=prompt_builder,
        llm_client=FakeLLMClient(),
    )

    assert summary is not None
    assert summary.recap.startswith("The caller queried a payment")
    assert summary.weaknesses == ["Could confirm the next step more clearly."]


@pytest.mark.asyncio
async def test_summary_service_returns_none_for_malformed_llm_output() -> None:
    class BadLLMClient:
        async def complete(self, *, prompt: str) -> dict[str, str]:
            return {"message": "not-json"}

    service = SummaryService()
    prompt_builder = PromptBuilder(persona={"name": "colleague_contact"})

    summary = await service.build(
        transcript=[{"role": "colleague", "text": "Hello"}],
        flags=[],
        prompt_builder=prompt_builder,
        llm_client=BadLLMClient(),
    )

    assert summary is None
