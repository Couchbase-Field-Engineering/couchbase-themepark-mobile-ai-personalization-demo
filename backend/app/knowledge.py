"""Knowledge Base documents published to AOM by the nightly loader.

Three kinds:

* **Park Guide** - what any guest or trip planner may be told: park hours,
  tickets, rides and height limits, bookings and refunds, dining, accessibility
  and Lumina Groups & Events.
  Contains no personal data, so answers grounded only in it are safe to share
  across users through AOM's LLM cache. The guest-facing RAG application
  (`parkchat-assistant`) is scoped to this document.
* **Crew Handbook** - IT help desk, shifts, benefits, time off, pay and onboarding.
  For crew members only: the workplace RAG application (`parkchat-workplace`)
  is scoped to it, and its phone copy travels on the `employees` channel.
* **User profile** - one per person, rendered from that night's export as
  plain prose. The assistant retrieves it with a `document_id`-scoped search,
  so an answer can only ever be grounded in the asker's *own* profile.

`FAQ` is the bundled copy of the CMS entries, served when no CMS endpoint is
configured (sources.py). Entries are also synced to the phone - guest
entries inside `catalog::v1`, crew entries inside `handbook::v1` - so the app
can answer the common questions offline from Couchbase Lite.
"""
from __future__ import annotations

from . import catalog as C
from .docs import days_until

_CO = C.PARK

