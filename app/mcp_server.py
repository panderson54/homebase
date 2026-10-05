"""A basic MCP (Model Context Protocol) server exposing Homebase's services
feature to an LLM client: logging a vendor service visit against an
existing appliance or zone, resolving an existing vendor or quick-adding a
stub for a new one. Deliberately does not expose creating appliances,
zones, or rooms — those stay a manual, browsable step in the web app.

It also lets agents file and read feature requests (the /agent-request page),
but not approve/deny them — reviewing stays with the homeowner.

Homebase is single-household (see README), so — like `flask create-user`
in cli.py — this operates on the one Household row rather than needing a
login/session of its own.

Run with: `.venv/bin/python -m app.mcp_server`
"""
from datetime import date

from mcp.server.mcpserver import MCPServer

from app import create_app, feature_request_service, service_record_service, vendor_service
from app.feature_request_data import STATUS_LABELS, agent_instructions_text
from app.models import Appliance, FeatureRequest, Household, ServiceCategory, Vendor, Zone

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


def _feature_request(household, request_id):
    feature_request = FeatureRequest.query.filter_by(id=request_id, household_id=household.id).first()
    if feature_request is None:
        raise ValueError(f'No feature request {request_id} in this household.')
    return feature_request


@mcp.tool()
def feature_request_instructions() -> str:
    """How to write a useful feature request, and every field's meaning and allowed values.
    Read this before submit_feature_request."""
    return agent_instructions_text()


@mcp.tool()
def list_feature_requests(status: str | None = None) -> list[dict]:
    """List feature requests (newest first; unread oldest first), optionally filtered by status
    (unread, approved, denied, implemented). Check this for duplicates before submitting."""
    household = _household()
    if status is not None and status not in STATUS_LABELS:
        raise ValueError(f'status must be one of {list(STATUS_LABELS)}.')
    return [
        feature_request_service.summary_dict(fr)
        for fr in feature_request_service.list_for_household(household.id, status)
    ]


@mcp.tool()
def get_feature_request(request_id: int) -> dict:
    """Get one feature request in full, including a `markdown` rendering to use as a build spec."""
    feature_request = _feature_request(_household(), request_id)
    return {
        **feature_request_service.full_dict(feature_request),
        'markdown': feature_request_service.to_markdown(feature_request),
    }


@mcp.tool()
def submit_feature_request(
    title: str,
    summary: str,
    request_type: str,
    area: str,
    trying_to_do: str,
    problem: str,
    proposed_behavior: str,
    acceptance_criteria: str,
    priority: str,
    submitted_by: str,
    priority_reason: str | None = None,
    page_url: str | None = None,
    workaround: str | None = None,
    data_entities: str | None = None,
    implementation_notes: str | None = None,
    out_of_scope: str | None = None,
    related_requests: str | None = None,
    context_url: str | None = None,
) -> dict:
    """File a new feature request (status starts as unread). Call feature_request_instructions
    first for field guidance and allowed values; acceptance_criteria is one check per line.
    All validation errors are reported together so they can be fixed in one retry."""
    fields = dict(locals())
    feature_request = feature_request_service.create(_household().id, fields)
    return feature_request_service.summary_dict(feature_request)


@mcp.tool()
def update_feature_request(
    request_id: int,
    title: str | None = None,
    summary: str | None = None,
    request_type: str | None = None,
    area: str | None = None,
    trying_to_do: str | None = None,
    problem: str | None = None,
    proposed_behavior: str | None = None,
    acceptance_criteria: str | None = None,
    priority: str | None = None,
    submitted_by: str | None = None,
    priority_reason: str | None = None,
    page_url: str | None = None,
    workaround: str | None = None,
    data_entities: str | None = None,
    implementation_notes: str | None = None,
    out_of_scope: str | None = None,
    related_requests: str | None = None,
    context_url: str | None = None,
) -> dict:
    """Edit an existing feature request — e.g. add your use case to a duplicate's trying_to_do
    instead of filing a new one. Only the fields you pass change; each replaces the whole
    field, so include the existing text when appending. Never changes status."""
    fields = dict(locals())
    changes = {k: v for k, v in fields.items() if k in feature_request_service.FIELD_NAMES and v is not None}
    feature_request = _feature_request(_household(), request_id)
    feature_request_service.update(feature_request, {**feature_request_service.form_values(feature_request), **changes})
    return feature_request_service.summary_dict(feature_request)


if __name__ == '__main__':
    mcp.run()
