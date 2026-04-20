"""Topic lineage helpers — walk merged_into_topic_id to collect full ancestor history.

Every merge prompt, verification prompt, and evidence-API consumer uses this module
as the single source of truth for per-topic history across M:N merges.
"""


def get_topic_lineage(topic_id: str, db) -> list[dict]:
    """BFS starting at topic_id, walking topics.merged_into_topic_id backwards.

    Returns [{id, name, archived, merged_into_topic_id}, ...] with self first.
    Cycle guard: visited set prevents infinite recursion.
    """
    visited: set[str] = set()
    result: list[dict] = []
    queue: list[str] = [topic_id]

    while queue:
        current_id = queue.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)

        # Fetch the topic row itself
        rows = (
            db.table("topics")
            .select("id, name, archived, merged_into_topic_id")
            .eq("id", current_id)
            .execute()
            .data
        )
        if not rows:
            continue
        result.append(rows[0])

        # Find source topics whose merged_into_topic_id = current
        sources = (
            db.table("topics")
            .select("id, name, archived, merged_into_topic_id")
            .eq("merged_into_topic_id", current_id)
            .execute()
            .data
        )
        for s in sources:
            if s["id"] not in visited:
                queue.append(s["id"])

    return result
