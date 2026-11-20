"""ParkChat actions - the business logic behind every MCP tool.

These functions are what actually changes state (bookings, changes and refunds, carts,
trip details, planning sessions, tickets, access, time off, benefits, onboarding). They
are only ever reached through `tool_gateway`, which routes them through the
Couchbase Agent Operations Manager when it is configured (RBAC, approvals,
tracing, audit) and calls them in-process otherwise. Every mutation bumps
the person's profile `rev`, which is what invalidates their context cache
and re-ranks their For You feed.

Each tool checks the caller's audience itself: a guest can't open an IT
ticket and a crew member's HR tools never run for a trip planner, whatever the
agent was asked to do.
"""
from __future__ import annotations

import datetime as dt
import uuid

from . import catalog as C
from .docs import INVENTORY_ID, activity_id, days_until, money, nice_date, now_iso, profile_id, today, user_channel
from .store import store


class ToolError(Exception):
    pass


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
async def load_profile(user_id: str) -> dict:
    p = await store.get("profiles", profile_id(user_id))
    if not p:
        raise ToolError(f"No profile for '{user_id}'")
    return p


def require(profile: dict, *audiences: str):
    if profile.get("audience") not in audiences:
        who = {"guest": "park guests", "lead": "trip planners", "employee": "Lumina Park crew members"}
        raise ToolError("This is only available to " + " and ".join(who[a] for a in audiences))


async def save_profile(p: dict):
    p["rev"] = int(p.get("rev", 0)) + 1
    p["updated_at"] = now_iso()
    await store.upsert("profiles", profile_id(p["user_id"]), p)
    from .loader import mark_live  # late import: loader -> personalization -> actions
    await mark_live(p["user_id"])


async def record_activity(user_id: str, item: dict):
    doc = await store.get("activity", activity_id(user_id)) or {
        "type": "activity", "user_id": user_id, "items": [], "channels": [user_channel(user_id)]}
    doc["items"] = [i for i in doc["items"] if i.get("item_id") != item["item_id"]] + [item]
    doc["updated_at"] = now_iso()
    await store.upsert("activity", activity_id(user_id), doc)


async def after_change(user_id: str):
    # late imports: personalization/assistant import this module
    from . import assistant, personalization
    await personalization.refresh_feed(user_id)
    await assistant.invalidate_context(user_id)


async def get_inventory() -> tuple[dict, int]:
    doc, cas = await store.get_with_cas("inventory", INVENTORY_ID)
    if doc is None:
        await store.insert("inventory", INVENTORY_ID, {"type": "inventory", **C.initial_inventory(today()), "created_at": now_iso()})
        doc, cas = await store.get_with_cas("inventory", INVENTORY_ID)
    return doc, cas


async def take(kind: str, key: str, what: str):
    """Take one place on an experience or one planning session seat (CAS: two phones can't
    both get the last one)."""
    for _ in range(10):
        doc, cas = await get_inventory()
        if doc[kind].get(key, 0) <= 0:
            raise ToolError(what)
        doc[kind][key] -= 1
        if await store.replace_cas("inventory", INVENTORY_ID, doc, cas):
            return doc[kind][key]
    raise ToolError("That's busy right now - please try again")


def _item(kind: str, title: str, **kw) -> dict:
    return {"item_id": f"{kind}-{uuid.uuid4().hex[:10]}", "kind": kind, "title": title, "status": "confirmed",
            "date": today().isoformat(), "created_at": now_iso(), **kw}


def _order(p: dict, booking_id: str) -> dict:
    o = next((o for o in p.get("bookings", []) if o["booking_id"] == booking_id), None)
    if not o:
        raise ToolError(f"I can't find booking {booking_id} on this account")
    return o


def _first(p: dict) -> str:
    return p["first_name"]


def change_status(p: dict, booking: dict, item: dict) -> dict:
    """Can this booking still be swapped or refunded, and for how much longer?
    Changes are free until the cut-off: the day before the visit, or the day
    itself for Gold and Platinum members."""
    cutoff = C.change_cutoff_days(p.get("loyalty", {}).get("tier"))
    until = days_until(booking.get("date"))
    changed = any(r["booking_id"] == booking["booking_id"] and r["exp_id"] == item["exp_id"] for r in p.get("changes", []))
    eligible = booking["status"] == "upcoming" and until is not None and until >= cutoff and not changed
    return {"cutoff_days": cutoff, "days_until_visit": until, "days_left": (until - cutoff) if until is not None else None,
            "eligible": eligible, "already_changed": changed}


def visit_end(p: dict) -> dt.date:
    try:
        return dt.date.fromisoformat((p.get("visit") or {}).get("end") or "")
    except ValueError:
        return today() + dt.timedelta(days=7)


def shortest_rider(p: dict) -> dict | None:
    """The party member a height limit matters for."""
    party = [m for m in (p.get("visit") or {}).get("party", []) if m.get("height_in")]
    return min(party, key=lambda m: m["height_in"]) if party else None


