from datetime import date

from flask import redirect, request, url_for
from flask_login import current_user, login_required

from app import db
from app.maintenance_calc import compute_next_due
from app.models import FrequencyUnit, MaintenanceLog, MaintenanceTask
from app.routes import main_bp
from app.routes.helpers import get_household_appliance_or_404, parse_date


def _get_task_or_404(task_id):
    task = MaintenanceTask.query.get_or_404(task_id)
    get_household_appliance_or_404(task.appliance_id)  # enforces household scoping
    return task


@main_bp.route('/appliances/<int:appliance_id>/maintenance-tasks', methods=['POST'])
@login_required
def maintenance_task_create(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)
    frequency_value = int(request.form['frequency_value'])
    frequency_unit = FrequencyUnit(request.form['frequency_unit'])
    task = MaintenanceTask(
        appliance_id=appliance.id,
        title=request.form.get('title', '').strip(),
        description=request.form.get('description', '').strip() or None,
        frequency_value=frequency_value,
        frequency_unit=frequency_unit,
    )
    db.session.add(task)
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))


@main_bp.route('/maintenance-tasks/<int:task_id>/complete', methods=['POST'])
@login_required
def maintenance_task_complete(task_id):
    task = _get_task_or_404(task_id)
    completed_at = parse_date(request.form.get('completed_at')) or date.today()

    db.session.add(MaintenanceLog(
        task_id=task.id,
        completed_at=completed_at,
        completed_by_user_id=current_user.id,
        notes=request.form.get('notes', '').strip() or None,
    ))
    task.last_completed_at = completed_at
    task.next_due_at = compute_next_due(completed_at, task.frequency_value, task.frequency_unit.value)
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=task.appliance_id))


@main_bp.route('/maintenance-tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def maintenance_task_delete(task_id):
    task = _get_task_or_404(task_id)
    appliance_id = task.appliance_id
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=appliance_id))
