import io
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app import document_service, vendor_quote_service
from app.context_export_service import build_context_markdown
from app.models import Appliance, Household, QuoteStatus, Vendor, VendorQuote, Zone
from app.vendor_quote_service import QuoteValidationError


def _pdf_bytes():
    return io.BytesIO(b'%PDF-1.4\n%fake quote\n')


@pytest.fixture
def other_vendor(db):
    other_household = Household(name='Other Home')
    db.session.add(other_household)
    db.session.commit()
    v = Vendor(household_id=other_household.id, name='Other Vendor', vendor_type='other')
    db.session.add(v)
    db.session.commit()
    return v


@pytest.fixture
def quote(db, vendor):
    return vendor_quote_service.create(vendor, quote_number='113170', amount=Decimal('315.07'))


@pytest.fixture
def rival_vendor(db, household):
    v = Vendor(household_id=household.id, name='AA Window', vendor_type='other')
    db.session.add(v)
    db.session.commit()
    return v


@pytest.fixture
def gutters(db, household):
    z = Zone(household_id=household.id, name='Gutters')
    db.session.add(z)
    db.session.commit()
    return z


@pytest.fixture
def furnace(db, household):
    a = Appliance(household_id=household.id, category='furnace', name='Furnace')
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def foreign_zone(db, other_vendor):
    z = Zone(household_id=other_vendor.household_id, name='Their gutters')
    db.session.add(z)
    db.session.commit()
    return z


