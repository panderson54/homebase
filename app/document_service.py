"""Document storage plus generic entity-linking. A Document (an uploaded file or an
external link) can be attached to more than one entity — an appliance, the home
itself, and other kinds later — via DocumentLink; see app/models.py for why that's
a generic (entity_type, entity_id) association rather than a per-relationship FK.
"""
import os
import uuid

from flask import current_app
from PIL import Image
from werkzeug.utils import secure_filename

from app import db
from app.models import Document, DocumentEntityType, DocumentLink, DocumentType

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
ALLOWED_DOC_EXTENSIONS = {'pdf'}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_DOC_EXTENSIONS


def _extension(filename):
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def _save_upload(file_storage, household_id):
    """Validate and persist an uploaded file to disk; re-encode images with Pillow.
    Returns (file_path, content_type) relative to UPLOAD_DIR, or (None, None) if
    the extension isn't allowed."""
    ext = _extension(file_storage.filename)
    if ext not in ALLOWED_EXTENSIONS:
        return None, None

    household_dir = os.path.join(current_app.config['UPLOAD_DIR'], str(household_id))
    os.makedirs(household_dir, exist_ok=True)
    stored_name = f'{uuid.uuid4().hex}_{secure_filename(file_storage.filename)}'
    dest_path = os.path.join(household_dir, stored_name)

    if ext in ALLOWED_IMAGE_EXTENSIONS:
        image = Image.open(file_storage.stream)
        image = image.convert('RGB') if image.mode not in ('RGB', 'L') else image
        image.save(dest_path)
        content_type = f'image/{"jpeg" if ext in ("jpg", "jpeg") else ext}'
    else:
        file_storage.save(dest_path)
        content_type = 'application/pdf'

    return os.path.join(str(household_id), stored_name), content_type


def save_and_link(household_id, entity_type, entity_id, doc_type, file_storage=None, external_url=None):
    """Create a Document (from an upload or a link) and link it to one entity.
    Returns the Document, or None if the upload was rejected (bad extension) or
    neither a file nor a link was given — callers flash an error in that case."""
    if doc_type not in DocumentType.__members__:
        doc_type = DocumentType.other.value

    if file_storage and file_storage.filename:
        file_path, content_type = _save_upload(file_storage, household_id)
        if file_path is None:
            return None
        document = Document(
            household_id=household_id,
            doc_type=DocumentType(doc_type),
            file_path=file_path,
            original_filename=file_storage.filename,
            content_type=content_type,
        )
    elif external_url:
        document = Document(
            household_id=household_id,
            doc_type=DocumentType(doc_type),
            external_url=external_url,
        )
    else:
        return None

    db.session.add(document)
    db.session.flush()  # assign document.id before linking
    db.session.add(DocumentLink(
        document_id=document.id, entity_type=DocumentEntityType(entity_type), entity_id=entity_id
    ))
    db.session.commit()
    return document


def _promote_to_primary(document, entity_type, entity_id):
    """Mark `document`'s link as the entity's primary photo, demoting whatever
    was primary before (it stays linked as an ordinary photo, just not the
    featured one)."""
    entity_type_enum = DocumentEntityType(entity_type)
    DocumentLink.query.filter(
        DocumentLink.entity_type == entity_type_enum,
        DocumentLink.entity_id == entity_id,
        DocumentLink.document_id != document.id,
        DocumentLink.is_primary.is_(True),
    ).update({'is_primary': False})
    DocumentLink.query.filter_by(
        document_id=document.id, entity_type=entity_type_enum, entity_id=entity_id
    ).update({'is_primary': True})
    db.session.commit()


def set_primary_photo(household_id, entity_type, entity_id, file_storage):
    """Upload a photo and mark it as the entity's one profile picture. Returns
    the new Document, or None if the upload was rejected (bad extension or
    missing file)."""
    document = save_and_link(household_id, entity_type, entity_id, DocumentType.photo.value, file_storage=file_storage)
    if document is None:
        return None
    _promote_to_primary(document, entity_type, entity_id)
    return document


def set_primary_photo_url(household_id, entity_type, entity_id, external_url):
    """Same as set_primary_photo, but for a photo hosted elsewhere (e.g. a
    vendor's favicon) rather than an upload. Returns None if `external_url`
    is falsy."""
    document = save_and_link(
        household_id, entity_type, entity_id, DocumentType.photo.value, external_url=external_url
    )
    if document is None:
        return None
    _promote_to_primary(document, entity_type, entity_id)
    return document


def get_primary_photo_for(entity_type, entity_id):
    """The entity's featured photo, or None if it doesn't have one set."""
    return (
        Document.query.join(DocumentLink, DocumentLink.document_id == Document.id)
        .filter(
            DocumentLink.entity_type == DocumentEntityType(entity_type),
            DocumentLink.entity_id == entity_id,
            DocumentLink.is_primary.is_(True),
        )
        .first()
    )


def get_primary_photos_for_many(entity_type, entity_ids):
    """Bulk form of get_primary_photo_for, for list pages — one query instead
    of one per row. Returns {entity_id: Document} for whichever ids have a
    primary photo set."""
    if not entity_ids:
        return {}
    rows = (
        db.session.query(DocumentLink.entity_id, Document)
        .join(Document, DocumentLink.document_id == Document.id)
        .filter(
            DocumentLink.entity_type == DocumentEntityType(entity_type),
            DocumentLink.entity_id.in_(entity_ids),
            DocumentLink.is_primary.is_(True),
        )
        .all()
    )
    return {entity_id: document for entity_id, document in rows}


def get_document_counts_for(entity_type, entity_ids):
    """Bulk document count per entity, for list pages that show a "has documents"
    indicator without a query per row. Returns {entity_id: count}; ids with no
    documents are simply absent rather than mapped to 0."""
    if not entity_ids:
        return {}
    rows = (
        db.session.query(DocumentLink.entity_id, db.func.count(DocumentLink.id))
        .filter(
            DocumentLink.entity_type == DocumentEntityType(entity_type),
            DocumentLink.entity_id.in_(entity_ids),
        )
        .group_by(DocumentLink.entity_id)
        .all()
    )
    return {entity_id: count for entity_id, count in rows}


def get_documents_for(entity_type, entity_id):
    """All documents linked to one entity, newest first."""
    return (
        Document.query.join(DocumentLink, DocumentLink.document_id == Document.id)
        .filter(
            DocumentLink.entity_type == DocumentEntityType(entity_type),
            DocumentLink.entity_id == entity_id,
        )
        .order_by(Document.uploaded_at.desc())
        .all()
    )


def unlink_and_maybe_delete(document_id, entity_type, entity_id):
    """Remove the link from one entity to a document; if that was the document's
    last remaining link, delete the Document row and its file on disk too, so
    unlinked uploads don't pile up."""
    link = DocumentLink.query.filter_by(
        document_id=document_id, entity_type=DocumentEntityType(entity_type), entity_id=entity_id
    ).first()
    if link is None:
        return

    db.session.delete(link)
    db.session.flush()

    remaining = DocumentLink.query.filter_by(document_id=document_id).count()
    if remaining == 0:
        document = db.session.get(Document, document_id)
        if document is not None:
            if document.file_path:
                abs_path = os.path.join(current_app.config['UPLOAD_DIR'], document.file_path)
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            db.session.delete(document)

    db.session.commit()
