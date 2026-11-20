"""End-to-end checks of the demo backend in memory mode (no Couchbase, no AOM):
the four use cases a park-wide chatbot covers, one persona each.

    cd backend && pytest -q
"""
import time
import uuid

# The `client` fixture (memory store, generated mock export, no AOM) lives in conftest.py.
MAYA, DANIEL, SOFIA = ("5510101", "Chen"), ("5520202", "Okafor"), ("5530303", "Alvarez")


def login(client, account, last):
    r = client.post("/api/auth/login", json={"account_id": account, "last_name": last})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user_id"]


def pull(client, h):
    docs = client.get("/api/sync/pull", headers=h).json()["docs"]
    return {(d["collection"], d["id"]): d["doc"] for d in docs}


def ask(client, h, message):
    r = client.post("/api/chat", headers=h, json={"message": message})
    assert r.status_code == 200, r.text
    return r.json()


def push(client, h, uid, tool, args):
    rid = f"req::{uid}::{uuid.uuid4().hex[:12]}"
    r = client.post("/api/sync/push", headers=h, json={"docs": [{"collection": "requests", "id": rid, "doc": {
        "type": "request", "user_id": uid, "tool": tool, "args": args, "created_at": "2026-11-13T15:00:00Z"}}]})
    assert r.status_code == 200, r.text
    for _ in range(40):
        d = pull(client, h).get(("requests", rid))
        if d and d["status"] not in ("pending", "processing"):
            return d
        time.sleep(0.1)
    raise AssertionError("request never processed")


