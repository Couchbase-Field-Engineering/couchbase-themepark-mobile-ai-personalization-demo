"""Ranks the "For You" feed for one person.

Inputs are the scores, segments and preferences from the nightly export,
plus live state the export can't know about: what the person has done since
(a booking swapped in chat, a ticket opened, a planning session booked), places
left on each experience and open planning session slots. The result is written to
`feed::<user_id>`, which Sync Gateway replicates to the person's phone - so
the feed renders from Couchbase Lite, even offline, and re-ranks itself on
the next sync after every action.

A card carries everything its screen needs (swap options, planning session
slots), so the Change and Planning session screens work offline too.
"""
from __future__ import annotations

from . import catalog as C
from .docs import days_until, feed_id, money, nice_date, now_iso, profile_id, user_channel
from .store import store

PALETTES = {  # gradient keys the app maps to brand gradients
    "booking": "ink", "change": "ember", "cart": "red", "experience": "sand", "planning": "red", "lead": "ink", "shift": "ink",
    "onboarding": "red", "benefits": "ember", "ticket": "ink", "it": "sand", "timeoff": "sand", "reward": "ember",
}


def _card(kind: str, card_id: str, title: str, subtitle: str, reason: str, badge: str, score: float, cta: dict, **extra) -> dict:
    return {"card_id": card_id, "kind": kind, "palette": PALETTES.get(kind, "ink"), "area": AREA_OF[kind], "title": title,
            "subtitle": subtitle, "reason": reason, "badge": badge, "score": score, "cta": cta, **extra}


AREA_OF = {"booking": "commerce", "change": "commerce", "cart": "commerce", "reward": "support", "experience": "sales",
           "planning": "sales", "lead": "sales", "onboarding": "workplace", "benefits": "workplace", "ticket": "workplace",
           "it": "workplace", "timeoff": "workplace", "shift": "workplace"}


async def _guest(p: dict) -> list[dict]:
    from .actions import change_status, get_inventory, shortest_rider  # avoid import cycle

    s, cards = p["ml_scores"], []
    inv, _ = await get_inventory()
    upcoming = sorted((o for o in p["bookings"] if o["status"] == "upcoming"), key=lambda o: (o.get("date") or "", o.get("time_window") or ""))
    for n, o in enumerate(upcoming[:3]):
        d = days_until(o["date"]) or 0
        when = "today" if d <= 0 else "tomorrow" if d == 1 else f"in {d} days"
        movable = o["kind"] in C.MOVABLE_KINDS
        cards.append(_card(
            "booking", f"booking-{o['booking_id']}", f"{o['items'][0]['name']} is {when}",
            f"{o['kind'].capitalize()} · {o['booking_id']}" + (f" · {o['time_window']}" if o.get("time_window") else " · all day"),
            ("Your window is today - head over when it opens" if d <= 0 else "You can move the time if plans change") if movable else "Show your confirmation at the entrance",
            nice_date(o["date"]), (0.95 if d <= 1 else 0.7) - n * 0.05,
            {"label": "View booking", "screen": "booking", "args": {"booking_id": o["booking_id"]}}))
    cart = p.get("cart")
    if cart and cart.get("items"):
        offer = cart.get("offer")
        left = days_until(offer["expires"]) if offer else None
        valid = offer and left is not None and left >= 0
        low = [i["name"] for i in cart["items"] if inv["stock"].get(i["exp_id"], 0) <= 3]
        total = cart["subtotal_usd"] * (1 - offer["pct_off"] / 100) if valid else cart["subtotal_usd"]
        cards.append(_card(
            "cart", "cart", "Still deciding on these?" if not valid else f"{offer['pct_off']}% off the extras in your cart",
            " + ".join(i["name"] for i in cart["items"][:2]) + (f" +{len(cart['items']) - 2} more" if len(cart["items"]) > 2 else ""),
            " · ".join(x for x in [f"Code {offer['code']} ends in {left} day{'s' if left != 1 else ''}" if valid else None,
                                    f"Only a few places left for {low[0]}" if low else None] if x) or "Saved for your visit",
            money(round(total, 2)), s.get("cart_recovery_propensity", 0.5) * (1.15 if valid else 0.9),
            {"label": "Book them", "tool": "checkout_cart", "args": {"apply_offer": True}}))
    options = []
    for o in upcoming:
        for i in o["items"]:
            st = change_status(p, o, i)
            if st["eligible"]:
                options.append({"booking_id": o["booking_id"], "exp_id": i["exp_id"], "name": i["name"], "price": i["price"],
                                "date": o["date"], "time_window": o.get("time_window"), "days_left": st["days_left"], "cutoff_days": st["cutoff_days"],
                                "swap_options": [{"exp_id": x["exp_id"], "name": x["name"], "price": x["price"],
                                                  "places_left": inv["stock"].get(x["exp_id"], 0)} for x in C.swap_options(i["exp_id"])]})
    if options:
        options.sort(key=lambda r: r["days_left"])
        soon = options[0]
        last = "today is the last day" if soon["days_left"] == 0 else f"{soon['days_left']} day{'s' if soon['days_left'] != 1 else ''} left"
        cards.append(_card(
            "change", "changes", "Plans changed? Swaps and refunds are free",
            f"{len(options)} booking{'s' if len(options) > 1 else ''} you can still swap or refund",
            f"{soon['name']}: {last} to change" + (f" · {p['loyalty']['tier']} members can change on the day" if soon["cutoff_days"] == 0 else ""),
            "Free", 0.32 + (0.2 if soon["days_left"] <= 1 else 0), {"label": "Change a booking", "screen": "change"},
            options=options, reasons=C.CHANGE_REASONS))
    owned = {i["exp_id"] for o in p["bookings"] for i in o["items"]} | {i["exp_id"] for i in (cart or {}).get("items", [])}
    likes = set(p["preferences"]["interests"])
    small = shortest_rider(p)
    for exp_id in [x for x in s.get("recommended_exp_ids", []) if x not in owned][:2]:
        prod = C.EXPERIENCE_BY_ID.get(exp_id)
        if not prod or (small and small["height_in"] < prod["min_height_in"]):
            continue
        match = sorted(likes & set(prod["tags"]))
        why = f"Because you like {' & '.join(match[:2])}" if match else "Popular with parties like yours"
        if small and prod["min_height_in"]:
            why += f" · {small['name']} is tall enough"
        cards.append(_card(
            "experience", f"experience-{exp_id}", prod["name"], prod["blurb"], why,
            f"~{prod['typical_wait_min']} min wait" if prod["typical_wait_min"] else f"${prod['price']}",
            s.get("upsell_propensity", 0.4) * 0.7, {"label": "Ask about it", "ask": f"Tell me about {prod['name']}"}))
    if p["loyalty"]["points"] >= 500:
        cards.append(_card("reward", "reward", f"You have {p['loyalty']['points']:,} points", f"{p['loyalty']['tier']} · {p['loyalty']['program']}",
                           f"That's {money(p['loyalty']['points'] // 500 * 5)} off dining and shops", p["loyalty"]["tier"], 0.25,
                           {"label": "How points work", "ask": "How does Lumina Club work?"}))
    return cards