class TestQuoteService:
    def test_create_defaults_to_pending(self, vendor):
        quote = vendor_quote_service.create(vendor, quote_number=' 113170 ', amount=Decimal('315.07'))
        assert quote.status == QuoteStatus.pending
        assert quote.quote_number == '113170'

    def test_create_requires_number_or_amount(self, vendor):
        with pytest.raises(QuoteValidationError):
            vendor_quote_service.create(vendor, quote_number='  ', description='Gutters')

    def test_create_rejects_negative_amount(self, vendor):
        with pytest.raises(QuoteValidationError):
            vendor_quote_service.create(vendor, amount=Decimal('-1'))

    def test_create_rejects_unknown_status(self, vendor):
        with pytest.raises(QuoteValidationError):
            vendor_quote_service.create(vendor, amount=Decimal('10'), status='maybe')

    def test_accept_declines_the_jobs_other_quotes_across_vendors(self, vendor, rival_vendor, gutters, furnace):
        gu_wi = vendor_quote_service.create(vendor, amount=Decimal('315.07'), zone=gutters)
        aa_window = vendor_quote_service.create(rival_vendor, amount=Decimal('400'), zone=gutters)
        other_job = vendor_quote_service.create(vendor, amount=Decimal('99'), appliance=furnace)
        unlinked = vendor_quote_service.create(vendor, amount=Decimal('50'))

        vendor_quote_service.accept(gu_wi)

        assert gu_wi.status == QuoteStatus.accepted
        assert aa_window.status == QuoteStatus.declined
        assert other_job.status == QuoteStatus.pending
        assert unlinked.status == QuoteStatus.pending
        assert gutters.pro_service_vendor == vendor
        assert furnace.pro_service_vendor is None

    def test_accepting_a_new_winner_demotes_the_old_one(self, vendor, rival_vendor, gutters):
        gu_wi = vendor_quote_service.create(vendor, amount=Decimal('315.07'), zone=gutters, status='accepted')
        aa_window = vendor_quote_service.create(rival_vendor, amount=Decimal('400'), zone=gutters)

        vendor_quote_service.accept(aa_window)

        assert gu_wi.status == QuoteStatus.declined
        assert gutters.pro_service_vendor == rival_vendor

    def test_accepting_an_unlinked_quote_declines_nothing(self, vendor, quote):
        other = vendor_quote_service.create(vendor, amount=Decimal('400'))
        vendor_quote_service.accept(other)
        assert other.status == QuoteStatus.accepted
        assert quote.status == QuoteStatus.pending

    def test_creating_an_accepted_linked_quote_declines_the_jobs_others(self, vendor, rival_vendor, gutters):
        pending = vendor_quote_service.create(vendor, amount=Decimal('315.07'), zone=gutters)
        accepted = vendor_quote_service.create(rival_vendor, amount=Decimal('400'), zone=gutters, status='accepted')
        assert accepted.status == QuoteStatus.accepted
        assert pending.status == QuoteStatus.declined

    def test_create_rejects_both_appliance_and_zone(self, vendor, gutters, furnace):
        with pytest.raises(QuoteValidationError):
            vendor_quote_service.create(vendor, amount=Decimal('1'), appliance=furnace, zone=gutters)

    def test_create_rejects_a_job_from_another_household(self, vendor, foreign_zone):
        with pytest.raises(QuoteValidationError):
            vendor_quote_service.create(vendor, amount=Decimal('1'), zone=foreign_zone)
        assert VendorQuote.query.count() == 0

    def test_link_and_unlink_keep_the_quote_on_its_vendor(self, vendor, quote, gutters):
        vendor_quote_service.link(quote, zone=gutters)
        assert gutters.quotes == [quote]

        vendor_quote_service.unlink(quote)
        assert gutters.quotes == []
        assert vendor.quotes == [quote]

    def test_link_requires_a_job(self, quote):
        with pytest.raises(QuoteValidationError):
            vendor_quote_service.link(quote)

    def test_linking_an_accepted_quote_makes_it_the_jobs_winner(self, vendor, rival_vendor, gutters):
        incumbent = vendor_quote_service.create(rival_vendor, amount=Decimal('400'), zone=gutters, status='accepted')
        arriving = vendor_quote_service.create(vendor, amount=Decimal('315.07'), status='accepted')

        vendor_quote_service.link(arriving, zone=gutters)

        assert incumbent.status == QuoteStatus.declined
        assert gutters.pro_service_vendor == vendor

    def test_deleting_the_job_unlinks_rather_than_deletes_quotes(self, db, vendor, quote, gutters):
        vendor_quote_service.link(quote, zone=gutters)
        db.session.delete(gutters)
        db.session.commit()
        db.session.refresh(quote)
        assert quote.zone_id is None
        assert vendor.quotes == [quote]

    def test_open_quotes_by_job_groups_pending_quotes_with_unlinked_last(
        self, vendor, rival_vendor, gutters, furnace, other_vendor,
    ):
        unlinked = vendor_quote_service.create(vendor, amount=Decimal('50'))
        gu_wi = vendor_quote_service.create(vendor, amount=Decimal('315.07'), zone=gutters)
        aa_window = vendor_quote_service.create(rival_vendor, amount=Decimal('400'), zone=gutters)
        vendor_quote_service.create(vendor, amount=Decimal('99'), appliance=furnace, status='declined')
        hvac = vendor_quote_service.create(rival_vendor, amount=Decimal('120'), appliance=furnace)
        vendor_quote_service.create(other_vendor, amount=Decimal('1'))

        groups = vendor_quote_service.open_quotes_by_job(vendor.household_id)

        assert [(g['appliance'], g['zone'], g['quotes']) for g in groups] == [
            (furnace, None, [hvac]),
            (None, gutters, [gu_wi, aa_window]),
            (None, None, [unlinked]),
        ]

    def test_unlinked_quotes_excludes_linked_and_foreign(self, vendor, quote, gutters, other_vendor):
        vendor_quote_service.create(vendor, amount=Decimal('1'), zone=gutters)
        vendor_quote_service.create(other_vendor, amount=Decimal('1'))
        assert vendor_quote_service.unlinked_quotes(vendor.household_id) == [quote]

    def test_is_expired(self, vendor):
        past = vendor_quote_service.create(vendor, amount=Decimal('1'), valid_until=date.today() - timedelta(days=1))
        today = vendor_quote_service.create(vendor, amount=Decimal('1'), valid_until=date.today())
        undated = vendor_quote_service.create(vendor, amount=Decimal('1'))
        assert past.is_expired
        assert not today.is_expired
        assert not undated.is_expired


