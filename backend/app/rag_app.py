"""ParkChat's registration as two AOM **RAG Applications**.

AOM's RAG Applications page lists registered apps (`/v1/rag/apps`) and
their activity: queries, LLM cache hits and Context Cache retrievals, all
attributed by the `rag:<app_id>:` namespace prefix.

A park-wide chatbot has two kinds of shared knowledge, and they must not
mix:

* `parkchat-assistant`  - guest-facing. Scoped to exactly one Knowledge
  Base document, today's **Park Guide**.
* `parkchat-workplace`  - crew members only. Scoped to today's **Crew
  Handbook** (IT help desk, shifts, benefits, time off, onboarding).

The scope matters because a RAG query answers from whatever its role can
read, and the agent's role can read every document the nightly loader
publishes: both knowledge documents and every per-person profile. Without
the scope, a guest's question could retrieve an HR policy or another
person's profile. The assistant picks the app from the asker's audience and
intent (`app_for`); a guest or trip planner is never routed to the workplace
app. Personal questions don't go through an app's /query endpoint at all:
the assistant builds those itself, with retrieval pinned to the asker's own
profile document.

Each knowledge document gets a new id every night, so the loader calls
`sync()` after each publish to point the apps at the new ones.
`scripts/register_with_aom.py` creates the apps the first time.
"""
from __future__ import annotations

import logging

from . import config
from .aom_client import AOMError, aom

log = logging.getLogger("parkchat.rag_app")

EMPLOYEE_INTENTS = {"it", "hr", "onboarding"}

_RULES = ("Answer concisely (under 120 words) using only the numbered passages. Never invent prices, policies, dates or "
          "availability. Cite the passages you used as [1], [2].")
APPS: dict[str, dict] = {
    "guest": {
        "app_id": config.RAG_APP_ID, "kb_key": "helpcenter", "kb_title": "Lumina Park Guide",
        "name": "ParkChat Assistant (guests & trip planners)",
        "description": ("Lumina Park's park-wide chatbot, guest side: park FAQs, rides and height limits, bookings and refund policy, and "
                        "Lumina Groups & Events. Shared questions are answered here from the nightly Park Guide document. "
                        "Personal answers use the asker's own profile, cached in the user-context namespace."),
        "system_prompt": ("You are ParkChat, Lumina Park's assistant for guests and trip planners. " + _RULES +
                          " If the passages do not answer the question, offer to connect the person with Guest Relations."),
        "no_answer_text": "I couldn't find that in the Park Guide. I can connect you with Guest Relations.",
    },
    "workplace": {
        "app_id": config.RAG_APP_ID_WORKPLACE, "kb_key": "handbook", "kb_title": "Lumina Park Crew Handbook",
        "name": "ParkChat Workplace (crew members)",
        "description": ("Lumina Park's park-wide chatbot, internal side: IT help desk, shifts, HR benefits, time off, pay and "
                        "onboarding. Scoped to the nightly Crew Handbook document; only signed-in crew members are routed here."),
        "system_prompt": ("You are ParkChat, the internal assistant for Lumina Park crew members: IT help desk and HR. " + _RULES +
                          " If the passages do not answer the question, offer to open a ticket or point to a People Partner."),
        "no_answer_text": "I couldn't find that in the Crew Handbook. I can open a ticket or point you to your People Partner.",
    },
}
STATUS: dict = {k: {"state": "not_synced", "app_id": a["app_id"]} for k, a in APPS.items()}


def app_for(intent: str, audience: str) -> str:
    """Which RAG application (and knowledge document) answers this."""
    return "workplace" if audience == "employee" and intent in EMPLOYEE_INTENTS else "guest"


def app_ids() -> list[str]:
    return [a["app_id"] for a in APPS.values()]


def definition(key: str, document_id: str | None) -> dict:
    a = APPS[key]
    return {
        "app_id": a["app_id"],
        "name": a["name"],
        "description": a["description"],
        "owner": "Lumina Park Digital",
        "enabled": bool(document_id),
        "allowed_roles": ["support_agent", "admin"],
        "set_id": "default",
        "document_ids": [document_id] if document_id else [],
        "top_k": 4,
        "min_score": 0.0,
        "retrieval_ttl_seconds": 6 * 3600,
        "semantic_cache": True,
        "system_prompt": a["system_prompt"],
        "no_answer_text": a["no_answer_text"],
    }


async def sync(key: str, document_id: str | None) -> dict:
    """Create one app, or update it in place (same app_id, same activity history)."""
    st = STATUS[key]
    if not (config.RAG_APP_ENABLED and aom.admin_enabled):
        st.update(state="disabled")
        return st
    app = definition(key, document_id)
    try:
        try:
            await aom.admin("POST", "/v1/rag/apps", {"app": app, "issue_key": False})
            action = "registered"
        except AOMError as exc:
            if exc.status != 409:
                raise
            await aom.admin("PUT", f"/v1/rag/apps/{app['app_id']}", {"app": app})
            action = "updated"
        st.update(state=action if app["enabled"] else "waiting_for_knowledge", document_ids=app["document_ids"], error=None)
        log.info("RAG application %s %s (%s %s)", app["app_id"], action, APPS[key]["kb_key"], document_id)
    except AOMError as exc:
        # 404 on the route = an AOM build without RAG Applications.
        st.update(state="unsupported" if exc.status in (404, 405) else "error", error=str(exc)[:300])
        log.warning("RAG application %s sync failed: %s", app["app_id"], exc)
    return st


async def sync_all(document_ids: dict[str, str | None]) -> dict:
    """`document_ids` is {kb_key: document_id} - helpcenter and handbook."""
    for key, a in APPS.items():
        await sync(key, document_ids.get(a["kb_key"]))
    return STATUS


def usable(key: str) -> bool:
    # "disabled" only means this backend has no admin login to manage the app;
    # the register script may still have created it, so a query is worth trying.
    return (aom.enabled and config.RAG_APP_ENABLED
            and STATUS[key].get("state") not in ("unsupported", "waiting_for_knowledge", "query_rejected"))


def query_failed(key: str, exc: AOMError):
    """404 (no such app / old AOM) or 403 (disabled, role not allowed): stop
    trying until the next sync, and use the assistant's own path instead."""
    if exc.status in (403, 404, 405):
        STATUS[key].update(state="query_rejected", error=str(exc)[:300])
