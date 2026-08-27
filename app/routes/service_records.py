from decimal import Decimal, InvalidOperation

from flask import redirect, request, url_for
from flask_login import login_required

from app import db
from app.models import ServiceRecord
from app.routes import main_bp
from app.routes.helpers import get_household_appliance_or_404, parse_date


def _get_service_record_or_404(record_id):
    record = ServiceRecord.query.get_or_404(record_id)
    get_household_appliance_or_404(record.appliance_id)  # enforces household scoping
    return record


@main_bp.route('/appliances/<int:appliance_id>/service-records', methods=['POST'])
@login_required
def service_record_create(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)
    cost_raw = request.form.get('cost', '').strip()
    try:
        cost = Decimal(cost_raw) if cost_raw else None
    except InvalidOperation:
        cost = None

    db.session.add(ServiceRecord(
        appliance_id=appliance.id,
        service_date=parse_date(request.form.get('service_date')),
        vendor=request.form.get('vendor', '').strip() or None,
        notes=request.form.get('notes', '').strip() or None,
        cost=cost,
    ))
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))


@main_bp.route('/service-records/<int:record_id>/delete', methods=['POST'])
@login_required
def service_record_delete(record_id):
    record = _get_service_record_or_404(record_id)
    appliance_id = record.appliance_id
    db.session.delete(record)
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=appliance_id))
