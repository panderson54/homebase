import io

from PIL import Image

from app import document_service
from app.models import Appliance, Household, ServiceRecord, Vendor, Zone


def _make_png_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (4, 4), color='red').save(buf, format='PNG')
    buf.seek(0)
    return buf


class TestVendorCRUD:
    def test_list_requires_login(self, client):
        resp = client.get('/vendors')
        assert resp.status_code == 302

    def test_create_vendor(self, logged_in_client, db, household):
        resp = logged_in_client.post('/vendors/new', data={
            'name': 'ACME HVAC',
            'vendor_type': 'hvac',
            'contact_name': 'Bob',
            'phone': '555-1234',
            'email': 'bob@acmehvac.com',
        })
        assert resp.status_code == 302
        vendor = Vendor.query.filter_by(household_id=household.id).first()
        assert vendor.name == 'ACME HVAC'
        assert vendor.vendor_type == 'hvac'
        assert vendor.contact_name == 'Bob'

    def test_create_vendor_with_custom_type(self, logged_in_client, household):
        logged_in_client.post('/vendors/new', data={
            'name': 'Joe the Handyman',
            'vendor_type': '__other__',
            'custom_vendor_type': 'General Handyman',
        })
        vendor = Vendor.query.filter_by(household_id=household.id).first()
        assert vendor.vendor_type == 'general_handyman'

    def test_detail_404_for_other_household(self, logged_in_client, db, household):
        other_household = Household(name='Other Home')
        db.session.add(other_household)
        db.session.commit()
        other_vendor = Vendor(household_id=other_household.id, name='Other Vendor', vendor_type='other')
        db.session.add(other_vendor)
        db.session.commit()

        resp = logged_in_client.get(f'/vendors/{other_vendor.id}')
        assert resp.status_code == 404

    def test_detail_404_for_nonexistent(self, logged_in_client):
        resp = logged_in_client.get('/vendors/999999')
        assert resp.status_code == 404

    def test_edit_updates_fields(self, logged_in_client, db, vendor):
        resp = logged_in_client.post(f'/vendors/{vendor.id}/edit', data={
            'name': 'ACME Heating & Air',
            'vendor_type': 'hvac',
            'phone': '555-9999',
        })
        assert resp.status_code == 302
        db.session.refresh(vendor)
        assert vendor.name == 'ACME Heating & Air'
        assert vendor.phone == '555-9999'

    def test_list_shows_vendor(self, logged_in_client, vendor):
        resp = logged_in_client.get('/vendors')
        assert vendor.name.encode() in resp.data

    def test_create_vendor_with_rating(self, logged_in_client, household):
        logged_in_client.post('/vendors/new', data={
            'name': 'ACME HVAC', 'vendor_type': 'hvac', 'rating': '4',
        })
        vendor = Vendor.query.filter_by(household_id=household.id).first()
        assert vendor.rating == 4

    def test_create_vendor_without_rating_leaves_it_unrated(self, logged_in_client, household):
        logged_in_client.post('/vendors/new', data={'name': 'Joe the Handyman', 'vendor_type': 'other'})
        vendor = Vendor.query.filter_by(household_id=household.id).first()
        assert vendor.rating is None

    def test_create_vendor_with_out_of_range_rating_is_ignored(self, logged_in_client, household):
        logged_in_client.post('/vendors/new', data={
            'name': 'ACME HVAC', 'vendor_type': 'hvac', 'rating': '7',
        })
        vendor = Vendor.query.filter_by(household_id=household.id).first()
        assert vendor.rating is None

    def test_edit_updates_rating(self, logged_in_client, db, vendor):
        resp = logged_in_client.post(f'/vendors/{vendor.id}/edit', data={
            'name': vendor.name, 'vendor_type': vendor.vendor_type, 'rating': '5',
        })
        assert resp.status_code == 302
        db.session.refresh(vendor)
        assert vendor.rating == 5

    def test_edit_clears_rating(self, logged_in_client, db, vendor):
        vendor.rating = 3
        db.session.commit()

        logged_in_client.post(f'/vendors/{vendor.id}/edit', data={
            'name': vendor.name, 'vendor_type': vendor.vendor_type,
        })
        db.session.refresh(vendor)
        assert vendor.rating is None


class TestVendorLogo:
    def test_create_with_website_sets_default_logo(self, logged_in_client, db, household):
        resp = logged_in_client.post('/vendors/new', data={
            'name': 'ACME HVAC', 'vendor_type': 'hvac', 'website': 'https://acmehvac.com',
        })
        assert resp.status_code == 302
        vendor = Vendor.query.filter_by(household_id=household.id).first()
        photo = document_service.get_primary_photo_for('vendor', vendor.id)
        assert photo is not None
        assert 'acmehvac.com' in photo.external_url

    def test_create_without_website_has_no_logo(self, logged_in_client, db, household):
        logged_in_client.post('/vendors/new', data={'name': 'Joe the Handyman', 'vendor_type': 'other'})
        vendor = Vendor.query.filter_by(household_id=household.id).first()
        assert document_service.get_primary_photo_for('vendor', vendor.id) is None

    def test_manual_upload_survives_a_later_edit(self, logged_in_client, db, vendor):
        logged_in_client.post(f'/vendors/{vendor.id}/photo', data={
            'photo': (_make_png_bytes(), 'logo.png'),
        }, content_type='multipart/form-data')
        uploaded = document_service.get_primary_photo_for('vendor', vendor.id)
        assert uploaded.file_path is not None

        logged_in_client.post(f'/vendors/{vendor.id}/edit', data={
            'name': vendor.name, 'vendor_type': 'hvac', 'website': 'https://acmehvac.com',
        })
        current = document_service.get_primary_photo_for('vendor', vendor.id)
        assert current.id == uploaded.id  # not replaced by the auto-favicon

    def test_photo_upload_404_for_other_household(self, logged_in_client, db):
        other = Household(name='Other')
        db.session.add(other)
        db.session.commit()
        other_vendor = Vendor(household_id=other.id, name='Other Vendor', vendor_type='other')
        db.session.add(other_vendor)
        db.session.commit()

        resp = logged_in_client.post(f'/vendors/{other_vendor.id}/photo', data={
            'photo': (_make_png_bytes(), 'logo.png'),
        }, content_type='multipart/form-data')
        assert resp.status_code == 404


