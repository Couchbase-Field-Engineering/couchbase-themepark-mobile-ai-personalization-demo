#!/usr/bin/env python3
"""Generate the mock nightly export ParkChat is loaded from.

Lumina Park (the demo park, see backend/app/catalog.py) keeps the people a
park-wide chatbot serves in three systems of record:

* the **ticketing and reservations platform / CDP** - guests, their visit and
  party, bookings, carts, Lumina Club status, audience segments and
  propensity scores
* the **group sales CRM** - trip planners, their group, lead status and score
* the **HRIS, scheduling and ITSM** - crew members, their shifts, onboarding
  tasks, benefits, time off, devices, system access and help-desk tickets

Every night a scheduled export lands one JSON Lines dataset with a row per
person (`audience` says which kind) in a time-stamped folder. This script
writes that layout:

    data/parkchat-export/exportTime=20261113/
        part-00000-<uuid>-c000.json      # JSON Lines, one person per line
        part-00001-<uuid>-c000.json
        _SUCCESS
        _manifest.json                   # row/byte counts per audience, schema + model versions

Fully deterministic for a given --seed and --export-date, and standard
library only (runs anywhere Python 3.9+ does). Default target is 24 MiB.

    python datagen/generate_mock_export.py                 # today
    python datagen/generate_mock_export.py --export-date 2026-11-13 --target-mb 24
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
from app import catalog as C  # noqa: E402

SCHEMA_VERSION = "parkchat_person_v2"
MODEL_VERSION = "parkchat-propensity-v3"
PERSONAS = ["G00000101", "L00000201", "E00000301"]

FIRST = ["Ava", "Noah", "Mia", "Liam", "Zoe", "Ethan", "Nora", "Lucas", "Ivy", "Owen", "Leah", "Caleb", "Ruby", "Isaac",
         "Elena", "Mateo", "Amara", "Kofi", "Yuki", "Arjun", "Fatima", "Diego", "Hana", "Tariq", "Ingrid", "Rafael",
         "Chloe", "Jamal", "Mei", "Andre", "Sana", "Victor", "Lena", "Omar", "Tessa", "Reza", "Nia", "Paulo", "Greta", "Dev"]
LAST = ["Nguyen", "Patel", "Garcia", "Johnson", "Kim", "Hernandez", "Brown", "Singh", "Martinez", "Cohen", "Okonkwo",
        "Larsen", "Tanaka", "Ali", "Rossi", "Murphy", "Santos", "Haddad", "Novak", "Park", "Mensah", "Dubois", "Ivanov",
        "Castillo", "Reyes", "Walker", "Fischer", "Banerjee", "Costa", "Holt", "Yamamoto", "Abbasi", "Lindgren", "Okoye"]
CITIES = {
    "Northeast": ["Brooklyn, NY", "Boston, MA", "Philadelphia, PA", "Jersey City, NJ", "Providence, RI"],
    "Southeast": ["Atlanta, GA", "Miami, FL", "Charlotte, NC", "Nashville, TN", "Tampa, FL"],
    "Midwest": ["Chicago, IL", "Minneapolis, MN", "Columbus, OH", "Madison, WI", "Detroit, MI"],
    "Southwest": ["Austin, TX", "Phoenix, AZ", "Dallas, TX", "Denver, CO", "Albuquerque, NM"],
    "West": ["Seattle, WA", "San Francisco, CA", "Portland, OR", "San Diego, CA", "Oakland, CA"],
}
ORG_A = ["Brightwater", "Northgate", "Cedar Ridge", "Bluebird", "Ironwood", "Halcyon", "Lakeview", "Tidewater",
         "Meridian", "Copperline", "Fieldstone", "Maple Row", "Quarry Hill", "Wren Valley", "Harborview", "Skylark"]
ORG_B = {"Family reunion": "Family Reunion", "School band or choir": "High School Band", "Youth sports team": "Youth Soccer Club",
         "Company outing": "Team Day", "Scout troop": "Scout Troop", "Birthday celebration": "Birthday Party", "Graduation trip": "Class Trip",
         "Faith community": "Youth Group", "Travel club": "Travel Club", "Dance studio": "Dance Academy"}
ROLES = {"Family reunion": "Family organizer", "School band or choir": "Band Director", "Youth sports team": "Team Parent",
         "Company outing": "People & Culture Manager", "Scout troop": "Troop Leader", "Birthday celebration": "Parent",
         "Graduation trip": "Class Advisor", "Faith community": "Youth Leader", "Travel club": "Club Organizer", "Dance studio": "Studio Owner"}
KIDS = ["Leo", "Maya", "Sam", "Ella", "Max", "Aria", "Finn", "Luna", "Theo", "Ruby", "Eli", "Nora"]
HOTELS = ["Lantern Harbor Hotel", "Summit Lodge", "Emberwood Cabins", None, None, None]
TICKETS = {1: "1-Day Ticket", 2: "2-Day Ticket", 3: "3-Day Park Hopper", 4: "4-Day Park Hopper"}
SEGMENTS = {
    "seg-cart-abandoners": "Cart abandoners",
    "seg-gold-plus": "Gold & Platinum members",
    "seg-thrill-seekers": "Thrill seekers",
    "seg-at-risk": "Lapsing visitors",
    "seg-first-visit": "First-time visitors",
    "seg-frequent-changers": "Frequent rebookers",
    "seg-in-park": "In the park today",
    "seg-high-intent-groups": "High-intent group planners",
    "seg-researching-groups": "Group planners - researching",
    "seg-new-hires": "New hires (first 30 days)",
    "seg-people-managers": "People managers",
    "seg-attractions-crew": "Attractions crew",
}


def clamp(x: float, lo=0.01, hi=0.99) -> float:
    return round(max(lo, min(hi, x)), 2)


def seg(*ids) -> list[dict]:
    return [{"id": i, "name": SEGMENTS[i], "status": "realized"} for i in ids if i]


class Gen:
    def __init__(self, export_date: dt.date, seed: int):
        self.r = random.Random(seed)
        self.today = export_date
        self.n = {"guest": 1000, "lead": 1000, "employee": 1000}
        self.account = 6_000_000
        self.order_no = 700_000
        self.ticket_no = 200_000

    # ---- ids -------------------------------------------------------------
    def uid(self, audience: str) -> str:
        self.n[audience] += 1
        return f"{audience[0].upper()}{self.n[audience]:08d}"

    def next_account(self) -> str:
        self.account += self.r.randint(1, 9)
        return str(self.account)

    def next_order(self) -> str:
        self.order_no += self.r.randint(1, 40)
        return f"LP-{self.order_no}"

    def payday(self, later: bool = False) -> str:
        """The next Friday (we pay every other Friday)."""
        d = self.today + dt.timedelta(days=1)
        while d.weekday() != 4:
            d += dt.timedelta(days=1)
        return (d + dt.timedelta(days=7 if later else 0)).isoformat()

    def day(self, offset: int) -> str:
        return (self.today + dt.timedelta(days=offset)).isoformat()

    def person(self):
        return self.r.choice(FIRST), self.r.choice(LAST)

    def base(self, audience, user_id, account_id, first, last, city, region, group):
        return {
            "user_id": user_id, "audience": audience, "group_code": group, "account_id": account_id,
            "export_date": self.today.isoformat(), "schema_version": SCHEMA_VERSION,
            "first_name": first, "last_name": last,
            "email": f"{first}.{last}".lower().replace(" ", "") + ("@luminapark.example" if audience == "employee" else "@example.com"),
            "home_city": city, "region": region,
            "consent": {"personalization_opt_in": True, "marketing_opt_in": self.r.random() < 0.7},
        }

    # ---- guests ------------------------------------------------------------
    def booking(self, offset: int, exp_ids: list[str] | None = None, status: str | None = None, party: int = 2) -> dict:
        """One booking `offset` days from today (negative = already happened):
        an express pass, a dining reservation, a show or an add-on."""
        r = self.r
        exp_ids = exp_ids or [r.choice(C.EXPERIENCES)["exp_id"]]
        items = [{"exp_id": s, "name": C.EXPERIENCE_BY_ID[s]["name"], "qty": 1, "price": C.EXPERIENCE_BY_ID[s]["price"]} for s in exp_ids]
        total = sum(i["price"] * i["qty"] for i in items)
        if not status:
            status = "upcoming" if offset >= 0 else ("cancelled" if r.random() < 0.03 else "completed")
        kind = C.kind_of(exp_ids[0])
        booked = offset - r.randint(1, 21)
        events = [{"at": self.day(booked), "text": "Booked in the app"}]
        if status == "completed":
            events.append({"at": self.day(offset), "text": "Checked in"})
        if status == "cancelled":
            events.append({"at": self.day(booked + 1), "text": "Cancelled and refunded"})
        return {
            "booking_id": self.next_order(), "booked_at": self.day(booked), "status": status, "kind": kind, "items": items,
            "subtotal_usd": total, "total_usd": total, "party_size": party,
            "confirmation": f"LUM{r.randint(10**5, 10**6 - 1)}", "date": self.day(offset),
            "time_window": r.choice(C.TIME_WINDOWS) if kind in C.MOVABLE_KINDS else None,
            "completed_at": self.day(offset) if status == "completed" else None, "events": events,
        }

    def cart(self, exp_ids: list[str], abandoned_days: int, pct: int = 10) -> dict:
        items = [{"exp_id": s, "name": C.EXPERIENCE_BY_ID[s]["name"], "qty": 1, "price": C.EXPERIENCE_BY_ID[s]["price"]} for s in exp_ids]
        sub = sum(i["price"] for i in items)
        return {"updated_at": self.day(-abandoned_days), "items": items, "subtotal_usd": sub, "abandoned_days": abandoned_days,
                "offer": {"code": f"GLOW{pct}", "pct_off": pct, "expires": self.day(4)} if abandoned_days >= 2 else None}

    def visit(self, last: str) -> dict:
        """The trip the guest is on or has coming up, and who is in the party
        (children's heights decide which rides they can go on)."""
        r = self.r
        start, days = r.randint(-1, 21), r.choice([1, 1, 2, 3, 4])
        party = [{"name": "You", "age": r.randint(24, 62), "height_in": None}]
        for _ in range(r.choice([0, 0, 1, 1, 2])):
            party.append({"name": r.choice(FIRST), "age": r.randint(24, 70), "height_in": None})
        for _ in range(r.choice([0, 0, 1, 2, 3])):
            age = r.randint(3, 13)
            party.append({"name": r.choice(KIDS), "age": age, "height_in": 34 + age * 2 + r.randint(-2, 2)})
        return {"start": self.day(start), "end": self.day(start + days - 1), "ticket": TICKETS[days], "hotel": r.choice(HOTELS) if days > 1 else None,
                "party": party, "reservation_name": last}

    def guest(self, overrides: dict | None = None) -> dict:
        r = self.r
        first, last = self.person()
        region = r.choice(C.REGIONS)
        city = r.choice(CITIES[region])
        bookings_count = r.choice([0, 1, 1, 2, 2, 3, 4, 6, 9, 14])
        tier = "Platinum" if bookings_count >= 14 else "Gold" if bookings_count >= 6 else "Silver" if bookings_count >= 3 else "Member"
        visit = self.visit(last)
        v0 = (dt.date.fromisoformat(visit["start"]) - self.today).days
        v1 = (dt.date.fromisoformat(visit["end"]) - self.today).days
        interests = r.sample(C.INTERESTS, r.randint(2, 4))
        pool = [p["exp_id"] for p in C.EXPERIENCES if set(p["tags"]) & set(interests)] or [p["exp_id"] for p in C.EXPERIENCES]
        offsets = sorted({r.choice([r.randint(-120, -2), r.randint(v0, v1)]) for _ in range(min(bookings_count, r.choice([1, 2, 2, 3])))})
        bookings = [self.booking(a, [r.choice(pool)], party=len(visit["party"])) for a in offsets]
        has_cart = r.random() < 0.28
        booked = {i["exp_id"] for b in bookings for i in b["items"]}
        extras = [x for x in pool if x not in booked] or pool
        cart = self.cart(r.sample(extras, min(len(extras), r.choice([1, 2]))), r.randint(0, 9)) if has_cart else None
        spend = sum(o["total_usd"] for o in bookings)
        ltv = round(spend + max(0, bookings_count - len(bookings)) * r.uniform(90, 420), 2)
        changes_count = r.choice([0, 0, 0, 1, 1, 2, 4]) if bookings_count else 0
        churn = clamp(0.5 - bookings_count * 0.03 + r.uniform(-0.2, 0.25))
        cart_prop = clamp(0.35 + (0.25 if cart else 0) + r.uniform(-0.2, 0.25))
        in_park = v0 <= 0 <= v1
        row = self.base("guest", self.uid("guest"), self.next_account(), first, last, city, region, C.REGION_GROUP[region])
        row.update({
            "phone": f"+1 555 01{r.randint(10, 99)} {r.randint(1000, 9999)}",
            "identity": {"crm_id": f"CRM-{r.randint(10**6, 10**7 - 1)}", "namespace": "guestId", "source": "ticketing"},
            "loyalty": {"program": C.PARK["loyalty_program"], "tier": tier, "points": bookings_count * r.randint(120, 480),
                        "member_since": self.day(-r.randint(40, 2400))},
            "preferences": {"interests": interests, "communication_channel": r.choice(["email", "sms", "app"]),
                            "favorite_land": r.choice(C.LANDS)["id"]},
            "visit": visit,
            "bookings": bookings, "cart": cart, "changes": [], "credits": [],
            "history": {"lifetime_value_usd": ltv, "bookings_count": max(bookings_count, len(bookings)), "visits_count": 1 + bookings_count // 2,
                        "avg_booking_usd": round(ltv / max(bookings_count, len(bookings), 1), 2), "changes_count": changes_count},
            "segments": seg("seg-cart-abandoners" if cart and cart["abandoned_days"] >= 2 else None,
                            "seg-gold-plus" if tier in ("Gold", "Platinum") else None,
                            "seg-thrill-seekers" if "thrill" in interests else None,
                            "seg-at-risk" if churn >= 0.6 else None,
                            "seg-first-visit" if bookings_count <= 1 else None,
                            "seg-frequent-changers" if changes_count >= 2 else None,
                            "seg-in-park" if in_park else None),
            "ml_scores": {"model_version": MODEL_VERSION, "segment": ("Loyal passholder" if tier in ("Gold", "Platinum") else "Occasional visitor" if bookings_count else "First-time visitor"),
                          "next_best_action": ("recover_cart" if cart and cart["abandoned_days"] >= 2 else "show_plan" if any(o["status"] == "upcoming" for o in bookings) else "recommend_experiences"),
                          "churn_risk": churn, "cart_recovery_propensity": cart_prop,
                          "upsell_propensity": clamp(0.3 + bookings_count * 0.03 + r.uniform(-0.15, 0.3)),
                          "price_sensitivity": clamp(r.uniform(0.15, 0.9)),
                          "recommended_exp_ids": r.sample(pool, min(len(pool), 3))},
        })
        if overrides:
            deep_update(row, overrides)
        return row

    # ---- trip planners ---------------------------------------------------------
    def lead(self, overrides: dict | None = None) -> dict:
        r = self.r
        first, last = self.person()
        region = r.choice(C.REGIONS)
        city = r.choice(CITIES[region])
        members = r.choice([4, 6, 8, 9, 12, 18, 24, 28, 40, 55, 80, 120, 260, 600])
        group = "TRIP-FAM" if members < 10 else "TRIP-GRP"
        status = r.choice(["new", "new", "new", "qualified", "qualified", "session_booked"])
        qualified = status != "new"
        party_size = max(1, int(members * r.uniform(0.6, 1.0))) if qualified else None
        score = clamp(0.3 + (0.2 if qualified else 0) + (0.15 if members >= 10 else 0) + r.uniform(-0.15, 0.25))
        row = self.base("lead", self.uid("lead"), self.next_account(), first, last, city, region, group)
        gtype = r.choice(C.GROUP_TYPES[:1] + C.GROUP_TYPES[5:6]) if members < 10 else r.choice(C.GROUP_TYPES)
        row.update({
            "phone": f"+1 555 01{r.randint(10, 99)} {r.randint(1000, 9999)}" if qualified else None,
            "identity": {"crm_id": f"LEAD-{r.randint(10**6, 10**7 - 1)}", "namespace": "leadId", "source": "crm"},
            "organization": {"name": f"{last if members < 10 else r.choice(ORG_A)} {ORG_B[gtype]}", "group_type": gtype, "members": members,
                             "size_band": "1-9" if members < 10 else "10-49" if members < 50 else "50+", "city": city},
            "lead": {"source": r.choice(["Group visit guide download", "Ticket pricing page visit", "Travel expo", "Referral", "Park visit", "Webinar"]),
                     "status": status, "score": score, "party_size": party_size,
                     "budget_band": r.choice(C.BUDGET_BANDS) if qualified else None,
                     "timeline": r.choice(C.TIMELINES) if qualified else None,
                     "interest": r.sample(C.PLANNING_TOPICS, r.randint(1, 2)), "owner": r.choice(C.ADVISORS) if qualified else None,
                     "role": ROLES[gtype]},
            "browsing": {"viewed_exp_ids": r.sample([p["exp_id"] for p in C.EXPERIENCES], r.randint(2, 5)), "last_visit": self.day(-r.randint(0, 14)),
                         "sessions_30d": r.randint(1, 12)},
            "planning_session": ({"date": self.day(r.randint(2, 8)), "time": r.choice(C.PLANNING_TIMES), "topic": r.choice(C.PLANNING_TOPICS),
                                  "channel": "video", "advisor": r.choice(C.ADVISORS)} if status == "session_booked" else None),
            "preferences": {"interests": r.sample(C.INTERESTS, 3), "communication_channel": r.choice(["email", "phone"]), "favorite_land": None},
            "segments": seg("seg-high-intent-groups" if score >= 0.6 else "seg-researching-groups"),
            "ml_scores": {"model_version": MODEL_VERSION, "segment": "High-intent planner" if score >= 0.6 else "Researching",
                          "next_best_action": ("book_planning_session" if status != "session_booked" and score >= 0.5 else "capture_details" if not qualified else "nurture"),
                          "lead_score": score, "fit": clamp(0.4 + (0.2 if members >= 10 else 0) + r.uniform(-0.2, 0.3)),
                          "recommended_package": C.package_for_party(party_size or members)["code"]},
        })
        if overrides:
            deep_update(row, overrides)
        return row

    # ---- crew members -----------------------------------------------------------
    def onboarding(self, tenure: int, done: set[str] | None = None) -> dict:
        r = self.r
        tasks = []
        for t in C.ONBOARDING_TASKS:
            complete = (t["task_id"] in done) if done is not None else (tenure > t["due_day"] + 5 or r.random() < min(0.95, tenure / max(t["due_day"], 1) * 0.6))
            tasks.append({"task_id": t["task_id"], "title": t["title"], "kind": t["kind"], "due_date": self.day(t["due_day"] - tenure),
                          "status": "complete" if complete else "pending",
                          "completed_at": self.day(-max(0, tenure - min(t["due_day"], tenure))) if complete else None})
        return {"status": "complete" if all(t["status"] == "complete" for t in tasks) else "in_progress", "tasks": tasks}

    def employee(self, overrides: dict | None = None, onboarding_done: set[str] | None = None, tenure: int | None = None) -> dict:
        r = self.r
        first, last = self.person()
        dept = r.choice(list(C.DEPARTMENTS))
        d = C.DEPARTMENTS[dept]
        region = r.choice(C.REGIONS)
        city = r.choice(CITIES[region])
        tenure = tenure if tenure is not None else r.choice([2, 5, 9, 14, 21, 45, 90, 200, 400, 800, 1500, 2600])
        title = r.choice(d["titles"])
        device = r.choice(C.DEVICES[:2]) if dept != "Park Services & People" else r.choice(C.DEVICES)
        systems = [s["id"] for s in C.SYSTEMS if s["default"]]
        if dept in ("Food & Beverage", "Guest Relations"):
            systems.append("pos")
        if dept in ("Attractions", "Entertainment") or r.random() < 0.4:
            systems.append("network")
        tickets = []
        if r.random() < 0.3:
            cat = r.choice(C.IT_CATEGORIES)
            self.ticket_no += r.randint(1, 30)
            tickets.append({"ticket_id": f"INC-{self.ticket_no}", "category": cat["id"], "summary": r.choice([
                "Handheld battery drains before the end of a shift", "Can't join the morning briefing call from the break room",
                "Need the scheduling app on my tablet", "Shared mailbox isn't showing in Outlook",
                "Handheld drops off Backstage Wi-Fi near the Rapids queue", "Register 2 card reader is offline"]),
                "status": r.choice(["open", "in_progress"]), "priority": r.choice(C.IT_PRIORITIES),
                "opened_at": self.day(-r.randint(0, 6)), "queue": cat["queue"]})
        onboarding = self.onboarding(tenure, onboarding_done)
        enrolled = tenure > C.ENROLLMENT_WINDOW_DAYS or any(t["task_id"] == "benefits" and t["status"] == "complete" for t in onboarding["tasks"])
        accrued = round(min(tenure / 30.4 * C.PTO_ACCRUAL_PER_MONTH + 3, 30), 1)
        used = round(min(accrued, r.choice([0, 0, 1, 2, 3, 5, 8])), 1)
        post = r.choice(C.SHIFT_POSTS[dept])
        start, end = r.choice(C.SHIFT_TIMES)
        row = self.base("employee", self.uid("employee"), self.next_account(), first, last, city, region, d["group"])
        row.update({
            "identity": {"employee_number": f"LP{r.randint(10000, 99999)}", "namespace": "employeeId", "source": "hris"},
            "employment": {"title": title, "department": dept, "manager": " ".join(self.person()), "location": post,
                           "start_date": self.day(-tenure), "tenure_days": tenure,
                           "employment_type": "Full-time" if r.random() < 0.7 else "Part-time",
                           "is_manager": "Manager" in title or "Lead" in title},
            "it": {"devices": [{"asset_tag": f"{'LT' if device[2] == 'laptop' else 'HH'}-{r.randint(10000, 99999)}", "type": device[2], "model": device[0], "os": device[1]}],
                   "systems_access": systems, "open_tickets": tickets, "password_expires_in_days": r.randint(1, 85),
                   "mfa_enrolled": tenure > 2 or r.random() < 0.8, "access_requests": []},
            "hr": {"benefits": {"enrolled": enrolled, "medical": r.choice(["MED-CORE", "MED-HSA", "MED-PLUS"]) if enrolled else None,
                                "dental": r.choice(["DEN-BASE", "DEN-PLUS", None]) if enrolled else None,
                                "vision": r.choice(["VIS-STD", None]) if enrolled else None,
                                "k401_pct": r.choice([0, 3, 4, 6, 8]) if enrolled else 0,
                                "enrollment_deadline": self.day(C.ENROLLMENT_WINDOW_DAYS - tenure) if not enrolled else None},
                   "pto": {"balance_days": round(accrued - used, 1), "used_days": used, "accrual_per_month": C.PTO_ACCRUAL_PER_MONTH, "requests": []},
                   "pay": {"frequency": "biweekly", "next_pay_date": self.payday(r.random() < 0.5)},
                   "schedule": {"next_shift": {"date": self.day(r.randint(0, 3)), "start": start, "end": end, "location": post, "role": title},
                                "shifts_this_week": r.randint(3, 5)}},
            "onboarding": onboarding,
            "preferences": {"interests": r.sample(C.INTERESTS, 2), "communication_channel": "app", "favorite_land": None},
            "segments": seg("seg-new-hires" if tenure <= 30 else None, "seg-people-managers" if "Manager" in title or "Lead" in title else None,
                            "seg-attractions-crew" if dept == "Attractions" else None),
            "ml_scores": {"model_version": MODEL_VERSION, "segment": "New hire" if tenure <= 30 else "Tenured crew member",
                          "next_best_action": ("finish_onboarding" if onboarding["status"] != "complete" else "enroll_benefits" if not enrolled else "none")},
        })
        if overrides:
            deep_update(row, overrides)
        return row

    # ---- the three people the demo signs in as --------------------------------------
    def personas(self) -> list[dict]:
        saved = dict(self.n)
        self.n["guest"] = 100
        maya = self.guest({
            "account_id": "5510101", "first_name": "Maya", "last_name": "Chen", "email": "maya.chen@example.com",
            "home_city": "Brooklyn, NY", "region": "Northeast", "group_code": "GST-NE", "phone": "+1 555 0142 1101",
            "loyalty": {"tier": "Gold", "points": 4180, "member_since": self.day(-890)},
            "preferences": {"interests": ["thrill", "family", "foodie"], "communication_channel": "app", "favorite_land": "SUMMIT"},
            "history": {"lifetime_value_usd": 4326.0, "bookings_count": 9, "visits_count": 4, "avg_booking_usd": 480.67, "changes_count": 1},
            "segments": seg("seg-cart-abandoners", "seg-gold-plus", "seg-thrill-seekers", "seg-in-park"),
            "ml_scores": {"segment": "Loyal passholder", "next_best_action": "recover_cart", "churn_risk": 0.18,
                          "cart_recovery_propensity": 0.81, "upsell_propensity": 0.74, "price_sensitivity": 0.42,
                          "recommended_exp_ids": ["RID-COMET", "SHW-AURORA", "RID-EXPEDITION"]},
        })
        # Day two of a three-day stay with her partner and her son Leo, who is
        # 46 inches tall: tall enough for Comet Run, not for Starfall Coaster.
        maya["visit"] = {"start": self.day(-1), "end": self.day(1), "ticket": "3-Day Park Hopper", "hotel": "Lantern Harbor Hotel",
                         "reservation_name": "Chen",
                         "party": [{"name": "Maya", "age": 38, "height_in": None}, {"name": "Chris", "age": 40, "height_in": None},
                                   {"name": "Leo", "age": 7, "height_in": 46}]}
        o1 = self.booking(0, ["RID-STARFALL"], "upcoming", 3)
        o1.update({"booking_id": "LP-881042", "booked_at": self.day(-9), "time_window": "3:00pm-4:00pm", "confirmation": "LUM441028",
                   "events": [{"at": self.day(-9), "text": "Booked in the app"}, {"at": self.day(0), "text": "Reminder: your window opens at 3:00pm"}]})
        o2 = self.booking(1, ["DIN-HARBOR"], "upcoming", 3)
        o2.update({"booking_id": "LP-880517", "booked_at": self.day(-16), "time_window": "5:30pm-6:30pm", "confirmation": "LUM880517",
                   "events": [{"at": self.day(-16), "text": "Booked in the app"}]})
        o3 = self.booking(-1, ["RID-RAPIDS"], "completed", 3)
        o3.update({"booking_id": "LP-874233", "booked_at": self.day(-16), "time_window": "1:00pm-2:00pm", "confirmation": "LUM874233",
                   "events": [{"at": self.day(-16), "text": "Booked in the app"}, {"at": self.day(-1), "text": "Checked in"}]})
        maya["bookings"] = [o1, o2, o3]
        maya["cart"] = self.cart(["DIN-DESSERT", "EXT-MEMORY"], 3, 10)

        self.n["lead"] = 200
        daniel = self.lead({
            "account_id": "5520202", "first_name": "Daniel", "last_name": "Okafor", "email": "daniel@brightwaterband.example",
            "home_city": "Austin, TX", "region": "Southwest", "group_code": "TRIP-GRP", "phone": None,
            "organization": {"name": "Brightwater High School Band", "group_type": "School band or choir", "members": 28, "size_band": "10-49", "city": "Austin, TX"},
            "lead": {"source": "Group visit guide download", "status": "new", "score": 0.62, "party_size": None, "budget_band": None,
                     "timeline": None, "interest": ["School performance program", "Group visit"], "owner": None, "role": "Band Director"},
            "browsing": {"viewed_exp_ids": ["RID-COMET", "SHW-LEGENDS", "DIN-SMOKEHOUSE", "TUR-GEARS"], "last_visit": self.day(-1), "sessions_30d": 7},
            "planning_session": None,
            "preferences": {"interests": ["shows", "thrill", "family"], "communication_channel": "email", "favorite_land": "PLAZA"},
            "segments": seg("seg-high-intent-groups"),
            "ml_scores": {"segment": "High-intent planner", "next_best_action": "book_planning_session", "lead_score": 0.62, "fit": 0.78,
                          "recommended_package": "PK-GROUP"},
        })

        self.n["employee"] = 300
        self.ticket_no = 204_870
        sofia = self.employee({
            "account_id": "5530303", "first_name": "Sofia", "last_name": "Alvarez", "email": "sofia.alvarez@luminapark.example",
            "home_city": "Charlotte, NC", "region": "Southeast", "group_code": "EMP-GUEST",
            "identity": {"employee_number": "LP48213"},
            "employment": {"title": "Guest Relations Host", "department": "Guest Relations", "manager": "Marcus Reid",
                           "location": "Lantern Harbor Guest Relations", "employment_type": "Full-time", "is_manager": False},
            "it": {"devices": [{"asset_tag": "HH-48213", "type": "handheld", "model": "Trek H7 handheld", "os": "Android 14"}],
                   "systems_access": ["sso", "email", "hr-portal"], "password_expires_in_days": 5, "mfa_enrolled": True,
                   "open_tickets": [{"ticket_id": "INC-204871", "category": "network", "summary": "Handheld keeps dropping off Backstage Wi-Fi",
                                     "status": "open", "priority": "normal", "opened_at": self.day(-1), "queue": "Park Network"}]},
            "hr": {"benefits": {"enrolled": False, "medical": None, "dental": None, "vision": None, "k401_pct": 0,
                                "enrollment_deadline": self.day(24)},
                   "pto": {"balance_days": 3.0, "used_days": 0, "requests": []},
                   "pay": {"frequency": "biweekly", "next_pay_date": self.payday()},
                   "schedule": {"next_shift": {"date": self.day(1), "start": "9:00am", "end": "5:30pm",
                                               "location": "Lantern Harbor Guest Relations", "role": "Guest Relations Host"},
                                "shifts_this_week": 5}},
            "preferences": {"interests": ["shows", "foodie"], "communication_channel": "app", "favorite_land": "HARBOR"},
            "segments": seg("seg-new-hires"),
            "ml_scores": {"segment": "New hire", "next_best_action": "finish_onboarding"},
        }, onboarding_done={"i9", "w4", "emergency-contact"}, tenure=6)
        self.n = {k: max(v, saved[k]) for k, v in self.n.items()}
        self.n.update(saved)
        rows = [maya, daniel, sofia]
        for row, uid in zip(rows, PERSONAS):
            row["user_id"] = uid
        return rows

    def next_row(self) -> dict:
        x = self.r.random()
        return self.guest() if x < 0.74 else self.lead() if x < 0.86 else self.employee()

    def coverage(self) -> list[dict]:
        """A few users in every group right after the personas, so even a
        small export (tests, the in-memory quick start) covers the whole park."""
        rows = []
        for code, g in C.GROUPS.items():
            for _ in range(4):
                if g["audience"] == "guest":
                    region = g["region"]
                    rows.append(self.guest({"region": region, "group_code": code, "home_city": self.r.choice(CITIES[region])}))
                elif g["audience"] == "lead":
                    n = self.r.choice([4, 6, 8]) if code == "TRIP-FAM" else self.r.choice([14, 40, 120])
                    rows.append(self.lead({"group_code": code, "organization": {"members": n, "size_band": "1-9" if n < 10 else "10-49" if n < 50 else "50+"}}))
                else:
                    dept = g["department"]
                    rows.append(self.employee({"group_code": code, "employment": {"department": dept, "title": self.r.choice(C.DEPARTMENTS[dept]["titles"])}}))
        return rows


def deep_update(base: dict, upd: dict):
    for k, v in upd.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_update(base[k], v)
        else:
            base[k] = v


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export-date", default=dt.date.today().isoformat())
    ap.add_argument("--target-mb", type=float, default=24.0, help="approximate total size in MiB")
    ap.add_argument("--parts", type=int, default=2, help="number of part files")
    ap.add_argument("--seed", type=int, default=20261113)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "data", "parkchat-export"))
    args = ap.parse_args(argv)

    export_date = dt.date.fromisoformat(args.export_date)
    g = Gen(export_date, args.seed)
    target = int(args.target_mb * 1024 * 1024)
    per_part = target // args.parts + 1
    out_dir = os.path.abspath(os.path.join(args.out, f"exportTime={export_date:%Y%m%d}"))
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.startswith("part-") or f in ("_SUCCESS", "_manifest.json"):
            os.remove(os.path.join(out_dir, f))

    job_uuid = uuid.UUID(int=g.r.getrandbits(128))
    written, rows = 0, 0
    by_audience = {"guest": 0, "lead": 0, "employee": 0}
    files = []
    pending = g.personas() + g.coverage()
    for part in range(args.parts):
        name = f"part-{part:05d}-{job_uuid}-c000.json"
        part_bytes, part_rows = 0, 0
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            while pending or (part_bytes < per_part and written < target):
                row = pending.pop(0) if pending else g.next_row()
                line = json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n"
                b = len(line.encode("utf-8"))
                fh.write(line)
                part_bytes += b
                written += b
                part_rows += 1
                by_audience[row["audience"]] += 1
        rows += part_rows
        files.append({"file": name, "rows": part_rows, "bytes": part_bytes})
        print(f"  {name}  {part_rows:>7,} rows  {part_bytes / 1048576:6.1f} MiB", flush=True)

    manifest = {
        "system": "luminapark-data-platform", "dataset": "parkchat_people", "flow": "parkchat-nightly-export",
        "sources": {"guest": "Ticketing & reservations platform + CDP", "lead": "Group sales CRM", "employee": "HRIS, scheduling + ITSM"},
        "export_time": f"{export_date:%Y%m%d}", "export_date": export_date.isoformat(),
        "schema_version": SCHEMA_VERSION, "model_version": MODEL_VERSION,
        "format": "jsonl", "rows": rows, "by_audience": by_audience, "bytes": written, "files": files,
        "generator": "datagen/generate_mock_export.py", "seed": args.seed, "demo_personas": PERSONAS,
    }
    with open(os.path.join(out_dir, "_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    open(os.path.join(out_dir, "_SUCCESS"), "w").close()
    print(f"Wrote {rows:,} people ({by_audience['guest']:,} guests, {by_audience['lead']:,} trip planners, "
          f"{by_audience['employee']:,} crew members) = {written / 1048576:.1f} MiB to {out_dir}")


if __name__ == "__main__":
    main()
