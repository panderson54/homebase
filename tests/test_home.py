import io
from datetime import date

from PIL import Image

from app import document_service


def _make_png_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (4, 4), color='blue').save(buf, format='PNG')
    buf.seek(0)
    return buf


class TestHomePage:
    def test_requires_login(self, client):
        resp = client.get('/home')
        assert resp.status_code == 302
        assert '/login' in resp.headers['Location']

    def test_view_shows_current_values(self, logged_in_client, db, household):
        household.address = '123 Main St'
        household.square_footage = 2400
        household.year_built = 1998
        db.session.commit()

        resp = logged_in_client.get('/home')
        assert resp.status_code == 200
        assert b'123 Main St' in resp.data
        assert b'2400' in resp.data

    def test_update_persists_fields(self, logged_in_client, db, household):
        resp = logged_in_client.post('/home', data={
            'name': 'Anderson Home',
            'address': '456 Oak Ave',
            'square_footage': '1800',
            'year_built': '2005',
            'notes': 'Corner lot',
        })
        assert resp.status_code == 302
        db.session.refresh(household)
        assert household.address == '456 Oak Ave'
        assert household.square_footage == 1800
        assert household.year_built == 2005
        assert household.notes == 'Corner lot'
        assert household.age_years == date.today().year - 2005

    def test_clearing_year_built_clears_age(self, logged_in_client, db, household):
        household.year_built = 2000
        db.session.commit()

        logged_in_client.post('/home', data={'name': household.name, 'year_built': ''})
        db.session.refresh(household)
        assert household.year_built is None
        assert household.age_years is None


class TestHomeTabs:
    def test_default_tab_is_overview(self, logged_in_client):
        resp = logged_in_client.get('/home')
        assert b'Household name' in resp.data

    def test_paint_tab_shows_paint_colors(self, logged_in_client, paint_color):
        resp = logged_in_client.get('/home?tab=paint')
        assert paint_color.location.encode() in resp.data
        assert b'Household name' not in resp.data

    def test_rooms_tab_shows_rooms(self, logged_in_client, db, household):
        from app.models import Room
        room = Room(household_id=household.id, name='Kitchen', floor='1st floor')
        db.session.add(room)
        db.session.commit()

        resp = logged_in_client.get('/home?tab=rooms')
        assert b'Kitchen' in resp.data
        assert b'1st floor' in resp.data

    def test_unknown_tab_falls_back_to_overview(self, logged_in_client):
        resp = logged_in_client.get('/home?tab=bogus')
        assert b'Household name' in resp.data


class TestHomeDocuments:
    def test_upload_link_and_list(self, logged_in_client, db, household):
        resp = logged_in_client.post('/home/documents', data={
            'doc_type': 'floor_plan',
            'external_url': 'https://example.com/floor-plan.pdf',
        })
        assert resp.status_code == 302
        docs = document_service.get_documents_for('home', household.id)
        assert len(docs) == 1
        assert docs[0].doc_type.value == 'floor_plan'

        page = logged_in_client.get('/home')
        assert b'floor-plan.pdf' in page.data
        assert b'Floor plan' in page.data

    def test_upload_file_and_delete(self, logged_in_client, db, household):
        logged_in_client.post('/home/documents', data={
            'doc_type': 'inspection_report',
            'file': (_make_png_bytes(), 'inspection.png'),
        }, content_type='multipart/form-data')
        docs = document_service.get_documents_for('home', household.id)
        assert len(docs) == 1

        resp = logged_in_client.post(f'/home/documents/{docs[0].id}/delete')
        assert resp.status_code == 302
        assert document_service.get_documents_for('home', household.id) == []

    def test_upload_requires_file_or_link(self, logged_in_client, db, household):
        resp = logged_in_client.post('/home/documents', data={'doc_type': 'other'})
        assert resp.status_code == 302
        assert document_service.get_documents_for('home', household.id) == []

    def test_home_documents_do_not_leak_into_appliance_documents(self, logged_in_client, db, household):
        from app.models import Appliance
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        logged_in_client.post('/home/documents', data={
            'doc_type': 'floor_plan', 'external_url': 'https://example.com/plan.pdf',
        })
        assert document_service.get_documents_for('appliance', appliance.id) == []
