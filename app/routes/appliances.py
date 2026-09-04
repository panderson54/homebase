from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import appliance_lookup_service, db, document_service
from app.category_templates_data import CATEGORY_LABELS
from app.models import Appliance, ApplianceStatus, Room, Vendor
from app.routes import main_bp
from app.routes.helpers import get_household_appliance_or_404, parse_date, parse_pro_service_interval, slugify
from app.template_service import apply_category_template

_LOOKUP_IMAGE_MEDIA_TYPES = {
    'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp',
}


def _parse_room_id(form, household_id):
    room_id = form.get('room_id', '').strip()
    if not room_id:
        return None
    room = Room.query.filter_by(id=room_id, household_id=household_id).first()
    return room.id if room else None


def _parse_manufacture_year(form):
    value = form.get('manufacture_year', '').strip()
    return int(value) if value.isdigit() else None


@main_bp.route('/appliances/lookup', methods=['POST'])
@login_required
def appliance_lookup():
    model_number = request.form.get('model_number', '')
    image_bytes = None
    image_media_type = 'image/jpeg'
    photo = request.files.get('photo')
    if photo and photo.filename:
        ext = photo.filename.rsplit('.', 1)[-1].lower() if '.' in photo.filename else ''
        if ext in _LOOKUP_IMAGE_MEDIA_TYPES:
            image_media_type = _LOOKUP_IMAGE_MEDIA_TYPES[ext]
            image_bytes = photo.read()

    result = appliance_lookup_service.lookup_appliance(
        model_number=model_number, image_bytes=image_bytes, image_media_type=image_media_type,
    )
    return jsonify(result)


@main_bp.route('/appliances')
@login_required
def appliance_list():
    show_archived = request.args.get('archived') == '1'
    status = ApplianceStatus.archived if show_archived else ApplianceStatus.active
    appliances = Appliance.query.filter_by(
        household_id=current_user.household_id, status=status
    ).order_by(Appliance.name).all()
    return render_template('appliances/list.html', appliances=appliances, show_archived=show_archived)


@main_bp.route('/appliances/new', methods=['GET', 'POST'])
@login_required
def appliance_new():
    if request.method == 'POST':
        category = request.form.get('category', '')
        if category == '__other__':
            category = slugify(request.form.get('custom_category', ''))

        appliance = Appliance(
            household_id=current_user.household_id,
            category=category,
            name=request.form.get('name', '').strip(),
            make=request.form.get('make', '').strip() or None,
            model_number=request.form.get('model_number', '').strip() or None,
            serial_number=request.form.get('serial_number', '').strip() or None,
            room_id=_parse_room_id(request.form, current_user.household_id),
            manufacture_year=_parse_manufacture_year(request.form),
            install_date=parse_date(request.form.get('install_date')),
            purchase_date=parse_date(request.form.get('purchase_date')),
            notes=request.form.get('notes', '').strip() or None,
        )
        appliance.pro_service_interval_value, appliance.pro_service_interval_unit = (
            parse_pro_service_interval(request.form)
        )
        db.session.add(appliance)
        db.session.flush()  # assign appliance.id before seeding related rows

        if request.form.get('apply_template') == 'on':
            apply_category_template(appliance)

        db.session.commit()

        for file_storage in request.files.getlist('documents'):
            if not file_storage or not file_storage.filename:
                continue
            doc_type = 'photo' if file_storage.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) else 'manual'
            document_service.save_and_link(
                household_id=appliance.household_id, entity_type='appliance', entity_id=appliance.id,
                doc_type=doc_type, file_storage=file_storage,
            )

        manual_url = request.form.get('manual_url', '').strip()
        if manual_url:
            document_service.save_and_link(
                household_id=appliance.household_id, entity_type='appliance', entity_id=appliance.id,
                doc_type='manual', external_url=manual_url,
            )

        return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))

    rooms = Room.query.filter_by(household_id=current_user.household_id).order_by(Room.floor, Room.name).all()
    return render_template('appliances/form.html', appliance=None, category_labels=CATEGORY_LABELS, rooms=rooms)


@main_bp.route('/appliances/<int:appliance_id>')
@login_required
def appliance_detail(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)
    documents = document_service.get_documents_for('appliance', appliance.id)
    primary_photo = document_service.get_primary_photo_for('appliance', appliance.id)
    vendors = Vendor.query.filter_by(household_id=current_user.household_id).order_by(Vendor.name).all()
    record_document_counts = document_service.get_document_counts_for(
        'service_record', [r.id for r in appliance.service_records]
    )
    return render_template(
        'appliances/detail.html', appliance=appliance, documents=documents, primary_photo=primary_photo,
        vendors=vendors, record_document_counts=record_document_counts,
    )


@main_bp.route('/appliances/<int:appliance_id>/photo', methods=['POST'])
@login_required
def appliance_photo_upload(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)
    document = document_service.set_primary_photo(
        appliance.household_id, 'appliance', appliance.id, request.files.get('photo')
    )
    if document is None:
        flash('Choose a PNG, JPG, or WEBP image.', 'danger')
    return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))


@main_bp.route('/appliances/<int:appliance_id>/edit', methods=['GET', 'POST'])
@login_required
def appliance_edit(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)

    if request.method == 'POST':
        category = request.form.get('category', '')
        if category == '__other__':
            category = slugify(request.form.get('custom_category', ''))

        appliance.category = category
        appliance.name = request.form.get('name', '').strip()
        appliance.make = request.form.get('make', '').strip() or None
        appliance.model_number = request.form.get('model_number', '').strip() or None
        appliance.serial_number = request.form.get('serial_number', '').strip() or None
        appliance.room_id = _parse_room_id(request.form, appliance.household_id)
        appliance.manufacture_year = _parse_manufacture_year(request.form)
        appliance.install_date = parse_date(request.form.get('install_date'))
        appliance.purchase_date = parse_date(request.form.get('purchase_date'))
        appliance.notes = request.form.get('notes', '').strip() or None
        appliance.pro_service_interval_value, appliance.pro_service_interval_unit = (
            parse_pro_service_interval(request.form)
        )
        db.session.commit()
        return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))

    rooms = Room.query.filter_by(household_id=appliance.household_id).order_by(Room.floor, Room.name).all()
    return render_template('appliances/form.html', appliance=appliance, category_labels=CATEGORY_LABELS, rooms=rooms)


@main_bp.route('/appliances/<int:appliance_id>/archive', methods=['POST'])
@login_required
def appliance_archive(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)
    appliance.status = ApplianceStatus.archived
    db.session.commit()
    return redirect(url_for('main.appliance_list'))


@main_bp.route('/appliances/<int:appliance_id>/unarchive', methods=['POST'])
@login_required
def appliance_unarchive(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)
    appliance.status = ApplianceStatus.active
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))
