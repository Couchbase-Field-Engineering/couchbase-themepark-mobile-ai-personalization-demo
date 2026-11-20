"""Reference data for the ParkChat demo park.

**Lumina Park** is a fictional theme park resort: six themed lands, a few
dozen rides, shows and restaurants, a Groups & Events office (group visits
and celebrations sold through planning sessions) and a few thousand crew
members. One assistant - ParkChat - serves all of them:

* guests         park questions, today's plan, ride and dining bookings, changes and refunds
* trip planners  experience discovery, trip details and qualification, planning sessions
* crew members   IT help desk, shifts, HR benefits, onboarding paperwork

Everything here is shared by the mock export generator
(datagen/generate_mock_export.py), the business logic (actions.py), the For
You ranking (personalization.py) and the Knowledge Base documents
(knowledge.py). Names, prices and policies are invented demo data.
"""
from __future__ import annotations

import datetime as dt
import hashlib

PARK = {
    "name": "Lumina Park",
    "legal_name": "Lumina Park Resort, LLC",
    "tagline": "A brighter kind of day out.",
    "support_phone": "1-800-555-0142",
    "support_hours": "7am-11pm PT, every day",
    "business_brand": "Lumina Groups & Events",
    "loyalty_program": "Lumina Club",
    "website": "luminapark.example",
    "park_hours": "9am-10pm (11pm Fridays and Saturdays)",
}

AUDIENCES = {"guest": "Guest", "lead": "Trip planner", "employee": "Crew member"}

# The four things a park-wide chatbot is asked to do, and the intents
# (assistant.py) that belong to each. The app shows the area on every answer.
AREAS = {
    "support": {"name": "Guest Support", "icon": "help-buoy", "audiences": ["guest", "lead", "employee"]},
    "commerce": {"name": "Plans & Bookings", "icon": "ticket", "audiences": ["guest"]},
    "sales": {"name": "Trips & Groups", "icon": "briefcase", "audiences": ["guest", "lead"]},
    "workplace": {"name": "Crew IT & HR", "icon": "id-card", "audiences": ["employee"]},
}

# Groups the park-wide workload draws its users from (workload.py): every
# guest home region, both trip-planner tiers and every department gets sessions.
GROUPS: dict[str, dict] = {
    "GST-NE": {"name": "Guests · Northeast", "audience": "guest", "region": "Northeast"},
    "GST-SE": {"name": "Guests · Southeast", "audience": "guest", "region": "Southeast"},
    "GST-MW": {"name": "Guests · Midwest", "audience": "guest", "region": "Midwest"},
    "GST-SW": {"name": "Guests · Southwest", "audience": "guest", "region": "Southwest"},
    "GST-W": {"name": "Guests · West", "audience": "guest", "region": "West"},
    "TRIP-FAM": {"name": "Trip planners · Families & small parties", "audience": "lead", "region": None},
    "TRIP-GRP": {"name": "Trip planners · Schools, teams & events", "audience": "lead", "region": None},
    "EMP-ATTR": {"name": "Crew · Attractions", "audience": "employee", "department": "Attractions"},
    "EMP-GUEST": {"name": "Crew · Guest Relations", "audience": "employee", "department": "Guest Relations"},
    "EMP-ENT": {"name": "Crew · Entertainment", "audience": "employee", "department": "Entertainment"},
    "EMP-FNB": {"name": "Crew · Food & Beverage", "audience": "employee", "department": "Food & Beverage"},
    "EMP-CORP": {"name": "Crew · Park Services & People", "audience": "employee", "department": "Park Services & People"},
}

