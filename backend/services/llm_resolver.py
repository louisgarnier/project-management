"""Resolve the effective LLM + model for a given artifact type on a given project,
using the three-tier cascade:
    1. artifact_type.llm / .model (if set)
    2. project.default_llm / .default_model (if set)
    3. system_settings.default_llm / .default_model (always set)
"""

from backend.database.supabase_client import get_client


def resolve_effective_llm_model(
    type_llm: str | None,
    type_model: str | None,
    project_llm: str | None,
    project_model: str | None,
    db=None,
) -> tuple[str, str | None]:
    """Return (effective_llm, effective_model) walking the cascade."""
    if type_llm:
        return (type_llm, type_model)
    if project_llm:
        return (project_llm, project_model)
    # Fall back to system_settings
    if db is None:
        db = get_client()
    try:
        rows = (
            db.table("system_settings")
            .select("default_llm, default_model")
            .eq("id", 1)
            .execute()
            .data
        )
        if rows:
            return (
                rows[0].get("default_llm") or "openrouter",
                rows[0].get("default_model"),
            )
    except Exception:
        pass
    # Ultimate fallback
    return ("openrouter", "deepseek/deepseek-v3.2")
