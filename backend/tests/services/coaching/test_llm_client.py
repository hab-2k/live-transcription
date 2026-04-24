import logging

import httpx
import pytest

from app.services.coaching.llm_client import OpenAICompatibleClient


@pytest.mark.asyncio
async def test_llm_client_posts_openai_compatible_chat_completion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        payload = request.read().decode("utf-8")
        assert "local-model" in payload
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Lead with reassurance."}}]},
        )

    client = OpenAICompatibleClient(
        base_url="http://localhost:11434/v1",
        model="local-model",
        transport=httpx.MockTransport(handler),
    )

    result = await client.complete(prompt="hello")

    assert result["message"] == "Lead with reassurance."


@pytest.mark.asyncio
async def test_llm_client_logs_request_and_response(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Lead with reassurance."}}]},
        )

    caplog.set_level(logging.INFO)
    client = OpenAICompatibleClient(
        base_url="http://localhost:11434/v1",
        model="local-model",
        transport=httpx.MockTransport(handler),
    )

    await client.complete(prompt="hello")

    assert "llm request started" in caplog.text
    assert "model=local-model" in caplog.text
    assert "llm request completed" in caplog.text