# --------------------------------------------------------------------------
# read tools
# --------------------------------------------------------------------------
async def get_user_context(user_id: str) -> dict:
    p = await load_profile(user_id)
    out = {"user_id": user_id, "audience": p["audience"], "name": f"{p['first_name']} {p['last_name']}",
           "home_city": p.get("home_city"), "segment": p["ml_scores"].get("segment"),
           "next_best_action": p["ml_scores"].get("next_best_action"), "preferences": p.get("preferences")}
    if p["audience"] == "guest":
        upcoming = [o for o in p["bookings"] if o["status"] == "upcoming"]
        out.update({"loyalty": p["loyalty"], "visit": p.get("visit"), "upcoming_bookings": len(upcoming), "bookings_total": p["history"]["bookings_count"],
                    "cart_items": len((p.get("cart") or {}).get("items", [])),
                    "park_credit_usd": sum(c["amount_usd"] for c in p.get("credits", []))})
    elif p["audience"] == "lead":
        out.update({"organization": p["organization"], "lead": p["lead"], "planning_session": p.get("planning_session"),
                    "recommended_package": p["ml_scores"].get("recommended_package")})
    else:
        e = p["employment"]
        out.update({"employment": {k: e[k] for k in ("title", "department", "manager", "location", "start_date")},
                    "next_shift": p["hr"].get("schedule", {}).get("next_shift"),
                    "onboarding_pending": sum(1 for t in p["onboarding"]["tasks"] if t["status"] != "complete"),
                    "open_tickets": len(p["it"]["open_tickets"]), "benefits_enrolled": p["hr"]["benefits"]["enrolled"]})
    return out


async def get_bookings(user_id: str, booking_id: str = "") -> dict:
    p = await load_profile(user_id)
    require(p, "guest")
    bookings = []
    for o in p["bookings"]:
        if booking_id and o["booking_id"] != booking_id:
            continue
        away = days_until(o.get("date"))
        bookings.append({**o, "days_away": away,
                         "can_reschedule": o["status"] == "upcoming" and o["kind"] in C.MOVABLE_KINDS and (away or 0) >= 0,
                         "changeable_items": [i["exp_id"] for i in o["items"] if change_status(p, o, i)["eligible"]]})
    if booking_id and not bookings:
        raise ToolError(f"I can't find booking {booking_id} on this account")
    # What's next first: upcoming by day and time window, then what's done.
    bookings.sort(key=lambda o: (o["status"] != "upcoming", o.get("date") or "", C.TIME_WINDOWS.index(o["time_window"]) if o.get("time_window") in C.TIME_WINDOWS else 99)
                  if o["status"] == "upcoming" else (True, "", 0))
    return {"user_id": user_id, "visit": p.get("visit"), "bookings": bookings,
            "open": [o["booking_id"] for o in bookings if o["status"] == "upcoming"]}


async def get_change_options(user_id: str, booking_id: str = "") -> dict:
    p = await load_profile(user_id)
    require(p, "guest")
    inv, _ = await get_inventory()
    items = []
    for o in p["bookings"]:
        if o["status"] == "cancelled" or (booking_id and o["booking_id"] != booking_id):
            continue
        for i in o["items"]:
            st = change_status(p, o, i)
            if st["already_changed"]:
                continue
            items.append({"booking_id": o["booking_id"], "exp_id": i["exp_id"], "name": i["name"], "price": i["price"], "kind": o["kind"],
                          "date": o.get("date"), "time_window": o.get("time_window"), "status": o["status"], **st, "refund_usd": i["price"],
                          "swap_options": [{"exp_id": x["exp_id"], "name": x["name"], "price": x["price"],
                                            "places_left": inv["stock"].get(x["exp_id"], 0),
                                            "price_difference_usd": x["price"] - i["price"]}
                                           for x in C.swap_options(i["exp_id"])]})
    items.sort(key=lambda i: (not i["eligible"], i["date"] or ""))
    tier = p["loyalty"]["tier"]
    return {"user_id": user_id, "tier": tier, "cutoff_days": C.change_cutoff_days(tier),
            "items": items, "reasons": C.CHANGE_REASONS, "past_changes": p.get("changes", [])[-5:],
            "park_credit_usd": sum(c["amount_usd"] for c in p.get("credits", []))}


async def get_cart(user_id: str) -> dict:
    p = await load_profile(user_id)
    require(p, "guest")
    cart = p.get("cart")
    if not cart or not cart.get("items"):
        return {"user_id": user_id, "cart": None, "summary": "The cart is empty."}
    inv, _ = await get_inventory()
    offer = cart.get("offer")
    valid = bool(offer and (days_until(offer["expires"]) or 0) >= 0)
    sub = cart["subtotal_usd"]
    discount = round(sub * offer["pct_off"] / 100, 2) if valid else 0
    return {"user_id": user_id, "cart": {**cart, "items": [{**i, "places_left": inv["stock"].get(i["exp_id"], 0)} for i in cart["items"]]},
            "offer_valid": valid, "offer_days_left": days_until(offer["expires"]) if valid else None,
            "discount_usd": discount, "total_usd": round(sub - discount, 2),
            "low_stock": [i["name"] for i in cart["items"] if inv["stock"].get(i["exp_id"], 0) <= 3]}