# The six lands of the park. `city` is the one-line description shown under
# the name; the nightly Park Guide lists each with its hours.
LANDS = [
    {"id": "HARBOR", "name": "Lantern Harbor", "city": "Park entrance, shops and waterfront dining", "hours": "8:30am-10:30pm"},
    {"id": "SUMMIT", "name": "Starfall Summit", "city": "Coasters and big thrills", "hours": "9am-10pm"},
    {"id": "COVE", "name": "Tidewater Cove", "city": "Water rides and the grotto", "hours": "9am-9pm"},
    {"id": "COMMONS", "name": "Clockwork Commons", "city": "Gentle rides for small explorers", "hours": "9am-8pm"},
    {"id": "FOREST", "name": "Emberwood Forest", "city": "Rapids, expeditions and the live stage", "hours": "9am-9pm"},
    {"id": "PLAZA", "name": "Aurora Plaza", "city": "Shows, parades and the nightly spectacular", "hours": "10am-10pm"},
]
LAND_BY_ID = {s["id"]: s for s in LANDS}
REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]
REGION_GROUP = {"Northeast": "GST-NE", "Southeast": "GST-SE", "Midwest": "GST-MW", "Southwest": "GST-SW", "West": "GST-W"}

# --------------------------------------------------------------------------
# Experiences: what a guest can book. `price` is what the booking costs the
# party: an express pass for a ride, a deposit for dining, a reserved spot
# for a show. `family` groups experiences that can be swapped like for like.
# --------------------------------------------------------------------------
EXPERIENCES = [
    {"exp_id": "RID-STARFALL", "name": "Starfall Coaster", "category": "Rides", "land": "SUMMIT", "price": 22, "min_height_in": 48, "typical_wait_min": 75,
     "tags": ["thrill", "night", "coaster"], "family": "coaster", "blurb": "The park's tallest coaster: a 180-foot drop and two inversions under the summit lights."},
    {"exp_id": "RID-COMET", "name": "Comet Run", "category": "Rides", "land": "SUMMIT", "price": 18, "min_height_in": 44, "typical_wait_min": 55,
     "tags": ["thrill", "family", "coaster"], "family": "coaster", "blurb": "A launch coaster with no inversions - the first big coaster for most kids."},
    {"exp_id": "RID-RAPIDS", "name": "Emberwood Rapids", "category": "Rides", "land": "FOREST", "price": 16, "min_height_in": 42, "typical_wait_min": 60,
     "tags": ["water", "family", "adventure"], "family": "water-ride", "blurb": "Round rafts through the forest canyon. Someone always gets soaked."},
    {"exp_id": "RID-PLUNGE", "name": "Tidewater Plunge", "category": "Rides", "land": "COVE", "price": 16, "min_height_in": 40, "typical_wait_min": 50,
     "tags": ["water", "thrill"], "family": "water-ride", "blurb": "A log flume with a five-story final drop into the cove."},
    {"exp_id": "RID-GROTTO", "name": "Glowworm Grotto", "category": "Rides", "land": "COVE", "price": 12, "min_height_in": 0, "typical_wait_min": 35,
     "tags": ["family", "toddlers", "indoor"], "family": "gentle", "blurb": "A slow boat ride through caverns lit by ten thousand lights. Cool and dark on a hot day."},
    {"exp_id": "RID-FLIGHT", "name": "Lantern Flight", "category": "Rides", "land": "PLAZA", "price": 18, "min_height_in": 40, "typical_wait_min": 65,
     "tags": ["family", "indoor", "night"], "family": "gentle", "blurb": "A soaring simulator over a valley of floating lanterns."},
    {"exp_id": "RID-CAROUSEL", "name": "Clockwork Carousel", "category": "Rides", "land": "COMMONS", "price": 8, "min_height_in": 0, "typical_wait_min": 15,
     "tags": ["toddlers", "family", "classic"], "family": "gentle", "blurb": "A hand-painted carousel of brass animals; every seat suits the smallest riders."},
    {"exp_id": "RID-WHIRL", "name": "Gearwheel Whirl", "category": "Rides", "land": "COMMONS", "price": 8, "min_height_in": 0, "typical_wait_min": 20,
     "tags": ["toddlers", "family"], "family": "gentle", "blurb": "Spinning cogs you steer yourself - as fast or as slow as the table agrees."},
    {"exp_id": "RID-EXPEDITION", "name": "Canopy Expedition", "category": "Rides", "land": "FOREST", "price": 14, "min_height_in": 36, "typical_wait_min": 40,
     "tags": ["adventure", "family"], "family": "adventure", "blurb": "An off-road truck tour through the treetops and under a waterfall."},
    {"exp_id": "RID-SKYWAY", "name": "Summit Skyway", "category": "Rides", "land": "SUMMIT", "price": 10, "min_height_in": 0, "typical_wait_min": 25,
     "tags": ["family", "classic", "night"], "family": "adventure", "blurb": "Gondolas from Starfall Summit to Lantern Harbor with the best view of the park."},
    {"exp_id": "SHW-AURORA", "name": "Aurora Nights Spectacular · reserved viewing", "category": "Shows", "land": "PLAZA", "price": 25, "min_height_in": 0, "typical_wait_min": 0,
     "tags": ["shows", "night", "family"], "family": "night-show", "blurb": "Fireworks, fountains and drones over Aurora Plaza at 9pm, from a reserved terrace."},
    {"exp_id": "SHW-PARADE", "name": "Lantern Parade · reserved viewing", "category": "Shows", "land": "HARBOR", "price": 15, "min_height_in": 0, "typical_wait_min": 0,
     "tags": ["shows", "family", "toddlers"], "family": "night-show", "blurb": "A kerb-side spot for the evening parade, held until ten minutes before step-off."},
    {"exp_id": "SHW-LEGENDS", "name": "Emberwood Legends live show", "category": "Shows", "land": "FOREST", "price": 10, "min_height_in": 0, "typical_wait_min": 0,
     "tags": ["shows", "adventure", "indoor"], "family": "stage-show", "blurb": "A 25-minute stunt and puppetry show in the Forest Theater, five times a day."},
    {"exp_id": "SHW-LUMI", "name": "Meet Lumi the Firefly", "category": "Shows", "land": "COMMONS", "price": 12, "min_height_in": 0, "typical_wait_min": 0,
     "tags": ["characters", "toddlers", "family"], "family": "stage-show", "blurb": "A reserved time to meet the park's firefly mascot, with a photographer on hand."},
    {"exp_id": "DIN-HARBOR", "name": "Harbor Lights Grill", "category": "Dining", "land": "HARBOR", "price": 40, "min_height_in": 0, "typical_wait_min": 0,
     "tags": ["foodie", "night", "family"], "family": "table-dining", "blurb": "Table-service seafood and steaks on the waterfront; the deposit comes off the bill."},
    {"exp_id": "DIN-SMOKEHOUSE", "name": "Summit Lodge Smokehouse", "category": "Dining", "land": "SUMMIT", "price": 30, "min_height_in": 0, "typical_wait_min": 0,
     "tags": ["foodie", "family"], "family": "table-dining", "blurb": "Barbecue platters to share at long lodge tables."},
    {"exp_id": "DIN-FIREFLY", "name": "Firefly Character Breakfast", "category": "Dining", "land": "COMMONS", "price": 56, "min_height_in": 0, "typical_wait_min": 0,
     "tags": ["characters", "toddlers", "foodie"], "family": "character-dining", "blurb": "Breakfast buffet where Lumi and friends visit every table."},
    {"exp_id": "DIN-DESSERT", "name": "Starlight Dessert Party", "category": "Dining", "land": "PLAZA", "price": 65, "min_height_in": 0, "typical_wait_min": 0,
     "tags": ["foodie", "night", "shows"], "family": "character-dining", "blurb": "Desserts and drinks on the terrace with a front-row view of Aurora Nights."},
    {"exp_id": "DIN-CANTINA", "name": "Cove Cantina", "category": "Dining", "land": "COVE", "price": 20, "min_height_in": 0, "typical_wait_min": 0,
     "tags": ["foodie", "water", "value"], "family": "table-dining", "blurb": "Tacos and frozen drinks over the water; walk-ups wait about 40 minutes at lunch."},
    {"exp_id": "TUR-GEARS", "name": "Behind the Gears walking tour", "category": "Tours", "land": "COMMONS", "price": 55, "min_height_in": 0, "typical_wait_min": 0,
     "tags": ["classic", "indoor", "adventure"], "family": "tour", "blurb": "Ninety minutes backstage: the carousel workshop, the parade barn and the control room."},
    {"exp_id": "TUR-DAWN", "name": "First Light early entry", "category": "Tours", "land": "SUMMIT", "price": 45, "min_height_in": 0, "typical_wait_min": 0,
     "tags": ["thrill", "value", "adventure"], "family": "tour", "blurb": "In the park at 8am with a guide: two Summit coasters before the gates open."},
    {"exp_id": "EXT-MEMORY", "name": "Memory Pass photo package", "category": "Extras", "land": "HARBOR", "price": 69, "min_height_in": 0, "typical_wait_min": 0,
     "tags": ["family", "characters", "classic"], "family": "photo", "blurb": "Every ride photo and photographer shot from your visit, in the app the same day."},
    {"exp_id": "EXT-EXPRESS", "name": "All-Day Express Pass", "category": "Extras", "land": "HARBOR", "price": 89, "min_height_in": 0, "typical_wait_min": 0,
     "tags": ["thrill", "value", "family"], "family": "express", "blurb": "One express entry on every ride for the day, no return times to book."},
    {"exp_id": "EXT-STROLLER", "name": "Stroller rental · day", "category": "Extras", "land": "HARBOR", "price": 18, "min_height_in": 0, "typical_wait_min": 0,
     "tags": ["toddlers", "family", "value"], "family": "rental", "blurb": "A single stroller waiting at the Harbor gate, returned anywhere in the park."},
]
EXPERIENCE_BY_ID = {p["exp_id"]: p for p in EXPERIENCES}
INTERESTS = ["thrill", "family", "toddlers", "water", "shows", "characters", "foodie", "night", "indoor", "adventure"]
# What kind of booking each category makes; ride and dining times can be moved.
KIND_BY_CATEGORY = {"Rides": "express pass", "Dining": "dining", "Shows": "show", "Tours": "tour", "Extras": "add-on"}
BOOKING_KINDS = list(dict.fromkeys(KIND_BY_CATEGORY.values()))
MOVABLE_KINDS = ("express pass", "dining", "show")


