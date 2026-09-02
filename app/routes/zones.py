from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db, vendor_service
from app.models import ServiceCategory, ServiceRecord, Vendor, Zone
from app.routes import main_bp
from app.routes.helpers import get_household_zone_or_404, parse_date, parse_decimal, slugify


def _apply_form(zone, form):
    zone.name = form.get('name', '').strip()
    zone.notes = form.get('notes', '').strip() or None


@main_bp.route('/zones/new', methods=['POST'])
@login_required
def zone_new():
    zone = Zone(household_id=current_user.household_id)
    _apply_form(zone, request.form)
    if not zone.name:
        flash('Give the zone a name.', 'danger')
        return redirect(url_for('main.home', tab='zones'))
    db.session.add(zone)
    db.session.commit()
    return redirect(url_for('main.home', tab='zones'))


@main_bp.route('/zones/<int:zone_id>')
@login_required
def zone_detail(zone_id):
    zone = get_household_zone_or_404(zone_id)
    vendors = Vendor.query.filter_by(household_id=zone.household_id).order_by(Vendor.name).all()
    return render_template('zones/detail.html', zone=zone, vendors=vendors)


@main_bp.route('/zones/<int:zone_id>/edit', methods=['GET', 'POST'])
@login_required
def zone_edit(zone_id):
    zone = get_household_zone_or_404(zone_id)

    if request.method == 'POST':
        _apply_form(zone, request.form)
        if not zone.name:
            flash('Give the zone a name.', 'danger')
            return redirect(url_for('main.zone_edit', zone_id=zone.id))
        db.session.commit()
        return redirect(url_for('main.zone_detail', zone_id=zone.id))

    return render_template('zones/edit.html', zone=zone)


@main_bp.route('/zones/<int:zone_id>/delete', methods=['POST'])
@login_required
def zone_delete(zone_id):
    zone = get_household_zone_or_404(zone_id)
    db.session.delete(zone)
    db.session.commit()
    return redirect(url_for('main.home', tab='zones'))


@main_bp.route('/zones/<int:zone_id>/service-records', methods=['POST'])
@login_required
def zone_service_create(zone_id):
    zone = get_household_zone_or_404(zone_id)

    new_vendor_type = request.form.get('new_vendor_type', '').strip()
    vendor = vendor_service.resolve_vendor(
        household_id=zone.household_id,
        vendor_id=request.form.get('vendor_id', ''),
        new_vendor_name=request.form.get('new_vendor_name', '').strip(),
        new_vendor_type=slugify(new_vendor_type) if new_vendor_type else None,
    )
    if vendor is None:
        flash('Select an existing vendor or enter a name for a new one.', 'danger')
        return redirect(url_for('main.zone_detail', zone_id=zone.id))

    db.session.add(ServiceRecord(
        household_id=zone.household_id,
        vendor_id=vendor.id,
        zone_id=zone.id,
        service_date=parse_date(request.form.get('service_date')),
        notes=request.form.get('notes', '').strip() or None,
        cost=parse_decimal(request.form.get('cost')),
        category=ServiceCategory(request.form.get('category', 'maintenance')),
    ))
    db.session.commit()
    return redirect(url_for('main.zone_detail', zone_id=zone.id))
