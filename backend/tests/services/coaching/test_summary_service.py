import httpx
import pytest

from app.services.coaching.prompt_builder import PromptBuilder
from app.services.coaching.summary_service import SummaryService


class FakeLLMClient:
    async def complete(
        self,
        *,
        prompt: str,
        response_format: dict[str, object] | None = None,
    ) -> dict[str, str]:
        assert "Return valid JSON" in prompt
        assert response_format is not None
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


def test_prompt_builder_after_call_summary_includes_persona_transcript_and_flags() -> None:
    prompt_builder = PromptBuilder(
        persona={
            "name": "manager",
            "system_prompt": "You coach a banking team manager in real time.",
            "after_call_summary_prompt": "Write an after-call coaching summary for the manager.",
        }
    )

    prompt = prompt_builder.build_after_call_summary(
        transcript=[
            {"role": "colleague", "text": "I will take ownership of this issue."},
            {"role": "customer", "text": "I still need clarity on the payment."},
        ],
        flags=[{"code": "follow_up", "message": "Next steps were not clearly confirmed."}],
    )

    assert "Write an after-call coaching summary for the manager." in prompt
    assert "colleague: I will take ownership of this issue." in prompt
    assert "customer: I still need clarity on the payment." in prompt
    assert "follow_up" in prompt
    assert "Next steps were not clearly confirmed." in prompt


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
async def test_summary_service_requests_structured_output() -> None:
    class StructuredOutputLLMClient:
        async def complete(
            self,
            *,
            prompt: str,
            response_format: dict[str, object] | None = None,
        ) -> dict[str, str]:
            assert "Return valid JSON" in prompt
            assert response_format is not None
            assert response_format["type"] == "json_schema"
            json_schema = response_format["json_schema"]
            assert isinstance(json_schema, dict)
            assert json_schema["name"] == "after_call_summary"
            assert json_schema["strict"] is True
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

    service = SummaryService()
    prompt_builder = PromptBuilder(persona={"name": "colleague_contact"})

    summary = await service.build(
        transcript=[{"role": "colleague", "text": "Thanks for calling."}],
        flags=[],
        prompt_builder=prompt_builder,
        llm_client=StructuredOutputLLMClient(),
    )

    assert summary is not None
    assert summary.recap.startswith("The caller queried a payment")


@pytest.mark.asyncio
async def test_summary_service_returns_none_for_malformed_llm_output() -> None:
    class BadLLMClient:
        async def complete(
            self,
            *,
            prompt: str,
            response_format: dict[str, object] | None = None,
        ) -> dict[str, str]:
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


@pytest.mark.asyncio
async def test_summary_service_falls_back_when_structured_output_is_rejected() -> None:
    class FallbackLLMClient:
        def __init__(self) -> None:
            self.response_formats: list[dict[str, object] | None] = []

        async def complete(
            self,
            *,
            prompt: str,
            response_format: dict[str, object] | None = None,
        ) -> dict[str, str]:
            self.response_formats.append(response_format)
            if response_format is not None:
                request = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
                response = httpx.Response(400, request=request)
                raise httpx.HTTPStatusError("unsupported response_format", request=request, response=response)

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

    service = SummaryService()
    prompt_builder = PromptBuilder(persona={"name": "colleague_contact"})
    llm_client = FallbackLLMClient()

    summary = await service.build(
        transcript=[{"role": "colleague", "text": "Hello"}],
        flags=[],
        prompt_builder=prompt_builder,
        llm_client=llm_client,
    )

    assert summary is not None
    assert llm_client.response_formats[0] is not None
    assert llm_client.response_formats[1] is None


@pytest.mark.asyncio
async def test_summary_service_returns_none_when_llm_raises() -> None:
    class FailingLLMClient:
        async def complete(
            self,
            *,
            prompt: str,
            response_format: dict[str, object] | None = None,
        ) -> dict[str, str]:
            raise RuntimeError("llm unavailable")

    service = SummaryService()
    prompt_builder = PromptBuilder(persona={"name": "colleague_contact"})

    summary = await service.build(
        transcript=[{"role": "colleague", "text": "Hello"}],
        flags=[],
        prompt_builder=prompt_builder,
        llm_client=FailingLLMClient(),
    )

    assert summary is None


def test_summary_service_legacy_build_call_returns_none() -> None:
    service = SummaryService()

    summary = service.build(
        [{"role": "colleague", "text": "Hello"}]
    )

    assert summary is None


def test_summary_service_partial_new_api_call_raises() -> None:
    service = SummaryService()

    with pytest.raises(TypeError, match="requires transcript, flags, prompt_builder, and llm_client"):
        service.build(
            transcript=[{"role": "colleague", "text": "Hello"}],
            flags=[],
        )
