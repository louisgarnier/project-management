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