async def recommend_experiences(user_id: str, need: str = "") -> dict:
    p = await load_profile(user_id)
    likes = set(p.get("preferences", {}).get("interests", []))
    words = set(need.lower().replace(",", " ").split())
    owned = {i["exp_id"] for o in p.get("bookings", []) for i in o["items"]} | {i["exp_id"] for i in (p.get("cart") or {}).get("items", [])}
    viewed = set((p.get("browsing") or {}).get("viewed_exp_ids", []))
    picks = set(p["ml_scores"].get("recommended_exp_ids", []))
    small = shortest_rider(p)
    out = []
    for prod in C.EXPERIENCES:
        if prod["exp_id"] in owned:
            continue
        match = sorted(likes & set(prod["tags"]))
        asked = sorted(w for w in words if w in prod["tags"] or w in prod["name"].lower() or w in prod["category"].lower())
        score = 0.3 * len(match) + 0.6 * len(asked) + (0.35 if prod["exp_id"] in picks else 0) + (0.2 if prod["exp_id"] in viewed else 0)
        fits = not small or small["height_in"] >= prod["min_height_in"]
        if not fits:
            score -= 0.5          # someone in the party can't ride it
        if score > 0:
            out.append({**prod, "matched_interests": match, "matched_need": asked, "recently_viewed": prod["exp_id"] in viewed,
                        "fits_party": fits, "score": round(score, 2)})
    out.sort(key=lambda x: (-x["score"], x["price"]))
    res = {"user_id": user_id, "experiences": out[:6],
           "shortest_rider": {"name": small["name"], "height_in": small["height_in"]} if small else None}
    if p["audience"] == "lead":
        party_size = p["lead"].get("party_size") or p["organization"]["members"]
        b = C.package_for_party(party_size)
        res["package"] = {**b, "party_size": list(b["party_size"]), "estimated_guests": party_size, "estimate_usd": b["price_per_guest"] * party_size}
    return res


async def get_planning_slots(user_id: str) -> dict:
    p = await load_profile(user_id)
    require(p, "guest", "lead")
    inv, _ = await get_inventory()
    days: dict[str, list] = {}
    for sid, left in sorted(inv["slots"].items()):
        date, time = sid.split("T")
        if (days_until(date) or 0) < 1:
            continue
        days.setdefault(date, []).append({"time": time, "open": left})
    return {"user_id": user_id, "booked": p.get("planning_session"), "topics": C.PLANNING_TOPICS, "channels": C.PLANNING_CHANNELS,
            "days": [{"date": d, "slots": s} for d, s in list(days.items())[:6]],
            "qualified": (p.get("lead") or {}).get("status") in ("qualified", "session_booked")}


async def get_it_context(user_id: str) -> dict:
    p = await load_profile(user_id)
    require(p, "employee")
    it = p["it"]
    have = set(it["systems_access"])
    return {"user_id": user_id, "devices": it["devices"], "open_tickets": it["open_tickets"],
            "password_expires_in_days": it["password_expires_in_days"], "mfa_enrolled": it["mfa_enrolled"],
            "systems_access": [C.SYSTEM_BY_ID[s]["name"] for s in it["systems_access"] if s in C.SYSTEM_BY_ID],
            "requestable": [{"id": s["id"], "name": s["name"], "needs_approval": s["approval"]} for s in C.SYSTEMS if s["id"] not in have],
            "pending_access": [r for r in it.get("access_requests", []) if r.get("status") == "pending"],
            "categories": C.IT_CATEGORIES}


async def get_benefits_summary(user_id: str) -> dict:
    p = await load_profile(user_id)
    require(p, "employee")
    b = p["hr"]["benefits"]
    plan = lambda pid: ({"id": pid, "name": C.PLAN_BY_ID[pid]["name"], "cost_per_paycheck": C.PLAN_BY_ID[pid]["employee_cost_per_paycheck"]} if pid else None)  # noqa: E731
    return {"user_id": user_id, "enrolled": b["enrolled"], "enrollment_deadline": b.get("enrollment_deadline"),
            "days_to_enroll": days_until(b.get("enrollment_deadline")),
            "medical": plan(b.get("medical")), "dental": plan(b.get("dental")), "vision": plan(b.get("vision")),
            "k401_pct": b.get("k401_pct", 0), "k401_match_pct": C.K401_MATCH_PCT, "plans": C.BENEFIT_PLANS,
            "pto": p["hr"]["pto"], "pay": p["hr"]["pay"], "schedule": p["hr"].get("schedule"),
            "start_date": p["employment"]["start_date"]}


async def get_onboarding_tasks(user_id: str) -> dict:
    p = await load_profile(user_id)
    require(p, "employee")
    tasks = [{**t, "detail": C.ONBOARDING_BY_ID[t["task_id"]]["detail"], "due_in_days": days_until(t["due_date"])}
             for t in p["onboarding"]["tasks"]]
    pending = [t for t in tasks if t["status"] != "complete"]
    pending.sort(key=lambda t: t["due_date"])
    return {"user_id": user_id, "status": p["onboarding"]["status"], "start_date": p["employment"]["start_date"],
            "manager": p["employment"]["manager"], "pending": pending, "completed": [t for t in tasks if t["status"] == "complete"],
            "next_due": pending[0] if pending else None}


