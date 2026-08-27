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
