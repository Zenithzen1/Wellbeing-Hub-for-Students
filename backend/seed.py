"""Fake demo data: 3 counsellors, ~40 students, 20 events, 30 resources, a week of bookings.
No real student data, ever: every email is on the reserved .example domain.

    python scripts/gen_keys.py > ../.env     (once; the vault needs VAULT_PUBLIC_KEY)
    python seed.py

Every demo account uses the password below. It does nothing if accounts already exist.
Bookings and waitlists come from seed_booking.py (Aditya); this file makes the accounts and
pseudonyms they need, plus tags, resources, events, interests and engagements.
"""

import random
from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

import seed_booking
from app import auth, clock
from app.config import settings
from app.models import Account, Engagement, Registration, Tag
from app.services import events, identity, recommend

DEMO_PASSWORD = "wellbeing-demo"
N_STUDENTS = 40
NO_INTERESTS = 3  # the last few students have picked nothing yet (cold-start recommendations)

STAFF = [  # email, role, name
    ("noor@staff.example", "C", "Dr Noor Haddad"),
    ("mehta@staff.example", "C", "Dr Arjun Mehta"),
    ("farouk@staff.example", "C", "Ms Leila Farouk"),
    ("wellbeing@staff.example", "A", "Wellbeing team"),
    ("custodian@staff.example", "K", "Vault custodian"),
]

TAGS = ["anxiety", "exams", "exercise", "focus", "homesickness", "loneliness", "low mood", "mindfulness",
        "motivation", "nutrition", "relationships", "self-esteem", "sleep", "stress", "time management"]

RESOURCES = [  # title, kind, tags
    ("Sleep hygiene in ten minutes", "article", ["sleep"]),
    ("Wind-down breathing for bedtime", "audio", ["sleep", "mindfulness"]),
    ("Why all-nighters backfire", "video", ["sleep", "exams"]),
    ("Planning a revision week", "article", ["exams", "time management"]),
    ("Exam-day nerves: a 5-minute reset", "audio", ["exams", "anxiety"]),
    ("Past papers without panic", "article", ["exams", "stress"]),
    ("Box breathing, guided", "audio", ["anxiety", "mindfulness"]),
    ("Understanding panic attacks", "video", ["anxiety"]),
    ("Grounding with your five senses", "article", ["anxiety", "mindfulness"]),
    ("A body scan for busy days", "audio", ["mindfulness", "stress"]),
    ("Mindful walking around campus", "audio", ["mindfulness", "exercise"]),
    ("Pomodoro, explained", "video", ["focus", "time management"]),
    ("Phone-free study blocks", "article", ["focus"]),
    ("Beating procrastination gently", "article", ["motivation", "time management"]),
    ("Small wins: building momentum", "video", ["motivation", "low mood"]),
    ("When everything feels flat", "article", ["low mood"]),
    ("Behavioural activation worksheet", "article", ["low mood", "motivation"]),
    ("Missing home in your first year", "article", ["homesickness"]),
    ("Calling home without the guilt", "audio", ["homesickness", "relationships"]),
    ("Making friends after week one", "article", ["loneliness", "relationships"]),
    ("Clubs and societies to try", "article", ["loneliness"]),
    ("Healthy conflict with roommates", "video", ["relationships"]),
    ("Setting boundaries kindly", "article", ["relationships", "self-esteem"]),
    ("Talking back to your inner critic", "audio", ["self-esteem"]),
    ("Impostor feelings in engineering", "video", ["self-esteem", "stress"]),
    ("Cheap, quick hostel meals", "article", ["nutrition"]),
    ("Caffeine and your sleep", "article", ["nutrition", "sleep"]),
    ("Ten-minute desk stretches", "video", ["exercise", "focus"]),
    ("Running as stress relief", "article", ["exercise", "stress"]),
    ("Stress: the useful kind and the other kind", "video", ["stress"]),
]

EVENTS = [  # title, days from today, hour (Dubai), hours long, location, capacity, tags
    ("Yoga at dawn", -12, 7, 1, "Sports hall", 25, ["exercise", "mindfulness"]),
    ("Sleep clinic", -10, 17, 1, "Room A-104", 30, ["sleep"]),
    ("Exam-stress workshop", -8, 16, 2, "Lecture hall 2", 60, ["exams", "stress"]),
    ("Peer support circle", -6, 18, 1, "Wellbeing room", 12, ["loneliness", "relationships"]),
    ("Mindfulness hour", -4, 13, 1, "Library seminar room", 20, ["mindfulness"]),
    ("Cooking on a budget", -2, 18, 2, "Hostel kitchen", 15, ["nutrition"]),
    ("Art therapy drop-in", 1, 16, 2, "Studio 3", 15, ["low mood", "stress"]),
    ("Revision planning clinic", 2, 14, 1, "Lecture hall 1", 80, ["exams", "time management"]),
    ("Peer support circle", 3, 18, 1, "Wellbeing room", 12, ["loneliness", "relationships"]),
    ("Yoga at dawn", 4, 7, 1, "Sports hall", 25, ["exercise", "mindfulness"]),
    ("Managing exam anxiety", 5, 16, 1, "Lecture hall 2", 60, ["exams", "anxiety"]),
    ("Sleep clinic", 7, 17, 1, "Room A-104", 30, ["sleep"]),
    ("Mindfulness hour", 9, 13, 1, "Library seminar room", 20, ["mindfulness"]),
    ("Focus sprint (silent study)", 10, 10, 3, "Library", 40, ["focus"]),
    ("Homesickness meet-up", 12, 19, 1, "Common room", 20, ["homesickness", "loneliness"]),
    ("Self-esteem workshop", 14, 16, 2, "Room B-201", 25, ["self-esteem"]),
    ("Run club: campus loop", 16, 6, 1, "Main gate", 30, ["exercise"]),
    ("Healthy relationships talk", 18, 17, 1, "Lecture hall 1", 80, ["relationships"]),
    ("Winter wellness fair", 22, 11, 5, "Atrium", 200, ["stress", "nutrition", "exercise"]),
    ("Motivation reset for the new term", 28, 16, 1, "Lecture hall 2", 60, ["motivation"]),
]


