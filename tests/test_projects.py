from datetime import date
from decimal import Decimal

import pytest

from app import project_service, vendor_quote_service
from app.models import Household, QuoteStatus, Vendor, VendorQuote, Zone
from app.project_service import ProjectError


@pytest.fixture
def deck_quote(db, vendor):
    zone = Zone(household_id=vendor.household_id, name='Deck')
    db.session.add(zone)
    db.session.commit()
    return vendor_quote_service.create(
        vendor, quote_number='D-1', amount=Decimal('12803.33'), description='Deck resurfacing',
        zone=zone, status='accepted',
    )


@pytest.fixture
def pending_quote(db, vendor):
    return vendor_quote_service.create(vendor, quote_number='P-1', amount=Decimal('10'))


@pytest.fixture
def foreign_accepted_quote(db):
    other = Household(name='Other Home')
    db.session.add(other)
    db.session.commit()
    foreign_vendor = Vendor(household_id=other.id, name='Their Fence Co', vendor_type='other')
    db.session.add(foreign_vendor)
    db.session.commit()
    return vendor_quote_service.create(foreign_vendor, quote_number='F-1', status='accepted')


class TestProjectStages:
    def test_accepting_stamps_the_accepted_date_once(self, vendor, pending_quote):
        vendor_quote_service.accept(pending_quote)
        assert pending_quote.accepted_on == date.today()
        pending_quote.accepted_on = date(2026, 9, 14)
        vendor_quote_service.accept(pending_quote)
        assert pending_quote.accepted_on == date(2026, 9, 14)

    def test_creating_an_accepted_quote_stamps_the_date(self, deck_quote):
        assert deck_quote.accepted_on == date.today()

    def test_stage_is_the_furthest_dated_one(self, deck_quote):
        assert project_service.current_stage(deck_quote)[0] == 'accepted'
        deck_quote.scheduled_on = date(2026, 10, 20)
        assert project_service.current_stage(deck_quote)[0] == 'scheduled'
        assert project_service.next_stage(deck_quote)[0] == 'in_progress'

    def test_current_stage_defaults_to_accepted_for_undated_legacy_quotes(self, deck_quote):
        deck_quote.accepted_on = None
        assert project_service.current_stage(deck_quote)[0] == 'accepted'

    def test_advance_walks_every_stage_and_dates_each(self, deck_quote):
        for key, expected in [('deposit_paid', date(2026, 9, 21)), ('scheduled', date(2026, 10, 1)),
                              ('in_progress', date(2026, 10, 5)), ('done', date(2026, 10, 9))]:
            project_service.advance(deck_quote, expected)
            assert project_service.current_stage(deck_quote)[0] == key
        assert deck_quote.completed_on == date(2026, 10, 9)
        assert project_service.next_stage(deck_quote) is None
        with pytest.raises(ProjectError):
            project_service.advance(deck_quote)

    def test_advance_defaults_to_today(self, deck_quote):
        project_service.advance(deck_quote)
        assert deck_quote.deposit_paid_on == date.today()

    def test_non_accepted_quote_cannot_be_tracked(self, pending_quote):
        with pytest.raises(ProjectError):
            project_service.advance(pending_quote)
        with pytest.raises(ProjectError):
            project_service.set_dates(pending_quote, {})

    def test_active_projects_excludes_done_pending_and_other_households(
        self, vendor, deck_quote, pending_quote, foreign_accepted_quote,
    ):
        done = vendor_quote_service.create(vendor, quote_number='D-2', status='accepted')
        project_service.advance(done)  # deposit
        done.completed_on = date.today()
        assert project_service.active_projects(vendor.household_id) == [deck_quote]


