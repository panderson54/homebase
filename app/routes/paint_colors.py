from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db, document_service
from app.models import PaintColor, Room
from app.routes import main_bp
from app.routes.helpers import get_household_paint_color_or_404, parse_hex_color


def _normalize_locations(raw):
    return ', '.join(loc.strip() for loc in raw.split(',') if loc.strip())


def _parse_room_id(form, household_id):
    room_id = form.get('room_id', '').strip()
    if not room_id:
        return None
    room = Room.query.filter_by(id=room_id, household_id=household_id).first()
    return room.id if room else None


def _apply_form(paint_color, form):
    paint_color.location = _normalize_locations(form.get('location', ''))
    paint_color.room_id = _parse_room_id(form, paint_color.household_id)
    paint_color.manufacturer = form.get('manufacturer', '').strip() or None
    paint_color.color_name = form.get('color_name', '').strip() or None
    paint_color.color_code = form.get('color_code', '').strip() or None
    paint_color.product_url = form.get('product_url', '').strip() or None
    paint_color.notes = form.get('notes', '').strip() or None

    hex_input = form.get('hex_color', '').strip()
    hex_color = parse_hex_color(hex_input)
    if hex_input and hex_color is None:
        flash(f'"{hex_input}" isn\'t a valid color (expected e.g. #D1CBC1) — saved without it.', 'warning')
    paint_color.hex_color = hex_color


@main_bp.route('/paint-colors')
@login_required
def paint_color_list():
    """Standalone list page folded into the Home page's Paint tab."""
    return redirect(url_for('main.home', tab='paint'))


@main_bp.route('/paint-colors/new', methods=['GET', 'POST'])
@login_required
def paint_color_new():
    if request.method == 'POST':
        paint_color = PaintColor(household_id=current_user.household_id)
        _apply_form(paint_color, request.form)
        db.session.add(paint_color)
        db.session.commit()
        return redirect(url_for('main.paint_color_detail', paint_color_id=paint_color.id))

    rooms = Room.query.filter_by(household_id=current_user.household_id).order_by(Room.floor, Room.name).all()
    return render_template('paint_colors/form.html', paint_color=None, rooms=rooms)


@main_bp.route('/paint-colors/<int:paint_color_id>')
@login_required
def paint_color_detail(paint_color_id):
    paint_color = get_household_paint_color_or_404(paint_color_id)
    documents = document_service.get_documents_for('paint_color', paint_color.id)
    return render_template('paint_colors/detail.html', paint_color=paint_color, documents=documents)


@main_bp.route('/paint-colors/<int:paint_color_id>/edit', methods=['GET', 'POST'])
@login_required
def paint_color_edit(paint_color_id):
    paint_color = get_household_paint_color_or_404(paint_color_id)

    if request.method == 'POST':
        _apply_form(paint_color, request.form)
        db.session.commit()
        return redirect(url_for('main.paint_color_detail', paint_color_id=paint_color.id))

    rooms = Room.query.filter_by(household_id=paint_color.household_id).order_by(Room.floor, Room.name).all()
    return render_template('paint_colors/form.html', paint_color=paint_color, rooms=rooms)


@main_bp.route('/paint-colors/<int:paint_color_id>/documents', methods=['POST'])
@login_required
def paint_color_document_upload(paint_color_id):
    paint_color = get_household_paint_color_or_404(paint_color_id)
    document = document_service.save_and_link(
        household_id=paint_color.household_id,
        entity_type='paint_color',
        entity_id=paint_color.id,
        doc_type=request.form.get('doc_type', 'photo'),
        file_storage=request.files.get('file'),
        external_url=request.form.get('external_url', '').strip(),
    )
    if document is None:
        flash('Attach a file (PDF, PNG, JPG, WEBP) or provide a link.', 'danger')
    return redirect(url_for('main.paint_color_detail', paint_color_id=paint_color.id))


@main_bp.route('/paint-colors/<int:paint_color_id>/documents/<int:document_id>/delete', methods=['POST'])
@login_required
def paint_color_document_delete(paint_color_id, document_id):
    paint_color = get_household_paint_color_or_404(paint_color_id)
    document_service.unlink_and_maybe_delete(document_id, 'paint_color', paint_color.id)
    return redirect(url_for('main.paint_color_detail', paint_color_id=paint_color.id))


@main_bp.route('/paint-colors/<int:paint_color_id>/delete', methods=['POST'])
@login_required
def paint_color_delete(paint_color_id):
    paint_color = get_household_paint_color_or_404(paint_color_id)
    # Nothing else references a paint color the way ServiceRecord references a
    # Vendor, so a real delete is safe here — but its documents (a polymorphic
    # link, not a DB-enforced cascade) need cleaning up explicitly first.
    for document in document_service.get_documents_for('paint_color', paint_color.id):
        document_service.unlink_and_maybe_delete(document.id, 'paint_color', paint_color.id)
    db.session.delete(paint_color)
    db.session.commit()
    return redirect(url_for('main.home', tab='paint'))
