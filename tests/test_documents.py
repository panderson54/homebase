import io

from PIL import Image

from app.models import Appliance, Document


def _make_png_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (4, 4), color='red').save(buf, format='PNG')
    buf.seek(0)
    return buf


class TestDocuments:
    def test_upload_external_link(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/appliances/{appliance.id}/documents', data={
            'doc_type': 'manual',
            'external_url': 'https://example.com/manual.pdf',
        })
        assert resp.status_code == 302
        doc = Document.query.filter_by(appliance_id=appliance.id).first()
        assert doc.external_url == 'https://example.com/manual.pdf'
        assert doc.file_path is None

    def test_upload_image_file_is_saved_to_disk(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(
            f'/appliances/{appliance.id}/documents',
            data={
                'doc_type': 'photo',
                'file': (_make_png_bytes(), 'rating_plate.png'),
            },
            content_type='multipart/form-data',
        )
        assert resp.status_code == 302
        doc = Document.query.filter_by(appliance_id=appliance.id).first()
        assert doc.file_path is not None
        assert doc.original_filename == 'rating_plate.png'

        file_resp = logged_in_client.get(f'/documents/{doc.id}/file')
        assert file_resp.status_code == 200

    def test_upload_rejects_bad_extension(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(
            f'/appliances/{appliance.id}/documents',
            data={'doc_type': 'other', 'file': (io.BytesIO(b'not really a file'), 'malware.exe')},
            content_type='multipart/form-data',
        )
        assert resp.status_code == 302
        assert Document.query.filter_by(appliance_id=appliance.id).count() == 0

    def test_upload_requires_file_or_link(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/appliances/{appliance.id}/documents', data={'doc_type': 'manual'})
        assert resp.status_code == 302
        assert Document.query.filter_by(appliance_id=appliance.id).count() == 0

    def test_delete_document_removes_file(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()
        logged_in_client.post(
            f'/appliances/{appliance.id}/documents',
            data={'doc_type': 'photo', 'file': (_make_png_bytes(), 'plate.png')},
            content_type='multipart/form-data',
        )
        doc = Document.query.filter_by(appliance_id=appliance.id).first()

        resp = logged_in_client.post(f'/documents/{doc.id}/delete')
        assert resp.status_code == 302
        assert db.session.get(Document, doc.id) is None
