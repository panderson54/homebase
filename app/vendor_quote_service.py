"""Create/update/link/accept/delete vendor quotes. The one rule beyond plain
CRUD: a job (the Appliance or Zone a quote is linked to) has at most one
accepted quote, so accepting one declines that job's other quotes, whichever
vendor they came from. An unlinked quote has no competitors to decline."""
from app import db, document_service
from app.models import QuoteStatus, Vendor, VendorQuote


class QuoteValidationError(ValueError):
    pass


def _clean(quote_number, description, amount, valid_until, status):
    quote_number = (quote_number or '').strip() or None
    if quote_number is None and amount is None:
        raise QuoteValidationError('Enter a quote number or an amount.')
    if amount is not None and amount < 0:
        raise QuoteValidationError('Amount cannot be negative.')
    try:
        status = QuoteStatus(status or QuoteStatus.pending.value)
    except ValueError:
        raise QuoteValidationError('Status must be pending, accepted, or declined.') from None
    return {
        'quote_number': quote_number,
        'description': (description or '').strip() or None,
        'amount': amount,
        'valid_until': valid_until,
        'status': status,
    }


def _validate_job(vendor, appliance, zone):
    if appliance is not None and zone is not None:
        raise QuoteValidationError('Link the quote to an appliance or a zone, not both.')
    job = appliance or zone
    if job is not None and job.household_id != vendor.household_id:
        raise QuoteValidationError('That item is not in this household.')


def _decline_competitors(quote):
    if quote.job is None:
        return
    for other in quote.job.quotes:
        if other is not quote:
            other.status = QuoteStatus.declined


def create(vendor, quote_number=None, description=None, amount=None, valid_until=None, status=None,
           appliance=None, zone=None):
    """Raises QuoteValidationError if the fields don't describe a usable quote."""
    fields = _clean(quote_number, description, amount, valid_until, status)
    _validate_job(vendor, appliance, zone)
    quote = VendorQuote(vendor=vendor, appliance=appliance, zone=zone, **fields)
    db.session.add(quote)
    db.session.flush()
    if quote.status == QuoteStatus.accepted:
        _decline_competitors(quote)
    db.session.commit()
    return quote


def update(quote, quote_number=None, description=None, amount=None, valid_until=None, status=None,
           appliance=None, zone=None):
    """Raises QuoteValidationError if the fields don't describe a usable quote."""
    fields = _clean(quote_number, description, amount, valid_until, status)
    _validate_job(quote.vendor, appliance, zone)
    for name, value in {**fields, 'appliance': appliance, 'zone': zone}.items():
        setattr(quote, name, value)
    if quote.status == QuoteStatus.accepted:
        _decline_competitors(quote)
    db.session.commit()
    return quote


def link(quote, appliance=None, zone=None):
    """Raises QuoteValidationError for a missing, doubled, or foreign job."""
    if appliance is None and zone is None:
        raise QuoteValidationError('Choose an item to link the quote to.')
    _validate_job(quote.vendor, appliance, zone)
    quote.appliance = appliance
    quote.zone = zone
    # An already-accepted quote arriving on a job becomes that job's one winner.
    if quote.status == QuoteStatus.accepted:
        _decline_competitors(quote)
    db.session.commit()
    return quote


def unlink(quote):
    quote.appliance = None
    quote.zone = None
    db.session.commit()
    return quote


def accept(quote):
    quote.status = QuoteStatus.accepted
    _decline_competitors(quote)
    db.session.commit()
    return quote


def delete(quote):
    # Documents are a polymorphic link, not a DB-enforced cascade.
    for document in document_service.get_documents_for('vendor_quote', quote.id):
        document_service.unlink_and_maybe_delete(document.id, 'vendor_quote', quote.id)
    db.session.delete(quote)
    db.session.commit()


def _household_quotes(household_id):
    return VendorQuote.query.join(Vendor).filter(Vendor.household_id == household_id)


def unlinked_quotes(household_id):
    return _household_quotes(household_id).filter(
        VendorQuote.appliance_id.is_(None), VendorQuote.zone_id.is_(None),
    ).order_by(Vendor.name, VendorQuote.created_at.desc()).all()


def open_quotes_by_job(household_id):
    """Pending quotes grouped by job as [{'appliance', 'zone', 'quotes'}], jobs
    sorted by name with the unlinked group (both None) last."""
    quotes = _household_quotes(household_id).filter(
        VendorQuote.status == QuoteStatus.pending,
    ).order_by(VendorQuote.created_at).all()
    groups = {}
    for quote in quotes:
        key = (quote.appliance, quote.zone)
        groups.setdefault(key, []).append(quote)
    return sorted(
        ({'appliance': appliance, 'zone': zone, 'quotes': group} for (appliance, zone), group in groups.items()),
        key=_group_sort_key,
    )


def _group_sort_key(group):
    job = group['appliance'] or group['zone']
    return (job is None, job.name.lower() if job else '')
