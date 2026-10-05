"""Create/update/accept/delete vendor quotes. The one rule beyond plain CRUD:
accepting a quote declines every other quote on the same vendor."""
from app import db, document_service
from app.models import QuoteStatus, VendorQuote


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


def _decline_others(quote):
    for other in quote.vendor.quotes:
        if other.id != quote.id:
            other.status = QuoteStatus.declined


def create(vendor, quote_number=None, description=None, amount=None, valid_until=None, status=None):
    """Raises QuoteValidationError if the fields don't describe a usable quote."""
    quote = VendorQuote(vendor=vendor, **_clean(quote_number, description, amount, valid_until, status))
    db.session.add(quote)
    db.session.flush()
    if quote.status == QuoteStatus.accepted:
        _decline_others(quote)
    db.session.commit()
    return quote


def update(quote, quote_number=None, description=None, amount=None, valid_until=None, status=None):
    """Raises QuoteValidationError if the fields don't describe a usable quote."""
    for name, value in _clean(quote_number, description, amount, valid_until, status).items():
        setattr(quote, name, value)
    if quote.status == QuoteStatus.accepted:
        _decline_others(quote)
    db.session.commit()
    return quote


def accept(quote):
    quote.status = QuoteStatus.accepted
    _decline_others(quote)
    db.session.commit()
    return quote


def delete(quote):
    # Documents are a polymorphic link, not a DB-enforced cascade.
    for document in document_service.get_documents_for('vendor_quote', quote.id):
        document_service.unlink_and_maybe_delete(document.id, 'vendor_quote', quote.id)
    db.session.delete(quote)
    db.session.commit()