async def _lead(p: dict) -> list[dict]:
    from .actions import get_inventory

    s, lead, cards = p["ml_scores"], p["lead"], []
    inv, _ = await get_inventory()
    party_size = lead.get("party_size") or p["organization"]["members"]
    b = C.package_for_party(party_size)
    consult = p.get("planning_session")
    if consult:
        cards.append(_card("planning", "planning-booked", f"Planning session with {consult['advisor']}", f"{nice_date(consult['date'])} at {consult['time']} · {consult['channel']}",
                           consult["topic"], "Booked", 1.0, {"label": "What to bring", "ask": "How does a planning session work?"}))
    else:
        days: dict[str, list] = {}
        for sid, left in sorted(inv["slots"].items()):
            date, time = sid.split("T")
            if (days_until(date) or 0) >= 1:
                days.setdefault(date, []).append({"time": time, "open": left})
        cards.append(_card(
            "planning", "planning", "Book a free planning session",
            f"30 minutes with a {C.PARK['business_brand']} advisor - video, phone or at the park",
            f"For {p['organization']['name']}: {', '.join(lead.get('interest', [])[:2])}", "Free",
            s.get("lead_score", 0.5) * 1.2, {"label": "Pick a time", "screen": "planning"},
            slots=[{"date": d, "slots": sl} for d, sl in list(days.items())[:6]], topics=C.PLANNING_TOPICS, channels=C.PLANNING_CHANNELS))
    if not lead.get("party_size") or not lead.get("budget_band"):
        cards.append(_card("lead", "lead-details", "Get a tailored quote", "Tell us your party size, budget and timing",
                           "Takes a minute - we'll size the right package", "2 questions", s.get("lead_score", 0.5) * 1.05,
                           {"label": "Share details", "screen": "planning", "args": {"step": "details"}}))
    cards.append(_card(
        "experience", f"package-{b['code']}", b["name"], b["blurb"],
        f"Sized for about {party_size} guests from {p['organization']['name']}", f"${b['price_per_guest']:,}/guest · ~{money(b['price_per_guest'] * party_size)}",
        s.get("fit", 0.5) * 0.9, {"label": "Ask about it", "ask": f"What's included in {b['name']}?"}))
    for exp_id in p["browsing"]["viewed_exp_ids"][:2]:
        prod = C.EXPERIENCE_BY_ID.get(exp_id)
        if prod:
            cards.append(_card("experience", f"experience-{exp_id}", prod["name"], prod["blurb"], "You looked at this recently", f"${prod['price']}",
                               0.3, {"label": "Ask about it", "ask": f"Tell me about the {prod['name']}"}))
    return cards