# --------------------------------------------------------------------------
# guests: bookings, changes, cart
# --------------------------------------------------------------------------
async def reschedule_booking(user_id: str, booking_id: str, date: str, window: str = "") -> dict:
    p = await load_profile(user_id)
    require(p, "guest")
    o = _order(p, booking_id)
    name = o["items"][0]["name"]
    if o["status"] != "upcoming":
        raise ToolError(f"Booking {booking_id} is {o['status']}, so its time can't be moved")
    if o["kind"] not in C.MOVABLE_KINDS:
        raise ToolError(f"{name} is {C.a_or_an(o['kind'])} for the whole day, so there's no time to move")
    window = window or o.get("time_window") or C.TIME_WINDOWS[0]
    if window not in C.TIME_WINDOWS:
        raise ToolError(f"Time windows: {', '.join(C.TIME_WINDOWS)}")
    try:
        new = dt.date.fromisoformat(date)
    except ValueError:
        raise ToolError("Date must be YYYY-MM-DD") from None
    last = max(visit_end(p), dt.date.fromisoformat(o["date"]))
    if not (today() <= new <= last):
        raise ToolError(f"Pick a day of your visit, from {today().isoformat()} to {last.isoformat()}")
    if new.isoformat() == o["date"] and window == o.get("time_window"):
        raise ToolError(f"{name} is already booked for {window} that day")
    o.update(date=new.isoformat(), time_window=window)
    o["events"].append({"at": today().isoformat(), "text": f"Moved to {new.isoformat()}, {window}"})
    await save_profile(p)
    item = _item("reschedule", f"Time moved · {name}", booking_id=booking_id, date=new.isoformat(), time=window)
    await record_activity(user_id, item)
    await after_change(user_id)
    return {"ok": True, "status": "confirmed", "item": item,
            "summary": f"Done - {name} is now {nice_date(new.isoformat())} between {window}. We'll remind you 15 minutes before your window opens."}


async def change_booking(user_id: str, booking_id: str, exp_id: str, reason: str, resolution: str = "refund", swap_exp_id: str = "") -> dict:
    """Refund a booking or swap it for another experience, free until the
    guest's change cut-off."""
    p = await load_profile(user_id)
    require(p, "guest")
    o = _order(p, booking_id)
    i = next((i for i in o["items"] if i["exp_id"] == exp_id), None)
    if not i:
        raise ToolError(f"{exp_id} isn't on booking {booking_id}")
    st = change_status(p, o, i)
    if st["already_changed"]:
        raise ToolError(f"{i['name']} has already been changed")
    if o["status"] != "upcoming":
        raise ToolError(f"{i['name']} is {o['status']}, so it can't be swapped or refunded here - ask Guest Relations if something went wrong")
    if not st["eligible"]:
        raise ToolError(f"{i['name']} is {'today' if st['days_until_visit'] == 0 else 'in the past'}, past your change cut-off "
                        f"({'the day before' if st['cutoff_days'] else 'the day of'} the visit)")
    if not reason or len(reason.strip()) < 3:
        raise ToolError("A change needs a reason")
    if resolution not in ("refund", "swap"):
        raise ToolError("Resolution must be 'refund' or 'swap'")
    rid = f"CHG-{uuid.uuid4().hex[:8].upper()}"
    rec = {"change_id": rid, "booking_id": booking_id, "exp_id": exp_id, "name": i["name"], "reason": reason.strip()[:200],
           "resolution": resolution, "status": "swapped" if resolution == "swap" else "refunded", "created_at": today().isoformat()}
    if resolution == "swap":
        x = C.EXPERIENCE_BY_ID.get(swap_exp_id)
        if not x or swap_exp_id not in [e["exp_id"] for e in C.swap_options(exp_id)]:
            raise ToolError(f"{i['name']} can't be swapped for '{swap_exp_id}'")
        small = shortest_rider(p)
        if small and small["height_in"] < x["min_height_in"]:
            raise ToolError(f"{x['name']} needs riders to be {x['min_height_in']} inches tall and {small['name']} is {small['height_in']} - choose another option or a refund")
        await take("stock", swap_exp_id, f"{x['name']} has no places left that day - choose another option or a refund")
        diff = x["price"] - i["price"]
        rec.update(swap_exp_id=swap_exp_id, swap_name=x["name"], price_difference_usd=diff)
        i.update(exp_id=swap_exp_id, name=x["name"], price=x["price"])
        o["kind"] = C.kind_of(swap_exp_id)
        o["total_usd"] = round(sum(n["price"] * n.get("qty", 1) for n in o["items"]), 2)
        o["events"].append({"at": today().isoformat(), "text": f"Swapped {rec['name']} for {x['name']}"})
        summary = (f"Swapped: {rec['name']} for {x['name']}, same day"
                   + (f" between {o['time_window']}" if o.get("time_window") else "")
                   + (f"; {money(diff)} is charged to your card on file." if diff > 0 else f"; {money(-diff)} goes back to your card." if diff < 0 else ".")
                   + f" Your confirmation is still {o.get('confirmation')}.")
        charge = max(diff, 0)
    else:
        rec.update(refund_usd=i["price"])
        if len(o["items"]) == 1:
            o["status"] = "cancelled"
        o["events"].append({"at": today().isoformat(), "text": f"{i['name']} cancelled and refunded"})
        summary = (f"{i['name']} is cancelled and {money(i['price'])} goes back to your card within 3 business days. "
                   "The place is released for another party.")
        charge = 0
    p.setdefault("changes", []).append(rec)
    p["history"]["changes_count"] = int(p["history"].get("changes_count", 0)) + 1
    await save_profile(p)
    item = _item("swap" if resolution == "swap" else "refund", f"{'Swap' if resolution == 'swap' else 'Refund'} · {rec['name']}",
                 booking_id=booking_id, exp_id=exp_id, change_id=rid, resolution=resolution, reason=rec["reason"],
                 refund_usd=rec.get("refund_usd"), swap_name=rec.get("swap_name"), charge_usd=charge)
    await record_activity(user_id, item)
    await after_change(user_id)
    return {"ok": True, "status": "confirmed", "charge_usd": charge, "item": item, "summary": summary}


