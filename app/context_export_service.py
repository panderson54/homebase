"""Builds a verbose Markdown snapshot of everything Homebase knows about a
household, for use as LLM context (e.g. RAG grounding in another project).
Deliberately includes full history, not just current state — appliance counts
here are small enough that this comfortably fits a modern context window.

Document *contents* (PDF/photo bytes) are not inlined, only their metadata —
text-extraction from manuals is a separate, later feature.
"""
from datetime import datetime

from app import document_service
from app.category_templates_data import CATEGORY_LABELS
from app.models import ApplianceStatus
from app.vendor_types_data import VENDOR_TYPE_LABELS


def _document_lines(documents):
    if not documents:
        return ['  (no documents)']
    lines = []
    for doc in documents:
        label = doc.doc_type.value.replace('_', ' ')
        target = doc.original_filename if doc.file_path else doc.external_url
        lines.append(f'  - {label}: {target}')
    return lines


def _maintenance_task_lines(task):
    lines = [f'  - {task.title} (every {task.frequency_value} {task.frequency_unit.value})']
    if task.description:
        lines.append(f'    Description: {task.description}')
    if not task.active:
        lines.append('    Status: inactive')
    if task.next_due_at:
        lines.append(f'    Next due: {task.next_due_at.isoformat()}')
    if task.logs:
        lines.append('    Completion history (most recent first):')
        for log in task.logs:
            who = f' by {log.completed_by.name}' if log.completed_by else ''
            note = f' — {log.notes}' if log.notes else ''
            lines.append(f'      - {log.completed_at.isoformat()}{who}{note}')
    else:
        lines.append('    Never completed yet.')
    return lines


def _consumable_lines(consumable):
    freq = (
        f'every {consumable.frequency_value} {consumable.frequency_unit.value}'
        if consumable.frequency_value and consumable.frequency_unit else 'no replacement schedule'
    )
    lines = [f'  - {consumable.name} ({freq})']
    if consumable.part_number:
        lines.append(f'    Part number: {consumable.part_number}')
    if consumable.purchase_url:
        lines.append(f'    Purchase link: {consumable.purchase_url}')
    if consumable.last_replaced_at:
        lines.append(f'    Last replaced: {consumable.last_replaced_at.isoformat()}')
    if consumable.next_due_at:
        lines.append(f'    Next due: {consumable.next_due_at.isoformat()}')
    return lines


def _service_record_lines(records, show_vendor=True, show_appliance=False):
    if not records:
        return ['  (no service visits logged)']
    lines = []
    for record in records:
        vendor = f' — {record.vendor.name}' if show_vendor and record.vendor else ''
        appliance = f' — {record.appliance.name}' if show_appliance and record.appliance else ''
        cost = f' — ${record.cost:.2f}' if record.cost is not None else ''
        lines.append(f'  - {record.service_date.isoformat()}{vendor}{appliance}{cost}')
        if record.notes:
            lines.append(f'    Notes: {record.notes}')
    return lines


def _vendor_section(vendor):
    label = VENDOR_TYPE_LABELS.get(vendor.vendor_type, vendor.vendor_type)
    lines = [f'### {vendor.name} ({label})', '']
    for field_label, value in (
        ('Contact', vendor.contact_name),
        ('Phone', vendor.phone),
        ('Email', vendor.email),
        ('Website', vendor.website),
    ):
        if value:
            lines.append(f'- {field_label}: {value}')
    if vendor.notes:
        lines.append(f'- Notes: {vendor.notes}')
    lines.append('')

    lines.append('#### Documents')
    lines.extend(_document_lines(document_service.get_documents_for('vendor', vendor.id)))
    lines.append('')

    lines.append('#### Service history')
    lines.extend(_service_record_lines(vendor.services, show_vendor=False, show_appliance=True))
    lines.append('')

    return lines