def kind_of(exp_id: str) -> str:
    return KIND_BY_CATEGORY[EXPERIENCE_BY_ID[exp_id]["category"]]


# Lumina Groups & Events: group visits sold through a planning session.
PACKAGES = [
    {"code": "PK-DAY", "name": "Day Adventure", "party_size": (1, 9), "price_per_guest": 149,
     "includes": ["1-day ticket", "three express passes", "a meal voucher"],
     "blurb": "A full day for a family or a few friends, planned around the rides you care about."},
    {"code": "PK-GROUP", "name": "Group Getaway", "party_size": (10, 49), "price_per_guest": 129,
     "includes": ["1-day ticket", "group express entry on four rides", "a reserved lunch at Summit Lodge Smokehouse", "a chaperone ticket per ten guests"],
     "blurb": "Group pricing for schools, teams and reunions, with a meeting point and a host at the gate."},
    {"code": "PK-GRAND", "name": "Grand Gathering", "party_size": (50, 5000), "price_per_guest": 115,
     "includes": ["1-day ticket", "a private event space", "catering", "a performance slot on the Plaza stage", "reserved Aurora Nights viewing"],
     "blurb": "Large groups and company days with a dedicated event coordinator and after-hours options."},
]
PACKAGE_BY_CODE = {b["code"]: b for b in PACKAGES}
GROUP_TYPES = ["Family reunion", "School band or choir", "Youth sports team", "Company outing", "Scout troop", "Birthday celebration",
               "Graduation trip", "Faith community", "Travel club", "Dance studio"]