async def issue_courtesy_credit(user_id: str, amount_usd: float, reason: str, booking_id: str = "") -> dict:
    """Park credit as a service-recovery gesture (a ride that closed during
    the guest's window, a missed reservation, a booking past its change
    cut-off). Held for a human decision in AOM's approval tier before it can run."""
    if not reason or len(reason.strip()) < 5:
        raise ToolError("A courtesy credit needs a reason for the audit trail")
    amount = round(float(amount_usd), 2)
    if amount <= 0 or amount > C.COURTESY_CREDIT_MAX:
        raise ToolError(f"Courtesy credits are between $1 and {money(C.COURTESY_CREDIT_MAX)}")
    p = await load_profile(user_id)
    require(p, "guest")
    if booking_id:
        _order(p, booking_id)
    credit = {"credit_id": f"CR-{uuid.uuid4().hex[:8].upper()}", "amount_usd": amount, "reason": reason.strip()[:300],
              "booking_id": booking_id or None, "issued_at": today().isoformat(), "expires": (today() + dt.timedelta(days=365)).isoformat()}
    p.setdefault("credits", []).append(credit)
    await save_profile(p)
    item = _item("credit", f"Park credit · {money(amount)}", amount_usd=amount, booking_id=booking_id or None, reason=credit["reason"])
    await record_activity(user_id, item)
    await after_change(user_id)
    return {"ok": True, "status": "confirmed", "charge_usd": 0, "item": item,
            "summary": f"A {money(amount)} park credit is on your account, good for a year at any restaurant, shop or booking. Reason recorded: {reason.strip()[:120]}"}


async def checkout_cart(user_id: str, apply_offer: bool = True) -> dict:
    p = await load_profile(user_id)
    require(p, "guest")
    cart = p.get("cart")
    if not cart or not cart.get("items"):
        raise ToolError("Your cart is empty")
    offer = cart.get("offer")
    valid = bool(apply_offer and offer and (days_until(offer["expires"]) or 0) >= 0)
    for i in cart["items"]:
        await take("stock", i["exp_id"], f"{i['name']} just sold out for your dates - remove it from your cart to check out")
    sub = cart["subtotal_usd"]
    discount = round(sub * offer["pct_off"] / 100, 2) if valid else 0
    total = round(sub - discount, 2)
    try:
        start = dt.date.fromisoformat((p.get("visit") or {}).get("start") or "")
    except ValueError:
        start = today()
    day = max(start, today() + dt.timedelta(days=1)) if visit_end(p) > today() else today()
    kind = C.kind_of(cart["items"][0]["exp_id"])
    timed = kind in C.MOVABLE_KINDS
    booking = {"booking_id": f"LP-{900000 + C._h(user_id, p.get('rev', 0)) % 90000}", "booked_at": today().isoformat(), "status": "upcoming",
               "items": cart["items"], "subtotal_usd": sub, "discount_usd": discount, "offer_code": offer["code"] if valid else None,
               "total_usd": total, "kind": kind, "confirmation": f"LUM{C._h('conf', user_id, p.get('rev', 0)) % 10**6:06d}",
               "date": day.isoformat(), "time_window": C.TIME_WINDOWS[-1] if timed else None, "completed_at": None,
               "party_size": len((p.get("visit") or {}).get("party", [])) or 1,
               "events": [{"at": today().isoformat(), "text": "Booked in ParkChat"}]}
    p["bookings"].insert(0, booking)
    p["cart"] = None
    p["history"]["bookings_count"] = int(p["history"].get("bookings_count", 0)) + 1
    p["loyalty"]["points"] = int(p["loyalty"].get("points", 0)) + int(total)
    await save_profile(p)
    item = _item("booking", f"Booking {booking['booking_id']} · {len(booking['items'])} item{'s' if len(booking['items']) > 1 else ''}",
                 booking_id=booking["booking_id"], charge_usd=total, date=day.isoformat())
    await record_activity(user_id, item)
    await after_change(user_id)
    return {"ok": True, "status": "confirmed", "charge_usd": total, "item": item,
            "summary": f"Booked ({booking['booking_id']}): {', '.join(i['name'] for i in booking['items'])} for {nice_date(day.isoformat())}"
                       + (f", {booking['time_window']}" if timed else "") + ". "
                       + (f"{offer['code']} saved you {money(discount)}. " if valid else "")
                       + f"{money(total)} charged to your card on file; show confirmation {booking['confirmation']} at the entrance."}