async def _employee(p: dict) -> list[dict]:
    it, hr, cards = p["it"], p["hr"], []
    pend = sorted([t for t in p["onboarding"]["tasks"] if t["status"] != "complete"], key=lambda t: t["due_date"])
    if pend:
        nxt = pend[0]
        d = days_until(nxt["due_date"]) or 0
        due = "overdue" if d < 0 else "due today" if d == 0 else "due tomorrow" if d == 1 else f"due in {d} days"
        cards.append(_card("onboarding", "onboarding", f"{len(pend)} onboarding task{'s' if len(pend) > 1 else ''} left",
                           f"Next: {nxt['title']} · {due}", "Sign and submit right here, even offline", f"{len(p['onboarding']['tasks']) - len(pend)}/{len(p['onboarding']['tasks'])} done",
                           1.0 + (0.3 if d <= 2 else 0), {"label": "Open my checklist", "screen": "onboarding"}))
    b = hr["benefits"]
    if not b["enrolled"]:
        d = days_until(b.get("enrollment_deadline"))
        if d is not None and d >= 0:
            cards.append(_card("benefits", "benefits", "Choose your benefits", f"Enrollment closes in {d} day{'s' if d != 1 else ''} ({nice_date(b['enrollment_deadline'])})",
                               "Medical, dental, vision and 401(k) - coverage starts the 1st of next month", "Required",
                               0.9 + (0.3 if d <= 7 else 0), {"label": "Compare plans", "screen": "benefits"}))
    for t in it["open_tickets"][:2]:
        cards.append(_card("ticket", f"ticket-{t['ticket_id']}", f"{t['ticket_id']} · {t['status'].replace('_', ' ')}", t["summary"],
                           f"With the {t.get('queue') or C.IT_CATEGORY_BY_ID.get(t['category'], {}).get('queue', 'IT')} team since {nice_date(t['opened_at'])}",
                           t["priority"], 0.75, {"label": "Ask for an update", "ask": f"Any update on ticket {t['ticket_id']}?"}))
    if it["password_expires_in_days"] <= 10:
        d = it["password_expires_in_days"]
        cards.append(_card("it", "password", f"Your password expires in {d} day{'s' if d != 1 else ''}", "Reset it now in one tap",
                           "Avoid getting locked out before your shift", "CrewPass", 0.8 if d <= 5 else 0.6,
                           {"label": "Reset password", "tool": "reset_password", "args": {"system": "sso"}}))
    if "network" not in it["systems_access"]:
        cards.append(_card("it", "network", "Handheld won't connect backstage?", "Backstage Wi-Fi is a standard request, granted straight away",
                           "You don't have Backstage Wi-Fi access yet", "IT", 0.45,
                           {"label": "Request Wi-Fi access", "tool": "request_system_access",
                            "args": {"system": "network", "justification": "Handheld needs Backstage Wi-Fi on shift"}}))
    shift = (hr.get("schedule") or {}).get("next_shift")
    if shift:
        d = days_until(shift["date"]) or 0
        when = "today" if d <= 0 else "tomorrow" if d == 1 else nice_date(shift["date"])
        cards.append(_card("shift", "shift", f"Next shift: {when}, {shift['start']}-{shift['end']}", f"{shift['role']} · {shift['location']}",
                           f"{hr['schedule'].get('shifts_this_week', 0)} shifts this week · swaps need 24 hours' notice", "Shift", 0.85 if d <= 1 else 0.5,
                           {"label": "Shift swap rules", "ask": "How do I swap a shift?"}))
    cards.append(_card("timeoff", "pto", f"{hr['pto']['balance_days']:g} days of paid time off", f"Accruing {hr['pto'].get('accrual_per_month', C.PTO_ACCRUAL_PER_MONTH):g} days a month",
                       f"Requests go to {p['employment']['manager']}", "PTO", 0.3, {"label": "Request time off", "screen": "timeoff"}))
    return cards


async def compute_feed(profile: dict) -> list[dict]:
    if not profile.get("consent", {}).get("personalization_opt_in", True):
        return []
    cards = await {"guest": _guest, "lead": _lead, "employee": _employee}[profile["audience"]](profile)
    cards.sort(key=lambda c: c["score"], reverse=True)
    for i, c in enumerate(cards):
        c["rank"] = i + 1
        c["score"] = round(c["score"], 3)
    return cards


async def refresh_feed(user_id: str) -> dict | None:
    profile = await store.get("profiles", profile_id(user_id))
    if not profile:
        return None
    doc = {
        "type": "feed", "user_id": user_id, "audience": profile["audience"], "cards": await compute_feed(profile),
        "model_version": profile["ml_scores"].get("model_version"), "segment": profile["ml_scores"].get("segment"),
        "export_date": profile.get("export_date"), "profile_rev": profile.get("rev", 0),
        "generated_at": now_iso(), "channels": [user_channel(user_id)],
    }
    await store.upsert("feed", feed_id(user_id), doc)
    return doc
