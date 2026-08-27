from flask import redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db, document_service
from app.category_templates_data import CATEGORY_LABELS
from app.models import Appliance, ApplianceStatus, FrequencyUnit, Vendor
from app.routes import main_bp
from app.routes.helpers import get_household_appliance_or_404, parse_date, slugify
from app.template_service import apply_category_template


def _parse_pro_service_interval(form):
    value = form.get('pro_service_interval_value', '').strip()
    unit = form.get('pro_service_interval_unit', '').strip()
    if not value or not unit:
        return None, None
    return int(value), FrequencyUnit(unit)


@main_bp.route('/appliances')
@login_required
def appliance_list():
    show_archived = request.args.get('archived') == '1'
    status = ApplianceStatus.archived if show_archived else ApplianceStatus.active
    appliances = Appliance.query.filter_by(
        household_id=current_user.household_id, status=status
    ).order_by(Appliance.name).all()
    return render_template(
        'appliances/list.html', appliances=appliances, show_archived=show_archived,
        category_labels=CATEGORY_LABELS,
    )


@main_bp.route('/appliances/new', methods=['GET', 'POST'])
@login_required
def appliance_new():
    if request.method == 'POST':
        category = request.form.get('category', '')
        if category == '__other__':
            category = slugify(request.form.get('custom_category', ''))

        appliance = Appliance(
            household_id=current_user.household_id,
            category=category,
            name=request.form.get('name', '').strip(),
            make=request.form.get('make', '').strip() or None,
            model_number=request.form.get('model_number', '').strip() or None,
            serial_number=request.form.get('serial_number', '').strip() or None,
            location=request.form.get('location', '').strip() or None,
            install_date=parse_date(request.form.get('install_date')),
            purchase_date=parse_date(request.form.get('purchase_date')),
            notes=request.form.get('notes', '').strip() or None,
        )
        appliance.pro_service_interval_value, appliance.pro_service_interval_unit = (
            _parse_pro_service_interval(request.form)
        )
        db.session.add(appliance)
        db.session.flush()  # assign appliance.id before seeding related rows

        if request.form.get('apply_template') == 'on':
            apply_category_template(appliance)

        db.session.commit()
        return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))

    return render_template('appliances/form.html', appliance=None, category_labels=CATEGORY_LABELS)


@main_bp.route('/appliances/<int:appliance_id>')
@login_required
def appliance_detail(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)
    documents = document_service.get_documents_for('appliance', appliance.id)
    vendors = Vendor.query.filter_by(household_id=current_user.household_id).order_by(Vendor.name).all()
    return render_template(
        'appliances/detail.html', appliance=appliance, documents=documents, vendors=vendors,
        category_labels=CATEGORY_LABELS,
    )


@main_bp.route('/appliances/<int:appliance_id>/edit', methods=['GET', 'POST'])
@login_required
def appliance_edit(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)

    if request.method == 'POST':
        category = request.form.get('category', '')
        if category == '__other__':
            category = slugify(request.form.get('custom_category', ''))

        appliance.category = category
        appliance.name = request.form.get('name', '').strip()
        appliance.make = request.form.get('make', '').strip() or None
        appliance.model_number = request.form.get('model_number', '').strip() or None
        appliance.serial_number = request.form.get('serial_number', '').strip() or None
        appliance.location = request.form.get('location', '').strip() or None
        appliance.install_date = parse_date(request.form.get('install_date'))
        appliance.purchase_date = parse_date(request.form.get('purchase_date'))
        appliance.notes = request.form.get('notes', '').strip() or None
        appliance.pro_service_interval_value, appliance.pro_service_interval_unit = (
            _parse_pro_service_interval(request.form)
        )
        db.session.commit()
        return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))

    return render_template('appliances/form.html', appliance=appliance, category_labels=CATEGORY_LABELS)


@main_bp.route('/appliances/<int:appliance_id>/archive', methods=['POST'])
@login_required
def appliance_archive(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)
    appliance.status = ApplianceStatus.archived
    db.session.commit()
    return redirect(url_for('main.appliance_list'))


@main_bp.route('/appliances/<int:appliance_id>/unarchive', methods=['POST'])
@login_required
def appliance_unarchive(appliance_id):
    appliance = get_household_appliance_or_404(appliance_id)
    appliance.status = ApplianceStatus.active
    db.session.commit()
    return redirect(url_for('main.appliance_detail', appliance_id=appliance.id))
