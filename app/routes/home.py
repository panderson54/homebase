from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db, document_service
from app.routes import main_bp


@main_bp.route('/home', methods=['GET', 'POST'])
@login_required
def home():
    household = current_user.household

    if request.method == 'POST':
        household.name = request.form.get('name', '').strip() or household.name
        household.address = request.form.get('address', '').strip() or None
        square_footage = request.form.get('square_footage', '').strip()
        household.square_footage = int(square_footage) if square_footage else None
        year_built = request.form.get('year_built', '').strip()
        household.year_built = int(year_built) if year_built else None
        household.notes = request.form.get('notes', '').strip() or None
        db.session.commit()
        return redirect(url_for('main.home'))

    documents = document_service.get_documents_for('home', household.id)
    return render_template('home/home.html', household=household, documents=documents)


@main_bp.route('/home/documents', methods=['POST'])
@login_required
def home_document_upload():
    household = current_user.household
    document = document_service.save_and_link(
        household_id=household.id,
        entity_type='home',
        entity_id=household.id,
        doc_type=request.form.get('doc_type', 'other'),
        file_storage=request.files.get('file'),
        external_url=request.form.get('external_url', '').strip(),
    )
    if document is None:
        flash('Attach a file (PDF, PNG, JPG, WEBP) or provide a link.', 'danger')
    return redirect(url_for('main.home'))


@main_bp.route('/home/documents/<int:document_id>/delete', methods=['POST'])
@login_required
def home_document_delete(document_id):
    household = current_user.household
    document_service.unlink_and_maybe_delete(document_id, 'home', household.id)
    return redirect(url_for('main.home'))