BUDGET_BANDS = ["under $2k", "$2k-$10k", "$10k-$30k", "$30k+"]
TIMELINES = ["this month", "1-3 months", "3-6 months", "just researching"]
PLANNING_TOPICS = ["Group visit", "School performance program", "Company event", "Celebration package", "Resort stay"]
PLANNING_TIMES = ["09:00", "10:30", "13:00", "14:30", "16:00"]
PLANNING_CHANNELS = ["video", "phone", "at the park"]
ADVISORS = ["Jordan Avery", "Sam Whitlock", "Renee Castellano", "Imani Brooks", "Theo Lindqvist"]

# --------------------------------------------------------------------------
# Bookings, time changes, refunds
# --------------------------------------------------------------------------
TIME_WINDOWS = ["9:30am-10:30am", "11:00am-12:00pm", "1:00pm-2:00pm", "3:00pm-4:00pm", "5:30pm-6:30pm", "7:30pm-8:30pm"]
BOOKING_STATUSES = ["upcoming", "completed", "cancelled"]
CHANGE_REASONS = ["Change of plans", "Someone isn't tall enough", "Weather", "The ride was closed", "Booked the wrong time", "Booked by mistake"]
# How many days before the visit a booking can still be swapped or refunded.
# Gold and Platinum members can change on the day itself.
CHANGE_CUTOFF_DAYS = {"Member": 1, "Silver": 1, "Gold": 0, "Platinum": 0}
LOYALTY_TIERS = ["Member", "Silver", "Gold", "Platinum"]
COURTESY_CREDIT_MAX = 150

