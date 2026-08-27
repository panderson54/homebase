from datetime import date

import pytest

from app.maintenance_calc import add_interval, compute_next_due, due_bucket


class TestAddInterval:
    def test_days(self):
        assert add_interval(date(2026, 1, 1), 10, 'days') == date(2026, 1, 11)

    def test_weeks(self):
        assert add_interval(date(2026, 1, 1), 2, 'weeks') == date(2026, 1, 15)

    def test_months(self):
        assert add_interval(date(2026, 1, 1), 1, 'months') == date(2026, 1, 31)

    def test_years(self):
        assert add_interval(date(2026, 1, 1), 1, 'years') == date(2027, 1, 1)

    def test_none_inputs_return_none(self):
        assert add_interval(None, 1, 'days') is None
        assert add_interval(date(2026, 1, 1), None, 'days') is None
        assert add_interval(date(2026, 1, 1), 1, None) is None

    def test_unknown_unit_raises(self):
        with pytest.raises(ValueError):
            add_interval(date(2026, 1, 1), 1, 'fortnights')


class TestComputeNextDue:
    def test_matches_add_interval(self):
        assert compute_next_due(date(2026, 1, 1), 3, 'months') == add_interval(date(2026, 1, 1), 3, 'months')


class TestDueBucket:
    def test_none_due_date(self):
        assert due_bucket(None) == 'none'

    def test_overdue(self):
        today = date(2026, 6, 15)
        assert due_bucket(date(2026, 6, 1), today=today) == 'overdue'

    def test_due_soon_within_lead_days(self):
        today = date(2026, 6, 15)
        assert due_bucket(date(2026, 6, 20), today=today, lead_days=14) == 'due_soon'

    def test_ok_beyond_lead_days(self):
        today = date(2026, 6, 15)
        assert due_bucket(date(2026, 8, 1), today=today, lead_days=14) == 'ok'

    def test_boundary_exactly_on_lead_days_is_due_soon(self):
        today = date(2026, 6, 15)
        assert due_bucket(date(2026, 6, 29), today=today, lead_days=14) == 'due_soon'

    def test_boundary_today_is_due_soon_not_overdue(self):
        today = date(2026, 6, 15)
        assert due_bucket(today, today=today) == 'due_soon'
