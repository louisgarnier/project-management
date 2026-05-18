"""
Migrate existing unedited call_topics prompts to the new default.

Run once after deploying the new prompt:
    cd backend && python -m scripts.migrate_call_topics_prompt

Rows whose stored prompt matches OLD_DEFAULT_PROMPT_STRING exactly are
considered "unedited" and get updated. Any other prompt is considered
user-customized and is left untouched.
"""

from backend.database.supabase_client import get_client
from backend.prompts.call_topics import (
    CALL_TOPICS_V2_PROMPT_BODY as CALL_TOPICS_DEFAULT_PROMPT,
    OLD_DEFAULT_PROMPT_STRING,
)
from backend.utils.logger import get_logger

logger = get_logger("migrate_call_topics_prompt")


def migrate_prompts(db) -> dict:
    """For each call_topics artifact type row:
    - If prompt == OLD_DEFAULT_PROMPT_STRING → update to CALL_TOPICS_DEFAULT_PROMPT
    - Else → leave untouched (user customized)
    Returns {"migrated": N, "preserved": M}.
    """
    rows = (
        db.table("artifact_types")
        .select("id, prompt, project_id")
        .eq("category", "call_topics")
        .execute()
        .data
    )

    migrated = 0
    preserved = 0
    for row in rows:
        if row["prompt"] == OLD_DEFAULT_PROMPT_STRING:
            db.table("artifact_types").update(
                {"prompt": CALL_TOPICS_DEFAULT_PROMPT}
            ).eq("id", row["id"]).execute()
            migrated += 1
            logger.info(
                f"🔄 [Migrate] Updated project {row['project_id']} call_topics prompt"
            )
        else:
            preserved += 1

    logger.info(
        f"✅ [Migrate] Migrated {migrated} call_topics prompts; "
        f"preserved {preserved} customized rows."
    )
    return {"migrated": migrated, "preserved": preserved}


if __name__ == "__main__":
    db = get_client()
    result = migrate_prompts(db)
    print(f"Done. Migrated: {result['migrated']}, Preserved: {result['preserved']}")