FAQ = [
    # ---- Guest Support & FAQs ------------------------------------------------
    {"section": "Hours", "audience": "all", "intent": "general",
     "q": "What are the park hours?",
     "a": f"Lumina Park is open {_CO['park_hours']}. Lantern Harbor opens at 8:30am for breakfast and shopping, and guests of the "
          "three resort hotels can enter at 8:30am every day. Aurora Nights Spectacular starts at 9pm; rides close with the park. "
          "Each land's hours are listed in the app.",
     "keywords": ["park hours", "hours", "open", "close", "closing", "what time", "early entry", "opening"]},
    {"section": "Tickets", "audience": "all", "intent": "general",
     "q": "How much are tickets?",
     "a": "A 1-Day Ticket is $119 for ages 10 and up and $109 for ages 3-9; children under 3 are free. A 3-Day Park Hopper is $289. "
          "Lumina Club annual passes start at $449 (Silver), $649 (Gold) and $899 (Platinum). Tickets are dated: buy for the day you "
          "plan to visit.",
     "keywords": ["ticket", "tickets", "ticket price", "how much", "admission", "annual pass", "price", "pricing", "cost"]},
    {"section": "Rides", "audience": "all", "intent": "experience",
     "q": "What are the height requirements?",
     "a": "Starfall Coaster needs riders to be 48 inches tall, Comet Run 44, Emberwood Rapids 42, Tidewater Plunge and Lantern Flight "
          "40, and Canopy Expedition 36. Glowworm Grotto, Clockwork Carousel, Gearwheel Whirl and Summit Skyway have no minimum. "
          "Every ride with a height limit offers rider swap, so adults can take turns without queuing twice.",
     "keywords": ["height", "tall", "how tall", "height requirement", "tall enough", "rider swap", "inches"]},
    {"section": "Rides", "audience": "all", "intent": "experience",
     "q": "How long are the wait times?",
     "a": "Live wait times are on every ride's page in the app. On a typical day Starfall Coaster runs about 75 minutes, Lantern "
          "Flight 65, Emberwood Rapids 60 and Comet Run 55; the Commons rides are usually under 20. Waits are shortest in the first "
          "hour and during the 9pm spectacular.",
     "keywords": ["wait", "wait time", "wait times", "queue", "line", "how long", "busy", "crowded"]},
    {"section": "Rides", "audience": "all", "intent": "booking",
     "q": "How does an express pass work?",
     "a": "An express pass books a one-hour return window on one ride for your whole party: come back any time in the window and "
          "use the express entrance. Passes are $8 to $22 depending on the ride, and you can hold one for each ride at a time. "
          "The All-Day Express Pass ($89) covers one express entry on every ride with no windows to book.",
     "keywords": ["express pass", "express", "skip the line", "return window", "return time", "fast lane", "book a ride"]},
    {"section": "Bookings", "audience": "all", "intent": "change",
     "q": "What is your refund policy?",
     "a": "Express passes, dining reservations and show seats can be swapped or refunded free until the day before your visit - "
          "and on the day itself for Lumina Club Gold and Platinum members. Start a change in ParkChat; refunds go back to the "
          "original payment method within 3 business days. Park tickets can be moved to another date but not refunded.",
     "keywords": ["refund policy", "refund", "refunds", "cancel", "cancellation", "money back", "change policy", "refundable"]},
    {"section": "Bookings", "audience": "all", "intent": "change",
     "q": "Can I swap a booking for something else?",
     "a": "Yes. Until your change cut-off you can swap an express pass for another ride, or a dining reservation for another "
          "restaurant, on the same day while places last. You pay or get back any price difference, and your confirmation code "
          "stays the same.",
     "keywords": ["swap", "switch", "exchange", "different ride", "another ride", "change my booking", "trade"]},
    {"section": "Bookings", "audience": "all", "intent": "service_recovery",
     "q": "What if a ride closes during my express window?",
     "a": "If a ride is down during your window, your pass automatically works on any other ride for the rest of the day, or you "
          "can have it refunded. If the closure cost you a reservation or a big part of your day, a Guest Relations lead can "
          "approve a park credit as a courtesy.",
     "keywords": ["ride closed", "closed", "broke down", "breakdown", "down", "closure", "rained out", "weather"]},
    {"section": "Bookings", "audience": "all", "intent": "booking",
     "q": "How do I see or move my bookings?",
     "a": "Ask ParkChat \"what's my plan today?\" or open Activity: every booking shows its day, time window and confirmation "
          "code. You can move an express pass, dining reservation or show seat to another window or another day of your visit "
          "any time before the window opens.",
     "keywords": ["my bookings", "my plan", "itinerary", "move", "reschedule", "change time", "confirmation"]},
    {"section": "Bookings", "audience": "all", "intent": "cart",
     "q": "Why did I get an offer for the things in my cart?",
     "a": "If you leave extras in your cart for a couple of days we hold the places and may send a one-time offer code. The code "
          "applies to what's in the cart, expires on the date shown, and can't be combined with other promotions.",
     "keywords": ["cart", "offer code", "promo code", "coupon", "glow10", "checkout", "basket"]},
    {"section": "Dining", "audience": "all", "intent": "general",
     "q": "How does mobile food ordering work?",
     "a": "Order from any quick-service counter in the app, choose a pickup window and tap \"I'm here\" when you arrive; your food "
          "is ready in about five minutes at the mobile pickup shelf. Table-service restaurants take reservations up to 60 days "
          "ahead with a deposit that comes off the bill. Every kitchen can prepare allergy-friendly meals - tell your server.",
     "keywords": ["mobile order", "food", "order food", "eat", "restaurant", "dining", "allergy", "allergies", "lunch", "pickup"]},
    {"section": "Getting here", "audience": "all", "intent": "general",
     "q": "Where do I park and how much is it?",
     "a": "Parking is $30 a day in the Firefly and Lantern structures, free for Platinum members and resort hotel guests. Trams run "
          "to the Lantern Harbor gate every five minutes from an hour before opening until an hour after closing.",
     "keywords": ["parking", "park my car", "where do i park", "where can i park", "where to park", "tram", "garage", "drive", "directions", "shuttle"]},
    {"section": "Accessibility", "audience": "all", "intent": "general",
     "q": "What accessibility services do you offer?",
     "a": "Guests who can't wait in a standard queue can register for the Access Pass at Guest Relations in Lantern Harbor or by "
          "video chat before the visit: it gives a return time equal to the current wait. Wheelchairs ($15) and electric scooters "
          "($60) are rented at the main gate, and every show has captioning devices and sign-language performances on Saturdays.",
     "keywords": ["accessibility", "accessible", "wheelchair", "disability", "access pass", "scooter", "sensory", "captioning"]},
    {"section": "Guest services", "audience": "all", "intent": "general",
     "q": "I lost something - what do I do?",
     "a": "Report it in ParkChat or at Guest Relations in Lantern Harbor with where and when you last had it. Found items are "
          "logged within an hour; we hold them for 30 days and ship them home free. For a lost child, tell the nearest crew "
          "member straight away - every one of them is trained for it.",
     "keywords": ["lost", "lost and found", "found", "missing", "left my", "lost child"]},
    {"section": "Guest services", "audience": "all", "intent": "general",
     "q": "Can I bring a stroller, food or a bag?",
     "a": "Strollers up to 31 by 52 inches are welcome, and day rentals are $18 at the Harbor gate. You can bring snacks and water "
          "bottles but not glass or coolers larger than a six-pack. Lockers ($12 a day) are at the main gate and beside both "
          "water rides.",
     "keywords": ["stroller", "bring", "bag", "backpack", "locker", "cooler", "outside food", "water bottle"]},
    {"section": "Account", "audience": "all", "intent": "account",
     "q": "How does Lumina Club work?",
     "a": "You earn 1 point per dollar on bookings, dining and shops; 500 points is $5 off. Annual passholders move up by tier: "
          "Silver, Gold and Platinum. Gold adds same-day changes and 10% off dining; Platinum adds free parking and early entry. "
          "Your tickets, points and park credit are under Profile.",
     "keywords": ["lumina club", "points", "loyalty", "gold", "platinum", "silver", "tier", "member", "rewards", "account"]},
    {"section": "Support", "audience": "all", "intent": "general",
     "q": "How do I reach a person?",
     "a": f"Say \"talk to a person\" in ParkChat and we'll hand your conversation, with its context, to Guest Relations - "
          f"{_CO['support_hours']} - or call {_CO['support_phone']}. In the park, Guest Relations is just inside the Lantern Harbor gate.",
     "keywords": ["human", "agent", "person", "representative", "call", "phone number", "speak to someone", "talk to", "guest relations"]},
    # ---- Trips & Groups -----------------------------------------------------
    {"section": "Lumina Groups & Events", "audience": "all", "intent": "sales",
     "q": "What is Lumina Groups & Events?",
     "a": "Lumina Groups & Events plans visits for parties of any size: families and friends, schools and teams, company days. "
          "Three packages - Day Adventure, Group Getaway and Grand Gathering - are priced per guest with tickets included, with "
          "group rates from 10 guests and private event spaces from 50.",
     "keywords": ["groups", "group visit", "group rate", "group", "school", "team", "company", "event", "reunion", "celebration", "field trip"]},
    {"section": "Lumina Groups & Events", "audience": "all", "intent": "sales",
     "q": "How does a planning session work?",
     "a": "A planning session is a free 30-minute call with a Groups & Events advisor by video, phone or at the park. Bring your "
          "party size, dates and a rough budget; you leave with a recommended package, a per-guest price and a day plan. There's "
          "no obligation.",
     "keywords": ["planning session", "planning", "appointment", "book a call", "advisor", "meeting", "talk to sales", "specialist"]},
    {"section": "Lumina Groups & Events", "audience": "all", "intent": "sales",
     "q": "Do you offer group pricing?",
     "a": "Yes. Day Adventure is $149 a guest for up to 9 guests, Group Getaway $129 a guest for 10-49 with a free chaperone "
          "ticket per ten, and Grand Gathering $115 a guest from 50 with a dedicated event coordinator. School bands and choirs "
          "can add a performance slot on the Aurora Plaza stage. Quotes are valid for 30 days.",
     "keywords": ["group pricing", "group rate", "quote", "per guest", "pricing", "discount", "package", "performance", "band", "choir", "chaperone"]},
    # ---- Crew IT & HR (Crew Handbook) ------------------------------------------
    {"section": "IT help desk", "audience": "employee", "intent": "it",
     "q": "How do I reset my password?",
     "a": "Ask ParkChat to reset it: you'll approve a prompt in your authenticator app and choose a new password within 15 minutes. "
          "CrewPass passwords expire every 90 days and need 14 characters. If you haven't set up multi-factor sign-in yet, open an "
          "Account & access ticket and the Identity team will verify you.",
     "keywords": ["password", "reset", "locked out", "forgot", "expired", "sign in", "login", "log in", "crewpass"]},
    {"section": "IT help desk", "audience": "employee", "intent": "it",
     "q": "How do I get my handheld on Backstage Wi-Fi?",
     "a": "Join the LuminaCrew network and sign in with CrewPass. Backstage Wi-Fi access is a standard request that's granted "
          "straight away. If your handheld keeps dropping off, forget the network and rejoin once, then open a Wi-Fi & radios "
          "ticket with where it happens - the Park Network team answers within 4 business hours.",
     "keywords": ["wi-fi", "wifi", "backstage wi-fi", "network", "handheld", "dropping", "connect", "radio"]},
    {"section": "IT help desk", "audience": "employee", "intent": "it",
     "q": "How do I get access to a system?",
     "a": "Standard systems - Backstage Wi-Fi and point of sale - are granted as soon as you ask. Systems that touch ride "
          "controls, cash or guest data (the Ride Operations console, Cash Office & Finance, the Guest Recovery console, the guest "
          "data workspace) are privileged: you give a business justification, your request is held for approval, and you need "
          "your park safety & evacuation training complete first.",
     "keywords": ["access", "permission", "console", "ride operations", "guest recovery", "finance", "request access", "system access"]},
    {"section": "IT help desk", "audience": "employee", "intent": "it",
     "q": "My handheld is broken - what do I do?",
     "a": "Open a Handhelds & devices ticket with what's wrong and swap it at the Device Depot in the Crew Center: spares are "
          "charged and ready at the start of every shift. A cracked screen or a battery that won't last a shift counts. Card "
          "readers and registers go to Park Systems, who answer within 2 business hours.",
     "keywords": ["handheld", "hardware", "broken", "screen", "battery", "tablet", "device", "scanner", "card reader", "register"]},
    {"section": "IT help desk", "audience": "employee", "intent": "it",
     "q": "How do I install an app?",
     "a": "Approved apps - scheduling, radio, ride checklists - install in one tap from Crew Apps. Anything else needs an Apps & "
          "software ticket with the app name and why you need it; licensed tools also need your lead's cost-centre approval.",
     "keywords": ["software", "install", "application", "app", "license", "crew apps"]},
    {"section": "Shifts", "audience": "employee", "intent": "hr",
     "q": "How do I swap a shift?",
     "a": "Post the shift on the shift board in the Crew Portal at least 24 hours before it starts. Anyone trained for the same "
          "post can pick it up, and the trade is final once your lead approves it. Schedules are published two weeks ahead on "
          "Thursdays; a shift with less than 24 hours' notice needs your lead directly.",
     "keywords": ["shift", "swap a shift", "swap", "trade", "roster", "schedule", "cover", "pick up a shift"]},
    {"section": "Shifts", "audience": "employee", "intent": "hr",
     "q": "What do I do if I'm running late or can't make a shift?",
     "a": "Call the attendance line at least two hours before your start time and tell your lead. Three late arrivals in a "
          "rolling 90 days start a conversation with your lead; a no-call no-show goes to your People Partner.",
     "keywords": ["late", "call out", "can't make", "attendance", "absent", "no-show"]},
    {"section": "Benefits", "audience": "employee", "intent": "hr",
     "q": "When do I enroll in benefits?",
     "a": "New hires enroll within 30 days of their start date, and coverage starts the first of the following month. After that, "
          "changes wait for annual enrollment in November unless you have a qualifying life event such as marriage or a new child.",
     "keywords": ["enroll", "enrollment", "benefits", "open enrollment", "coverage start", "sign up for benefits"]},
    {"section": "Benefits", "audience": "employee", "intent": "hr",
     "q": "What medical plans are there?",
     "a": "Three: Core PPO ($48 per paycheck, $1,500 deductible, $25 office visits), HSA Advantage ($22 per paycheck, $3,200 "
          "deductible, with a $1,000 park HSA contribution) and Plus PPO ($92 per paycheck, $500 deductible, $15 office visits). "
          "Dental Base is $6 and Dental Plus $14 per paycheck; Vision Standard is $3.",
     "keywords": ["medical", "health insurance", "ppo", "hsa", "dental", "vision", "plan", "deductible", "insurance"]},
    {"section": "Benefits", "audience": "employee", "intent": "hr",
     "q": "Does Lumina Park match 401(k) contributions?",
     "a": f"Yes - dollar for dollar up to {C.K401_MATCH_PCT}% of pay, from your first paycheck, vested immediately. New hires are "
          "enrolled at 3% unless they choose another rate.",
     "keywords": ["401k", "401(k)", "retirement", "match", "pension", "contribution"]},
    {"section": "Time off", "audience": "employee", "intent": "hr",
     "q": "How much paid time off do I get?",
     "a": f"You start with 3 days and accrue {C.PTO_ACCRUAL_PER_MONTH:g} days a month (18 a year), rising to 2 days a month after "
          "three years. Request time off in ParkChat; it goes to your lead for approval. Up to 5 unused days carry over. Peak "
          "weeks - spring break, July and the last two weeks of December - are approved by seniority.",
     "keywords": ["pto", "time off", "leave", "days off", "day off", "accrue", "sick"]},
    {"section": "Time off", "audience": "employee", "intent": "hr",
     "q": "What is the parental leave policy?",
     "a": "16 weeks fully paid for birthing parents and 8 weeks for all other new parents, after 90 days of service, taken within a "
          "year of the birth or placement. Tell your People Partner at least 30 days ahead where you can.",
     "keywords": ["parental", "maternity", "paternity", "family leave", "baby", "adoption"]},
    {"section": "Pay", "audience": "employee", "intent": "hr",
     "q": "When do I get paid?",
     "a": "Every other Friday. Your first paycheck is a paper check unless direct deposit is set up before the payroll cut-off, the "
          "Monday of pay week. Pay stubs and tax forms are in the Crew Portal.",
     "keywords": ["paid", "payday", "paycheck", "pay stub", "payroll", "direct deposit", "salary", "w-2"]},
    {"section": "Onboarding", "audience": "employee", "intent": "onboarding",
     "q": "What paperwork do I need to finish as a new hire?",
     "a": "Eight items: Form I-9 (documents within three days), Form W-4 and direct deposit in your first week, the Crew Handbook "
          "and Code of Conduct to sign by day 10, park safety & evacuation training and an emergency contact by day 14, and "
          "benefits enrollment within 30 days. ParkChat lists what's left and you can sign most of them right here.",
     "keywords": ["onboarding", "paperwork", "new hire", "i-9", "i9", "w-4", "w4", "handbook", "first week", "forms", "orientation"]},
    {"section": "Onboarding", "audience": "employee", "intent": "onboarding",
     "q": "What documents do I need for the I-9?",
     "a": "Either one List A document (a US passport or permanent resident card) or one each from List B and List C (for example a "
          "driver's licence plus a Social Security card or birth certificate). Show the originals to your lead or a People "
          "Partner within three days of your start date.",
     "keywords": ["i-9", "i9", "documents", "passport", "eligibility", "identification"]},
    {"section": "Perks", "audience": "employee", "intent": "hr",
     "q": "What is the crew member discount?",
     "a": "Free park entry for you from your first day, 30% off dining and shops, and four complimentary guest tickets every "
          "quarter after 90 days. Complimentary tickets are blocked out on the park's peak days and can't be sold.",
     "keywords": ["employee discount", "crew discount", "discount", "perk", "complimentary tickets", "free tickets", "staff discount"]},
]
GUEST_FAQ = [f for f in FAQ if f["audience"] == "all"]
EMPLOYEE_FAQ = [f for f in FAQ if f["audience"] == "employee"]


