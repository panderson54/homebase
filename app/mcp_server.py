"""A basic MCP (Model Context Protocol) server exposing Homebase's services
feature to an LLM client: logging a vendor service visit against an
existing appliance or zone, resolving an existing vendor or quick-adding a
stub for a new one. Deliberately does not expose creating appliances,
zones, or rooms — those stay a manual, browsable step in the web app.

Homebase is single-household (see README), so — like `flask create-user`
in cli.py — this operates on the one Household row rather than needing a
login/session of its own.

Run with: `.venv/bin/python -m app.mcp_server`
"""
from datetime import date

from mcp.server.mcpserver import MCPServer

from app import create_app, service_record_service, vendor_service
from app.models import Appliance, Household, ServiceCategory, Vendor, Zone

mcp = MCPServer('homebase-services')

_flask_app = create_app()
_flask_app.app_context().push()


def _household():
    household = Household.query.first()
    if household is None:
        raise RuntimeError('No household exists yet — run `flask create-user` first.')
    return household


@mcp.tool()
def list_appliances() -> list[dict]:
    """List appliances a service visit can be logged against."""
    household = _household()
    return [
        {'id': a.id, 'name': a.name, 'category': a.category_label, 'room': a.room.name if a.room else None}
        for a in Appliance.query.filter_by(household_id=household.id).order_by(Appliance.name).all()
    ]


@mcp.tool()
def list_zones() -> list[dict]:
    """List zones (roof, gutters, garden, etc.) a service visit can be logged against."""
    household = _household()
    return [
        {'id': z.id, 'name': z.name}
        for z in Zone.query.filter_by(household_id=household.id).order_by(Zone.name).all()
    ]


@mcp.tool()
def list_vendors() -> list[dict]:
    """List vendors already on file, to check before adding a new one."""
    household = _household()
    return [
        {'id': v.id, 'name': v.name, 'vendor_type': v.vendor_type_label}
        for v in Vendor.query.filter_by(household_id=household.id).order_by(Vendor.name).all()
    ]


@mcp.tool()
def create_service(
    service_date: str,
    appliance_id: int | None = None,
    zone_id: int | None = None,
    vendor_id: int | None = None,
    vendor_name: str | None = None,
    vendor_type: str | None = None,
    notes: str | None = None,
    cost: float | None = None,
    category: str = 'maintenance',
) -> dict:
    """Log a vendor service visit against an existing appliance or zone.

    Pass exactly one of appliance_id/zone_id (use list_appliances/list_zones
    to find the id) — this never creates a new appliance, zone, or room.
    For the vendor, pass exactly one of vendor_id (an existing vendor from
    list_vendors) or vendor_name: a name matching an existing vendor reuses
    it, otherwise a new vendor stub is created (optionally tagged with
    vendor_type, e.g. "hvac", "plumbing").
    """
    household = _household()

    if bool(appliance_id) == bool(zone_id):
        raise ValueError('Pass exactly one of appliance_id or zone_id.')
    appliance = zone = None
    if appliance_id:
        appliance = Appliance.query.filter_by(id=appliance_id, household_id=household.id).first()
        if appliance is None:
            raise ValueError(f'No appliance {appliance_id} in this household.')
    else:
        zone = Zone.query.filter_by(id=zone_id, household_id=household.id).first()
        if zone is None:
            raise ValueError(f'No zone {zone_id} in this household.')

    if bool(vendor_id) == bool(vendor_name):
        raise ValueError('Pass exactly one of vendor_id or vendor_name.')
    vendor_created = False
    if vendor_id:
        vendor = Vendor.query.filter_by(id=vendor_id, household_id=household.id).first()
        if vendor is None:
            raise ValueError(f'No vendor {vendor_id} in this household.')
    else:
        vendor, vendor_created = vendor_service.find_or_create_by_name(household.id, vendor_name, vendor_type)

    try:
        parsed_date = date.fromisoformat(service_date)
    except ValueError:
        raise ValueError('service_date must be in YYYY-MM-DD format.')
    try:
        category = ServiceCategory(category)
    except ValueError:
        raise ValueError(f'category must be one of {[c.value for c in ServiceCategory]}.')

    record = service_record_service.create(
        household_id=household.id, vendor=vendor, service_date=parsed_date,
        appliance=appliance, zone=zone, notes=notes, cost=cost, category=category,
    )
    return {
        'service_record_id': record.id,
        'vendor': {'id': vendor.id, 'name': vendor.name, 'created': vendor_created},
        'appliance_id': appliance.id if appliance else None,
        'zone_id': zone.id if zone else None,
        'service_date': record.service_date.isoformat(),
        'category': record.category.value,
    }


if __name__ == '__main__':
    mcp.run()
