"""Resolve the effective LLM + model for any prompt — ALWAYS project-level.

Post-EPIC-16: per-prompt and per-artifact_type LLM overrides are intentionally
ignored. The single source of truth is projects.default_llm + default_model,
with system_settings as fallback. The legacy 4-arg signature is preserved for
backwards compatibility with existing call sites; the first two args are
accepted but DISCARDED.
"""

from backend.database.supabase_client import get_client


def resolve_effective_llm_model(
    type_llm: str | None,
    type_model: str | None,
    project_llm: str | None,
    project_model: str | None,
    db=None,
) -> tuple[str, str | None]:
    """Return (effective_llm, effective_model).

    type_llm and type_model are accepted for signature compatibility but ignored.
    Resolution: project_llm/model → system_settings → 'openrouter' fallback.
    """
    if project_llm:
        return (project_llm, project_model)
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
    return ("openrouter", "deepseek/deepseek-v3.2")
