"""ParkChat Changes Agent - the second AOM agent identity in the demo.

It is triggered by **Confirm** on the Change screen (or a courtesy-credit
button in chat): the phone writes a `requests` document (`change_booking` or
`issue_courtesy_credit`), and the worker hands either tool to this agent
instead of the assistant. One change = one AOM run, attributed to the
*ParkChat Changes Agent* on AOM's Agents, Traces and Audit pages, scoped to
the five booking-and-change tools only - it cannot touch a trip planner, a
ticket or anything in HR.

What makes it an agent rather than a tool call is **AOM Agent Memory**:

1. Before processing it recalls what AOM already remembers about this
   guest's changes (`POST /v1/memory/search`): earlier swaps and refunds,
   credits, and anything they told ParkChat about their party - who is too
   small for which ride, what scared the kids.
2. After the change is processed it writes an episodic memory
   (`POST /v1/memory`) - what was changed, on which booking, why, and whether
   it was refunded, swapped (for what) or credited - plus a semantic
   preference memory when the reason shows one ("Leo isn't tall enough for
   Starfall Coaster").

The assistant recalls the same memories on its next turn, so "what should
we ride next?" is answered knowing the last pick was too tall.
"""
from __future__ import annotations

import logging

from . import tool_gateway
from .aom_client import AOMError, changes_aom
from .docs import profile_id
from .store import store

log = logging.getLogger("parkchat.changes_agent")

AGENT_ID = "parkchat-changes-agent"
AGENT_NAME = "ParkChat Changes Agent"
TOOLS = ["get_user_context", "get_bookings", "get_change_options", "change_booking", "issue_courtesy_credit"]
# Tools the worker routes to this agent (the request documents a Confirm creates).
TRIGGER_TOOLS = {"change_booking", "issue_courtesy_credit"}
DESCRIPTION = ("Lumina Park booking changes agent. Triggered when a guest confirms a swap, a refund or a "
               "courtesy credit in the ParkChat mobile app: recalls the guest's change history and what they said about "
               "their party from Agent Memory, processes the change as a governed tool call, and remembers the outcome for the assistant.")


def enabled() -> bool:
    return changes_aom.enabled


async def recall(user_id: str) -> list[str]:
    if not enabled():
        return []
    try:
        res = await changes_aom.memory_search(user_id, "swap refund credit ride height party preference", top_k=4)
        return [e.get("content", "") for e in res.get("entries", []) if e.get("content")]
    except AOMError as exc:
        log.info("memory search skipped: %s", exc)
        return []


def _episode(tool: str, profile: dict, args: dict, result: dict) -> str:
    item = result.get("item") or {}
    tier = (profile.get("loyalty") or {}).get("tier")
    if tool == "issue_courtesy_credit":
        what = (f"received a ${item.get('amount_usd', args.get('amount_usd')):,.0f} courtesy park credit approved by Guest Relations"
                + (f" on booking {item['booking_id']}" if item.get("booking_id") else "") + f" - reason: {item.get('reason') or args.get('reason')}")
    else:
        rec = next((r for r in profile.get("changes", []) if r.get("change_id") == item.get("change_id")), {})
        name = rec.get("name") or args.get("exp_id")
        if item.get("resolution") == "swap":
            what = f"swapped {name} (booking {item.get('booking_id')}) for {item.get('swap_name')} - reason: {item.get('reason')}"
        else:
            what = (f"cancelled {name} (booking {item.get('booking_id')}) for a ${item.get('refund_usd') or 0:,.0f} refund - reason: "
                    f"{item.get('reason')}")
    return f"Change history: {what}." + (f" Guest is a {tier} member." if tier else "")


def _preference(args: dict, result: dict) -> str | None:
    reason = ((result.get("item") or {}).get("reason") or args.get("reason") or "").strip()
    name = (result.get("item") or {}).get("title", "").split("·")[-1].strip()
    low = reason.lower()
    if any(k in low for k in ("tall", "height", "small", "scared", "scary", "dark", "wet", "loud", "fast", "motion", "allerg", "early", "late")) and name:
        return f"Experience preferences: found {name} wasn't right - {reason}."
    return None


async def run(doc: dict, args: dict, approval_id: str | None = None) -> dict:
    """Process a change request as the Changes Agent. Returns the tool result
    plus `agent`, `memories_recalled` and `remembered`."""
    user_id = doc.get("user_id")
    tool = doc.get("tool")
    memories = await recall(user_id)
    result = await tool_gateway.invoke(tool, args, approval_id=approval_id, client=changes_aom if enabled() else None)
    result.update({"agent": AGENT_ID, "memories_recalled": len(memories), "remembered": False})

    if result.get("ok") and result.get("status") in ("ok", "confirmed", "accepted", "submitted") and enabled():
        try:
            after = await store.get("profiles", profile_id(user_id)) or {}
            await changes_aom.memory_add(
                user_id, _episode(tool, after, args, result), session_id=doc.get("session_id"), memory_type="episodic",
                metadata={"agent": AGENT_ID, "tool": tool, "booking_id": args.get("booking_id"),
                          "trace_id": result.get("trace_id"), "app": "parkchat-mobile"})
            pref = _preference(args, result)
            if pref:
                await changes_aom.memory_add(user_id, pref, memory_type="semantic", metadata={"agent": AGENT_ID, "app": "parkchat-mobile"})
            result["remembered"] = True
        except AOMError as exc:
            log.info("memory add skipped: %s", exc)
    if memories and result.get("summary"):
        last = next((m for m in memories if m.startswith("Change history:")), None)
        if last:
            result["summary"] += f" (The changes agent remembered: {last[len('Change history: '):].rstrip('.')}.)"
    return result
