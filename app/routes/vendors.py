from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db, document_service
from app.models import Appliance, ApplianceStatus, ServiceRecord, Vendor
from app.routes import main_bp
from app.routes.helpers import get_household_vendor_or_404, parse_date, parse_decimal, slugify
from app.vendor_types_data import VENDOR_TYPE_LABELS


def _parse_vendor_type(form):
    vendor_type = form.get('vendor_type', '')
    if vendor_type == '__other__':
        vendor_type = slugify(form.get('custom_vendor_type', ''))
    return vendor_type or 'other'


@main_bp.route('/vendors')
@login_required
def vendor_list():
    vendors = Vendor.query.filter_by(household_id=current_user.household_id).order_by(Vendor.name).all()
    return render_template('vendors/list.html', vendors=vendors, vendor_type_labels=VENDOR_TYPE_LABELS)


@main_bp.route('/vendors/new', methods=['GET', 'POST'])
@login_required
def vendor_new():
    if request.method == 'POST':
        vendor = Vendor(
            household_id=current_user.household_id,
            name=request.form.get('name', '').strip(),
            vendor_type=_parse_vendor_type(request.form),
            contact_name=request.form.get('contact_name', '').strip() or None,
            phone=request.form.get('phone', '').strip() or None,
            email=request.form.get('email', '').strip() or None,
            website=request.form.get('website', '').strip() or None,
            notes=request.form.get('notes', '').strip() or None,
        )
        db.session.add(vendor)
        db.session.commit()
        return redirect(url_for('main.vendor_detail', vendor_id=vendor.id))

    return render_template('vendors/form.html', vendor=None, vendor_type_labels=VENDOR_TYPE_LABELS)


@main_bp.route('/vendors/<int:vendor_id>')
@login_required
def vendor_detail(vendor_id):
    vendor = get_household_vendor_or_404(vendor_id)
    documents = document_service.get_documents_for('vendor', vendor.id)
    appliances = Appliance.query.filter_by(
        household_id=current_user.household_id, status=ApplianceStatus.active
    ).order_by(Appliance.name).all()
    return render_template(
        'vendors/detail.html', vendor=vendor, documents=documents, appliances=appliances,
        vendor_type_labels=VENDOR_TYPE_LABELS,
    )


@main_bp.route('/vendors/<int:vendor_id>/edit', methods=['GET', 'POST'])
@login_required
def vendor_edit(vendor_id):
    vendor = get_household_vendor_or_404(vendor_id)

    if request.method == 'POST':
        vendor.name = request.form.get('name', '').strip()
        vendor.vendor_type = _parse_vendor_type(request.form)
        vendor.contact_name = request.form.get('contact_name', '').strip() or None
        vendor.phone = request.form.get('phone', '').strip() or None
        vendor.email = request.form.get('email', '').strip() or None
        vendor.website = request.form.get('website', '').strip() or None
        vendor.notes = request.form.get('notes', '').strip() or None
        db.session.commit()
        return redirect(url_for('main.vendor_detail', vendor_id=vendor.id))

    return render_template('vendors/form.html', vendor=vendor, vendor_type_labels=VENDOR_TYPE_LABELS)


@main_bp.route('/vendors/<int:vendor_id>/documents', methods=['POST'])
@login_required
def vendor_document_upload(vendor_id):
    vendor = get_household_vendor_or_404(vendor_id)
    document = document_service.save_and_link(
        household_id=vendor.household_id,
        entity_type='vendor',
        entity_id=vendor.id,
        doc_type=request.form.get('doc_type', 'other'),
        file_storage=request.files.get('file'),
        external_url=request.form.get('external_url', '').strip(),
    )
    if document is None:
        flash('Attach a file (PDF, PNG, JPG, WEBP) or provide a link.', 'danger')
    return redirect(url_for('main.vendor_detail', vendor_id=vendor.id))


@main_bp.route('/vendors/<int:vendor_id>/documents/<int:document_id>/delete', methods=['POST'])
@login_required
def vendor_document_delete(vendor_id, document_id):
    vendor = get_household_vendor_or_404(vendor_id)
    document_service.unlink_and_maybe_delete(document_id, 'vendor', vendor.id)
    return redirect(url_for('main.vendor_detail', vendor_id=vendor.id))


@main_bp.route('/vendors/<int:vendor_id>/services', methods=['POST'])
@login_required
def vendor_service_create(vendor_id):
    vendor = get_household_vendor_or_404(vendor_id)
    appliance_id = request.form.get('appliance_id', '').strip()
    appliance = None
    if appliance_id:
        appliance = Appliance.query.filter_by(
            id=appliance_id, household_id=vendor.household_id
        ).first()

    db.session.add(ServiceRecord(
        household_id=vendor.household_id,
        vendor_id=vendor.id,
        appliance_id=appliance.id if appliance else None,
        service_date=parse_date(request.form.get('service_date')),
        notes=request.form.get('notes', '').strip() or None,
        cost=parse_decimal(request.form.get('cost')),
    ))
    db.session.commit()
    return redirect(url_for('main.vendor_detail', vendor_id=vendor.id))
