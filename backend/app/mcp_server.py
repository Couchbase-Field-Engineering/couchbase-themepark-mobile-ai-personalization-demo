"""`parkchat-services` - the MCP server registered with AOM.

Streamable HTTP at /pk/mcp/. AOM ingests these tool definitions into its
vetted catalog (embeddings for discovery, RBAC per role, drift detection)
and is the only caller the demo expects: the app and the assistant reach
these tools through `POST /v1/tools/invoke`, never directly.

Business errors (no places left, past the change cut-off, wrong audience)
come back as `{"ok": false, ...}` results rather than MCP errors, so AOM
records a completed call and the person gets a useful message instead of a
gateway failure.
"""
from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import actions

log = logging.getLogger("parkchat.mcp")

mcp = FastMCP(
    "parkchat-services",
    instructions=("Lumina Park ParkChat services, one tool set for the park-wide chatbot: guest bookings (express passes, dining, shows), "
                  "time changes, swaps, refunds, carts and courtesy credits; group trip details and planning session booking; and the "
                  "crew IT help desk (tickets, password resets, system access) and HR (shifts, benefits, time off, onboarding)."),
    stateless_http=True,
    # Called by AOM over the Docker host gateway, so the Host header is not
    # localhost; same reasoning as AOM's own bundled sample servers.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


async def _run(fn, **kw) -> dict:
    try:
        res = await fn(**kw)
    except actions.ToolError as exc:
        return {"ok": False, "status": "failed", "summary": str(exc)}
    return res if isinstance(res, dict) and "ok" in res else {"ok": True, "status": "ok", "data": res}


# ---- read ---------------------------------------------------------------------
@mcp.tool()
async def get_user_context(user_id: str) -> dict:
    """Read who a ParkChat user is: audience (guest, trip planner or crew member), loyalty or lead or employment summary, segment and next best action."""
    return await _run(actions.get_user_context, user_id=user_id)


@mcp.tool()
async def get_bookings(user_id: str, booking_id: str = "") -> dict:
    """List a guest's bookings (express passes, dining, shows, add-ons) with status, day, time window and confirmation code, whether the time can be moved, and which can still be swapped or refunded. Includes the visit dates and the party."""
    return await _run(actions.get_bookings, user_id=user_id, booking_id=booking_id)


@mcp.tool()
async def get_change_options(user_id: str, booking_id: str = "") -> dict:
    """List a guest's bookings with change cut-off eligibility, refund amount and swap options that still have places."""
    return await _run(actions.get_change_options, user_id=user_id, booking_id=booking_id)


@mcp.tool()
async def get_cart(user_id: str) -> dict:
    """Read a guest's saved cart of extras: items, places left, any recovery offer code, and the total."""
    return await _run(actions.get_cart, user_id=user_id)


@mcp.tool()
async def recommend_experiences(user_id: str, need: str = "") -> dict:
    """Recommend experiences for a user from their interests, browsing and an optional stated need; flags rides someone in the party is too short for; for trip planners also the group package sized to their party."""
    return await _run(actions.recommend_experiences, user_id=user_id, need=need)


@mcp.tool()
async def get_planning_slots(user_id: str) -> dict:
    """List open Groups & Events planning session slots for the next business days, and any planning session already booked."""
    return await _run(actions.get_planning_slots, user_id=user_id)


@mcp.tool()
async def get_it_context(user_id: str) -> dict:
    """Read a crew member's IT picture: devices, open help-desk tickets, password expiry, system access and what they can request."""
    return await _run(actions.get_it_context, user_id=user_id)


@mcp.tool()
async def get_benefits_summary(user_id: str) -> dict:
    """Read a crew member's benefits enrollment and deadline, plan options, 401(k), paid-time-off balance, next pay date and next shift."""
    return await _run(actions.get_benefits_summary, user_id=user_id)


@mcp.tool()
async def get_onboarding_tasks(user_id: str) -> dict:
    """List a new hire's onboarding paperwork: pending and completed tasks with due dates."""
    return await _run(actions.get_onboarding_tasks, user_id=user_id)


# ---- guests ------------------------------------------------------------------
@mcp.tool()
async def reschedule_booking(user_id: str, booking_id: str, date: str, window: str = "") -> dict:
    """Move an upcoming express pass, dining reservation or show seat to another day of the visit (YYYY-MM-DD) and one-hour window (e.g. 3:00pm-4:00pm)."""
    return await _run(actions.reschedule_booking, user_id=user_id, booking_id=booking_id, date=date, window=window)


@mcp.tool()
async def change_booking(user_id: str, booking_id: str, exp_id: str, reason: str, resolution: str = "refund", swap_exp_id: str = "") -> dict:
    """Refund an upcoming booking or swap it for another experience, inside the guest's change cut-off. resolution is 'refund' or 'swap' (with swap_exp_id)."""
    return await _run(actions.change_booking, user_id=user_id, booking_id=booking_id, exp_id=exp_id, reason=reason,
                      resolution=resolution, swap_exp_id=swap_exp_id)


@mcp.tool()
async def issue_courtesy_credit(user_id: str, amount_usd: float, reason: str, booking_id: str = "") -> dict:
    """Issue park credit (up to $150) as a service-recovery gesture for a ride that closed, a missed reservation or a booking past its change cut-off. Requires a reason; held for a Guest Relations lead's approval."""
    return await _run(actions.issue_courtesy_credit, user_id=user_id, amount_usd=amount_usd, reason=reason, booking_id=booking_id)


@mcp.tool()
async def checkout_cart(user_id: str, apply_offer: bool = True) -> dict:
    """Book everything in a guest's saved cart of extras using the card on file, applying the cart recovery offer if it is still valid."""
    return await _run(actions.checkout_cart, user_id=user_id, apply_offer=apply_offer)


# ---- trip planners ----------------------------------------------------------------------
@mcp.tool()
async def submit_trip_details(user_id: str, party_size: int, budget_band: str, timeline: str, phone: str = "", interest: str = "") -> dict:
    """Capture and qualify a group trip: party_size (guests), budget band (under $2k, $2k-$10k, $10k-$30k, $30k+), timeline, optional phone. Scores the lead, sizes a package and assigns an advisor."""
    return await _run(actions.submit_trip_details, user_id=user_id, party_size=party_size, budget_band=budget_band, timeline=timeline,
                      phone=phone, interest=interest)


@mcp.tool()
async def book_planning_session(user_id: str, date: str, time: str, topic: str = "", channel: str = "video") -> dict:
    """Book a free planning session with a Lumina Groups & Events advisor. date YYYY-MM-DD, time HH:MM, channel video, phone or at the park."""
    return await _run(actions.book_planning_session, user_id=user_id, date=date, time=time, topic=topic, channel=channel)


# ---- crew members -----------------------------------------------------------------------
@mcp.tool()
async def create_it_ticket(user_id: str, category: str, summary: str, priority: str = "normal") -> dict:
    """Open an IT help desk ticket for a crew member. category: access, hardware, network, software, email or pos; priority low, normal or high."""
    return await _run(actions.create_it_ticket, user_id=user_id, category=category, summary=summary, priority=priority)


@mcp.tool()
async def reset_password(user_id: str, system: str = "sso") -> dict:
    """Send a crew member a self-service password reset to their authenticator app (requires multi-factor sign-in to be set up)."""
    return await _run(actions.reset_password, user_id=user_id, system=system)


@mcp.tool()
async def request_system_access(user_id: str, system: str, justification: str) -> dict:
    """Grant a crew member access to a standard system (network = Backstage Wi-Fi, pos) with a business justification."""
    return await _run(actions.request_system_access, user_id=user_id, system=system, justification=justification)


@mcp.tool()
async def request_privileged_access(user_id: str, system: str, justification: str) -> dict:
    """Grant a crew member access to a privileged system touching ride controls, cash or guest data (ride-ops, cash-office, guest-recovery, guest-data). Requires a justification; held for approval."""
    return await _run(actions.request_privileged_access, user_id=user_id, system=system, justification=justification)


@mcp.tool()
async def request_time_off(user_id: str, start_date: str, end_date: str, note: str = "") -> dict:
    """Request paid time off for a crew member (dates YYYY-MM-DD); checks the balance and sends it to their lead."""
    return await _run(actions.request_time_off, user_id=user_id, start_date=start_date, end_date=end_date, note=note)


@mcp.tool()
async def enroll_benefits(user_id: str, medical: str, dental: str = "", vision: str = "", k401_pct: int = -1) -> dict:
    """Enroll a new hire in benefits within their 30-day window: medical (MED-CORE, MED-HSA, MED-PLUS), optional dental (DEN-BASE, DEN-PLUS), vision (VIS-STD) and 401(k) percent."""
    return await _run(actions.enroll_benefits, user_id=user_id, medical=medical, dental=dental, vision=vision, k401_pct=k401_pct)


@mcp.tool()
async def complete_onboarding_task(user_id: str, task_id: str, acknowledgment: str = "") -> dict:
    """Complete a new-hire onboarding task (i9, w4, direct-deposit, handbook, code-of-conduct, safety-training, emergency-contact). Sign tasks need the person's typed name."""
    return await _run(actions.complete_onboarding_task, user_id=user_id, task_id=task_id, acknowledgment=acknowledgment)
