"""Creates a ServiceRecord for either an appliance or a zone — the one piece
of logic shared by the appliance-scoped route, the vendor-scoped route, and
the MCP service tool.
"""
from app import db
from app.models import ServiceCategory, ServiceRecord


def create(household_id, vendor, service_date, appliance=None, zone=None, notes=None, cost=None,
           category=ServiceCategory.maintenance):
    """Create and commit a ServiceRecord. Caller is responsible for ensuring
    vendor/appliance/zone all belong to household_id."""
    record = ServiceRecord(
        household_id=household_id,
        vendor_id=vendor.id,
        appliance_id=appliance.id if appliance else None,
        zone_id=zone.id if zone else None,
        service_date=service_date,
        notes=notes or None,
        cost=cost,
        category=ServiceCategory(category),
    )
    db.session.add(record)
    db.session.commit()
    return record
