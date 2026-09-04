"""Pure order pickup/drop-off workflow with bounded cargo and audit state."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from .models import BehaviorContractError, make_advisory_snapshot, token, uint64


DELIVERY_STATES = frozenset(
    {
        "ORDER_READY",
        "EN_ROUTE_PICKUP",
        "PICKUP_DOCK_REQUIRED",
        "PICKUP_CONFIRMATION_REQUIRED",
        "CARGO_UPDATED",
        "EN_ROUTE_DESTINATION",
        "DROPOFF_DOCK_REQUIRED",
        "DROPOFF_CONFIRMATION_REQUIRED",
        "ORDER_COMPLETE",
        "PAUSED",
        "FAILED",
    }
)


class DeliveryWorkflow:
    def __init__(self, order: Mapping[str, Any]) -> None:
        lines = order.get("lines") if isinstance(order, Mapping) else None
        total = order.get("total_quantity") if isinstance(order, Mapping) else None
        destination = (
            order.get("destination_id") if isinstance(order, Mapping) else None
        )
        if (
            not isinstance(lines, list)
            or not lines
            or isinstance(total, bool)
            or not isinstance(total, int)
            or not 1 <= total <= 5
        ):
            raise BehaviorContractError("normalized order is invalid")
        self._destination_id = token(destination, "destination")
        quantities: dict[str, int] = {}
        venue_order: list[str] = []
        for line in sorted(lines, key=lambda item: int(item.get("sequence", 0))):
            venue = token(line.get("restaurant_id"), "restaurant")
            quantity = line.get("quantity")
            if (
                isinstance(quantity, bool)
                or not isinstance(quantity, int)
                or not 1 <= quantity <= 5
            ):
                raise BehaviorContractError("order quantity is invalid")
            if venue not in quantities:
                venue_order.append(venue)
                quantities[venue] = 0
            quantities[venue] += quantity
        if sum(quantities.values()) != total or not 1 <= len(venue_order) <= 5:
            raise BehaviorContractError("order totals are inconsistent")
        self._quantities = quantities
        self._remaining = venue_order
        self._picked: list[str] = []
        self._cargo_count = 0
        self._state = "ORDER_READY"
        self._reason_codes: list[str] = []
        self._audit: list[dict[str, Any]] = []
        self._last_updated_ns = 0
        self._state_before_pause = "ORDER_READY"
        self._resume_requires_evidence = False

    @property
    def state(self) -> str:
        return self._state

    @property
    def cargo_count(self) -> int:
        return self._cargo_count

    @property
    def next_venue_id(self) -> str | None:
        return self._remaining[0] if self._remaining else None

    def audit(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._audit)

    def _record(self, event: str, now_ns: int, *, venue_id: str | None = None) -> None:
        entry = {
            "event": event,
            "state": self._state,
            "updated_at_ns": now_ns,
            "venue_id": venue_id,
        }
        self._audit.append(entry)
        self._audit = self._audit[-32:]

    def _fail(self, reason: str, now_ns: int, event: str) -> dict[str, Any]:
        self._state = "FAILED"
        self._reason_codes = [reason]
        self._record(event, now_ns)
        return self.snapshot(now_ns)

    def transition(
        self, event: str, *, now_ns: int, payload: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        now = uint64(now_ns, "now_ns")
        data = dict(payload or {})
        if now < self._last_updated_ns:
            return self._fail("TIME_ROLLBACK", self._last_updated_ns, event)
        self._last_updated_ns = now
        try:
            event_name = token(event, "delivery event")
        except BehaviorContractError:
            return self._fail("EVENT_INVALID", now, "EVENT_INVALID")
        self._reason_codes = []
        if event_name == "RESTART":
            if self._state not in {"ORDER_COMPLETE", "FAILED"}:
                self._state_before_pause = self._state
                self._state = "PAUSED"
                self._resume_requires_evidence = True
                self._reason_codes = ["SERVER_RESTART"]
            self._record(event_name, now)
            return self.snapshot(now)
        if event_name == "PAUSE":
            if self._state not in {"ORDER_COMPLETE", "FAILED", "PAUSED"}:
                self._state_before_pause = self._state
                self._state = "PAUSED"
                self._reason_codes = ["OPERATOR_PAUSED"]
            self._record(event_name, now)
            return self.snapshot(now)
        if event_name == "RESUME":
            if self._state != "PAUSED":
                return self._fail("INVALID_TRANSITION", now, event_name)
            if data != {"fresh_evidence": True, "operator_confirmed": True}:
                self._reason_codes = ["EXPLICIT_RESUME_REQUIRED"]
                self._record(event_name, now)
                return self.snapshot(now)
            self._state = self._state_before_pause
            self._resume_requires_evidence = False
            self._record(event_name, now)
            return self.snapshot(now)
        if self._state in {"FAILED", "ORDER_COMPLETE", "PAUSED"}:
            return self._fail("INVALID_TRANSITION", now, event_name)
        if event_name.startswith("DROPOFF") or event_name == "ARRIVE_DESTINATION":
            if self._remaining:
                return self._fail("DROPOFF_BEFORE_PICKUP", now, event_name)
        if event_name == "START" and self._state == "ORDER_READY":
            self._state = "EN_ROUTE_PICKUP"
        elif event_name == "ARRIVE_PICKUP" and self._state == "EN_ROUTE_PICKUP":
            try:
                venue = self._payload_venue(data)
            except BehaviorContractError:
                return self._fail("PICKUP_PAYLOAD_INVALID", now, event_name)
            if venue != self.next_venue_id:
                return self._fail("PICKUP_SEQUENCE_MISMATCH", now, event_name)
            self._state = "PICKUP_DOCK_REQUIRED"
        elif event_name == "PICKUP_DOCKED" and self._state == "PICKUP_DOCK_REQUIRED":
            self._state = "PICKUP_CONFIRMATION_REQUIRED"
        elif event_name == "CONFIRM_PICKUP":
            try:
                venue = self._payload_venue(data)
            except BehaviorContractError:
                return self._fail("PICKUP_PAYLOAD_INVALID", now, event_name)
            if venue in self._picked:
                self._reason_codes = ["DUPLICATE_PICKUP_CONFIRMATION"]
                self._record(event_name, now, venue_id=venue)
                return self.snapshot(now)
            if (
                self._state != "PICKUP_CONFIRMATION_REQUIRED"
                or venue != self.next_venue_id
            ):
                return self._fail("PICKUP_CONFIRMATION_INVALID", now, event_name)
            quantity = self._quantities[venue]
            if self._cargo_count + quantity > 5:
                return self._fail("CARGO_CAPACITY_EXCEEDED", now, event_name)
            self._cargo_count += quantity
            self._picked.append(venue)
            self._remaining.pop(0)
            self._state = "CARGO_UPDATED"
        elif event_name == "DEPART_PICKUP" and self._state == "CARGO_UPDATED":
            self._state = (
                "EN_ROUTE_PICKUP" if self._remaining else "EN_ROUTE_DESTINATION"
            )
        elif (
            event_name == "ARRIVE_DESTINATION" and self._state == "EN_ROUTE_DESTINATION"
        ):
            if data not in ({}, {"destination_id": self._destination_id}):
                return self._fail("DESTINATION_MISMATCH", now, event_name)
            self._state = "DROPOFF_DOCK_REQUIRED"
        elif event_name == "DROPOFF_DOCKED" and self._state == "DROPOFF_DOCK_REQUIRED":
            self._state = "DROPOFF_CONFIRMATION_REQUIRED"
        elif (
            event_name == "CONFIRM_DROPOFF"
            and self._state == "DROPOFF_CONFIRMATION_REQUIRED"
        ):
            if data not in ({}, {"destination_id": self._destination_id}):
                return self._fail("DESTINATION_MISMATCH", now, event_name)
            self._cargo_count = 0
            self._state = "ORDER_COMPLETE"
        elif event_name == "FAIL":
            return self._fail("EXTERNAL_ACTION_FAILED", now, event_name)
        else:
            return self._fail("INVALID_TRANSITION", now, event_name)
        venue_id = (
            data.get("venue_id") if isinstance(data.get("venue_id"), str) else None
        )
        self._record(event_name, now, venue_id=venue_id)
        return self.snapshot(now)

    @staticmethod
    def _payload_venue(payload: Mapping[str, Any]) -> str:
        if set(payload) != {"venue_id"}:
            raise BehaviorContractError("pickup payload schema is invalid")
        return token(payload.get("venue_id"), "pickup venue")

    def snapshot(self, now_ns: int | None = None) -> dict[str, Any]:
        now = self._last_updated_ns if now_ns is None else uint64(now_ns, "now_ns")
        advisory = "HOLD"
        if self._state == "PICKUP_CONFIRMATION_REQUIRED":
            advisory = "PICKUP_CONFIRMATION_REQUIRED"
        elif self._state == "DROPOFF_CONFIRMATION_REQUIRED":
            advisory = "DROPOFF_CONFIRMATION_REQUIRED"
        elif self._state == "ORDER_COMPLETE":
            advisory = "COMPLETE"
        elif self._state == "FAILED":
            advisory = "FAULT"
        elif self._state in {"EN_ROUTE_PICKUP", "EN_ROUTE_DESTINATION"}:
            advisory = "PROCEED_RECOMMENDED"
        return make_advisory_snapshot(
            behavior="DELIVERY",
            state=self._state,
            advisory=advisory,
            ready_for_manual_proceed=False,
            autonomous_edge_ready=False,
            reason_codes=self._reason_codes,
            requirements={
                "cargo_count": self._cargo_count,
                "cargo_capacity": 5,
                "remaining_restaurants": len(self._remaining),
                "next_venue": self.next_venue_id,
                "destination": self._destination_id,
                "resume_requires_evidence": self._resume_requires_evidence,
            },
            updated_at_ns=now,
        )


__all__ = ["DELIVERY_STATES", "DeliveryWorkflow"]