# --------------------------------------------------------------------------
# trip planners: trip details, qualification, planning sessions
# --------------------------------------------------------------------------
async def submit_trip_details(user_id: str, party_size: int, budget_band: str, timeline: str, phone: str = "", interest: str = "") -> dict:
    p = await load_profile(user_id)
    require(p, "lead")
    party_size = int(party_size)
    if party_size < 1 or party_size > 5000:
        raise ToolError("Party size must be between 1 and 5,000 guests")
    if budget_band not in C.BUDGET_BANDS:
        raise ToolError(f"Budget: {', '.join(C.BUDGET_BANDS)}")
    if timeline not in C.TIMELINES:
        raise ToolError(f"Timeline: {', '.join(C.TIMELINES)}")
    lead = p["lead"]
    # Qualification the way a group-sales advisor would score it.
    score = 0.35 + (0.2 if party_size >= 10 else 0.05) + dict(zip(C.BUDGET_BANDS, (0.0, 0.1, 0.2, 0.25)))[budget_band] \
        + {"this month": 0.2, "1-3 months": 0.15, "3-6 months": 0.05, "just researching": -0.1}[timeline]
    score = round(max(0.05, min(0.99, score)), 2)
    qualified = score >= 0.5
    advisor = lead.get("owner") or C.ADVISORS[C._h(user_id) % len(C.ADVISORS)]
    lead.update(party_size=party_size, budget_band=budget_band, timeline=timeline, score=score, owner=advisor,
                status=("session_booked" if p.get("planning_session") else "qualified" if qualified else "nurture"))
    if interest:
        lead["interest"] = list(dict.fromkeys([interest] + lead.get("interest", [])))[:3]
    if phone.strip():
        p["phone"] = phone.strip()[:30]
    b = C.package_for_party(party_size)
    p["ml_scores"].update(lead_score=score, recommended_package=b["code"],
                          next_best_action="book_planning_session" if qualified and not p.get("planning_session") else "nurture")
    await save_profile(p)
    item = _item("lead", f"Trip details shared · {party_size} guests · {budget_band}", party_size=party_size, budget_band=budget_band, timeline=timeline,
                 score=score, qualified=qualified, owner=advisor)
    await record_activity(user_id, item)
    await after_change(user_id)
    est = b["price_per_guest"] * party_size
    return {"ok": True, "status": "confirmed", "item": item, "qualified": qualified,
            "summary": f"Thanks, {_first(p)} - for {party_size} guests, {b['name']} is the fit: about {money(est)} ({money(b['price_per_guest'])} a guest), "
                       f"tickets included. {advisor} from {C.PARK['business_brand']} is your contact"
                       + (" - book a planning session and they'll bring a day plan." if qualified else "; we'll send the group visit guide and check in when you're closer.")}


async def book_planning_session(user_id: str, date: str, time: str, topic: str = "", channel: str = "video") -> dict:
    p = await load_profile(user_id)
    require(p, "guest", "lead")
    if time not in C.PLANNING_TIMES:
        raise ToolError(f"Times available: {', '.join(C.PLANNING_TIMES)}")
    if channel not in C.PLANNING_CHANNELS:
        raise ToolError(f"Choose one of: {', '.join(C.PLANNING_CHANNELS)}")
    topic = topic or ((p.get("lead") or {}).get("interest") or C.PLANNING_TOPICS[-1:])[0]
    inv, _ = await get_inventory()
    sid = C.slot_id(date, time)
    if sid not in inv["slots"] or (days_until(date) or 0) < 1:
        raise ToolError("Pick a weekday in the next two weeks")
    if inv["slots"][sid] <= 0:
        alts = [t for t in C.PLANNING_TIMES if inv["slots"].get(C.slot_id(date, t), 0) > 0][:3]
        raise ToolError(f"{time} on {date} is fully booked." + (f" Open that day: {', '.join(alts)}" if alts else " Try another day."))
    await take("slots", sid, f"{time} on {date} was just taken - pick another time")
    advisor = (p.get("lead") or {}).get("owner") or C.ADVISORS[C._h(user_id) % len(C.ADVISORS)]
    p["planning_session"] = {"date": date, "time": time, "topic": topic, "channel": channel, "advisor": advisor, "booked_at": now_iso()}
    if p["audience"] == "lead":
        p["lead"].update(status="session_booked", owner=advisor)
        p["ml_scores"]["next_best_action"] = "prepare_for_planning session"
    await save_profile(p)
    item = _item("planning_session", f"Planning session · {topic}", date=date, time=time, channel=channel, advisor=advisor, topic=topic)
    await record_activity(user_id, item)
    await after_change(user_id)
    return {"ok": True, "status": "confirmed", "item": item,
            "summary": f"Booked: {topic} with {advisor} on {nice_date(date)} at {time} ({channel}). A calendar invite is on its way to {p.get('email')}."}


# --------------------------------------------------------------------------
# crew members: IT help desk
# --------------------------------------------------------------------------
async def create_it_ticket(user_id: str, category: str, summary: str, priority: str = "normal") -> dict:
    p = await load_profile(user_id)
    require(p, "employee")
    cat = C.IT_CATEGORY_BY_ID.get(category)
    if not cat:
        raise ToolError(f"Categories: {', '.join(c['id'] for c in C.IT_CATEGORIES)}")
    if priority not in C.IT_PRIORITIES:
        raise ToolError(f"Priority: {', '.join(C.IT_PRIORITIES)}")
    if not summary or len(summary.strip()) < 5:
        raise ToolError("Describe the problem in a sentence")
    dup = next((t for t in p["it"]["open_tickets"] if t["category"] == category and t["summary"].lower() == summary.strip().lower()), None)
    if dup:
        raise ToolError(f"{dup['ticket_id']} is already open for this")
    tid = f"INC-{300000 + C._h(user_id, summary, p.get('rev', 0)) % 600000}"
    sla = cat["sla_hours"] // (2 if priority == "high" else 1)
    ticket = {"ticket_id": tid, "category": category, "summary": summary.strip()[:200], "status": "open", "priority": priority,
              "opened_at": today().isoformat(), "queue": cat["queue"], "sla_hours": sla,
              "device": (p["it"]["devices"] or [{}])[0].get("asset_tag")}
    p["it"]["open_tickets"].append(ticket)
    await save_profile(p)
    item = _item("ticket", f"{tid} · {cat['name']}", ticket_id=tid, category=category, priority=priority, queue=cat["queue"], summary=ticket["summary"])
    await record_activity(user_id, item)
    await after_change(user_id)
    return {"ok": True, "status": "confirmed", "item": item,
            "summary": f"{tid} is open with the {cat['queue']} team ({priority} priority). First response within {sla} business hour{'s' if sla != 1 else ''}; "
                       f"they have your {ticket['device'] or 'device'} details already."}


