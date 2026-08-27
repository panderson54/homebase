from flask import render_template
from flask_login import current_user, login_required

from app.maintenance_calc import due_bucket
from app.models import Appliance, ApplianceStatus
from app.routes import main_bp

DEFAULT_LEAD_DAYS = 14


def _build_dashboard_items(household_id):
    appliances = Appliance.query.filter_by(
        household_id=household_id, status=ApplianceStatus.active
    ).all()

    items = []
    for appliance in appliances:
        for task in appliance.maintenance_tasks:
            if not task.active:
                continue
            items.append({
                'appliance': appliance,
                'kind': 'maintenance',
                'label': task.title,
                'next_due_at': task.next_due_at,
                'bucket': due_bucket(task.next_due_at, lead_days=DEFAULT_LEAD_DAYS),
            })
        for consumable in appliance.consumables:
            items.append({
                'appliance': appliance,
                'kind': 'consumable',
                'label': consumable.name,
                'next_due_at': consumable.next_due_at,
                'bucket': due_bucket(consumable.next_due_at, lead_days=DEFAULT_LEAD_DAYS),
            })
        pro_service_due = appliance.pro_service_next_due
        if pro_service_due is not None:
            items.append({
                'appliance': appliance,
                'kind': 'pro_service',
                'label': 'Professional service',
                'next_due_at': pro_service_due,
                'bucket': due_bucket(pro_service_due, lead_days=DEFAULT_LEAD_DAYS),
            })

    return items


@main_bp.route('/')
@main_bp.route('/dashboard')
@login_required
def dashboard():
    items = _build_dashboard_items(current_user.household_id)
    buckets = {
        'overdue': [i for i in items if i['bucket'] == 'overdue'],
        'due_soon': [i for i in items if i['bucket'] == 'due_soon'],
        'ok': [i for i in items if i['bucket'] == 'ok'],
    }
    for bucket_items in buckets.values():
        bucket_items.sort(key=lambda i: (i['next_due_at'] is None, i['next_due_at']))

    return render_template('dashboard/dashboard.html', buckets=buckets)
