"""Shared route utilities. Does NOT import main_bp (avoids circular imports)."""
import re

from flask import abort
from flask_login import current_user

from app.models import Appliance, Vendor


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