async def reset_password(user_id: str, system: str = "sso") -> dict:
    p = await load_profile(user_id)
    require(p, "employee")
    s = C.SYSTEM_BY_ID.get(system)
    if not s or system not in p["it"]["systems_access"]:
        raise ToolError(f"You don't have an account on '{system}' to reset")
    if not p["it"]["mfa_enrolled"]:
        raise ToolError("You need multi-factor sign-in set up before a self-service reset - open an Account & access ticket and the Identity team will verify you")
    p["it"]["password_expires_in_days"] = 90
    p["it"]["last_password_reset"] = now_iso()
    await save_profile(p)
    item = _item("password", f"Password reset · {s['name']}", system=system)
    await record_activity(user_id, item)
    await after_change(user_id)
    return {"ok": True, "status": "confirmed", "item": item,
            "summary": f"A reset link for {s['name']} is in your authenticator app - approve the prompt, then choose a new password within 15 minutes. "
                       "Your other devices will ask you to sign in again."}


async def _grant_access(user_id: str, system: str, justification: str, privileged: bool) -> dict:
    if not justification or len(justification.strip()) < 5:
        raise ToolError("Access requests need a business justification for the audit trail")
    p = await load_profile(user_id)
    require(p, "employee")
    s = C.SYSTEM_BY_ID.get(system)
    if not s:
        raise ToolError(f"Unknown system '{system}'. Requestable: {', '.join(x['id'] for x in C.SYSTEMS if not x['default'])}")
    if system in p["it"]["systems_access"]:
        raise ToolError(f"You already have access to {s['name']}")
    if s["approval"] != privileged:
        raise ToolError(f"{s['name']} " + ("holds guest data, cash handling or ride controls, so it goes through a privileged access request"
                                           if s["approval"] else "is a standard system - request it with a standard access request"))
    if privileged and not all(t["status"] == "complete" for t in p["onboarding"]["tasks"] if t["task_id"] == "safety-training"):
        raise ToolError(f"Finish your park safety & evacuation training before requesting {s['name']}")
    p["it"]["systems_access"].append(system)
    p["it"].setdefault("access_requests", []).append({"system": system, "justification": justification.strip()[:300],
                                                       "status": "granted", "privileged": privileged, "at": today().isoformat()})
    await save_profile(p)
    item = _item("access", f"Access granted · {s['name']}", system=system, privileged=privileged, justification=justification.strip()[:300])
    await record_activity(user_id, item)
    await after_change(user_id)
    return {"ok": True, "status": "confirmed", "item": item,
            "summary": f"You now have access to {s['name']}. It appears in your CrewPass launcher within a few minutes. Justification recorded: {justification.strip()[:120]}"}


async def request_system_access(user_id: str, system: str, justification: str) -> dict:
    """Standard systems (Backstage Wi-Fi, point of sale): granted straight away."""
    return await _grant_access(user_id, system, justification, privileged=False)


async def request_privileged_access(user_id: str, system: str, justification: str) -> dict:
    """Systems that expose guest data, cash handling or ride controls. Held for a
    human decision in AOM's approval tier before it can run."""
    return await _grant_access(user_id, system, justification, privileged=True)


# --------------------------------------------------------------------------
# crew members: HR
# --------------------------------------------------------------------------
async def request_time_off(user_id: str, start_date: str, end_date: str, note: str = "") -> dict:
    p = await load_profile(user_id)
    require(p, "employee")
    try:
        a, b = dt.date.fromisoformat(start_date), dt.date.fromisoformat(end_date)
    except ValueError:
        raise ToolError("Dates must be YYYY-MM-DD") from None
    if b < a or a <= today():
        raise ToolError("Pick a future start date and an end date on or after it")
    days = sum(1 for n in range((b - a).days + 1) if (a + dt.timedelta(days=n)).weekday() < 5)
    if days == 0:
        raise ToolError("Those dates are a weekend - no time off needed")
    pto = p["hr"]["pto"]
    if days > pto["balance_days"]:
        raise ToolError(f"That's {days} working days and your balance is {pto['balance_days']:g}. You accrue {pto.get('accrual_per_month', C.PTO_ACCRUAL_PER_MONTH):g} days a month.")
    if any(r["start_date"] <= end_date and start_date <= r["end_date"] for r in pto.get("requests", [])):
        raise ToolError("You already have time off requested over those dates")
    pto["balance_days"] = round(pto["balance_days"] - days, 1)
    pto.setdefault("requests", []).append({"start_date": start_date, "end_date": end_date, "days": days, "status": "pending_manager",
                                           "note": note.strip()[:200], "requested_at": today().isoformat()})
    await save_profile(p)
    mgr = p["employment"]["manager"]
    item = _item("timeoff", f"Time off · {days} day{'s' if days != 1 else ''}", status="submitted", date=start_date, end_date=end_date,
                 days=days, manager=mgr)
    await record_activity(user_id, item)
    await after_change(user_id)
    return {"ok": True, "status": "submitted", "item": item,
            "summary": f"Requested {days} day{'s' if days != 1 else ''} off, {nice_date(start_date)}" + (f" to {nice_date(end_date)}" if end_date != start_date else "") + f". It's with {mgr} for approval; "
                       f"your balance after this is {pto['balance_days']:g} days."}


