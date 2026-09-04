import io

from PIL import Image

from app import document_service
from app.models import Appliance, Document, DocumentEntityType, DocumentLink


def _make_file_storage(name='plate.png'):
    from werkzeug.datastructures import FileStorage
    buf = io.BytesIO()
    Image.new('RGB', (4, 4), color='green').save(buf, format='PNG')
    buf.seek(0)
    return FileStorage(stream=buf, filename=name)


class TestPrimaryPhoto:
    def test_set_primary_photo_is_returned_by_get(self, app, db, household):
        with app.test_request_context():
            doc = document_service.set_primary_photo(household.id, 'home', household.id, _make_file_storage())
        assert doc is not None
        primary = document_service.get_primary_photo_for('home', household.id)
        assert primary.id == doc.id

    def test_no_primary_photo_returns_none(self, db, household):
        assert document_service.get_primary_photo_for('home', household.id) is None

    def test_setting_new_primary_demotes_previous_one(self, app, db, household):
        with app.test_request_context():
            first = document_service.set_primary_photo(household.id, 'home', household.id, _make_file_storage('a.png'))
            second = document_service.set_primary_photo(household.id, 'home', household.id, _make_file_storage('b.png'))

        primary = document_service.get_primary_photo_for('home', household.id)
        assert primary.id == second.id
        first_link = DocumentLink.query.filter_by(document_id=first.id).first()
        assert first_link.is_primary is False
        # the demoted photo is still an ordinary linked document, not deleted
        assert db.session.get(Document, first.id) is not None

    def test_rejects_bad_extension(self, app, db, household):
        with app.test_request_context():
            doc = document_service.set_primary_photo(household.id, 'home', household.id, _make_file_storage('malware.exe'))
        assert doc is None

    def test_primary_photo_is_scoped_per_entity(self, app, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()
        with app.test_request_context():
            home_photo = document_service.set_primary_photo(household.id, 'home', household.id, _make_file_storage())
            appliance_photo = document_service.set_primary_photo(
                household.id, 'appliance', appliance.id, _make_file_storage()
            )
        assert document_service.get_primary_photo_for('home', household.id).id == home_photo.id
        assert document_service.get_primary_photo_for('appliance', appliance.id).id == appliance_photo.id


class TestPrimaryPhotoUrl:
    def test_set_primary_photo_url_is_returned_by_get(self, db, household):
        doc = document_service.set_primary_photo_url(household.id, 'vendor', 1, 'https://example.com/logo.png')
        assert doc is not None
        assert doc.external_url == 'https://example.com/logo.png'
        primary = document_service.get_primary_photo_for('vendor', 1)
        assert primary.id == doc.id

    def test_blank_url_returns_none(self, db, household):
        assert document_service.set_primary_photo_url(household.id, 'vendor', 1, '') is None

    def test_new_url_demotes_previous_upload(self, app, db, household):
        with app.test_request_context():
            uploaded = document_service.set_primary_photo(household.id, 'vendor', 1, _make_file_storage())
        url_doc = document_service.set_primary_photo_url(household.id, 'vendor', 1, 'https://example.com/logo.png')

        primary = document_service.get_primary_photo_for('vendor', 1)
        assert primary.id == url_doc.id
        uploaded_link = DocumentLink.query.filter_by(document_id=uploaded.id).first()
        assert uploaded_link.is_primary is False


class TestPrimaryPhotosForMany:
    def test_returns_dict_keyed_by_entity_id(self, app, db, household):
        with app.test_request_context():
            doc1 = document_service.set_primary_photo(household.id, 'vendor', 1, _make_file_storage('a.png'))
            doc2 = document_service.set_primary_photo(household.id, 'vendor', 2, _make_file_storage('b.png'))

        photos = document_service.get_primary_photos_for_many('vendor', [1, 2, 3])
        assert photos[1].id == doc1.id
        assert photos[2].id == doc2.id
        assert 3 not in photos

    def test_empty_ids_returns_empty_dict(self, db):
        assert document_service.get_primary_photos_for_many('vendor', []) == {}


class TestDocumentCountsForMany:
    def test_returns_dict_keyed_by_entity_id(self, app, db, household):
        with app.test_request_context():
            document_service.save_and_link(
                household_id=household.id, entity_type='service_record', entity_id=1,
                doc_type='invoice', external_url='https://example.com/a.pdf',
            )
            document_service.save_and_link(
                household_id=household.id, entity_type='service_record', entity_id=1,
                doc_type='receipt', external_url='https://example.com/b.pdf',
            )
            document_service.save_and_link(
                household_id=household.id, entity_type='service_record', entity_id=2,
                doc_type='invoice', external_url='https://example.com/c.pdf',
            )

        counts = document_service.get_document_counts_for('service_record', [1, 2, 3])
        assert counts[1] == 2
        assert counts[2] == 1
        assert 3 not in counts

    def test_empty_ids_returns_empty_dict(self, db):
        assert document_service.get_document_counts_for('service_record', []) == {}


class TestSaveAndLink:
    def test_creates_document_and_link_from_url(self, app, db, household):
        with app.test_request_context():
            doc = document_service.save_and_link(
                household_id=household.id, entity_type='home', entity_id=household.id,
                doc_type='floor_plan', external_url='https://example.com/plan.pdf',
            )
        assert doc is not None
        assert doc.household_id == household.id
        link = DocumentLink.query.filter_by(document_id=doc.id).first()
        assert link.entity_type.value == 'home'
        assert link.entity_id == household.id

    def test_creates_document_and_link_from_file(self, app, db, household):
        with app.test_request_context():
            doc = document_service.save_and_link(
                household_id=household.id, entity_type='home', entity_id=household.id,
                doc_type='photo', file_storage=_make_file_storage(),
            )
        assert doc.file_path is not None

    def test_returns_none_without_file_or_url(self, app, db, household):
        with app.test_request_context():
            doc = document_service.save_and_link(
                household_id=household.id, entity_type='home', entity_id=household.id, doc_type='other',
            )
        assert doc is None

    def test_returns_none_for_bad_extension(self, app, db, household):
        from werkzeug.datastructures import FileStorage
        bad_file = FileStorage(stream=io.BytesIO(b'x'), filename='virus.exe')
        with app.test_request_context():
            doc = document_service.save_and_link(
                household_id=household.id, entity_type='home', entity_id=household.id,
                doc_type='other', file_storage=bad_file,
            )
        assert doc is None


class TestGetDocumentsFor:
    def test_returns_only_linked_documents(self, app, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        with app.test_request_context():
            document_service.save_and_link(
                household_id=household.id, entity_type='appliance', entity_id=appliance.id,
                doc_type='manual', external_url='https://example.com/manual.pdf',
            )
            document_service.save_and_link(
                household_id=household.id, entity_type='home', entity_id=household.id,
                doc_type='floor_plan', external_url='https://example.com/plan.pdf',
            )

        appliance_docs = document_service.get_documents_for('appliance', appliance.id)
        home_docs = document_service.get_documents_for('home', household.id)
        assert len(appliance_docs) == 1
        assert appliance_docs[0].doc_type.value == 'manual'
        assert len(home_docs) == 1
        assert home_docs[0].doc_type.value == 'floor_plan'


class TestUnlinkAndMaybeDelete:
    def test_last_link_deletes_document(self, app, db, household):
        with app.test_request_context():
            doc = document_service.save_and_link(
                household_id=household.id, entity_type='home', entity_id=household.id,
                doc_type='floor_plan', external_url='https://example.com/plan.pdf',
            )
            document_service.unlink_and_maybe_delete(doc.id, 'home', household.id)

        assert db.session.get(Document, doc.id) is None

    def test_unlinking_one_of_two_links_keeps_document(self, app, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        with app.test_request_context():
            doc = document_service.save_and_link(
                household_id=household.id, entity_type='home', entity_id=household.id,
                doc_type='floor_plan', external_url='https://example.com/plan.pdf',
            )
            db.session.add(DocumentLink(
                document_id=doc.id, entity_type=DocumentEntityType.appliance, entity_id=appliance.id
            ))
            db.session.commit()

            document_service.unlink_and_maybe_delete(doc.id, 'home', household.id)

        # still linked to the appliance, so the document itself survives
        assert db.session.get(Document, doc.id) is not None
        assert document_service.get_documents_for('appliance', appliance.id) == [
            db.session.get(Document, doc.id)
        ]
        assert document_service.get_documents_for('home', household.id) == []

    def test_unlink_nonexistent_link_is_a_no_op(self, app, db, household):
        with app.test_request_context():
            document_service.unlink_and_maybe_delete(999999, 'home', household.id)
        # no exception raised is the assertion here
