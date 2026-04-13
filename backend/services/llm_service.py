import asyncio
import os

import anthropic
from backend.utils.logger import get_logger
from openai import AsyncOpenAI
from openai import RateLimitError as OpenAIRateLimitError

logger = get_logger("llm_service")

_MAX_RETRIES = 3  # 3 retries = 4 total attempts


async def generate_artifact(prompt_used: str, transcript: str, llm: str) -> str:
    """
    Generate an artifact using the specified LLM provider.
    llm must be one of: "groq", "claude", "openai".
    Retries up to 3 times with exponential backoff on rate-limit errors.
    """
    if llm == "claude":
        return await _generate_claude(prompt_used, transcript)
    elif llm == "groq":
        return await _generate_openai_compat(
            prompt_used, transcript,
            api_key=os.environ.get("GROQ_API_KEY", ""),
            base_url="https://api.x.ai/v1",
            model="grok-3",
            provider="Grok",
        )
    elif llm == "openai":
        return await _generate_openai_compat(
            prompt_used, transcript,
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            base_url=None,
            model="gpt-4o",
            provider="OpenAI",
        )
    else:
        raise ValueError(f"Unknown LLM provider: {llm!r}. Must be 'groq', 'claude', or 'openai'.")


async def _generate_claude(prompt_used: str, transcript: str) -> str:
    client = anthropic.AsyncAnthropic()
    user_message = f"Transcript:\n{transcript}\n\nTask:\n{prompt_used}"

    for attempt in range(_MAX_RETRIES + 1):
        try:
            logger.info(f"🤖 [Claude] Generating artifact (attempt {attempt + 1})")
            message = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                messages=[{"role": "user", "content": user_message}],
            )
            content = message.content[0].text
            logger.info(
                f"✅ [Claude] Generated — "
                f"input={message.usage.input_tokens} output={message.usage.output_tokens}"
            )
            return content
        except anthropic.RateLimitError:
            if attempt == _MAX_RETRIES:
                logger.error("❌ [Claude] Rate limit exhausted after 3 retries")
                raise
            wait = 2 ** attempt
            logger.warning(f"⚠️ [Claude] Rate limited — retrying in {wait}s")
            await asyncio.sleep(wait)

    raise RuntimeError("unreachable")  # pragma: no cover


async def _generate_openai_compat(
    prompt_used: str,
    transcript: str,
    api_key: str,
    base_url: str | None,
    model: str,
    provider: str,
) -> str:
    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = AsyncOpenAI(**kwargs)
    user_message = f"Transcript:\n{transcript}\n\nTask:\n{prompt_used}"

    for attempt in range(_MAX_RETRIES + 1):
        try:
            logger.info(f"🤖 [{provider}] Generating artifact (attempt {attempt + 1})")
            response = await client.chat.completions.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": user_message}],
            )
            content = response.choices[0].message.content or ""
            logger.info(
                f"✅ [{provider}] Generated — "
                f"input={response.usage.prompt_tokens} output={response.usage.completion_tokens}"
            )
            return content
        except OpenAIRateLimitError:
            if attempt == _MAX_RETRIES:
                logger.error(f"❌ [{provider}] Rate limit exhausted after 3 retries")
                raise
            wait = 2 ** attempt
            logger.warning(f"⚠️ [{provider}] Rate limited — retrying in {wait}s")
            await asyncio.sleep(wait)

    raise RuntimeError("unreachable")  # pragma: no cover
