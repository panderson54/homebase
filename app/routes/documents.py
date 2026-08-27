import os
import uuid

from flask import abort, current_app, flash, redirect, request, send_from_directory, url_for
from flask_login import current_user, login_required
from PIL import Image
from werkzeug.utils import secure_filename

from app import db
from app.models import Document, DocumentType
from app.routes import main_bp
from app.routes.helpers import get_household_appliance_or_404

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
ALLOWED_DOC_EXTENSIONS = {'pdf'}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_DOC_EXTENSIONS


def _extension(filename):
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def _save_upload(file_storage, household_id):
    """Validate and persist an uploaded file to disk; re-encode images with Pillow.
    Returns (file_path, content_type) relative to UPLOAD_DIR."""
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


@main_bp.route('/appliances/<int:appliance_id>/documents', methods=['POST'])
@login_required
def document_upload(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)
    doc_type = request.form.get('doc_type', 'other')
    if doc_type not in DocumentType.__members__:
        doc_type = 'other'

    external_url = request.form.get('external_url', '').strip()
    file_storage = request.files.get('file')

    if file_storage and file_storage.filename:
        file_path, content_type = _save_upload(file_storage, appliance.household_id)
        if file_path is None:
            flash('Unsupported file type. Allowed: PDF, PNG, JPG, WEBP.', 'danger')
            return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))
        document = Document(
            appliance_id=appliance.id,
            doc_type=DocumentType(doc_type),
            file_path=file_path,
            original_filename=file_storage.filename,
            content_type=content_type,
        )
    elif external_url:
        document = Document(
            appliance_id=appliance.id,
            doc_type=DocumentType(doc_type),
            external_url=external_url,
        )
    else:
        flash('Attach a file or provide a link.', 'danger')
        return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))

    db.session.add(document)
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))


@main_bp.route('/documents/<int:document_id>/delete', methods=['POST'])
@login_required
def document_delete(document_id):
    document = Document.query.get_or_404(document_id)
    appliance = get_household_appliance_or_404(document.appliance_id)

    if document.file_path:
        abs_path = os.path.join(current_app.config['UPLOAD_DIR'], document.file_path)
        if os.path.exists(abs_path):
            os.remove(abs_path)

    db.session.delete(document)
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))


@main_bp.route('/documents/<int:document_id>/file')
@login_required
def document_file(document_id):
    document = Document.query.get_or_404(document_id)
    get_household_appliance_or_404(document.appliance_id)  # enforces household scoping
    if not document.file_path:
        abort(404)
    return send_from_directory(current_app.config['UPLOAD_DIR'], document.file_path)
