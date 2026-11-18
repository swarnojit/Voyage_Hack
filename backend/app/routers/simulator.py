"""Deliberately vulnerable in *approved synthetic demo mode only*.
This router must not be connected to real customer databases or exposed on a public host.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import current_user, require_admin
from ..models import Booking, Refund, SimulatorConfig, User, Traffic
from ..schemas import RefundIn, CloneIn, NewHoldIn
from ..services.serialize import obj
from ..config import settings

router = APIRouter(prefix="/sim", tags=["synthetic-travel-platform"])


def get_booking(db: Session, booking_id: int) -> Booking:
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Synthetic booking not found")
    return booking


def ownership(booking: Booking, user: User):
    if user.role != "admin" and booking.agency_id != user.agency_id:
        raise HTTPException(403, "Agency is not allowed to access this booking")


def log_traffic(db: Session, route: str, method="GET", source="scanner"):
    db.add(Traffic(path_template=route, method=method, source=source))


@router.get("/bookings")
def list_my_bookings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Booking).where(Booking.universe == "baseline")
    if user.role != "admin":
        stmt = stmt.where(Booking.agency_id == user.agency_id)
    return [obj(b, "id", "agency_id", "itinerary", "amount_paise", "status") for b in db.scalars(stmt).all()]


@router.get("/bookings/{booking_id}")
def read_booking(booking_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    booking = get_booking(db, booking_id)
    config = db.get(SimulatorConfig, 1)
    if not config.cross_agency_bug:
        ownership(booking, user)
    log_traffic(db, "/sim/bookings/{id}")
    db.commit()
    return obj(booking, "id", "agency_id", "itinerary", "amount_paise", "status", "universe")


@router.post("/bookings/{booking_id}/refund")
def refund_booking(booking_id: int, payload: RefundIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    booking = get_booking(db, booking_id)
    ownership(booking, user)
    if booking.status not in ('confirmed', 'cancelled'):
        raise HTTPException(409, 'Only paid bookings can be refunded')
    cfg = db.get(SimulatorConfig, 1)
    if cfg.double_refund_bug:
        # Intentionally planted flaw: isolated training mode ONLY. Does not
        # populate the secure unique key, so the oracle can reproduce it.
        r = Refund(booking_id=booking.id, amount_paise=payload.amount_paise,
                   idempotency_key=payload.idempotency_key)
        db.add(r); log_traffic(db, '/sim/bookings/{id}/refund', 'POST')
        db.commit(); db.refresh(r)
        return {'refund_id': r.id, 'amount_paise': r.amount_paise,
                'idempotent_replay': False}

    # The first write locks the booking row on PostgreSQL and takes SQLite's
    # single-writer lock. ALL secure refunds for a booking serialize BEFORE
    # checking the key and aggregate, including requests with DIFFERENT keys.
    # A separate nullable, unique safe key is a database-backed backstop.
    db.execute(update(Booking).where(Booking.id == booking_id)
               .values(status=Booking.status))
    existing = db.scalar(select(Refund).where(
        Refund.booking_id == booking.id,
        Refund.idempotency_key == payload.idempotency_key
    ).order_by(Refund.id.asc()))
    if existing:
        if existing.amount_paise != payload.amount_paise:
            raise HTTPException(409, 'Idempotency key reused with a different amount')
        db.commit()
        return {'refund_id': existing.id, 'amount_paise': existing.amount_paise,
                'idempotent_replay': True}
    refunded = db.scalar(select(func.coalesce(func.sum(Refund.amount_paise), 0))
                         .where(Refund.booking_id == booking.id)) or 0
    if refunded + payload.amount_paise > booking.amount_paise:
        raise HTTPException(409, 'Refund exceeds paid booking amount')
    r = Refund(booking_id=booking.id, amount_paise=payload.amount_paise,
               idempotency_key=payload.idempotency_key,
               safe_idempotency_key=payload.idempotency_key)
    db.add(r)
    log_traffic(db, '/sim/bookings/{id}/refund', 'POST')
    db.commit(); db.refresh(r)
    return {'refund_id': r.id, 'amount_paise': r.amount_paise,
            'idempotent_replay': False}


@router.get("/bookings/{booking_id}/refund-total")
def refund_total(booking_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    booking = get_booking(db, booking_id)
    ownership(booking, user)
    value = db.scalar(select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(Refund.booking_id == booking.id)) or 0
    return {"booking_id": booking.id, "paid_paise": booking.amount_paise, "refunded_paise": value}


@router.get("/legacy/v1/bookings/{booking_id}")
def read_legacy(booking_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    booking = get_booking(db, booking_id)
    cfg = db.get(SimulatorConfig, 1)
    if not cfg.legacy_bypass_bug:
        ownership(booking, user)
    log_traffic(db, "/sim/legacy/v1/bookings/{id}")
    db.commit()
    return obj(booking, "id", "agency_id", "itinerary", "amount_paise")


@router.get("/partner/shortcut/{booking_id}")
def partner_shortcut(booking_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    booking = get_booking(db, booking_id)
    ownership(booking, user)
    return {"booking_id": booking.id, "state": booking.status}


@router.post("/internal/clone", include_in_schema=False)
def clone(payload: CloneIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    original = get_booking(db, payload.original_booking_id)
    b = Booking(agency_id=original.agency_id, itinerary=original.itinerary,
                amount_paise=original.amount_paise, universe=payload.universe,
                original_booking_id=original.id)
    db.add(b); db.commit(); db.refresh(b)
    return obj(b, "id", "agency_id", "amount_paise", "universe")


# Hotel/flight labels and all values below are fictional, created for this demo.
OFFERS = {
    "DXB-102": {"destination": "Dubai", "hotel": "Downtown Palm Hotel", "nights": 2, "price_paise": 1000000, "available": True},
    "SIN-201": {"destination": "Singapore", "hotel": "Bay Harbour Suites", "nights": 1, "price_paise": 760000, "available": True},
    "BKK-305": {"destination": "Bangkok", "hotel": "Riverside Boutique", "nights": 3, "price_paise": 1240000, "available": True},
}


@router.get("/catalog")
def catalog(user: User = Depends(current_user)):
    return [{"offer_id": key, **value} for key, value in OFFERS.items()]


@router.post("/holds")
def create_hold(payload: NewHoldIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    offer = OFFERS[payload.offer_id]
    if not offer["available"]:
        raise HTTPException(409, "Offer no longer available")
    if user.role == "admin":
        agency_id = payload.agency_id or 1
        from ..models import Agency
        if db.get(Agency, agency_id) is None:
            raise HTTPException(422, "Unknown synthetic agency")
    else:
        if payload.agency_id is not None and payload.agency_id != user.agency_id:
            raise HTTPException(403, "Cannot create holds for another agency")
        agency_id = user.agency_id
    b = Booking(agency_id=agency_id, itinerary=f"{offer['hotel']} - {offer['nights']} nights",
                amount_paise=offer['price_paise'], status='held', universe='baseline')
    db.add(b); db.flush()
    db.add(Traffic(path_template='/sim/holds', method='POST', source='business'))
    db.commit(); db.refresh(b)
    return obj(b, 'id', 'agency_id', 'status', 'amount_paise', 'itinerary')


@router.post("/bookings/{booking_id}/pay")
def pay_test_booking(booking_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    booking = get_booking(db, booking_id)
    ownership(booking, user)
    if booking.status == 'confirmed':
        return {'booking_id': booking.id, 'status': 'confirmed', 'duplicate_charge': False, 'idempotent_replay': True}
    if booking.status != 'held':
        raise HTTPException(409, 'Only held bookings can be paid')
    booking.status = 'confirmed'  # Synthetic payment ledger only, no card processor.
    db.add(Traffic(path_template='/sim/bookings/{id}/pay', method='POST', source='business'))
    db.commit()
    return {'booking_id': booking.id, 'status': 'confirmed', 'duplicate_charge': False, 'idempotent_replay': False}


@router.post("/bookings/{booking_id}/cancel")
def cancel_test_booking(booking_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    booking = get_booking(db, booking_id)
    ownership(booking, user)
    if booking.status == 'cancelled':
        return {'booking_id': booking.id, 'status': 'cancelled', 'idempotent_replay': True}
    if booking.status not in ('held','confirmed'):
        raise HTTPException(409, 'Booking cannot be cancelled')
    booking.status = 'cancelled'
    db.add(Traffic(path_template='/sim/bookings/{id}/cancel', method='POST', source='business'))
    db.commit()
    return {'booking_id': booking.id, 'status': 'cancelled', 'idempotent_replay': False}
