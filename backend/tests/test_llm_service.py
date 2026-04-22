from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
@patch("backend.services.llm_service.anthropic.AsyncAnthropic")
async def test_generate_with_claude(mock_cls):
    mock_client = AsyncMock()
    mock_cls.return_value = mock_client
    msg = MagicMock()
    msg.content = [MagicMock(text="Claude output")]
    msg.usage.input_tokens = 100
    msg.usage.output_tokens = 50
    mock_client.messages.create = AsyncMock(return_value=msg)

    from backend.services.llm_service import generate_artifact

    result = await generate_artifact("prompt", "transcript", "claude")
    assert result == "Claude output"


@pytest.mark.asyncio
@patch("backend.services.llm_service.AsyncOpenAI")
async def test_generate_with_groq(mock_cls):
    mock_client = AsyncMock()
    mock_cls.return_value = mock_client
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "Groq output"
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    mock_client.chat.completions.create = AsyncMock(return_value=response)

    from backend.services.llm_service import generate_artifact

    result = await generate_artifact("prompt", "transcript", "groq")
    assert result == "Groq output"
    # Verify Groq base_url was used
    call_kwargs = mock_cls.call_args[1]
    assert "groq.com" in call_kwargs["base_url"]


@pytest.mark.asyncio
@patch("backend.services.llm_service.AsyncOpenAI")
async def test_generate_with_openai(mock_cls):
    mock_client = AsyncMock()
    mock_cls.return_value = mock_client
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "OpenAI output"
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    mock_client.chat.completions.create = AsyncMock(return_value=response)

    from backend.services.llm_service import generate_artifact

    result = await generate_artifact("prompt", "transcript", "openai")
    assert result == "OpenAI output"
    # Verify no base_url override for OpenAI
    call_kwargs = mock_cls.call_args[1]
    assert "base_url" not in call_kwargs


@pytest.mark.asyncio
async def test_generate_unknown_llm():
    from backend.services.llm_service import generate_artifact

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        await generate_artifact("prompt", "transcript", "unknown")


@pytest.mark.asyncio
async def test_openrouter_dispatches_with_base_url_and_model(monkeypatch):
    """generate_artifact(llm='openrouter', model='X') uses OpenRouter base_url + the given model."""
    captured = {}

    class FakeChatCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)

            class R:
                choices = [
                    type("C", (), {"message": type("M", (), {"content": "result"})()})()
                ]
                usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 5})()

            return R()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = type("Chat", (), {"completions": FakeChatCompletions()})()

    monkeypatch.setattr("backend.services.llm_service.AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    from backend.services.llm_service import generate_artifact

    result = await generate_artifact(
        prompt_used="hello",
        transcript="t",
        llm="openrouter",
        model="anthropic/claude-sonnet-4.6",
    )

    assert result == "result"
    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "anthropic/claude-sonnet-4.6"


@pytest.mark.asyncio
async def test_openrouter_without_model_raises():
    """generate_artifact(llm='openrouter') without model raises ValueError."""
    from backend.services.llm_service import generate_artifact

    with pytest.raises(ValueError, match="model"):
        await generate_artifact(
            prompt_used="hello",
            transcript="t",
            llm="openrouter",
            model=None,
        )


@pytest.mark.asyncio
async def test_call_llm_raw_openrouter_branch(monkeypatch):
    """call_llm_raw also supports openrouter."""
    captured = {}

    class FakeChatCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)

            class R:
                choices = [
                    type("C", (), {"message": type("M", (), {"content": "ok"})()})()
                ]
                usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()

            return R()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = type("Chat", (), {"completions": FakeChatCompletions()})()

    monkeypatch.setattr("backend.services.llm_service.AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "key2")

    from backend.services.llm_service import call_llm_raw

    result = await call_llm_raw("sys", "user", "openrouter", model="openai/gpt-4o")
    assert result == "ok"
    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["model"] == "openai/gpt-4o"
