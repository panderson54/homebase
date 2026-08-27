from flask import abort, current_app, flash, redirect, request, send_from_directory, url_for
from flask_login import current_user, login_required

from app import document_service
from app.models import Document
from app.routes import main_bp
from app.routes.helpers import get_household_appliance_or_404


@main_bp.route('/appliances/<int:appliance_id>/documents', methods=['POST'])
@login_required
def document_upload(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)
    document = document_service.save_and_link(
        household_id=appliance.household_id,
        entity_type='appliance',
        entity_id=appliance.id,
        doc_type=request.form.get('doc_type', 'other'),
        file_storage=request.files.get('file'),
        external_url=request.form.get('external_url', '').strip(),
    )
    if document is None:
        flash('Attach a file (PDF, PNG, JPG, WEBP) or provide a link.', 'danger')
    return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))


@main_bp.route('/documents/<int:document_id>/delete', methods=['POST'])
@login_required
def document_delete(document_id):
    document = Document.query.get_or_404(document_id)
    appliance_id = request.form.get('appliance_id', type=int)
    appliance = get_household_appliance_or_404(appliance_id)
    document_service.unlink_and_maybe_delete(document_id, 'appliance', appliance.id)
    return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))


@main_bp.route('/documents/<int:document_id>/file')
@login_required
def document_file(document_id):
    document = Document.query.get_or_404(document_id)
    if document.household_id != current_user.household_id:
        abort(404)
    if not document.file_path:
        abort(404)
    return send_from_directory(current_app.config['UPLOAD_DIR'], document.file_path)
