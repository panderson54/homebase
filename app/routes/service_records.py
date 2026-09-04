from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db, document_service, vendor_service
from app.models import Appliance, ServiceCategory, ServiceRecord, Vendor, Zone
from app.routes import main_bp
from app.routes.helpers import (
    get_household_appliance_or_404, parse_date, parse_decimal, parse_service_target, slugify,
)


def _get_service_record_or_404(record_id):
    record = ServiceRecord.query.get_or_404(record_id)
    if record.household_id != current_user.household_id:
        abort(404)
    return record


@main_bp.route('/appliances/<int:appliance_id>/service-records', methods=['POST'])
@login_required
def service_record_create(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)

    new_vendor_type = request.form.get('new_vendor_type', '').strip()
    vendor = vendor_service.resolve_vendor(
        household_id=appliance.household_id,
        vendor_id=request.form.get('vendor_id', ''),
        new_vendor_name=request.form.get('new_vendor_name', '').strip(),
        new_vendor_type=slugify(new_vendor_type) if new_vendor_type else None,
    )
    if vendor is None:
        flash('Select an existing vendor or enter a name for a new one.', 'danger')
        return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))

    db.session.add(ServiceRecord(
        household_id=appliance.household_id,
        vendor_id=vendor.id,
        appliance_id=appliance.id,
        service_date=parse_date(request.form.get('service_date')),
        notes=request.form.get('notes', '').strip() or None,
        cost=parse_decimal(request.form.get('cost')),
        category=ServiceCategory(request.form.get('category', 'maintenance')),
    ))
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))


@main_bp.route('/service-records/<int:record_id>/edit', methods=['GET', 'POST'])
@login_required
def service_record_edit(record_id):
    record = _get_service_record_or_404(record_id)

    if request.method == 'POST':
        vendor_id = request.form.get('vendor_id', '').strip()
        vendor = None
        if vendor_id:
            vendor = Vendor.query.filter_by(id=vendor_id, household_id=record.household_id).first()
        if vendor is None:
            flash('Select a vendor.', 'danger')
            return redirect(url_for('main.service_record_edit', record_id=record.id))

        appliance, zone = parse_service_target(request.form.get('target'), record.household_id)

        record.vendor_id = vendor.id
        record.appliance_id = appliance.id if appliance else None
        record.zone_id = zone.id if zone else None
        record.service_date = parse_date(request.form.get('service_date'))
        record.notes = request.form.get('notes', '').strip() or None
        record.cost = parse_decimal(request.form.get('cost'))
        record.category = ServiceCategory(request.form.get('category', 'maintenance'))
        db.session.commit()

        if record.appliance_id:
            return redirect(url_for('main.appliance_detail', appliance_id=record.appliance_id))
        if record.zone_id:
            return redirect(url_for('main.zone_detail', zone_id=record.zone_id))
        return redirect(url_for('main.vendor_detail', vendor_id=record.vendor_id))

    vendors = Vendor.query.filter_by(household_id=record.household_id).order_by(Vendor.name).all()
    appliances = Appliance.query.filter_by(household_id=record.household_id).order_by(Appliance.name).all()
    zones = Zone.query.filter_by(household_id=record.household_id).order_by(Zone.name).all()
    documents = document_service.get_documents_for('service_record', record.id)
    return render_template(
        'service_records/edit.html', record=record, vendors=vendors, appliances=appliances, zones=zones,
        documents=documents,
    )


@main_bp.route('/service-records/<int:record_id>/documents', methods=['POST'])
@login_required
def service_record_document_upload(record_id):
    record = _get_service_record_or_404(record_id)
    document = document_service.save_and_link(
        household_id=record.household_id,
        entity_type='service_record',
        entity_id=record.id,
        doc_type=request.form.get('doc_type', 'invoice'),
        file_storage=request.files.get('file'),
        external_url=request.form.get('external_url', '').strip(),
    )
    if document is None:
        flash('Attach a file (PDF, PNG, JPG, WEBP) or provide a link.', 'danger')
    return redirect(url_for('main.service_record_edit', record_id=record.id))


@main_bp.route('/service-records/<int:record_id>/documents/<int:document_id>/delete', methods=['POST'])
@login_required
def service_record_document_delete(record_id, document_id):
    record = _get_service_record_or_404(record_id)
    document_service.unlink_and_maybe_delete(document_id, 'service_record', record.id)
    return redirect(url_for('main.service_record_edit', record_id=record.id))


@main_bp.route('/service-records/<int:record_id>/delete', methods=['POST'])
@login_required
def service_record_delete(record_id):
    record = _get_service_record_or_404(record_id)
    appliance_id = record.appliance_id
    zone_id = record.zone_id
    vendor_id = record.vendor_id
    # Documents are a polymorphic link, not a DB-enforced cascade — clean them
    # up explicitly before the record itself goes away.
    for document in document_service.get_documents_for('service_record', record.id):
        document_service.unlink_and_maybe_delete(document.id, 'service_record', record.id)
    db.session.delete(record)
    db.session.commit()
    if appliance_id:
        return redirect(url_for('main.appliance_detail', appliance_id=appliance_id))
    if zone_id:
        return redirect(url_for('main.zone_detail', zone_id=zone_id))
    return redirect(url_for('main.vendor_detail', vendor_id=vendor_id))