def _paint_color_section(paint_color):
    header = paint_color.location
    if paint_color.color_name:
        header += f' — {paint_color.color_name}'
    lines = [f'### {header}', '']
    for field_label, value in (
        ('Manufacturer', paint_color.manufacturer),
        ('Color code', paint_color.color_code),
        ('Hex color', paint_color.hex_color),
        ('Product link', paint_color.product_url),
    ):
        if value:
            lines.append(f'- {field_label}: {value}')
    if paint_color.notes:
        lines.append(f'- Notes: {paint_color.notes}')
    lines.append('')

    lines.append('#### Documents')
    lines.extend(_document_lines(document_service.get_documents_for('paint_color', paint_color.id)))
    lines.append('')

    return lines


def _appliance_section(appliance):
    label = CATEGORY_LABELS.get(appliance.category, appliance.category)
    lines = [f'### {appliance.name} ({label})', '']
    for field_label, value in (
        ('Make', appliance.make),
        ('Model number', appliance.model_number),
        ('Serial number', appliance.serial_number),
        ('Location', appliance.location),
        ('Installed', appliance.install_date.isoformat() if appliance.install_date else None),
        ('Purchased', appliance.purchase_date.isoformat() if appliance.purchase_date else None),
    ):
        if value:
            lines.append(f'- {field_label}: {value}')
    if appliance.notes:
        lines.append(f'- Notes: {appliance.notes}')
    if appliance.pro_service_interval_value:
        next_due = appliance.pro_service_next_due
        next_due_str = f', next due {next_due.isoformat()}' if next_due else ''
        lines.append(
            f'- Professional service: every {appliance.pro_service_interval_value} '
            f'{appliance.pro_service_interval_unit.value}{next_due_str}'
        )
    lines.append('')

    lines.append('#### Documents')
    lines.extend(_document_lines(document_service.get_documents_for('appliance', appliance.id)))
    lines.append('')

    lines.append('#### Maintenance tasks')
    if appliance.maintenance_tasks:
        for task in appliance.maintenance_tasks:
            lines.extend(_maintenance_task_lines(task))
    else:
        lines.append('  (none tracked)')
    lines.append('')

    lines.append('#### Consumables')
    if appliance.consumables:
        for consumable in appliance.consumables:
            lines.extend(_consumable_lines(consumable))
    else:
        lines.append('  (none tracked)')
    lines.append('')

    lines.append('#### Service history')
    lines.extend(_service_record_lines(appliance.service_records))
    lines.append('')

    return lines


def build_context_markdown(household):
    lines = [
        '# Homebase Context Export',
        f'Generated: {datetime.utcnow().isoformat(timespec="seconds")} UTC',
        '',
        '## Home',
        f'- Name: {household.name}',
    ]
    if household.address:
        lines.append(f'- Address: {household.address}')
    if household.square_footage:
        lines.append(f'- Square footage: {household.square_footage}')
    if household.year_built:
        lines.append(f'- Year built: {household.year_built} ({household.age_years} years old)')
    if household.notes:
        lines.append(f'- Notes: {household.notes}')
    lines.append('')
    lines.append('### Home documents')
    lines.extend(_document_lines(document_service.get_documents_for('home', household.id)))
    lines.append('')

    active = sorted(
        (a for a in household.appliances if a.status == ApplianceStatus.active), key=lambda a: a.name
    )
    archived = sorted(
        (a for a in household.appliances if a.status == ApplianceStatus.archived), key=lambda a: a.name
    )

    lines.append('## Appliances')
    lines.append('')
    if active:
        for appliance in active:
            lines.extend(_appliance_section(appliance))
    else:
        lines.append('(no active appliances)')
        lines.append('')

    if archived:
        lines.append('## Archived appliances')
        lines.append('')
        for appliance in archived:
            lines.extend(_appliance_section(appliance))

    vendors = sorted(household.vendors, key=lambda v: v.name)
    if vendors:
        lines.append('## Vendors')
        lines.append('')
        for vendor in vendors:
            lines.extend(_vendor_section(vendor))

    paint_colors = sorted(household.paint_colors, key=lambda p: p.location)
    if paint_colors:
        lines.append('## Paint Colors')
        lines.append('')
        for paint_color in paint_colors:
            lines.extend(_paint_color_section(paint_color))

    return '\n'.join(lines)