def faq_public(entries: list[dict]) -> list[dict]:
    return [{"q": f["q"], "a": f["a"], "keywords": f["keywords"], "section": f.get("section"), "intent": f.get("intent")} for f in entries]


def _faq_md(entries: list[dict]) -> list[str]:
    lines, section = [], None
    for f in entries:
        if f.get("section") != section:
            section = f.get("section")
            lines += ["", f"## {section}", ""]
        lines += [f"### {f['q']}", f["a"], ""]
    return lines


def help_center_markdown(export_date: str, entries: list[dict] | None = None) -> str:
    entries = [e for e in (entries or FAQ) if e.get("audience", "all") == "all"]
    lines = [f"# {_CO['name']} Guide", f"Published {export_date}. Public information for guests and trip planners.", ""]
    lines += _faq_md(entries)
    lines += ["", "## Lands and hours", ""]
    for s in C.LANDS:
        lines.append(f"- {s['name']} ({s['city']}): {s['hours']}.")
    lines += ["", "## Rides, shows, dining and extras", ""]
    for p in C.EXPERIENCES:
        lines.append(f"- {p['name']} ({p['exp_id']}), {p['category']} in {C.LAND_BY_ID[p['land']]['name']}: "
                     + (f"minimum height {p['min_height_in']} inches, " if p["min_height_in"] else "no height requirement, " if p["category"] == "Rides" else "")
                     + (f"typical wait {p['typical_wait_min']} minutes, express pass ${p['price']}. " if p["typical_wait_min"] else f"${p['price']} to book. ")
                     + f"{p['blurb']} Good for {', '.join(p['tags'])}.")
    lines += ["", f"## {_CO['business_brand']} packages", ""]
    for b in C.PACKAGES:
        lines.append(f"- {b['name']} ({b['code']}): {b['party_size'][0]}-{b['party_size'][1]} guests at ${b['price_per_guest']:,} per guest. "
                     f"Includes {', '.join(b['includes'])}. {b['blurb']}")
    return "\n".join(lines)