# --------------------------------------------------------------------------
# Workplace: IT help desk and HR
# --------------------------------------------------------------------------
DEPARTMENTS = {
    "Attractions": {"group": "EMP-ATTR", "titles": ["Ride Operator", "Attractions Lead", "Area Manager", "Ride Safety Trainer"]},
    "Guest Relations": {"group": "EMP-GUEST", "titles": ["Guest Relations Host", "Senior Host", "Guest Relations Lead", "Accessibility Specialist"]},
    "Entertainment": {"group": "EMP-ENT", "titles": ["Performer", "Stage Technician", "Parade Coordinator", "Show Lead"]},
    "Food & Beverage": {"group": "EMP-FNB", "titles": ["Line Cook", "Server", "Restaurant Lead", "Culinary Manager"]},
    "Park Services & People": {"group": "EMP-CORP", "titles": ["Custodial Host", "People Partner", "Payroll Specialist", "Security Officer"]},
}
# Where a department's shifts are worked (datagen builds the next shift from it).
SHIFT_POSTS = {
    "Attractions": ["Starfall Coaster", "Comet Run", "Emberwood Rapids", "Glowworm Grotto", "Clockwork Carousel"],
    "Guest Relations": ["Lantern Harbor Guest Relations", "Aurora Plaza information kiosk", "Main gate"],
    "Entertainment": ["Forest Theater", "Lantern Parade route", "Aurora Plaza stage"],
    "Food & Beverage": ["Harbor Lights Grill", "Summit Lodge Smokehouse", "Cove Cantina"],
    "Park Services & People": ["Lantern Harbor", "Crew Center", "Aurora Plaza"],
}
SHIFT_TIMES = [("7:30am", "4:00pm"), ("9:00am", "5:30pm"), ("1:30pm", "10:00pm"), ("3:00pm", "11:30pm")]
IT_CATEGORIES = [
    {"id": "access", "name": "Account & access", "queue": "Identity", "sla_hours": 4},
    {"id": "hardware", "name": "Handhelds & devices", "queue": "Device Depot", "sla_hours": 8},
    {"id": "network", "name": "Wi-Fi & radios", "queue": "Park Network", "sla_hours": 4},
    {"id": "software", "name": "Apps & software", "queue": "Device Depot", "sla_hours": 8},
    {"id": "email", "name": "Email & calendar", "queue": "Collaboration", "sla_hours": 8},
    {"id": "pos", "name": "Point of sale & scanners", "queue": "Park Systems", "sla_hours": 2},
]
IT_CATEGORY_BY_ID = {c["id"]: c for c in IT_CATEGORIES}
IT_PRIORITIES = ["low", "normal", "high"]
# Systems a crew member can ask for. `approval` ones change what a person can
# see, spend or operate, so AOM holds the request for a human (request_privileged_access).
SYSTEMS = [
    {"id": "sso", "name": "CrewPass sign-on", "approval": False, "default": True},
    {"id": "email", "name": "Email & calendar", "approval": False, "default": True},
    {"id": "hr-portal", "name": "Crew Portal", "approval": False, "default": True},
    {"id": "network", "name": "Backstage Wi-Fi", "approval": False, "default": False},
    {"id": "pos", "name": "Point of sale", "approval": False, "default": False},
    {"id": "ride-ops", "name": "Ride Operations console", "approval": True, "default": False},
    {"id": "cash-office", "name": "Cash Office & Finance", "approval": True, "default": False},
    {"id": "guest-recovery", "name": "Guest Recovery console", "approval": True, "default": False},
    {"id": "guest-data", "name": "Guest data workspace (read-only)", "approval": True, "default": False},
]
SYSTEM_BY_ID = {s["id"]: s for s in SYSTEMS}
DEVICES = [("Trek H7 handheld", "Android 14", "handheld"), ("Crew Tablet 11", "iPadOS 18", "tablet"), ("Aero 14 Laptop", "Windows 11", "laptop")]

