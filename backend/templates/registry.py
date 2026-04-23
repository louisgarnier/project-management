"""Maps template_id → render function. The only place kind=template / hybrid
artifact generation looks up its renderer."""

from backend.templates import (
    agenda_skeleton,
    decisions_digest,
    next_steps,
    questions_list,
    risk_register,
)

TEMPLATE_REGISTRY = {
    "next_steps": next_steps.render,
    "questions_list": questions_list.render,
    "agenda_skeleton": agenda_skeleton.render,
    "risk_register": risk_register.render,
    "decisions_digest": decisions_digest.render,
}
