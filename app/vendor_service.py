"""Resolves the vendor for a service-visit submission that offers a "pick an
existing vendor, or quick-add a new one" choice — used by the appliance-scoped
service-record route (routes that already know their vendor, like the
vendor-scoped one, don't need this).
"""
from app import db
from app.models import Vendor

NEW_VENDOR_SENTINEL = '__new__'


def resolve_vendor(household_id, vendor_id, new_vendor_name=None, new_vendor_type=None):
    """Return the picked existing Vendor (verified to belong to household_id) or a
    newly created one from new_vendor_name/new_vendor_type. Returns None if
    vendor_id is missing/invalid, belongs to a different household, or no name
    was given for a new vendor — callers should treat that as a validation error.
    """
    if vendor_id and vendor_id != NEW_VENDOR_SENTINEL:
        try:
            vendor = db.session.get(Vendor, int(vendor_id))
        except ValueError:
            return None
        if vendor is None or vendor.household_id != household_id:
            return None
        return vendor

    if not new_vendor_name:
        return None

    vendor = Vendor(household_id=household_id, name=new_vendor_name, vendor_type=new_vendor_type or 'other')
    db.session.add(vendor)
    db.session.flush()
    return vendor
