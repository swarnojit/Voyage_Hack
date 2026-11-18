"""All tables contain only fictional booking/agency/security demonstration data."""
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, DateTime, Integer, Boolean, Text, JSON, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Agency(Base):
    __tablename__ = "agencies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    pw_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(30))
    agency_id: Mapped[int | None] = mapped_column(ForeignKey("agencies.id"), nullable=True)


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agencies.id"), index=True)
    itinerary: Mapped[str] = mapped_column(String(140))
    amount_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    universe: Mapped[str] = mapped_column(String(90), default="baseline")
    original_booking_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Refund(Base):
    __tablename__ = "refunds"
    # Only normal-path refunds populate this key. Deliberately vulnerable
    # training refunds use NULL, keeping the planted regression demonstrable.
    __table_args__ = (UniqueConstraint('booking_id', 'safe_idempotency_key',
                                      name='uq_secure_refund_booking_key'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(140))
    safe_idempotency_key: Mapped[str | None] = mapped_column(String(140), nullable=True)
    amount_paise: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SimulatorConfig(Base):
    __tablename__ = "simulator_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    cross_agency_bug: Mapped[bool] = mapped_column(Boolean, default=False)
    double_refund_bug: Mapped[bool] = mapped_column(Boolean, default=False)
    legacy_bypass_bug: Mapped[bool] = mapped_column(Boolean, default=False)
    scanning_paused: Mapped[bool] = mapped_column(Boolean, default=False)


class Deploy(Base):
    __tablename__ = "deploys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    scenario: Mapped[str] = mapped_column(String(50))
    changed_routes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScanRun(Base):
    __tablename__ = "scan_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deploy_id: Mapped[int | None] = mapped_column(ForeignKey("deploys.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tests_run: Mapped[int] = mapped_column(Integer, default=0)
    requests_sent: Mapped[int] = mapped_column(Integer, default=0)
    confirmed: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"))
    fingerprint: Mapped[str] = mapped_column(String(100), index=True)
    kind: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(160))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(25), default="confirmed")
    owner: Mapped[str] = mapped_column(String(80), default="Travel Platform Security")
    description: Mapped[str] = mapped_column(Text)
    proof: Mapped[dict] = mapped_column(JSON)
    recommended_fix: Mapped[str] = mapped_column(Text)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    retested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"))
    test: Mapped[str] = mapped_column(String(60))
    universe: Mapped[str] = mapped_column(String(40))
    passed: Mapped[bool] = mapped_column(Boolean)
    expected: Mapped[str] = mapped_column(String(150))
    observed: Mapped[str] = mapped_column(String(150))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Traffic(Base):
    __tablename__ = "traffic"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path_template: Mapped[str] = mapped_column(String(150))
    method: Mapped[str] = mapped_column(String(12))
    source: Mapped[str] = mapped_column(String(30), default="business")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Inventory(Base):
    __tablename__ = "api_inventory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path_template: Mapped[str] = mapped_column(String(150), unique=True)
    method: Mapped[str] = mapped_column(String(12), default="GET")
    classification: Mapped[str] = mapped_column(String(20))
    documented: Mapped[bool] = mapped_column(Boolean)
    seen_in_logs: Mapped[bool] = mapped_column(Boolean)
    last_legitimate_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner: Mapped[str] = mapped_column(String(80))
    recommendation: Mapped[str] = mapped_column(String(240))


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(100))
    actor: Mapped[str] = mapped_column(String(80))
    result: Mapped[str] = mapped_column(String(40))
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), unique=True)
    state: Mapped[str] = mapped_column(String(48), default="needs-human-review")
    owner: Mapped[str] = mapped_column(String(80))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RunEvent(Base):
    __tablename__ = "run_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), index=True)
    phase: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(20), default="info")
    title: Mapped[str] = mapped_column(String(180))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelSnapshot(Base):
    """Immutable evaluation information for reproducible local model builds."""
    __tablename__ = 'model_snapshots'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    training_source: Mapped[str] = mapped_column(String(100))
    metrics: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelPrediction(Base):
    """Auditable ML inference metadata: no real customer text or network data."""
    __tablename__ = 'model_predictions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey('scan_runs.id'), index=True, nullable=True)
    actor: Mapped[str] = mapped_column(String(80))
    case: Mapped[str] = mapped_column(String(70), default='interactive-preview')
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    feature_vector: Mapped[dict] = mapped_column(JSON)
    risk_score: Mapped[float] = mapped_column(Float)
    novelty_score: Mapped[float] = mapped_column(Float)
    predicted_class: Mapped[str] = mapped_column(String(50))
    class_confidence: Mapped[float] = mapped_column(Float)
    explanation: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
