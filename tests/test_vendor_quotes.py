import io
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app import document_service, vendor_quote_service
from app.context_export_service import build_context_markdown
from app.models import Household, QuoteStatus, Vendor, VendorQuote
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

    def test_accept_declines_other_quotes_on_same_vendor(self, db, vendor, household):
        first = vendor_quote_service.create(vendor, amount=Decimal('315.07'))
        second = vendor_quote_service.create(vendor, amount=Decimal('400'))
        elsewhere = Vendor(household_id=household.id, name='AA Window', vendor_type='other')
        db.session.add(elsewhere)
        db.session.commit()
        unrelated = vendor_quote_service.create(elsewhere, amount=Decimal('400'))

        vendor_quote_service.accept(second)

        assert second.status == QuoteStatus.accepted
        assert first.status == QuoteStatus.declined
        assert unrelated.status == QuoteStatus.pending

    def test_creating_an_accepted_quote_declines_others(self, vendor, quote):
        accepted = vendor_quote_service.create(vendor, amount=Decimal('400'), status='accepted')
        assert accepted.status == QuoteStatus.accepted
        assert quote.status == QuoteStatus.declined

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

    def test_accept_route_declines_others(self, logged_in_client, db, vendor, quote):
        other = vendor_quote_service.create(vendor, quote_number='AA-1', amount=Decimal('400'))
        resp = logged_in_client.post(f'/vendors/{vendor.id}/quotes/{other.id}/accept')
        assert resp.status_code == 302
        db.session.refresh(quote)
        db.session.refresh(other)
        assert other.status == QuoteStatus.accepted
        assert quote.status == QuoteStatus.declined

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
    def test_vendor_section_lists_quotes(self, household, vendor):
        vendor_quote_service.create(
            vendor, quote_number='113170', amount=Decimal('315.07'), valid_until=date(2026, 11, 1),
            description='Gutter cleaning',
        )
        vendors_section = build_context_markdown(household).split('## Vendors')[1]
        assert '#113170 — $315.07 — valid until 2026-11-01 [pending]' in vendors_section
        assert 'Gutter cleaning' in vendors_section
