import io

from PIL import Image

from app import document_service
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
        docs = document_service.get_documents_for('appliance', appliance.id)
        assert len(docs) == 1
        assert docs[0].external_url == 'https://example.com/manual.pdf'
        assert docs[0].file_path is None
        assert docs[0].household_id == household.id

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
        docs = document_service.get_documents_for('appliance', appliance.id)
        assert docs[0].file_path is not None
        assert docs[0].original_filename == 'rating_plate.png'

        file_resp = logged_in_client.get(f'/documents/{docs[0].id}/file')
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
        assert document_service.get_documents_for('appliance', appliance.id) == []

    def test_upload_requires_file_or_link(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/appliances/{appliance.id}/documents', data={'doc_type': 'manual'})
        assert resp.status_code == 302
        assert document_service.get_documents_for('appliance', appliance.id) == []

    def test_delete_document_removes_file(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()
        logged_in_client.post(
            f'/appliances/{appliance.id}/documents',
            data={'doc_type': 'photo', 'file': (_make_png_bytes(), 'plate.png')},
            content_type='multipart/form-data',
        )
        doc = document_service.get_documents_for('appliance', appliance.id)[0]

        resp = logged_in_client.post(
            f'/documents/{doc.id}/delete', data={'appliance_id': appliance.id}
        )
        assert resp.status_code == 302
        assert db.session.get(Document, doc.id) is None

    def test_delete_requires_matching_appliance(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        other_appliance = Appliance(household_id=household.id, name='Dishwasher', category='dishwasher')
        db.session.add_all([appliance, other_appliance])
        db.session.commit()
        logged_in_client.post(f'/appliances/{appliance.id}/documents', data={
            'doc_type': 'manual', 'external_url': 'https://example.com/manual.pdf',
        })
        doc = document_service.get_documents_for('appliance', appliance.id)[0]

        # Deleting via a different (but valid, household-owned) appliance_id is a no-op:
        # the document isn't linked to that appliance, so nothing is unlinked/deleted.
        resp = logged_in_client.post(
            f'/documents/{doc.id}/delete', data={'appliance_id': other_appliance.id}
        )
        assert resp.status_code == 302
        assert db.session.get(Document, doc.id) is not None