class TestProjectRoutes:
    def test_edit_page_shows_project_form_only_for_accepted_quotes(self, logged_in_client, vendor, deck_quote, pending_quote):
        accepted = logged_in_client.get(f'/vendors/{vendor.id}/quotes/{deck_quote.id}/edit').data.decode()
        assert 'Save project dates' in accepted
        pending = logged_in_client.get(f'/vendors/{vendor.id}/quotes/{pending_quote.id}/edit').data.decode()
        assert 'Save project dates' not in pending

    def test_update_saves_and_clears_stage_dates(self, logged_in_client, db, vendor, deck_quote):
        url = f'/vendors/{vendor.id}/quotes/{deck_quote.id}/project'
        resp = logged_in_client.post(url, data={
            'accepted_on': '2026-09-14', 'deposit_paid_on': '2026-09-21', 'scheduled_on': '2026-10-20',
        })
        assert resp.status_code == 302
        db.session.refresh(deck_quote)
        assert (deck_quote.accepted_on, deck_quote.deposit_paid_on, deck_quote.scheduled_on) == (
            date(2026, 9, 14), date(2026, 9, 21), date(2026, 10, 20))
        assert deck_quote.started_on is None

        logged_in_client.post(url, data={'accepted_on': '2026-09-14'})
        db.session.refresh(deck_quote)
        assert deck_quote.deposit_paid_on is None and deck_quote.scheduled_on is None

    def test_update_malformed_date_changes_nothing(self, logged_in_client, db, vendor, deck_quote):
        before = deck_quote.accepted_on
        resp = logged_in_client.post(
            f'/vendors/{vendor.id}/quotes/{deck_quote.id}/project', data={'accepted_on': 'soon'},
            follow_redirects=True,
        )
        assert 'YYYY-MM-DD' in resp.data.decode()
        db.session.refresh(deck_quote)
        assert deck_quote.accepted_on == before

    def test_update_on_pending_quote_is_rejected(self, logged_in_client, db, vendor, pending_quote):
        logged_in_client.post(
            f'/vendors/{vendor.id}/quotes/{pending_quote.id}/project', data={'deposit_paid_on': '2026-09-21'},
        )
        db.session.refresh(pending_quote)
        assert pending_quote.deposit_paid_on is None

    def test_advance_records_the_next_stage_and_returns_to_dashboard(self, logged_in_client, db, vendor, deck_quote):
        resp = logged_in_client.post(
            f'/vendors/{vendor.id}/quotes/{deck_quote.id}/project/advance',
            data={'on': '2026-09-21', 'return_to': 'dashboard'},
        )
        assert resp.status_code == 302 and resp.headers['Location'].endswith('/dashboard')
        db.session.refresh(deck_quote)
        assert deck_quote.deposit_paid_on == date(2026, 9, 21)

    def test_advance_malformed_date_changes_nothing(self, logged_in_client, db, vendor, deck_quote):
        logged_in_client.post(f'/vendors/{vendor.id}/quotes/{deck_quote.id}/project/advance', data={'on': 'x'})
        db.session.refresh(deck_quote)
        assert deck_quote.deposit_paid_on is None

    @pytest.mark.parametrize('suffix', ['project', 'project/advance'])
    def test_other_households_quote_is_404(self, logged_in_client, foreign_accepted_quote, suffix):
        foreign_vendor_id = foreign_accepted_quote.vendor_id
        resp = logged_in_client.post(f'/vendors/{foreign_vendor_id}/quotes/{foreign_accepted_quote.id}/{suffix}')
        assert resp.status_code == 404

    def test_quote_under_wrong_vendor_is_404(self, logged_in_client, db, household, deck_quote):
        stranger = Vendor(household_id=household.id, name='Someone Else', vendor_type='other')
        db.session.add(stranger)
        db.session.commit()
        resp = logged_in_client.post(f'/vendors/{stranger.id}/quotes/{deck_quote.id}/project/advance')
        assert resp.status_code == 404


class TestProjectDashboard:
    def test_shows_active_project_stage_and_next_step(self, logged_in_client, vendor, deck_quote):
        project_service.advance(deck_quote, date(2026, 9, 21))
        page = logged_in_client.get('/dashboard').data.decode()
        assert 'Active projects' in page
        assert 'Deck resurfacing' in page
        assert 'Deposit paid · Sep 21, 2026' in page
        assert 'Next: Scheduled' in page

    def test_finished_and_pending_quotes_are_not_listed(self, logged_in_client, vendor, deck_quote, pending_quote):
        deck_quote.completed_on = date.today()
        page = logged_in_client.get('/dashboard').data.decode()
        assert 'Active projects' not in page