def test_personas_and_login(client):
    ps = client.get("/api/demo/personas").json()["personas"]
    assert [p["user_id"] for p in ps] == ["G00000101", "L00000201", "E00000301"]
    assert [p["audience"] for p in ps] == ["guest", "lead", "employee"]
    assert client.post("/api/auth/login", json={"account_id": "5510101", "last_name": "Nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"account_id": "5530303", "last_name": "alvarez"}).json()
    assert r["channels"] == ["user:E00000301", "catalog", "employees"]


def test_feed_is_personalized_per_audience(client):
    h, uid = login(client, *MAYA)
    docs = pull(client, h)
    kinds = [c["kind"] for c in docs[("feed", f"feed::{uid}")]["cards"]]
    assert {"booking", "cart", "change"} <= set(kinds)
    assert ("catalog", "catalog::v1") in docs
    h, uid = login(client, *DANIEL)
    kinds = [c["kind"] for c in pull(client, h)[("feed", f"feed::{uid}")]["cards"]]
    assert kinds[0] == "planning" and "lead" in kinds
    h, uid = login(client, *SOFIA)
    cards = pull(client, h)[("feed", f"feed::{uid}")]["cards"]
    assert cards[0]["kind"] == "onboarding" and {"benefits", "ticket"} <= {c["kind"] for c in cards}


def test_handbook_only_reaches_crew_members(client):
    """Sync Gateway's `employees` channel, mirrored by the preview sync."""
    h, _ = login(client, *MAYA)
    assert ("catalog", "handbook::v1") not in pull(client, h)
    h, _ = login(client, *DANIEL)
    assert ("catalog", "handbook::v1") not in pull(client, h)
    h, _ = login(client, *SOFIA)
    hb = pull(client, h)[("catalog", "handbook::v1")]
    assert hb["channels"] == ["employees"] and any("password" in f["q"].lower() for f in hb["faq"])


# ---- Guest Support & FAQs ---------------------------------------------------
def test_support_faqs_are_shared_answers(client):
    h, _ = login(client, *MAYA)
    for q, expect in (("What are the park hours?", "9am-10pm"), ("How tall do you have to be for Starfall Coaster?", "48 inches"),
                      ("What is your refund policy?", "day before"), ("How much are tickets?", "$119"),
                      ("Where do I park?", "$30"), ("How long is the wait for Comet Run?", "55 minutes")):
        a = ask(client, h, q)
        assert a["personal"] is False and expect in a["reply"], (q, a["reply"])
        assert a["area"] in ("support", "commerce") and not a.get("restricted")
    a = ask(client, h, "How many points do I have?")
    assert a["intent"] == "account" and a["personal"] and "4,180" in a["reply"]


# ---- Plans & Bookings -------------------------------------------------------
def test_todays_plan_uses_the_context_cache(client):
    h, uid = login(client, *MAYA)
    a = ask(client, h, "What's my next ride?")
    assert a["intent"] == "booking" and a["area"] == "commerce" and a["personal"] and a["context"]["status"] == "miss"
    assert "LP-881042" in a["reply"] and "3:00pm-4:00pm" in a["reply"]
    # the party is part of the answer: Leo is 46 inches, Starfall Coaster needs 48
    assert "Leo is 46" in a["reply"] and any(x.get("screen") == "change" for x in a["actions"])
    # the context was built with the person's current CDP record
    assert a["context"]["sor"]["system"] == "cdp" and "Cart abandoners" in a["context"]["sor"]["segments"]
    assert any(x.get("screen") == "booking" for x in a["actions"])
    b = ask(client, h, "When is our dinner reservation?")
    assert b["context"]["status"] == "hit" and "Harbor Lights Grill" in b["reply"]
    assert ("context_cache", f"ctx::{uid}::booking") in pull(client, h)
    plan = ask(client, h, "What's on my plan?")
    assert "Starfall Coaster" in plan["reply"] and "Harbor Lights Grill" in plan["reply"]


def test_reschedule_refund_and_invalidation(client):
    h, uid = login(client, *MAYA)
    a = ask(client, h, "Can I get a refund on my dinner booking?")
    assert a["intent"] == "change" and "$40" in a["reply"]
    assert ("context_cache", f"ctx::{uid}::change") in pull(client, h)
    r = push(client, h, uid, "reschedule_booking", {"booking_id": "LP-880517", "date": "2026-11-14", "window": "7:30pm-8:30pm"})
    assert r["status"] == "confirmed", r
    # only days of the visit, and only real windows
    assert push(client, h, uid, "reschedule_booking", {"booking_id": "LP-880517", "date": "2026-11-25"})["status"] == "failed"
    assert push(client, h, uid, "reschedule_booking", {"booking_id": "LP-880517", "date": "2026-11-14", "window": "midnight"})["status"] == "failed"
    r = push(client, h, uid, "change_booking", {"booking_id": "LP-880517", "exp_id": "DIN-HARBOR", "reason": "Change of plans"})
    assert r["status"] == "confirmed" and "$40" in r["summary"], r
    docs = pull(client, h)
    p = docs[("profiles", f"profile::{uid}")]
    dinner = next(o for o in p["bookings"] if o["booking_id"] == "LP-880517")
    assert dinner["time_window"] == "7:30pm-8:30pm" and dinner["status"] == "cancelled"
    assert p["changes"][0]["exp_id"] == "DIN-HARBOR" and p["rev"] >= 2
    assert ("context_cache", f"ctx::{uid}::change") not in docs       # invalidated by the change
    assert {i["kind"] for i in docs[("activity", f"activity::{uid}")]["items"]} >= {"reschedule", "refund"}
    # the same booking can't be refunded twice, and yesterday's ride is past the cut-off
    assert push(client, h, uid, "change_booking", {"booking_id": "LP-880517", "exp_id": "DIN-HARBOR", "reason": "again"})["status"] == "failed"
    late = push(client, h, uid, "change_booking", {"booking_id": "LP-874233", "exp_id": "RID-RAPIDS", "reason": "It was closed"})
    assert late["status"] == "failed" and "completed" in late["summary"]
    # ... which is what the courtesy credit is for
    sr = ask(client, h, "Emberwood Rapids broke down while we were in line and nobody helped us")
    assert sr["intent"] == "service_recovery" and sr["actions"][0]["tool"] == "issue_courtesy_credit"
    assert sr["actions"][0]["args"]["booking_id"] == "LP-874233"


def test_swap_and_cart_recovery(client):
    h, uid = login(client, *MAYA)
    a = ask(client, h, "Is the offer on my cart still valid?")
    assert a["intent"] == "cart" and "GLOW10" in a["reply"] and a["actions"][0]["tool"] == "checkout_cart"
    s = ask(client, h, "Can I swap the Starfall Coaster pass? Leo isn't tall enough")
    swap = next(x for x in s["actions"] if x.get("args", {}).get("resolution") == "swap")
    assert swap["args"]["swap_exp_id"] == "RID-COMET"
    r = push(client, h, uid, "change_booking", {"booking_id": "LP-881042", "exp_id": "RID-STARFALL", "reason": "Someone isn't tall enough",
                                                "resolution": "swap", "swap_exp_id": "RID-COMET"})
    assert r["status"] == "confirmed" and "Comet Run" in r["summary"], r
    r = push(client, h, uid, "checkout_cart", {"apply_offer": True})
    assert r["status"] == "confirmed" and r["charge_usd"] == 120.6, r
    p = pull(client, h)[("profiles", f"profile::{uid}")]
    ride = next(o for o in p["bookings"] if o["booking_id"] == "LP-881042")
    assert ride["items"][0]["exp_id"] == "RID-COMET" and ride["status"] == "upcoming" and ride["total_usd"] == 18
    assert p["cart"] is None and p["bookings"][0]["status"] == "upcoming" and p["bookings"][0]["offer_code"] == "GLOW10"
    assert p["bookings"][0]["date"] == "2026-11-14"
    assert push(client, h, uid, "checkout_cart", {})["status"] == "failed"


# ---- Trips & Groups ---------------------------------------------------------
def test_trip_details_qualification_and_planning_session(client):
    h, uid = login(client, *DANIEL)
    a = ask(client, h, "We're bringing our band to the park - where do I start?")
    assert a["intent"] == "sales" and a["area"] == "sales" and a["personal"]
    assert "Brightwater High School Band" in a["reply"] and a["context"]["sor"]["system"] == "crm"
    labels = [x["label"] for x in a["actions"]]
    assert any("quote" in x.lower() for x in labels) and any(x.get("tool") == "book_planning_session" for x in a["actions"])
    r = push(client, h, uid, "submit_trip_details", {"party_size": 24, "budget_band": "$2k-$10k", "timeline": "1-3 months"})
    assert r["status"] == "confirmed" and "Group Getaway" in r["summary"], r
    p = pull(client, h)[("profiles", f"profile::{uid}")]
    assert p["lead"]["status"] == "qualified" and p["lead"]["owner"] and p["lead"]["score"] >= 0.5 and p["lead"]["party_size"] == 24
    book = next(x for x in ask(client, h, "Can I book a planning session this week?")["actions"] if x.get("tool") == "book_planning_session")
    r = push(client, h, uid, "book_planning_session", book["args"])
    assert r["status"] == "confirmed", r
    docs = pull(client, h)
    assert docs[("profiles", f"profile::{uid}")]["lead"]["status"] == "session_booked"
    assert docs[("feed", f"feed::{uid}")]["cards"][0]["card_id"] == "planning-booked"
    # experience discovery is personal too
    d = ask(client, h, "Can you recommend a coaster for me?")
    assert d["intent"] == "experience" and "Group Getaway" in d["reply"]


# ---- Internal Operations & HR ------------------------------------------------------
def test_it_help_desk(client):
    h, uid = login(client, *SOFIA)
    g = ask(client, h, "How do I reset my password?")
    assert g["intent"] == "it" and g["area"] == "workplace" and g["personal"] is False and "authenticator" in g["reply"]
    a = ask(client, h, "I forgot my password and I'm locked out")
    assert a["personal"] and a["context"]["sor"]["system"] == "hris" and a["actions"][0]["tool"] == "reset_password"
    assert push(client, h, uid, "reset_password", {"system": "sso"})["status"] == "confirmed"
    v = ask(client, h, "My handheld keeps dropping off the Wi-Fi")
    assert "INC-204871" in v["reply"] and v["actions"][0]["tool"] == "request_system_access"
    assert push(client, h, uid, "request_system_access", {"system": "network", "justification": "Handheld on shift"})["status"] == "confirmed"
    t = push(client, h, uid, "create_it_ticket", {"category": "hardware", "summary": "Handheld battery drains in an hour", "priority": "high"})
    assert t["status"] == "confirmed" and "Device Depot" in t["summary"]
    p = pull(client, h)[("profiles", f"profile::{uid}")]
    assert "network" in p["it"]["systems_access"] and len(p["it"]["open_tickets"]) == 2 and p["it"]["password_expires_in_days"] == 90
    # privileged systems go through the approval-tier tool, and need safety training first
    assert "privileged" in push(client, h, uid, "request_system_access", {"system": "ride-ops", "justification": "Covering the Rapids tower"})["summary"]
    assert "safety & evacuation training" in push(client, h, uid, "request_privileged_access",
                                                 {"system": "ride-ops", "justification": "Covering the Rapids tower"})["summary"]


def test_hr_benefits_time_off_and_onboarding(client):
    h, uid = login(client, *SOFIA)
    b = ask(client, h, "Am I enrolled in benefits?")
    assert b["intent"] == "hr" and "Dec 7" in b["reply"] and b["actions"][0]["screen"] == "benefits"
    assert "Core PPO" in ask(client, h, "What medical plans are there?")["reply"]
    o = ask(client, h, "What's left on my onboarding checklist?")
    sh = ask(client, h, "When is my next shift?")
    assert sh["intent"] == "hr" and "9:00am" in sh["reply"] and "Lantern Harbor Guest Relations" in sh["reply"]
    assert "24 hours" in ask(client, h, "How do I swap a shift?")["reply"]
    assert o["intent"] == "onboarding" and "5 onboarding tasks" in o["reply"] and "Direct deposit" in o["reply"]
    dd = push(client, h, uid, "complete_onboarding_task", {"task_id": "direct-deposit"})
    assert dd["status"] == "confirmed", dd
    assert push(client, h, uid, "complete_onboarding_task", {"task_id": "handbook"})["status"] == "failed"      # needs a signature
    assert push(client, h, uid, "complete_onboarding_task", {"task_id": "handbook", "acknowledgment": "Sofia Alvarez"})["status"] == "confirmed"
    e = push(client, h, uid, "enroll_benefits", {"medical": "MED-HSA", "dental": "DEN-BASE", "k401_pct": 4})
    assert e["status"] == "confirmed" and "$28" in e["summary"], e
    t = push(client, h, uid, "request_time_off", {"start_date": "2026-11-27", "end_date": "2026-11-27"})
    assert t["status"] == "submitted" and "Marcus Reid" in t["summary"]
    assert push(client, h, uid, "request_time_off", {"start_date": "2026-12-01", "end_date": "2026-12-12"})["status"] == "failed"
    p = pull(client, h)[("profiles", f"profile::{uid}")]
    assert p["hr"]["benefits"]["enrolled"] and p["hr"]["pto"]["balance_days"] == 2.0
    assert sum(t["status"] != "complete" for t in p["onboarding"]["tasks"]) == 2


# ---- one chatbot, three audiences: the guard rails ------------------------------------
def test_internal_questions_are_refused_for_guests_and_trip_planners(client):
    for who in (MAYA, DANIEL):
        h, _ = login(client, *who)
        for q in ("How do I reset my CrewPass password?", "What medical plans do employees get?", "When do I enroll in benefits?"):
            a = ask(client, h, q)
            assert a["restricted"] and a["area"] == "workplace" and "crew members" in a["reply"], q
            assert not a["sources"] and not a["actions"] and a["llm"]["status"] == "skipped"
        # ... but everyday park questions that happen to share a word with the handbook are not
        for q in ("How much are tickets?", "Is there Wi-Fi in the park?", "We're planning a vacation in July", "Is there a medical station?"):
            assert not ask(client, h, q).get("restricted"), q


def test_tools_check_the_audience(client):
    h, uid = login(client, *MAYA)
    r = push(client, h, uid, "create_it_ticket", {"category": "network", "summary": "let me in please"})
    assert r["status"] == "failed" and "crew members" in r["summary"]
    assert push(client, h, uid, "get_bookings", {})["status"] == "failed"          # read tools can't be requested from a phone
    h, uid = login(client, *SOFIA)
    assert "guests" in push(client, h, uid, "checkout_cart", {})["summary"]


def test_push_rejects_other_users(client):
    h, uid = login(client, *DANIEL)
    r = client.post("/api/sync/push", headers=h, json={"docs": [{"collection": "requests", "id": "req::G00000101::x",
                                                                 "doc": {"user_id": "G00000101", "tool": "checkout_cart"}}]})
    assert r.status_code == 403


def test_personas_are_pinned_to_the_export_date(client):
    import datetime as dt
    day = dt.date(2026, 11, 13)
    h, uid = login(client, *SOFIA)
    p = pull(client, h)[("profiles", f"profile::{uid}")]
    assert (day - dt.date.fromisoformat(p["employment"]["start_date"])).days == 6
