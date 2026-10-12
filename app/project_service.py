"""Lifecycle of an accepted quote: Accepted → Deposit paid → Scheduled → In progress → Done.
Each stage is one date column on the quote; the current stage is the furthest one with a date."""
from datetime import date

from app import db
from app.models import QuoteStatus, Vendor, VendorQuote

STAGES = (
    ('accepted', 'Accepted', 'accepted_on'),
    ('deposit_paid', 'Deposit paid', 'deposit_paid_on'),
    ('scheduled', 'Scheduled', 'scheduled_on'),
    ('in_progress', 'In progress', 'started_on'),
    ('done', 'Done', 'completed_on'),
)
DATE_FIELDS = tuple(field for _, _, field in STAGES)


class ProjectError(ValueError):
    pass


def current_stage(quote):
    """The (key, label, field) of the furthest stage with a date; Accepted if none is dated."""
    reached = [stage for stage in STAGES if getattr(quote, stage[2]) is not None]
    return reached[-1] if reached else STAGES[0]


def next_stage(quote):
    """The stage after the current one, or None once the project is Done."""
    index = STAGES.index(current_stage(quote))
    return STAGES[index + 1] if index + 1 < len(STAGES) else None


def _require_accepted(quote):
    if quote.status != QuoteStatus.accepted:
        raise ProjectError('Only an accepted quote can be tracked as a project.')


def advance(quote, on=None):
    """Date the next stage (today by default). Raises ProjectError for a non-accepted or finished quote."""
    _require_accepted(quote)
    stage = next_stage(quote)
    if stage is None:
        raise ProjectError('This project is already done.')
    setattr(quote, stage[2], on or date.today())
    db.session.commit()
    return quote


def set_dates(quote, dates):
    """Replace every stage date from {field: date | None}. Raises ProjectError for a non-accepted quote."""
    _require_accepted(quote)
    for field in DATE_FIELDS:
        setattr(quote, field, dates.get(field))
    db.session.commit()
    return quote


def active_projects(household_id):
    """Accepted quotes not yet Done, oldest acceptance first (undated last)."""
    quotes = VendorQuote.query.join(Vendor).filter(
        Vendor.household_id == household_id,
        VendorQuote.status == QuoteStatus.accepted,
        VendorQuote.completed_on.is_(None),
    ).all()
    return sorted(quotes, key=lambda q: (q.accepted_on is None, q.accepted_on or date.min, q.id))
