import asyncio
import json
import os

import anthropic
from backend.utils.logger import get_logger
from openai import AsyncOpenAI
from openai import RateLimitError as OpenAIRateLimitError

logger = get_logger("llm_service")

_MAX_RETRIES = 3  # 3 retries = 4 total attempts


async def call_llm_raw(system: str, user_message: str, llm: str, max_tokens: int = 4096) -> str:
    """
    Call any supported LLM with an explicit system prompt and user message.
    Returns the raw text response (no transcript/task wrapping).
    llm must be one of: "groq", "deepseek", "claude", "openai".
    """
    if llm == "claude":
        client = anthropic.AsyncAnthropic()
        for attempt in range(_MAX_RETRIES + 1):
            try:
                logger.info(f"🤖 [Claude] Calling LLM (attempt {attempt + 1})")
                message = await client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user_message}],
                )
                content = message.content[0].text
                logger.info(
                    f"✅ [Claude] Done — "
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
    elif llm in ("groq", "deepseek", "openai"):
        configs = {
            "groq":     dict(api_key=os.environ.get("GROQ_API_KEY", ""),     base_url="https://api.groq.com/openai/v1", model="llama-3.3-70b-versatile", provider="Groq"),
            "deepseek": dict(api_key=os.environ.get("DEEPSEEK_API_KEY", ""), base_url="https://api.deepseek.com",        model="deepseek-chat",             provider="DeepSeek"),
            "openai":   dict(api_key=os.environ.get("OPENAI_API_KEY", ""),   base_url=None,                              model="gpt-4o-mini",               provider="OpenAI"),
        }
        cfg = configs[llm]
        kwargs: dict = {"api_key": cfg["api_key"]}
        if cfg["base_url"]:
            kwargs["base_url"] = cfg["base_url"]
        client_oa = AsyncOpenAI(**kwargs)
        for attempt in range(_MAX_RETRIES + 1):
            try:
                logger.info(f"🤖 [{cfg['provider']}] Calling LLM (attempt {attempt + 1})")
                response = await client_oa.chat.completions.create(
                    model=cfg["model"],
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user_message},
                    ],
                )
                content = response.choices[0].message.content or ""
                logger.info(
                    f"✅ [{cfg['provider']}] Done — "
                    f"input={response.usage.prompt_tokens} output={response.usage.completion_tokens}"
                )
                return content
            except OpenAIRateLimitError:
                if attempt == _MAX_RETRIES:
                    logger.error(f"❌ [{cfg['provider']}] Rate limit exhausted after 3 retries")
                    raise
                wait = 2 ** attempt
                logger.warning(f"⚠️ [{cfg['provider']}] Rate limited — retrying in {wait}s")
                await asyncio.sleep(wait)
        raise RuntimeError("unreachable")  # pragma: no cover
    else:
        raise ValueError(f"Unknown LLM provider: {llm!r}. Must be 'groq', 'deepseek', 'claude', or 'openai'.")


async def generate_artifact(
    prompt_used: str,
    transcript: str,
    llm: str,
    topics: list[dict] | None = None,
) -> str:
    """
    Generate an artifact using the specified LLM provider.
    llm must be one of: "groq", "deepseek", "claude", "openai".
    If topics are provided, they are injected between transcript and task prompt.
    Retries up to 3 times with exponential backoff on rate-limit errors.
    """
    topics_block = ""
    if topics:
        topics_block = (
            f"\n\nTopics from this call:\n{json.dumps(topics, indent=2)}"
        )

    user_message = (
        f"Transcript:\n{transcript}"
        f"{topics_block}"
        f"\n\nTask:\n{prompt_used}"
    )

    if llm == "claude":
        return await _generate_claude(user_message)
    elif llm == "groq":
        return await _generate_openai_compat(
            user_message,
            api_key=os.environ.get("GROQ_API_KEY", ""),
            base_url="https://api.groq.com/openai/v1",
            model="llama-3.3-70b-versatile",
            provider="Groq",
        )
    elif llm == "deepseek":
        return await _generate_openai_compat(
            user_message,
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            provider="DeepSeek",
        )
    elif llm == "openai":
        return await _generate_openai_compat(
            user_message,
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            base_url=None,
            model="gpt-4o-mini",
            provider="OpenAI",
        )
    else:
        raise ValueError(f"Unknown LLM provider: {llm!r}. Must be 'groq', 'deepseek', 'claude', or 'openai'.")


async def _generate_claude(user_message: str) -> str:
    client = anthropic.AsyncAnthropic()

    for attempt in range(_MAX_RETRIES + 1):
        try:
            logger.info(f"🤖 [Claude] Generating artifact (attempt {attempt + 1})")
            message = await client.messages.create(
                model="claude-haiku-4-5-20251001",
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
    user_message: str,
    api_key: str,
    base_url: str | None,
    model: str,
    provider: str,
) -> str:
    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = AsyncOpenAI(**kwargs)

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