def handbook_markdown(export_date: str, entries: list[dict] | None = None) -> str:
    entries = [e for e in (entries or FAQ) if e.get("audience") == "employee"]
    lines = [f"# {_CO['name']} Crew Handbook", f"Published {export_date}. Internal - for {_CO['name']} crew members only.", ""]
    lines += _faq_md(entries)
    lines += ["", "## IT help desk queues", ""]
    for c in C.IT_CATEGORIES:
        lines.append(f"- {c['name']} ({c['id']}): {c['queue']} team, first response within {c['sla_hours']} business hours.")
    lines += ["", "## Systems and access", ""]
    for s in C.SYSTEMS:
        lines.append(f"- {s['name']} ({s['id']}): " + ("given to everyone on day one." if s["default"] else
                                                      "privileged - needs a justification and approval." if s["approval"] else "standard request, granted straight away."))
    lines += ["", "## Benefit plans", ""]
    for kind, plans in C.BENEFIT_PLANS.items():
        for p in plans:
            lines.append(f"- {p['name']} ({p['id']}, {kind}): ${p['employee_cost_per_paycheck']} per paycheck. {p['blurb']}")
    lines += ["", "## New-hire onboarding checklist", ""]
    for t in C.ONBOARDING_TASKS:
        lines.append(f"- {t['title']} (due day {t['due_day']}): {t['detail']}")
    return "\n".join(lines)


