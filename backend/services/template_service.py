"""Template rendering service. Dispatches artifact_type rows to the
correct renderer in backend.templates.registry based on template_id.
"""

from backend.database.supabase_client import get_client
from backend.services.topics_service import list_call_topics, list_project_topics
from backend.templates.registry import TEMPLATE_REGISTRY


async def render_template(artifact_type: dict, call_id: str) -> str:
    """Render a template or hybrid-skeleton artifact.

    For kind='template' → returns full template output.
    For kind='hybrid'   → returns just the skeleton (intro/closing come from LLM separately).
    """
    template_id = artifact_type.get("template_id")
    if not template_id:
        raise ValueError(
            f"Artifact type {artifact_type.get('id')} has kind={artifact_type.get('kind')} but no template_id"
        )
    renderer = TEMPLATE_REGISTRY.get(template_id)
    if not renderer:
        raise ValueError(f"Unknown template_id: {template_id}")

    scope = artifact_type.get("context_scope", "this_call_topics")
    if scope == "project":
        db = get_client()
        call_row = (
            db.table("calls").select("project_id").eq("id", call_id).execute().data
        )
        if not call_row:
            raise ValueError(f"Call {call_id} not found")
        topics = await list_project_topics(call_row[0]["project_id"])
    else:
        topics = await list_call_topics(call_id)
    return renderer(topics, scope=scope)


def render_template_for_preview(artifact_type: dict, call_id: str) -> str:
    """Synchronous preview variant — wraps the async render for the sync preview endpoint."""
    import asyncio

    return asyncio.run(render_template(artifact_type, call_id))
