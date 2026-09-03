"""Shared route utilities. Does NOT import main_bp (avoids circular imports)."""
import re

from flask import abort
from flask_login import current_user

from app.models import Appliance, FrequencyUnit, PaintColor, Room, Vendor, Zone

_HEX_COLOR_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')


def slugify(text):
    return re.sub(r'[^a-z0-9]+', '_', text.strip().lower()).strip('_')


def _bad_request(msg):
    return {'error': msg}, 400


def _not_found(resource):
    return {'error': f'{resource} not found'}, 404


def get_household_appliance_or_404(appliance_id):
    """Fetch an appliance scoped to the current user's household, or 404."""
    appliance = Appliance.query.filter_by(
        id=appliance_id, household_id=current_user.household_id
    ).first()
    if appliance is None:
        abort(404)
    return appliance


def get_household_vendor_or_404(vendor_id):
    """Fetch a vendor scoped to the current user's household, or 404."""
    vendor = Vendor.query.filter_by(
        id=vendor_id, household_id=current_user.household_id
    ).first()
    if vendor is None:
        abort(404)
    return vendor


def get_household_paint_color_or_404(paint_color_id):
    """Fetch a paint color scoped to the current user's household, or 404."""
    paint_color = PaintColor.query.filter_by(
        id=paint_color_id, household_id=current_user.household_id
    ).first()
    if paint_color is None:
        abort(404)
    return paint_color


def get_household_room_or_404(room_id):
    """Fetch a room scoped to the current user's household, or 404."""
    room = Room.query.filter_by(
        id=room_id, household_id=current_user.household_id
    ).first()
    if room is None:
        abort(404)
    return room


def get_household_zone_or_404(zone_id):
    """Fetch a zone scoped to the current user's household, or 404."""
    zone = Zone.query.filter_by(
        id=zone_id, household_id=current_user.household_id
    ).first()
    if zone is None:
        abort(404)
    return zone


def parse_service_target(value, household_id):
    """Parse a service-record form's 'appliance:<id>' / 'zone:<id>' target select
    into (appliance, zone) — both None if blank, malformed, or the referenced row
    isn't in this household."""
    value = (value or '').strip()
    if not value:
        return None, None
    kind, _, raw_id = value.partition(':')
    try:
        target_id = int(raw_id)
    except ValueError:
        return None, None
    if kind == 'appliance':
        return Appliance.query.filter_by(id=target_id, household_id=household_id).first(), None
    if kind == 'zone':
        return None, Zone.query.filter_by(id=target_id, household_id=household_id).first()
    return None, None


def parse_hex_color(value):
    """Validate a '#RRGGBB' color input; returns the uppercased value or None if
    blank/malformed. Validating here means any hex value that reaches a template
    is already safe to drop into a `style="background-color: ..."` attribute."""
    value = (value or '').strip()
    if not value:
        return None
    return value.upper() if _HEX_COLOR_RE.match(value) else None


def parse_date(value):
    """Parse an HTML date input (YYYY-MM-DD) into a date, or None if blank."""
    from datetime import datetime
    if not value:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def parse_decimal(value):
    """Parse a form's cost/price input into a Decimal, or None if blank/invalid."""
    from decimal import Decimal, InvalidOperation
    value = (value or '').strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def parse_pro_service_interval(form):
    """Parse an Appliance/Zone edit form's paired interval-value + interval-unit
    fields; both must be present or the interval is treated as unset."""
    value = form.get('pro_service_interval_value', '').strip()
    unit = form.get('pro_service_interval_unit', '').strip()
    if not value or not unit:
        return None, None
    return int(value), FrequencyUnit(unit)
