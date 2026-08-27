from datetime import date

from flask import redirect, request, url_for
from flask_login import login_required

from app import db
from app.maintenance_calc import compute_next_due
from app.models import Consumable, FrequencyUnit
from app.routes import main_bp
from app.routes.helpers import get_household_appliance_or_404, parse_date


def _get_consumable_or_404(consumable_id):
    consumable = Consumable.query.get_or_404(consumable_id)
    get_household_appliance_or_404(consumable.appliance_id)  # enforces household scoping
    return consumable


@main_bp.route('/appliances/<int:appliance_id>/consumables', methods=['POST'])
@login_required
def consumable_create(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)
    frequency_value = request.form.get('frequency_value', '').strip()
    frequency_unit = request.form.get('frequency_unit', '').strip()
    consumable = Consumable(
        appliance_id=appliance.id,
        name=request.form.get('name', '').strip(),
        part_number=request.form.get('part_number', '').strip() or None,
        purchase_url=request.form.get('purchase_url', '').strip() or None,
        frequency_value=int(frequency_value) if frequency_value else None,
        frequency_unit=FrequencyUnit(frequency_unit) if frequency_unit else None,
    )
    db.session.add(consumable)
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))


@main_bp.route('/consumables/<int:consumable_id>/replace', methods=['POST'])
@login_required
def consumable_replace(consumable_id):
    consumable = _get_consumable_or_404(consumable_id)
    replaced_at = parse_date(request.form.get('replaced_at')) or date.today()

    consumable.last_replaced_at = replaced_at
    if consumable.frequency_value and consumable.frequency_unit:
        consumable.next_due_at = compute_next_due(
            replaced_at, consumable.frequency_value, consumable.frequency_unit.value
        )
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=consumable.appliance_id))


@main_bp.route('/consumables/<int:consumable_id>/delete', methods=['POST'])
@login_required
def consumable_delete(consumable_id):
    consumable = _get_consumable_or_404(consumable_id)
    appliance_id = consumable.appliance_id
    db.session.delete(consumable)
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=appliance_id))
