import asyncio

import anthropic

from backend.utils.logger import get_logger

logger = get_logger("claude_service")

_MAX_RETRIES = 3


async def generate_artifact(prompt_used: str, transcript: str) -> str:
    """
    Call claude-sonnet-4-6 to generate an artifact from a transcript.
    Retries up to 3 times with exponential backoff on 429 rate-limit errors.
    Raises the last exception if all retries are exhausted.
    """
    client = anthropic.AsyncAnthropic()
    user_message = f"Transcript:\n{transcript}\n\nTask:\n{prompt_used}"

    for attempt in range(_MAX_RETRIES):
        try:
            logger.info(f"🤖 [Claude] Generating artifact (attempt {attempt + 1})")
            message = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                messages=[{"role": "user", "content": user_message}],
            )
            content = message.content[0].text
            logger.info(
                f"✅ [Claude] Artifact generated — "
                f"input_tokens={message.usage.input_tokens} "
                f"output_tokens={message.usage.output_tokens}"
            )
            return content
        except anthropic.RateLimitError:
            if attempt == _MAX_RETRIES - 1:
                logger.error("❌ [Claude] Rate limit exceeded after 3 retries")
                raise
            wait = 2 ** attempt
            logger.warning(f"⚠️ [Claude] Rate limited — retrying in {wait}s")
            await asyncio.sleep(wait)
