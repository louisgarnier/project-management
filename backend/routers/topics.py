from backend.database.supabase_client import get_client
from backend.services.topics_service import extract_topics
from backend.utils.logger import get_logger
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["topics"])
logger = get_logger("topics_router")


@router.post("/calls/{call_id}/topics/extract")
async def extract(call_id: str):
    logger.info(f"📥 [Topics] Extract requested: call={call_id}")
    try:
        result = await extract_topics(call_id)
        total = sum(len(v) for v in result.values() if isinstance(v, list))
        logger.info(f"✅ [Topics] Extracted {total} topics")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ [Topics] Extraction failed: {e}")
        raise HTTPException(status_code=500, detail="Topic extraction failed")