def _at(days: int, hour: int) -> datetime:
    day = clock.to_local(clock.now()).date() + timedelta(days=days)
    return datetime.combine(day, time(hour), tzinfo=clock.DUBAI)


def seed(db: Session, rng_seed: int = 2026) -> dict | None:
    """Make everything. Returns counts, or None if accounts already exist."""
    if db.scalar(select(Account.id).limit(1)) is not None:
        return None
    if not settings.vault_public_key:
        raise SystemExit("VAULT_PUBLIC_KEY is not set: run `python scripts/gen_keys.py > ../.env` first")
    rng = random.Random(rng_seed)

    staff = [identity.create_staff(db, email, DEMO_PASSWORD, role, name) for email, role, name in STAFF]
    emails = [f"student{i:02d}@students.example" for i in range(1, N_STUDENTS + 1)]
    for i, email in enumerate(emails, 1):
        identity.register(db, email, DEMO_PASSWORD, f"Demo Student {i:02d}")
    students = [auth.pseudonym_for(email) for email in emails]

    made = seed_booking.seed(db, counsellor_accounts=[a.id for a in staff if a.role == "C"], students=students,
                             rng_seed=rng_seed) or {}

    for name in TAGS:
        db.add(Tag(name=name))
    db.commit()
    res = [recommend.create_resource(db, title, kind, f"https://example.org/hub/r{i}", tags)
           for i, (title, kind, tags) in enumerate(RESOURCES, 1)]
    evs = [events.create(db, title, _at(d, h), _at(d, h) + timedelta(hours=n), where, cap, tags)
           for title, d, h, n, where, cap, tags in EVENTS]

    # interests: 1-3 tags each; the demo student (student01) gets exams and sleep
    for i, pse in enumerate(students):
        if i >= N_STUDENTS - NO_INTERESTS:
            continue
        picks = ["exams", "sleep"] if i == 0 else rng.sample(TAGS, rng.randint(1, 3))
        recommend.set_interests(db, pse, picks)

    # past events: who attended (rows written directly; the service refuses to register for the past)
    attended = 0
    now = clock.now()
    for ev in evs:
        if ev.start > now:
            continue
        for pse in rng.sample(students, rng.randint(6, min(ev.capacity, 18))):
            db.add(Registration(event_id=ev.id, pseudonym=pse, status="registered", position=0))
            db.add(Engagement(pseudonym=pse, item=f"e:{ev.id}", kind="attended", at=ev.end))
            attended += 1
    db.commit()
    events.rebuild(db)

    # resources students saved or finished (student01 keeps some unread for the dashboard)
    engaged = 0
    for i, pse in enumerate(students):
        for r in rng.sample(res, rng.randint(0, 2 if i == 0 else 5)):
            if recommend.engage(db, pse, f"r:{r.id}", rng.choice(("saved", "finished"))):
                engaged += 1

    # upcoming events: some sign-ups (each one schedules a reminder)
    registered = 0
    for ev in evs:
        if ev.start <= now:
            continue
        for pse in rng.sample(students, rng.randint(2, min(ev.capacity, 14))):
            events.register(db, ev.id, pse)
            registered += 1
    recommend.rebuild(db)  # the past-event engagements were written directly

    return {**made, "staff": len(staff), "students": len(students), "tags": len(TAGS), "resources": len(res),
            "events": len(evs), "past_attendance": attended, "engagements": engaged, "registrations": registered}


def main() -> None:
    from app import services
    from app.db import SessionLocal, init_db

    init_db()
    services.rebuild_all()
    db = SessionLocal()
    try:
        made = seed(db)
    finally:
        db.close()
    if made is None:
        print("accounts already exist; nothing seeded")
        return
    print("seeded:", made)
    print(f"\nDemo logins (password: {DEMO_PASSWORD}):")
    for email, role, name in STAFF:
        print(f"  {email:28} {name}")
    print("  student01@students.example   ... student40@students.example")


if __name__ == "__main__":
    main()
