from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import hash_password
from .config import settings
from .models import Agency, User, Booking, SimulatorConfig, Traffic, utcnow


def seed(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)) is not None:
        return
    a, b = Agency(name="Atlas Travel (synthetic)"), Agency(name="Bluebird Tours (synthetic)")
    db.add_all([a, b]); db.flush()
    db.add_all([
        User(username="admin", role="admin", pw_hash=hash_password(settings().admin_password)),
        User(username="atlas_agent", agency_id=a.id, role="agency", pw_hash=hash_password(settings().agency_password)),
        User(username="bluebird_agent", agency_id=b.id, role="agency", pw_hash=hash_password(settings().agency_password)),
        Booking(agency_id=a.id, itinerary="Dubai Downtown Hotel - 2 nights", amount_paise=1000000),
        Booking(agency_id=b.id, itinerary="Singapore Bay Hotel - 1 night", amount_paise=760000),
        SimulatorConfig(id=1),
        Traffic(path_template="/sim/bookings/{id}", method="GET", source="business", recorded_at=utcnow()-timedelta(days=1)),
        Traffic(path_template="/sim/bookings/{id}/refund", method="POST", source="business", recorded_at=utcnow()-timedelta(days=2)),
        Traffic(path_template="/sim/partner/shortcut/{id}", method="GET", source="business", recorded_at=utcnow()-timedelta(days=1)),
    ])
    db.commit()
