from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import document_service, vendor_quote_service
from app.models import Appliance, ApplianceStatus, QuoteStatus, Zone
from app.routes import main_bp
from app.routes.helpers import (
    get_household_appliance_or_404, get_household_quote_or_404, get_household_vendor_or_404,
    get_household_zone_or_404, get_vendor_quote_or_404, parse_date, parse_decimal, parse_service_target,
)
from app.vendor_quote_service import QuoteValidationError

_ATTACH_ERROR = 'Attach a file (PDF, PNG, JPG, WEBP) or provide a link.'


def _quote_fields(form):
    """Raises QuoteValidationError for a malformed valid-until date."""
    try:
        valid_until = parse_date(form.get('valid_until'))
    except ValueError:
        raise QuoteValidationError('Enter the valid-until date as YYYY-MM-DD.') from None
    appliance, zone = parse_service_target(form.get('target'), current_user.household_id)
    return {
        'quote_number': form.get('quote_number'),
        'description': form.get('description'),
        'amount': parse_decimal(form.get('amount')),
        'valid_until': valid_until,
        'status': form.get('status'),
        'appliance': appliance,
        'zone': zone,
    }


def _job_url(appliance=None, zone=None):
    if appliance is not None:
        return url_for('main.appliance_detail', appliance_id=appliance.id)
    return url_for('main.zone_detail', zone_id=zone.id)


def _compare_url(appliance=None, zone=None):
    target = f'appliance:{appliance.id}' if appliance is not None else f'zone:{zone.id}'
    return url_for('main.quote_compare', target=target)


def _job_choices(household_id):
    appliances = Appliance.query.filter_by(
        household_id=household_id, status=ApplianceStatus.active
    ).order_by(Appliance.name).all()
    zones = Zone.query.filter_by(household_id=household_id).order_by(Zone.name).all()
    return appliances, zones


def _attach(quote, form, files):
    """Returns None if nothing was submitted, else whether the attachment was accepted."""
    file_storage = files.get('file')
    external_url = form.get('external_url', '').strip()
    if not (file_storage and file_storage.filename) and not external_url:
        return None
    document = document_service.save_and_link(
        household_id=quote.vendor.household_id, entity_type='vendor_quote', entity_id=quote.id,
        doc_type='quote', file_storage=file_storage, external_url=external_url,
    )
    return document is not None


@main_bp.route('/vendors/<int:vendor_id>/quotes', methods=['POST'])
@login_required
def vendor_quote_create(vendor_id):
    vendor = get_household_vendor_or_404(vendor_id)
    try:
        quote = vendor_quote_service.create(vendor, **_quote_fields(request.form))
    except QuoteValidationError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('main.vendor_detail', vendor_id=vendor.id))
    if _attach(quote, request.form, request.files) is False:
        flash(f'Quote saved, but the attachment was rejected. {_ATTACH_ERROR}', 'danger')
    return redirect(url_for('main.vendor_detail', vendor_id=vendor.id))


@main_bp.route('/vendors/<int:vendor_id>/quotes/<int:quote_id>/edit', methods=['GET', 'POST'])
@login_required
def vendor_quote_edit(vendor_id, quote_id):
    vendor = get_household_vendor_or_404(vendor_id)
    quote = get_vendor_quote_or_404(vendor, quote_id)

    if request.method == 'POST':
        try:
            vendor_quote_service.update(quote, **_quote_fields(request.form))
        except QuoteValidationError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('main.vendor_quote_edit', vendor_id=vendor.id, quote_id=quote.id))
        return redirect(url_for('main.vendor_detail', vendor_id=vendor.id))

    documents = document_service.get_documents_for('vendor_quote', quote.id)
    appliances, zones = _job_choices(vendor.household_id)
    if quote.appliance is not None and quote.appliance not in appliances:
        appliances.append(quote.appliance)  # a retired appliance must stay selectable or saving would unlink it
    return render_template(
        'vendors/quote_edit.html', vendor=vendor, quote=quote, documents=documents,
        appliances=appliances, zones=zones,
    )


@main_bp.route('/vendors/<int:vendor_id>/quotes/<int:quote_id>/accept', methods=['POST'])
@login_required
def vendor_quote_accept(vendor_id, quote_id):
    vendor = get_household_vendor_or_404(vendor_id)
    quote = vendor_quote_service.accept(get_vendor_quote_or_404(vendor, quote_id))
    if request.form.get('return_to') == 'compare' and quote.job is not None:
        return redirect(_compare_url(quote.appliance, quote.zone))
    return redirect(url_for('main.vendor_detail', vendor_id=vendor.id))


