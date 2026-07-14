"""Decides whether a re-observed apartment's price/status actually changed enough to
write a new history row — see docs/07_Analysis_Engine.md "Write Sequence". Keeping this
decision separate from storage/apartment_repository.py is what keeps storage/ free of
business rules about *when* to write (docs/01_System_Architecture.md).
"""

from __future__ import annotations

from src.storage.models import Apartment


def price_changed(existing: Apartment, new_price: float) -> bool:
    return existing.current_price != new_price


def status_changed(existing: Apartment, new_status: str) -> bool:
    return existing.current_status != new_status
