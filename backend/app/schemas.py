from pydantic import BaseModel, Field, ConfigDict
from typing import Literal


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LoginIn(StrictRequest):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class DeployIn(StrictRequest):
    scenario: Literal["cross_agency", "double_refund", "legacy_bypass", "all", "secure"]
    auto_scan: bool = True


class RefundIn(StrictRequest):
    amount_paise: int = Field(gt=0, le=10_000_000)
    idempotency_key: str = Field(min_length=3, max_length=140)


class CloneIn(StrictRequest):
    original_booking_id: int = Field(gt=0)
    universe: str = Field(min_length=1, max_length=80)


class PauseIn(StrictRequest):
    paused: bool


class TicketDecisionIn(StrictRequest):
    decision: Literal["approve", "reject"]
    note: str = Field(min_length=8, max_length=500)


class NewHoldIn(StrictRequest):
    offer_id: Literal["DXB-102", "SIN-201", "BKK-305"]
    agency_id: int | None = Field(default=None, gt=0)

