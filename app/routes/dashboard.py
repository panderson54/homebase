from flask import render_template, url_for
from flask_login import current_user, login_required

from app.maintenance_calc import due_bucket
from app.models import Appliance, ApplianceStatus, Zone
from app.routes import main_bp

DEFAULT_LEAD_DAYS = 14


def _item(target_name, target_url, kind, label, next_due_at):
    return {
        'target_name': target_name,
        'target_url': target_url,
        'kind': kind,
        'label': label,
        'next_due_at': next_due_at,
        'bucket': due_bucket(next_due_at, lead_days=DEFAULT_LEAD_DAYS),
    }


def _appliance_items(appliance):
    url = url_for('main.appliance_detail', appliance_id=appliance.id)
    items = []
    for task in appliance.maintenance_tasks:
        if not task.active:
            continue
        items.append(_item(appliance.name, url, 'maintenance', task.title, task.next_due_at))
    for consumable in appliance.consumables:
        items.append(_item(appliance.name, url, 'consumable', consumable.name, consumable.next_due_at))
    pro_service_due = appliance.pro_service_next_due
    if pro_service_due is not None:
        items.append(_item(appliance.name, url, 'pro_service', 'Professional service', pro_service_due))
    return items


def _zone_items(zone):
    url = url_for('main.zone_detail', zone_id=zone.id)
    items = []
    for task in zone.maintenance_tasks:
        if not task.active:
            continue
        items.append(_item(zone.name, url, 'maintenance', task.title, task.next_due_at))
    pro_service_due = zone.pro_service_next_due
    if pro_service_due is not None:
        items.append(_item(zone.name, url, 'pro_service', 'Professional service', pro_service_due))
    return items


def _build_dashboard_items(household_id):
    appliances = Appliance.query.filter_by(
        household_id=household_id, status=ApplianceStatus.active
    ).all()
    zones = Zone.query.filter_by(household_id=household_id).all()

    items = []
    for appliance in appliances:
        items.extend(_appliance_items(appliance))
    for zone in zones:
        items.extend(_zone_items(zone))
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