class TestQuoteRoutes:
    def test_create_shows_on_vendor_page(self, logged_in_client, vendor):
        resp = logged_in_client.post(f'/vendors/{vendor.id}/quotes', data={
            'quote_number': '113170', 'description': 'Gutter cleaning', 'amount': '315.07',
            'valid_until': '2026-11-01', 'status': 'pending',
        })
        assert resp.status_code == 302
        quote = VendorQuote.query.filter_by(vendor_id=vendor.id).one()
        assert quote.amount == Decimal('315.07')
        assert quote.valid_until == date(2026, 11, 1)

        page = logged_in_client.get(f'/vendors/{vendor.id}').data
        assert b'113170' in page
        assert b'$315.07' in page
        assert b'>pending<' in page

    def test_create_with_pdf_attaches_it_to_the_quote(self, logged_in_client, vendor):
        logged_in_client.post(f'/vendors/{vendor.id}/quotes', data={
            'quote_number': '113170', 'file': (_pdf_bytes(), 'quote.pdf'),
        }, content_type='multipart/form-data')
        quote = VendorQuote.query.filter_by(vendor_id=vendor.id).one()
        docs = document_service.get_documents_for('vendor_quote', quote.id)
        assert [d.original_filename for d in docs] == ['quote.pdf']
        assert docs[0].doc_type.value == 'quote'
        assert document_service.get_documents_for('vendor', vendor.id) == []

    def test_create_invalid_input_is_rejected(self, logged_in_client, vendor):
        resp = logged_in_client.post(f'/vendors/{vendor.id}/quotes', data={'description': 'No numbers'})
        assert resp.status_code == 302
        assert VendorQuote.query.count() == 0

    def test_create_malformed_date_is_rejected(self, logged_in_client, vendor):
        logged_in_client.post(f'/vendors/{vendor.id}/quotes', data={'amount': '10', 'valid_until': 'soon'})
        assert VendorQuote.query.count() == 0

    def test_create_404_for_other_household(self, logged_in_client, other_vendor):
        resp = logged_in_client.post(f'/vendors/{other_vendor.id}/quotes', data={'amount': '10'})
        assert resp.status_code == 404
        assert VendorQuote.query.count() == 0

    def test_edit_page_renders(self, logged_in_client, vendor, quote):
        resp = logged_in_client.get(f'/vendors/{vendor.id}/quotes/{quote.id}/edit')
        assert resp.status_code == 200
        assert b'113170' in resp.data

    def test_edit_updates_fields(self, logged_in_client, db, vendor, quote):
        resp = logged_in_client.post(f'/vendors/{vendor.id}/quotes/{quote.id}/edit', data={
            'quote_number': '113171', 'amount': '299.00', 'valid_until': '', 'status': 'declined',
        })
        assert resp.status_code == 302
        db.session.refresh(quote)
        assert quote.quote_number == '113171'
        assert quote.amount == Decimal('299.00')
        assert quote.status == QuoteStatus.declined

    def test_edit_invalid_input_leaves_quote_unchanged(self, logged_in_client, db, vendor, quote):
        logged_in_client.post(f'/vendors/{vendor.id}/quotes/{quote.id}/edit', data={'status': 'bogus', 'amount': '1'})
        db.session.refresh(quote)
        assert quote.status == QuoteStatus.pending
        assert quote.amount == Decimal('315.07')

    def test_quote_under_wrong_vendor_is_404(self, logged_in_client, db, household, quote):
        sibling = Vendor(household_id=household.id, name='Sibling', vendor_type='other')
        db.session.add(sibling)
        db.session.commit()
        resp = logged_in_client.get(f'/vendors/{sibling.id}/quotes/{quote.id}/edit')
        assert resp.status_code == 404

    def test_other_household_quote_is_404(self, logged_in_client, other_vendor):
        foreign = vendor_quote_service.create(other_vendor, amount=Decimal('10'))
        for path in ('edit', 'accept', 'delete'):
            resp = logged_in_client.post(f'/vendors/{other_vendor.id}/quotes/{foreign.id}/{path}', data={'amount': '1'})
            assert resp.status_code == 404
        assert foreign.status == QuoteStatus.pending

    def test_accept_route_declines_the_jobs_others(self, logged_in_client, db, vendor, rival_vendor, gutters):
        gu_wi = vendor_quote_service.create(vendor, amount=Decimal('315.07'), zone=gutters)
        aa_window = vendor_quote_service.create(rival_vendor, amount=Decimal('400'), zone=gutters)
        resp = logged_in_client.post(f'/vendors/{rival_vendor.id}/quotes/{aa_window.id}/accept')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(f'/vendors/{rival_vendor.id}')
        db.session.refresh(gu_wi)
        db.session.refresh(aa_window)
        assert aa_window.status == QuoteStatus.accepted
        assert gu_wi.status == QuoteStatus.declined

    def test_accept_from_compare_returns_to_compare(self, logged_in_client, vendor, gutters):
        gu_wi = vendor_quote_service.create(vendor, amount=Decimal('315.07'), zone=gutters)
        resp = logged_in_client.post(
            f'/vendors/{vendor.id}/quotes/{gu_wi.id}/accept', data={'return_to': 'compare'},
        )
        assert resp.headers['Location'].endswith(f'/quotes/compare?target=zone:{gutters.id}')

    def test_create_with_target_links_the_quote(self, logged_in_client, vendor, gutters):
        logged_in_client.post(f'/vendors/{vendor.id}/quotes', data={'amount': '315.07', 'target': f'zone:{gutters.id}'})
        assert VendorQuote.query.one().zone_id == gutters.id

    def test_edit_can_change_and_clear_the_target(self, logged_in_client, db, vendor, quote, gutters, furnace):
        vendor_quote_service.link(quote, zone=gutters)
        logged_in_client.post(f'/vendors/{vendor.id}/quotes/{quote.id}/edit', data={
            'amount': '315.07', 'target': f'appliance:{furnace.id}',
        })
        db.session.refresh(quote)
        assert (quote.appliance_id, quote.zone_id) == (furnace.id, None)

        logged_in_client.post(f'/vendors/{vendor.id}/quotes/{quote.id}/edit', data={'amount': '315.07', 'target': ''})
        db.session.refresh(quote)
        assert quote.job is None

    def test_delete_removes_quote_and_its_documents(self, logged_in_client, vendor, quote):
        document_service.save_and_link(
            vendor.household_id, 'vendor_quote', quote.id, 'quote', external_url='https://example.com/q.pdf',
        )
        resp = logged_in_client.post(f'/vendors/{vendor.id}/quotes/{quote.id}/delete')
        assert resp.status_code == 302
        assert VendorQuote.query.count() == 0
        assert document_service.get_documents_for('vendor_quote', quote.id) == []

    def test_document_upload_and_remove(self, logged_in_client, vendor, quote):
        resp = logged_in_client.post(f'/vendors/{vendor.id}/quotes/{quote.id}/documents', data={
            'file': (_pdf_bytes(), 'gu-wi.pdf'),
        }, content_type='multipart/form-data')
        assert resp.status_code == 302
        docs = document_service.get_documents_for('vendor_quote', quote.id)
        assert len(docs) == 1

        logged_in_client.post(f'/vendors/{vendor.id}/quotes/{quote.id}/documents/{docs[0].id}/delete')
        assert document_service.get_documents_for('vendor_quote', quote.id) == []

    def test_document_upload_requires_file_or_link(self, logged_in_client, vendor, quote):
        logged_in_client.post(f'/vendors/{vendor.id}/quotes/{quote.id}/documents', data={})
        assert document_service.get_documents_for('vendor_quote', quote.id) == []

    def test_document_upload_404_for_other_household(self, logged_in_client, other_vendor):
        foreign = vendor_quote_service.create(other_vendor, amount=Decimal('10'))
        resp = logged_in_client.post(f'/vendors/{other_vendor.id}/quotes/{foreign.id}/documents', data={
            'external_url': 'https://example.com/q.pdf',
        })
        assert resp.status_code == 404


