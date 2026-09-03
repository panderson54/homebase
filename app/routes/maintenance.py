from datetime import date

from flask import redirect, request, url_for
from flask_login import current_user, login_required

from app import db
from app.maintenance_calc import compute_next_due
from app.models import FrequencyUnit, MaintenanceLog, MaintenanceTask
from app.routes import main_bp
from app.routes.helpers import get_household_appliance_or_404, get_household_zone_or_404, parse_date


def _get_task_or_404(task_id):
    task = MaintenanceTask.query.get_or_404(task_id)
    if task.appliance_id is not None:
        get_household_appliance_or_404(task.appliance_id)  # enforces household scoping
    else:
        get_household_zone_or_404(task.zone_id)  # enforces household scoping
    return task


def _task_parent_redirect(task):
    if task.appliance_id is not None:
        return redirect(url_for('main.appliance_detail', appliance_id=task.appliance_id))
    return redirect(url_for('main.zone_detail', zone_id=task.zone_id))


def _new_task(**owner_kwargs):
    return MaintenanceTask(
        title=request.form.get('title', '').strip(),
        description=request.form.get('description', '').strip() or None,
        frequency_value=int(request.form['frequency_value']),
        frequency_unit=FrequencyUnit(request.form['frequency_unit']),
        **owner_kwargs,
    )


@main_bp.route('/appliances/<int:appliance_id>/maintenance-tasks', methods=['POST'])
@login_required
def maintenance_task_create(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)
    db.session.add(_new_task(appliance_id=appliance.id))
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))


@main_bp.route('/zones/<int:zone_id>/maintenance-tasks', methods=['POST'])
@login_required
def zone_maintenance_task_create(zone_id):
    zone = get_household_zone_or_404(zone_id)
    db.session.add(_new_task(zone_id=zone.id))
    db.session.commit()
    return redirect(url_for('main.zone_detail', zone_id=zone.id))


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
    return _task_parent_redirect(task)


@main_bp.route('/maintenance-tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def maintenance_task_delete(task_id):
    task = _get_task_or_404(task_id)
    redirect_response = _task_parent_redirect(task)
    db.session.delete(task)
    db.session.commit()
    return redirect_response