@main_bp.route('/vendors/<int:vendor_id>/quotes/<int:quote_id>/delete', methods=['POST'])
@login_required
def vendor_quote_delete(vendor_id, quote_id):
    vendor = get_household_vendor_or_404(vendor_id)
    vendor_quote_service.delete(get_vendor_quote_or_404(vendor, quote_id))
    return redirect(url_for('main.vendor_detail', vendor_id=vendor.id))


@main_bp.route('/vendors/<int:vendor_id>/quotes/<int:quote_id>/documents', methods=['POST'])
@login_required
def vendor_quote_document_upload(vendor_id, quote_id):
    vendor = get_household_vendor_or_404(vendor_id)
    quote = get_vendor_quote_or_404(vendor, quote_id)
    if not _attach(quote, request.form, request.files):
        flash(_ATTACH_ERROR, 'danger')
    return redirect(url_for('main.vendor_quote_edit', vendor_id=vendor.id, quote_id=quote.id))


@main_bp.route('/vendors/<int:vendor_id>/quotes/<int:quote_id>/documents/<int:document_id>/delete', methods=['POST'])
@login_required
def vendor_quote_document_delete(vendor_id, quote_id, document_id):
    vendor = get_household_vendor_or_404(vendor_id)
    quote = get_vendor_quote_or_404(vendor, quote_id)
    document_service.unlink_and_maybe_delete(document_id, 'vendor_quote', quote.id)
    return redirect(url_for('main.vendor_quote_edit', vendor_id=vendor.id, quote_id=quote.id))


@main_bp.route('/quotes/compare')
@login_required
def quote_compare():
    appliance, zone = parse_service_target(request.args.get('target'), current_user.household_id)
    job = appliance or zone
    if job is None:
        abort(404)
    open_quotes = [q for q in job.quotes if q.status == QuoteStatus.pending]
    decided_quotes = [q for q in job.quotes if q.status != QuoteStatus.pending]
    quote_documents = {q.id: document_service.get_documents_for('vendor_quote', q.id) for q in job.quotes}
    return render_template(
        'quotes/compare.html', job=job, job_url=_job_url(appliance, zone),
        open_quotes=open_quotes, decided_quotes=decided_quotes, quote_documents=quote_documents,
    )


def _create_for_job(appliance=None, zone=None):
    vendor_id = request.form.get('vendor_id', type=int)
    if vendor_id is None:
        flash('Choose the vendor that gave this quote.', 'danger')
        return redirect(_job_url(appliance, zone))
    vendor = get_household_vendor_or_404(vendor_id)
    try:
        fields = {**_quote_fields(request.form), 'appliance': appliance, 'zone': zone}
        quote = vendor_quote_service.create(vendor, **fields)
    except QuoteValidationError as exc:
        flash(str(exc), 'danger')
        return redirect(_job_url(appliance, zone))
    if _attach(quote, request.form, request.files) is False:
        flash(f'Quote saved, but the attachment was rejected. {_ATTACH_ERROR}', 'danger')
    return redirect(_job_url(appliance, zone))


@main_bp.route('/appliances/<int:appliance_id>/quotes', methods=['POST'])
@login_required
def appliance_quote_create(appliance_id):
    return _create_for_job(appliance=get_household_appliance_or_404(appliance_id))


@main_bp.route('/zones/<int:zone_id>/quotes', methods=['POST'])
@login_required
def zone_quote_create(zone_id):
    return _create_for_job(zone=get_household_zone_or_404(zone_id))


def _link_to_job(appliance=None, zone=None):
    quote_id = request.form.get('quote_id', type=int)
    if quote_id is None:
        flash('Choose a quote to link.', 'danger')
        return redirect(_job_url(appliance, zone))
    vendor_quote_service.link(get_household_quote_or_404(quote_id), appliance=appliance, zone=zone)
    return redirect(_job_url(appliance, zone))


@main_bp.route('/appliances/<int:appliance_id>/quotes/link', methods=['POST'])
@login_required
def appliance_quote_link(appliance_id):
    return _link_to_job(appliance=get_household_appliance_or_404(appliance_id))


@main_bp.route('/zones/<int:zone_id>/quotes/link', methods=['POST'])
@login_required
def zone_quote_link(zone_id):
    return _link_to_job(zone=get_household_zone_or_404(zone_id))


@main_bp.route('/quotes/<int:quote_id>/unlink', methods=['POST'])
@login_required
def quote_unlink(quote_id):
    quote = get_household_quote_or_404(quote_id)
    if quote.job is None:
        return redirect(url_for('main.vendor_detail', vendor_id=quote.vendor_id))
    redirect_url = _job_url(quote.appliance, quote.zone)
    vendor_quote_service.unlink(quote)
    return redirect(redirect_url)
