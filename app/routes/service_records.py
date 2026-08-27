from flask import abort, flash, redirect, request, url_for
from flask_login import current_user, login_required

from app import db, vendor_service
from app.models import ServiceRecord
from app.routes import main_bp
from app.routes.helpers import get_household_appliance_or_404, parse_date, parse_decimal, slugify


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
    ))
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))


@main_bp.route('/service-records/<int:record_id>/delete', methods=['POST'])
@login_required
def service_record_delete(record_id):
    record = _get_service_record_or_404(record_id)
    appliance_id = record.appliance_id
    vendor_id = record.vendor_id
    db.session.delete(record)
    db.session.commit()
    if appliance_id:
        return redirect(url_for('main.appliance_detail', appliance_id=appliance_id))
    return redirect(url_for('main.vendor_detail', vendor_id=vendor_id))
