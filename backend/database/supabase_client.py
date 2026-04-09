import os
from functools import lru_cache

from backend.utils.logger import db_logger
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()


@lru_cache(maxsize=1)
def get_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")
    db_logger.info("🗄️ [DB] Supabase client initialised")
    return create_client(url, key)
