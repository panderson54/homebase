from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import document_service, vendor_quote_service
from app.routes import main_bp
from app.routes.helpers import get_household_vendor_or_404, get_vendor_quote_or_404, parse_date, parse_decimal
from app.vendor_quote_service import QuoteValidationError

_ATTACH_ERROR = 'Attach a file (PDF, PNG, JPG, WEBP) or provide a link.'


def _quote_fields(form):
    """Raises QuoteValidationError for a malformed valid-until date."""
    try:
        valid_until = parse_date(form.get('valid_until'))
    except ValueError:
        raise QuoteValidationError('Enter the valid-until date as YYYY-MM-DD.') from None
    return {
        'quote_number': form.get('quote_number'),
        'description': form.get('description'),
        'amount': parse_decimal(form.get('amount')),
        'valid_until': valid_until,
        'status': form.get('status'),
    }


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
    return render_template('vendors/quote_edit.html', vendor=vendor, quote=quote, documents=documents)


@main_bp.route('/vendors/<int:vendor_id>/quotes/<int:quote_id>/accept', methods=['POST'])
@login_required
def vendor_quote_accept(vendor_id, quote_id):
    vendor = get_household_vendor_or_404(vendor_id)
    vendor_quote_service.accept(get_vendor_quote_or_404(vendor, quote_id))
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
