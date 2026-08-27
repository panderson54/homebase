"""Applies a category's seeded maintenance tasks / consumables / pro-service interval
to a newly created appliance. Kept separate from routes per the Routes -> Services ->
Models dependency rule.
"""
from app import db
from app.category_templates_data import CATEGORY_TEMPLATES
from app.maintenance_calc import compute_next_due
from app.models import CategoryTemplate, Consumable, FrequencyUnit, MaintenanceTask, TemplateKind


def apply_category_template(appliance):
    """Seed maintenance_tasks/consumables from category_templates rows and set the
    appliance's pro-service interval default, if the category has a template."""
    baseline = appliance.install_date or appliance.purchase_date

    if not appliance.pro_service_interval_value:
        default_interval = CATEGORY_TEMPLATES.get(appliance.category, {}).get('pro_service_interval')
        if default_interval:
            appliance.pro_service_interval_value, unit = default_interval
            appliance.pro_service_interval_unit = FrequencyUnit(unit)

    templates = CategoryTemplate.query.filter_by(category=appliance.category).all()
    for tmpl in templates:
        next_due = compute_next_due(baseline, tmpl.frequency_value, tmpl.frequency_unit.value) if baseline else None
        if tmpl.kind == TemplateKind.maintenance:
            db.session.add(MaintenanceTask(
                appliance_id=appliance.id,
                title=tmpl.title,
                description=tmpl.description,
                frequency_value=tmpl.frequency_value,
                frequency_unit=tmpl.frequency_unit,
                next_due_at=next_due,
            ))
        elif tmpl.kind == TemplateKind.consumable:
            db.session.add(Consumable(
                appliance_id=appliance.id,
                name=tmpl.title,
                part_number=tmpl.part_number_hint,
                frequency_value=tmpl.frequency_value,
                frequency_unit=tmpl.frequency_unit,
                next_due_at=next_due,
            ))
