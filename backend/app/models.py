"""SQLAlchemy tables (plan section 10).

Identity zone:    accounts, counsellors, identity_vault, audit_log
Operational zone: availability, bookings, waitlist_entries, offers, events, registrations,
                  tags, item_tags, resources, interests, engagements, notifications

Rule: no foreign key goes from the operational zone to `accounts`; operational rows
carry the HMAC pseudonym only.
"""

from app.db import Base  # noqa: F401  (tables subclass Base)

# TODO(all, Day 1): define the tables here.