async def enroll_benefits(user_id: str, medical: str, dental: str = "", vision: str = "", k401_pct: int = -1) -> dict:
    p = await load_profile(user_id)
    require(p, "employee")
    b = p["hr"]["benefits"]
    left = days_until(b.get("enrollment_deadline"))
    if b["enrolled"]:
        raise ToolError("You're already enrolled - changes open again at annual enrollment in November, or after a qualifying life event")
    if left is not None and left < 0:
        raise ToolError("Your 30-day new-hire enrollment window has closed - talk to a People Partner about a qualifying life event")
    chosen = []
    for kind, pid in (("medical", medical), ("dental", dental), ("vision", vision)):
        if not pid:
            continue
        plan = C.PLAN_BY_ID.get(pid)
        if not plan or plan["kind"] != kind:
            raise ToolError(f"'{pid}' isn't a {kind} plan. Options: {', '.join(x['id'] for x in C.BENEFIT_PLANS[kind])}")
        b[kind] = pid
        chosen.append(plan)
    if not medical:
        raise ToolError("Choose a medical plan (or ask about waiving coverage)")
    if 0 <= int(k401_pct) <= 50:
        b["k401_pct"] = int(k401_pct)
    b.update(enrolled=True, enrolled_at=today().isoformat())
    for t in p["onboarding"]["tasks"]:
        if t["task_id"] == "benefits":
            t.update(status="complete", completed_at=today().isoformat())
    _close_onboarding(p)
    await save_profile(p)
    cost = sum(x["employee_cost_per_paycheck"] for x in chosen)
    item = _item("benefits", "Benefits enrolled · " + ", ".join(x["name"] for x in chosen), plans=[x["id"] for x in chosen],
                 cost_per_paycheck=cost, k401_pct=b.get("k401_pct", 0))
    await record_activity(user_id, item)
    await after_change(user_id)
    return {"ok": True, "status": "confirmed", "item": item,
            "summary": f"You're enrolled: {', '.join(x['name'] for x in chosen)} - {money(cost)} per paycheck, effective the first of next month. "
                       + (f"401(k) set to {b['k401_pct']}% (we match up to {C.K401_MATCH_PCT}%). " if b.get("k401_pct") else "")
                       + "Your ID cards arrive by mail in about 10 days and are in the Crew Portal now."}


def _close_onboarding(p: dict):
    if all(t["status"] == "complete" for t in p["onboarding"]["tasks"]):
        p["onboarding"]["status"] = "complete"
        p["ml_scores"]["next_best_action"] = "none"


async def complete_onboarding_task(user_id: str, task_id: str, acknowledgment: str = "") -> dict:
    p = await load_profile(user_id)
    require(p, "employee")
    t = next((t for t in p["onboarding"]["tasks"] if t["task_id"] == task_id), None)
    if not t:
        raise ToolError(f"Unknown onboarding task '{task_id}'")
    if t["status"] == "complete":
        raise ToolError(f"{t['title']} is already complete")
    if task_id == "benefits":
        raise ToolError("Benefits enrollment is completed by choosing your plans")
    if t["kind"] == "sign" and len(acknowledgment.strip()) < 2:
        raise ToolError("Type your full name to sign")
    t.update(status="complete", completed_at=today().isoformat())
    if t["kind"] == "sign":
        t["signed_as"] = acknowledgment.strip()[:80]
    _close_onboarding(p)
    await save_profile(p)
    left = [x for x in p["onboarding"]["tasks"] if x["status"] != "complete"]
    item = _item("onboarding", f"{t['title']} · complete", task_id=task_id, task_kind=t["kind"])
    await record_activity(user_id, item)
    await after_change(user_id)
    nxt = sorted(left, key=lambda x: x["due_date"])[0] if left else None
    return {"ok": True, "status": "confirmed", "item": item,
            "summary": f"{t['title']} is done" + (" and signed" if t["kind"] == "sign" else "") + ". "
                       + (f"{len(left)} to go - next is {nxt['title']}, due {nice_date(nxt['due_date'])}." if nxt else "That's your onboarding complete - welcome to Lumina Park!")}


TOOLS = {
    "get_user_context": get_user_context,
    "get_bookings": get_bookings,
    "get_change_options": get_change_options,
    "get_cart": get_cart,
    "recommend_experiences": recommend_experiences,
    "get_planning_slots": get_planning_slots,
    "get_it_context": get_it_context,
    "get_benefits_summary": get_benefits_summary,
    "get_onboarding_tasks": get_onboarding_tasks,
    "reschedule_booking": reschedule_booking,
    "change_booking": change_booking,
    "issue_courtesy_credit": issue_courtesy_credit,
    "checkout_cart": checkout_cart,
    "submit_trip_details": submit_trip_details,
    "book_planning_session": book_planning_session,
    "create_it_ticket": create_it_ticket,
    "reset_password": reset_password,
    "request_system_access": request_system_access,
    "request_privileged_access": request_privileged_access,
    "request_time_off": request_time_off,
    "enroll_benefits": enroll_benefits,
    "complete_onboarding_task": complete_onboarding_task,
}
READ_ONLY_TOOLS = {"get_user_context", "get_bookings", "get_change_options", "get_cart", "recommend_experiences",
                   "get_planning_slots", "get_it_context", "get_benefits_summary", "get_onboarding_tasks"}
# Held for a person in AOM's approval tier before they run.
APPROVAL_TOOLS = ["issue_courtesy_credit", "request_privileged_access"]