def user_profile_markdown(p: dict) -> str:
    s = p.get("ml_scores", {})
    head = [f"# User profile {p['user_id']}: {p['first_name']} {p['last_name']} ({C.AUDIENCES[p['audience']]})",
            f"Source: ParkChat nightly export {p.get('export_date')}, scores by {s.get('model_version')}"
            + (f"; segments: {', '.join(a['name'] for a in p['segments'])}" if p.get("segments") else "") + ".", ""]
    prefs = p.get("preferences", {})
    names = lambda ids: ", ".join(C.EXPERIENCE_BY_ID[x]["name"] for x in ids if x in C.EXPERIENCE_BY_ID)  # noqa: E731
    if p["audience"] == "guest":
        bookings = "; ".join(
            f"booking {o['booking_id']} - {', '.join(i['name'] for i in o['items'])} ({o['kind']}) - ${o['total_usd']:,.2f}, {o['status']}, "
            f"{o.get('date')}" + (f" {o['time_window']}" if o.get("time_window") else "") + (f", confirmation {o['confirmation']}" if o["status"] == "upcoming" else "")
            for o in p.get("bookings", [])) or "no bookings"
        cart = p.get("cart")
        cart_txt = ("empty" if not cart else f"{', '.join(i['name'] for i in cart['items'])} (${cart['subtotal_usd']:,}), left "
                    f"{cart['abandoned_days']} days ago" + (f"; offer {cart['offer']['code']} for {cart['offer']['pct_off']}% off until {cart['offer']['expires']}" if cart.get("offer") else ""))
        v = p.get("visit") or {}
        party = "; ".join(f"{m['name']}, {m['age']}" + (f", {m['height_in']} inches tall" if m.get("height_in") else "") for m in v.get("party", []))
        cutoff = C.change_cutoff_days(p["loyalty"]["tier"])
        body = [
            "## Account and loyalty",
            f"{p['first_name']} lives in {p['home_city']} and is a {p['loyalty']['program']} {p['loyalty']['tier']} member with "
            f"{p['loyalty']['points']:,} points, a member since {p['loyalty']['member_since']}. Bookings can be changed free until "
            f"{'the day itself' if cutoff == 0 else 'the day before'}. Lifetime value ${p['history']['lifetime_value_usd']:,.0f} over "
            f"{p['history']['bookings_count']} bookings; {p['history']['changes_count']} past changes. Favorite land: "
            f"{(C.LAND_BY_ID.get(prefs.get('favorite_land')) or {}).get('name', 'none')}.",
            "", "## Visit",
            f"Visiting {v.get('start')} to {v.get('end')} on a {v.get('ticket')}" + (f", staying at {v['hotel']}" if v.get("hotel") else "")
            + f". Party: {party or 'one adult'}.",
            "", "## Bookings", f"Bookings: {bookings}.",
            "", "## Cart", f"Cart: {cart_txt}.",
            "", "## Preferences", f"Interests: {', '.join(prefs.get('interests', []))}. Prefers {prefs.get('communication_channel')} messages.",
            "", "## Personalization signals",
            f"Segment: {s.get('segment')}. Next best action: {s.get('next_best_action')}. Cart recovery propensity "
            f"{s.get('cart_recovery_propensity')}, upsell propensity {s.get('upsell_propensity')}, churn risk {s.get('churn_risk')}, "
            f"price sensitivity {s.get('price_sensitivity')}. Recommended: {names(s.get('recommended_exp_ids', []))}.",
        ]
    elif p["audience"] == "lead":
        c, lead = p["organization"], p["lead"]
        session = p.get("planning_session")
        body = [
            "## Group",
            f"{p['first_name']} is {lead.get('role', 'the contact')} for {c['name']}, a {c['group_type'].lower()} of {c['members']} "
            f"people from {c['city']}.",
            "", "## Lead",
            f"Source: {lead['source']}. Status: {lead['status']}. Lead score {lead['score']}. Party size: {lead.get('party_size') or 'not captured'}. "
            f"Budget: {lead.get('budget_band') or 'not captured'}. Timeline: {lead.get('timeline') or 'not captured'}. Interested in: "
            f"{', '.join(lead.get('interest', []))}. Advisor: {lead.get('owner') or 'unassigned'}.",
            "", "## Browsing",
            f"Viewed {names(p['browsing']['viewed_exp_ids'])}; "
            f"{p['browsing']['sessions_30d']} sessions in 30 days, last visit {p['browsing']['last_visit']}.",
            "", "## Planning session",
            (f"Booked {session['date']} at {session['time']} ({session['channel']}) with {session['advisor']} on {session['topic']}." if session else "None booked."),
            "", "## Personalization signals",
            f"Segment: {s.get('segment')}. Next best action: {s.get('next_best_action')}. Fit {s.get('fit')}. Recommended package: "
            f"{C.PACKAGE_BY_CODE[s['recommended_package']]['name'] if s.get('recommended_package') in C.PACKAGE_BY_CODE else 'n/a'}.",
        ]
    else:
        e, it, hr = p["employment"], p["it"], p["hr"]
        pend = [t for t in p["onboarding"]["tasks"] if t["status"] != "complete"]
        b = hr["benefits"]
        sh = (hr.get("schedule") or {}).get("next_shift")
        body = [
            "## Employment",
            f"{p['first_name']} is a {e['title']} in {e['department']}, posted at {e['location']}, reporting to {e['manager']}. "
            f"Started {e['start_date']} ({e['employment_type']}).",
            "", "## Schedule",
            (f"Next shift {sh['date']} from {sh['start']} to {sh['end']} at {sh['location']} as {sh['role']}; "
             f"{hr['schedule'].get('shifts_this_week', 0)} shifts this week." if sh else "No shifts scheduled."),
            "", "## Onboarding",
            f"Status: {p['onboarding']['status']}. " + ("Still to do: " + "; ".join(f"{t['title']} (due {t['due_date']})" for t in pend) + "." if pend else "All tasks complete."),
            "", "## IT",
            f"Devices: {', '.join(d['model'] + ' (' + d['os'] + ', ' + d['asset_tag'] + ')' for d in it['devices'])}. Access: "
            f"{', '.join(C.SYSTEM_BY_ID[x]['name'] for x in it['systems_access'] if x in C.SYSTEM_BY_ID)}. Password expires in "
            f"{it['password_expires_in_days']} days; multi-factor sign-in {'set up' if it['mfa_enrolled'] else 'not set up'}. Open tickets: "
            + ("; ".join(f"{t['ticket_id']} {t['summary']} ({t['status']})" for t in it["open_tickets"]) or "none") + ".",
            "", "## Benefits and time off",
            (f"Enrolled: medical {b.get('medical')}, dental {b.get('dental') or 'waived'}, vision {b.get('vision') or 'waived'}; 401(k) {b.get('k401_pct')}%."
             if b["enrolled"] else f"Not enrolled yet; the new-hire window closes {b.get('enrollment_deadline')} ({days_until(b.get('enrollment_deadline'))} days).")
            + f" Paid time off balance {hr['pto']['balance_days']:g} days. Paid {hr['pay']['frequency']}; next pay date {hr['pay']['next_pay_date']}.",
            "", "## Personalization signals", f"Segment: {s.get('segment')}. Next best action: {s.get('next_best_action')}.",
        ]
    return "\n".join(head + body)


