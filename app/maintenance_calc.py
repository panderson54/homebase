"""Pure due-date math for maintenance tasks, consumables, and pro service.

No Flask/DB imports — unit-testable in isolation, matching ledger_finance's
convention for pure calculation modules (dividend_calc.py, projections.py).
"""
from datetime import date, timedelta

_DAYS_PER_UNIT = {
    'days': 1,
    'weeks': 7,
    'months': 30,
    'years': 365,
}


def add_interval(base_date, value, unit):
    """Return base_date + (value * unit), approximating months/years as 30/365 days.

    Calendar-exact month/year arithmetic isn't worth the added complexity here:
    maintenance intervals are advisory ("every 3 months"), not billing dates.
    """
    if base_date is None or value is None or unit is None:
        return None
    days_per_unit = _DAYS_PER_UNIT.get(unit)
    if days_per_unit is None:
        raise ValueError(f'Unknown frequency unit: {unit!r}')
    return base_date + timedelta(days=value * days_per_unit)


def compute_next_due(last_date, value, unit):
    """Next due date given the last completed/replaced/serviced date and a frequency."""
    return add_interval(last_date, value, unit)


def due_bucket(next_due_at, today=None, lead_days=14):
    """Classify a due date as 'overdue', 'due_soon', 'ok', or 'none' (no due date set)."""
    if next_due_at is None:
        return 'none'
    today = today or date.today()
    if next_due_at < today:
        return 'overdue'
    if next_due_at <= today + timedelta(days=lead_days):
        return 'due_soon'
    return 'ok'