class TestVendorDocuments:
    def test_upload_link(self, logged_in_client, db, vendor):
        resp = logged_in_client.post(f'/vendors/{vendor.id}/documents', data={
            'doc_type': 'quote',
            'external_url': 'https://example.com/quote.pdf',
        })
        assert resp.status_code == 302
        docs = document_service.get_documents_for('vendor', vendor.id)
        assert len(docs) == 1
        assert docs[0].doc_type.value == 'quote'

    def test_upload_file_and_delete(self, logged_in_client, db, vendor):
        logged_in_client.post(f'/vendors/{vendor.id}/documents', data={
            'doc_type': 'invoice',
            'file': (_make_png_bytes(), 'invoice.png'),
        }, content_type='multipart/form-data')
        docs = document_service.get_documents_for('vendor', vendor.id)
        assert len(docs) == 1

        resp = logged_in_client.post(f'/vendors/{vendor.id}/documents/{docs[0].id}/delete')
        assert resp.status_code == 302
        assert document_service.get_documents_for('vendor', vendor.id) == []

    def test_upload_requires_file_or_link(self, logged_in_client, vendor):
        resp = logged_in_client.post(f'/vendors/{vendor.id}/documents', data={'doc_type': 'quote'})
        assert resp.status_code == 302
        assert document_service.get_documents_for('vendor', vendor.id) == []


class TestVendorServiceVisits:
    def test_log_visit_without_appliance(self, logged_in_client, db, household, vendor):
        resp = logged_in_client.post(f'/vendors/{vendor.id}/services', data={
            'service_date': '2026-03-01',
            'notes': 'Whole-house inspection',
        })
        assert resp.status_code == 302
        record = ServiceRecord.query.filter_by(vendor_id=vendor.id).first()
        assert record.appliance_id is None
        assert record.household_id == household.id
        assert record.notes == 'Whole-house inspection'
        assert record.category.value == 'maintenance'

    def test_log_visit_with_appliance(self, logged_in_client, db, household, vendor):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/vendors/{vendor.id}/services', data={
            'service_date': '2026-03-01',
            'target': f'appliance:{appliance.id}',
            'cost': '150.00',
        })
        assert resp.status_code == 302
        record = ServiceRecord.query.filter_by(vendor_id=vendor.id).first()
        assert record.appliance_id == appliance.id
        assert record.zone_id is None
        assert record.cost == 150

        # shows up on both the vendor's and the appliance's pages
        vendor_page = logged_in_client.get(f'/vendors/{vendor.id}')
        assert b'Furnace' in vendor_page.data
        appliance_page = logged_in_client.get(f'/appliances/{appliance.id}')
        assert vendor.name.encode() in appliance_page.data

    def test_log_visit_with_zone_and_category(self, logged_in_client, db, household, vendor):
        zone = Zone(household_id=household.id, name='Roof')
        db.session.add(zone)
        db.session.commit()

        resp = logged_in_client.post(f'/vendors/{vendor.id}/services', data={
            'service_date': '2026-03-01',
            'target': f'zone:{zone.id}',
            'category': 'improvement',
        })
        assert resp.status_code == 302
        record = ServiceRecord.query.filter_by(vendor_id=vendor.id).first()
        assert record.zone_id == zone.id
        assert record.appliance_id is None
        assert record.category.value == 'improvement'

        # shows up on both the vendor's and the zone's pages
        vendor_page = logged_in_client.get(f'/vendors/{vendor.id}')
        assert b'Roof' in vendor_page.data
        zone_page = logged_in_client.get(f'/zones/{zone.id}')
        assert vendor.name.encode() in zone_page.data

    def test_delete_visit_with_no_appliance_redirects_to_vendor(self, logged_in_client, db, vendor):
        logged_in_client.post(f'/vendors/{vendor.id}/services', data={'service_date': '2026-03-01'})
        record = ServiceRecord.query.filter_by(vendor_id=vendor.id).first()

        resp = logged_in_client.post(f'/service-records/{record.id}/delete')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(f'/vendors/{vendor.id}')

    def test_delete_visit_with_zone_redirects_to_zone(self, logged_in_client, db, household, vendor):
        zone = Zone(household_id=household.id, name='Garden')
        db.session.add(zone)
        db.session.commit()
        logged_in_client.post(f'/vendors/{vendor.id}/services', data={
            'service_date': '2026-03-01', 'target': f'zone:{zone.id}',
        })
        record = ServiceRecord.query.filter_by(vendor_id=vendor.id).first()

        resp = logged_in_client.post(f'/service-records/{record.id}/delete')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(f'/zones/{zone.id}')
