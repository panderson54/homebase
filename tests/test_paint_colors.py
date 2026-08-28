import io

from PIL import Image

from app import document_service
from app.models import Household, PaintColor
from app.routes.helpers import parse_hex_color


def _make_png_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (4, 4), color='red').save(buf, format='PNG')
    buf.seek(0)
    return buf


class TestParseHexColor:
    def test_valid_hex(self):
        assert parse_hex_color('#d1cbc1') == '#D1CBC1'

    def test_valid_hex_already_uppercase(self):
        assert parse_hex_color('#D1CBC1') == '#D1CBC1'

    def test_blank_returns_none(self):
        assert parse_hex_color('') is None
        assert parse_hex_color(None) is None

    def test_invalid_format_returns_none(self):
        assert parse_hex_color('not-a-color') is None
        assert parse_hex_color('D1CBC1') is None  # missing '#'
        assert parse_hex_color('#D1C') is None  # wrong length
        assert parse_hex_color('#D1CBC1FF') is None  # too long


class TestPaintColorCRUD:
    def test_list_requires_login(self, client):
        resp = client.get('/paint-colors')
        assert resp.status_code == 302

    def test_create_paint_color(self, logged_in_client, db, household):
        resp = logged_in_client.post('/paint-colors/new', data={
            'location': 'Kitchen cabinets',
            'manufacturer': 'Benjamin Moore',
            'color_name': 'Simply White',
            'color_code': 'OC-117',
            'hex_color': '#F6F4EF',
            'product_url': 'https://example.com/simply-white',
        })
        assert resp.status_code == 302
        paint = PaintColor.query.filter_by(household_id=household.id).first()
        assert paint.location == 'Kitchen cabinets'
        assert paint.manufacturer == 'Benjamin Moore'
        assert paint.hex_color == '#F6F4EF'

    def test_create_with_multiple_locations(self, logged_in_client, db, household):
        resp = logged_in_client.post('/paint-colors/new', data={
            'location': ' Living room , Hallway,Stairwell ',
            'hex_color': '#F6F4EF',
        })
        assert resp.status_code == 302
        paint = PaintColor.query.filter_by(household_id=household.id).first()
        assert paint.location == 'Living room, Hallway, Stairwell'
        assert paint.location_list == ['Living room', 'Hallway', 'Stairwell']

    def test_create_with_invalid_hex_saves_without_swatch(self, logged_in_client, db, household):
        resp = logged_in_client.post('/paint-colors/new', data={
            'location': 'Hallway',
            'hex_color': 'notacolor',
        })
        assert resp.status_code == 302
        paint = PaintColor.query.filter_by(household_id=household.id).first()
        assert paint is not None
        assert paint.hex_color is None

    def test_detail_404_for_other_household(self, logged_in_client, db, household):
        other_household = Household(name='Other Home')
        db.session.add(other_household)
        db.session.commit()
        other_paint = PaintColor(household_id=other_household.id, location='Other Room')
        db.session.add(other_paint)
        db.session.commit()

        resp = logged_in_client.get(f'/paint-colors/{other_paint.id}')
        assert resp.status_code == 404

    def test_detail_404_for_nonexistent(self, logged_in_client):
        resp = logged_in_client.get('/paint-colors/999999')
        assert resp.status_code == 404

    def test_edit_updates_fields(self, logged_in_client, db, paint_color):
        resp = logged_in_client.post(f'/paint-colors/{paint_color.id}/edit', data={
            'location': 'Living room accent wall',
            'hex_color': '#123456',
        })
        assert resp.status_code == 302
        db.session.refresh(paint_color)
        assert paint_color.location == 'Living room accent wall'
        assert paint_color.hex_color == '#123456'

    def test_list_redirects_to_home_paint_tab(self, logged_in_client):
        resp = logged_in_client.get('/paint-colors')
        assert resp.status_code == 302
        assert resp.headers['Location'] == '/home?tab=paint'

    def test_home_paint_tab_shows_swatch(self, logged_in_client, paint_color):
        resp = logged_in_client.get('/home?tab=paint')
        assert paint_color.location.encode() in resp.data
        assert paint_color.hex_color.encode() in resp.data


class TestPaintColorDocuments:
    def test_upload_link(self, logged_in_client, db, paint_color):
        resp = logged_in_client.post(f'/paint-colors/{paint_color.id}/documents', data={
            'doc_type': 'photo',
            'external_url': 'https://example.com/wall.jpg',
        })
        assert resp.status_code == 302
        docs = document_service.get_documents_for('paint_color', paint_color.id)
        assert len(docs) == 1
        assert docs[0].doc_type.value == 'photo'

    def test_upload_file_and_delete(self, logged_in_client, db, paint_color):
        logged_in_client.post(f'/paint-colors/{paint_color.id}/documents', data={
            'doc_type': 'photo',
            'file': (_make_png_bytes(), 'wall.png'),
        }, content_type='multipart/form-data')
        docs = document_service.get_documents_for('paint_color', paint_color.id)
        assert len(docs) == 1

        resp = logged_in_client.post(
            f'/paint-colors/{paint_color.id}/documents/{docs[0].id}/delete'
        )
        assert resp.status_code == 302
        assert document_service.get_documents_for('paint_color', paint_color.id) == []


class TestPaintColorDelete:
    def test_delete_removes_paint_color_and_its_documents(self, logged_in_client, db, paint_color):
        logged_in_client.post(f'/paint-colors/{paint_color.id}/documents', data={
            'doc_type': 'photo',
            'file': (_make_png_bytes(), 'wall.png'),
        }, content_type='multipart/form-data')
        doc = document_service.get_documents_for('paint_color', paint_color.id)[0]
        import os
        from flask import current_app
        abs_path = os.path.join(current_app.config['UPLOAD_DIR'], doc.file_path)
        assert os.path.exists(abs_path)

        resp = logged_in_client.post(f'/paint-colors/{paint_color.id}/delete')
        assert resp.status_code == 302
        assert db.session.get(PaintColor, paint_color.id) is None
        assert not os.path.exists(abs_path)

    def test_delete_404_for_other_household(self, logged_in_client, db, household):
        other_household = Household(name='Other Home')
        db.session.add(other_household)
        db.session.commit()
        other_paint = PaintColor(household_id=other_household.id, location='Other Room')
        db.session.add(other_paint)
        db.session.commit()

        resp = logged_in_client.post(f'/paint-colors/{other_paint.id}/delete')
        assert resp.status_code == 404
        assert db.session.get(PaintColor, other_paint.id) is not None
