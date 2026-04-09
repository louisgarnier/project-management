import time
import logging

from fastapi import Request

request_logger = logging.getLogger("calltracker.api.requests")


async def log_requests(request: Request, call_next):
    start = time.time()
    request_logger.info(f"📥 {request.method} {request.url.path}")

    response = await call_next(request)

    ms = (time.time() - start) * 1000
    request_logger.info(
        f"📤 {request.method} {request.url.path} → {response.status_code} ({ms:.0f}ms)"
    )
    return response