BENEFIT_PLANS = {
    "medical": [
        {"id": "MED-CORE", "name": "Core PPO", "employee_cost_per_paycheck": 48, "deductible": 1500, "blurb": "Broad network, $1,500 deductible, $25 office visits."},
        {"id": "MED-HSA", "name": "HSA Advantage", "employee_cost_per_paycheck": 22, "deductible": 3200, "blurb": "High-deductible plan with a $1,000 park HSA contribution."},
        {"id": "MED-PLUS", "name": "Plus PPO", "employee_cost_per_paycheck": 92, "deductible": 500, "blurb": "Lowest deductible and $15 office visits."},
    ],
    "dental": [
        {"id": "DEN-BASE", "name": "Dental Base", "employee_cost_per_paycheck": 6, "blurb": "Two cleanings a year and basic restorative care."},
        {"id": "DEN-PLUS", "name": "Dental Plus", "employee_cost_per_paycheck": 14, "blurb": "Adds orthodontia and major restorative care."},
    ],
    "vision": [
        {"id": "VIS-STD", "name": "Vision Standard", "employee_cost_per_paycheck": 3, "blurb": "Annual exam and a $180 frame allowance."},
    ],
}
PLAN_BY_ID = {p["id"]: {**p, "kind": k} for k, plans in BENEFIT_PLANS.items() for p in plans}
ENROLLMENT_WINDOW_DAYS = 30          # new hires enroll within 30 days of their start date
PTO_ACCRUAL_PER_MONTH = 1.5          # days
K401_MATCH_PCT = 4
ONBOARDING_TASKS = [
    {"task_id": "i9", "title": "Form I-9 employment eligibility", "kind": "form", "due_day": 3,
     "detail": "Section 1 is due by your first day; bring your documents to your lead or a People Partner within three days."},
    {"task_id": "w4", "title": "Form W-4 tax withholding", "kind": "form", "due_day": 7,
     "detail": "Sets the federal tax withheld from each paycheck. You can change it any time in the Crew Portal."},
    {"task_id": "direct-deposit", "title": "Direct deposit", "kind": "form", "due_day": 7,
     "detail": "Add the bank account your pay goes to. Set it up before the payroll cut-off to avoid a paper check."},
    {"task_id": "handbook", "title": "Crew Handbook acknowledgment", "kind": "sign", "due_day": 10,
     "detail": "Read the Crew Handbook and sign to confirm you've received it."},
    {"task_id": "code-of-conduct", "title": "Code of Conduct", "kind": "sign", "due_day": 10,
     "detail": "Our standards for how we treat guests and each other, on stage and backstage."},
    {"task_id": "safety-training", "title": "Park safety & evacuation training", "kind": "training", "due_day": 14,
     "detail": "A 40-minute course on ride evacuations, radio calls, lost children and guest data. Required before privileged systems."},
    {"task_id": "benefits", "title": "Benefits enrollment", "kind": "form", "due_day": 30,
     "detail": "Choose medical, dental and vision within 30 days of your start date or wait for open enrollment."},
    {"task_id": "emergency-contact", "title": "Emergency contact", "kind": "form", "due_day": 14,
     "detail": "Who we should call if something happens at work."},
]
ONBOARDING_BY_ID = {t["task_id"]: t for t in ONBOARDING_TASKS}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _h(*parts) -> int:
    return int(hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def a_or_an(noun: str) -> str:
    return ("an " if noun[:1].lower() in "aeiou" else "a ") + noun


def change_cutoff_days(tier: str | None) -> int:
    return CHANGE_CUTOFF_DAYS.get(tier or "Member", 1)


def package_for_party(party_size: int | None) -> dict:
    n = int(party_size or 10)
    return next((b for b in PACKAGES if b["party_size"][0] <= n <= b["party_size"][1]), PACKAGES[-1])


def swap_options(exp_id: str) -> list[dict]:
    """What a booking can be swapped for: like for like first (another
    coaster for a coaster), then anything else in the same category."""
    p = EXPERIENCE_BY_ID.get(exp_id)
    if not p:
        return []
    same = [x for x in EXPERIENCES if x["family"] == p["family"] and x["exp_id"] != exp_id]
    cat = [x for x in EXPERIENCES if x["category"] == p["category"] and x["family"] != p["family"]]
    return (same + cat)[:4]


def business_days(start: dt.date, n: int) -> list[dt.date]:
    out, d = [], start
    while len(out) < n:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out


def slot_id(date: str, time: str) -> str:
    return f"{date}T{time}"


def initial_inventory(today: dt.date) -> dict:
    """Bookable places left per experience and open planning-session party_size per
    slot. One CAS-protected document (`inv::v1`): two parties can't take the
    last express pass or the same planning slot. Deterministic, so a reset
    restores it."""
    stock = {p["exp_id"]: 3 + _h("stock", p["exp_id"]) % 40 for p in EXPERIENCES}
    stock["RID-COMET"] = 2           # scarcity for the swap story
    slots = {}
    for d in business_days(today, 8):
        for t in PLANNING_TIMES:
            slots[slot_id(d.isoformat(), t)] = _h("slot", d.isoformat(), t) % 4   # 0 = fully booked
    return {"stock": stock, "slots": slots}


def public_catalog() -> dict:
    """What every signed-in user's phone gets (`catalog::v1`, channel `catalog`)."""
    return {
        "park": PARK,
        "areas": AREAS,
        "lands": LANDS,
        "experiences": EXPERIENCES,
        "packages": [{**b, "party_size": list(b["party_size"])} for b in PACKAGES],
        "time_windows": TIME_WINDOWS,
        "change_reasons": CHANGE_REASONS,
        "change_cutoff_days": CHANGE_CUTOFF_DAYS,
        "planning_topics": PLANNING_TOPICS,
        "planning_times": PLANNING_TIMES,
        "planning_channels": PLANNING_CHANNELS,
        "budget_bands": BUDGET_BANDS,
        "timelines": TIMELINES,
    }


def workplace_catalog() -> dict:
    """Crew-only reference data (`handbook::v1`, channel `employees`):
    Sync Gateway never sends this document to a guest's phone."""
    return {
        "it_categories": IT_CATEGORIES,
        "it_priorities": IT_PRIORITIES,
        "systems": SYSTEMS,
        "benefit_plans": BENEFIT_PLANS,
        "onboarding_tasks": ONBOARDING_TASKS,
        "pto_accrual_per_month": PTO_ACCRUAL_PER_MONTH,
        "k401_match_pct": K401_MATCH_PCT,
        "enrollment_cutoff_days": ENROLLMENT_WINDOW_DAYS,
        "shift_swap_notice_hours": 24,
    }