class TestQuoteExport:
    def test_linked_quote_and_chosen_vendor_are_exported(self, household, vendor, gutters):
        vendor_quote_service.create(vendor, quote_number='113170', amount=Decimal('315.07'), zone=gutters,
                                    status='accepted')
        markdown = build_context_markdown(household)
        assert '#113170 — $315.07 [accepted] — for Gutters' in markdown
        assert f'- Chosen pro-service vendor: {vendor.name}' in markdown

    def test_vendor_section_lists_quotes(self, household, vendor):
        vendor_quote_service.create(
            vendor, quote_number='113170', amount=Decimal('315.07'), valid_until=date(2026, 11, 1),
            description='Gutter cleaning',
        )
        vendors_section = build_context_markdown(household).split('## Vendors')[1]
        assert '#113170 — $315.07 — valid until 2026-11-01 [pending]' in vendors_section
        assert 'Gutter cleaning' in vendors_section


class TestJobQuoteRoutes:
    def test_compare_shows_open_and_decided_quotes(self, logged_in_client, vendor, rival_vendor, gutters):
        vendor_quote_service.create(vendor, quote_number='113170', amount=Decimal('315.07'), zone=gutters)
        vendor_quote_service.create(rival_vendor, amount=Decimal('400'), description='+ tax', zone=gutters)
        vendor_quote_service.create(rival_vendor, quote_number='OLD-1', amount=Decimal('500'), zone=gutters,
                                    status='declined')
        resp = logged_in_client.get(f'/quotes/compare?target=zone:{gutters.id}')
        assert resp.status_code == 200
        page = resp.data.decode()
        assert '$315.07' in page and '$400.00' in page and '+ tax' in page
        assert 'Open <span class="text-muted">(2)' in page
        assert 'Decided <span class="text-muted">(1)' in page
        assert 'OLD-1' in page

    @pytest.mark.parametrize('target', ['', 'zone:abc', 'garage:1', 'zone:9999'])
    def test_compare_404_for_missing_or_malformed_target(self, logged_in_client, target):
        assert logged_in_client.get(f'/quotes/compare?target={target}').status_code == 404

    def test_compare_404_for_other_households_job(self, logged_in_client, foreign_zone):
        assert logged_in_client.get(f'/quotes/compare?target=zone:{foreign_zone.id}').status_code == 404

    def test_link_existing_quote_to_zone(self, logged_in_client, db, quote, gutters):
        resp = logged_in_client.post(f'/zones/{gutters.id}/quotes/link', data={'quote_id': quote.id})
        assert resp.status_code == 302
        db.session.refresh(quote)
        assert quote.zone_id == gutters.id

    def test_link_existing_quote_to_appliance(self, logged_in_client, db, quote, furnace):
        logged_in_client.post(f'/appliances/{furnace.id}/quotes/link', data={'quote_id': quote.id})
        db.session.refresh(quote)
        assert quote.appliance_id == furnace.id

    def test_link_without_a_quote_is_rejected(self, logged_in_client, gutters):
        resp = logged_in_client.post(f'/zones/{gutters.id}/quotes/link', data={'quote_id': ''})
        assert resp.status_code == 302
        assert gutters.quotes == []

    def test_link_404_for_other_households_quote_or_job(self, logged_in_client, quote, other_vendor, foreign_zone, gutters):
        foreign_quote = vendor_quote_service.create(other_vendor, amount=Decimal('10'))
        assert logged_in_client.post(
            f'/zones/{gutters.id}/quotes/link', data={'quote_id': foreign_quote.id}).status_code == 404
        assert logged_in_client.post(
            f'/zones/{foreign_zone.id}/quotes/link', data={'quote_id': quote.id}).status_code == 404
        assert logged_in_client.post(
            '/appliances/9999/quotes/link', data={'quote_id': quote.id}).status_code == 404
        assert foreign_quote.job is None and quote.job is None

    def test_unlink_keeps_quote_on_vendor_page(self, logged_in_client, db, vendor, quote, gutters):
        vendor_quote_service.link(quote, zone=gutters)
        resp = logged_in_client.post(f'/quotes/{quote.id}/unlink')
        assert resp.headers['Location'].endswith(f'/zones/{gutters.id}')
        db.session.refresh(quote)
        assert quote.job is None
        assert b'113170' in logged_in_client.get(f'/vendors/{vendor.id}').data

    def test_unlink_404_for_other_household(self, logged_in_client, other_vendor, foreign_zone):
        foreign_quote = vendor_quote_service.create(other_vendor, amount=Decimal('10'), zone=foreign_zone)
        assert logged_in_client.post(f'/quotes/{foreign_quote.id}/unlink').status_code == 404
        assert foreign_quote.zone_id == foreign_zone.id

    def test_inline_create_lands_on_vendor_and_job(self, logged_in_client, vendor, furnace):
        resp = logged_in_client.post(f'/appliances/{furnace.id}/quotes', data={
            'vendor_id': vendor.id, 'quote_number': 'HV-9', 'amount': '120',
        })
        assert resp.headers['Location'].endswith(f'/appliances/{furnace.id}')
        quote = VendorQuote.query.one()
        assert quote.vendor_id == vendor.id and quote.appliance_id == furnace.id
        assert quote.status == QuoteStatus.pending

    def test_inline_create_invalid_input_is_rejected(self, logged_in_client, vendor, gutters):
        logged_in_client.post(f'/zones/{gutters.id}/quotes', data={'amount': '120'})
        logged_in_client.post(f'/zones/{gutters.id}/quotes', data={'vendor_id': vendor.id, 'description': 'no amount'})
        logged_in_client.post(f'/zones/{gutters.id}/quotes', data={'vendor_id': vendor.id, 'amount': '1', 'valid_until': 'soon'})
        assert VendorQuote.query.count() == 0

    def test_inline_create_404_for_other_households_vendor_or_job(self, logged_in_client, vendor, other_vendor,
                                                                  foreign_zone, gutters):
        assert logged_in_client.post(
            f'/zones/{gutters.id}/quotes', data={'vendor_id': other_vendor.id, 'amount': '1'}).status_code == 404
        assert logged_in_client.post(
            f'/zones/{foreign_zone.id}/quotes', data={'vendor_id': vendor.id, 'amount': '1'}).status_code == 404
        assert VendorQuote.query.count() == 0

    def test_job_page_shows_linked_quotes_and_chosen_vendor(self, logged_in_client, vendor, rival_vendor, gutters):
        vendor_quote_service.create(vendor, quote_number='113170', amount=Decimal('315.07'), zone=gutters,
                                    status='accepted')
        vendor_quote_service.create(rival_vendor, amount=Decimal('400'))
        page = logged_in_client.get(f'/zones/{gutters.id}').data.decode()
        assert '113170' in page
        assert 'Chosen vendor:' in page and vendor.name in page
        assert f'/quotes/compare?target=zone:{gutters.id}' in page
        assert 'Link an existing quote' in page and 'AA Window' in page

    def test_appliance_page_renders_quote_section(self, logged_in_client, furnace):
        page = logged_in_client.get(f'/appliances/{furnace.id}').data.decode()
        assert 'No quotes linked yet.' in page


class TestOpenQuotesDashboard:
    def test_lists_open_quotes_by_job(self, logged_in_client, vendor, rival_vendor, gutters):
        vendor_quote_service.create(vendor, amount=Decimal('315.07'), zone=gutters, valid_until=date(2026, 11, 1))
        vendor_quote_service.create(rival_vendor, amount=Decimal('400'), zone=gutters)
        vendor_quote_service.create(rival_vendor, amount=Decimal('777'), zone=gutters, status='declined')
        page = logged_in_client.get('/').data.decode()
        assert 'Open quotes' in page
        assert '$315.07' in page and '$400.00' in page
        assert '$777.00' not in page
        assert f'/quotes/compare?target=zone:{gutters.id}' in page

    def test_hidden_when_nothing_is_open(self, logged_in_client, vendor):
        vendor_quote_service.create(vendor, amount=Decimal('1'), status='declined')
        assert 'Open quotes' not in logged_in_client.get('/').data.decode()
