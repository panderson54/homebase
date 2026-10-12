"""Google sign-in authorization: allowlist matching and just-in-time user provisioning.

The allowlist lives only in server config (`HOMEBASE_ALLOWED_EMAILS`); there is
deliberately no database table or UI for it.
"""
from app import db
from app.models import Household, User

_GMAIL_DOMAINS = frozenset({'gmail.com', 'googlemail.com'})


def normalize_email(email):
    """Lowercase an address; for Gmail also drop the dots Google ignores and fold googlemail.com in."""
    email = (email or '').strip().lower()
    local, sep, domain = email.rpartition('@')
    if not sep or domain not in _GMAIL_DOMAINS:
        return email
    return f"{local.replace('.', '')}@gmail.com"


def parse_allowed_emails(raw):
    """Parse a comma-separated allowlist into a frozenset of normalized addresses."""
    return frozenset(normalize_email(entry) for entry in (raw or '').split(',') if entry.strip())


def is_email_allowed(email, allowed_emails):
    normalized = normalize_email(email)
    return bool(normalized) and normalized in allowed_emails


def is_authorized(claims, allowed_emails):
    """True only for a Google-verified email that is on the allowlist."""
    # `is True`, not truthiness: an absent or string-valued claim must not pass.
    return claims.get('email_verified') is True and is_email_allowed(claims.get('email'), allowed_emails)


def get_or_create_user(claims):
    """Find the User for these ID-token claims, creating it (and the household) on first sign-in."""
    email = claims['email'].strip().lower()
    user = (
        User.query.filter_by(google_sub=claims['sub']).first()
        # Accounts that predate Google sign-in are linked by email exactly once.
        or User.query.filter_by(email=email, google_sub=None).first()
    )
    if user is None:
        user = User(household_id=_single_household().id)
        db.session.add(user)
    user.google_sub = claims['sub']
    user.email = email
    user.name = claims.get('name') or email
    db.session.commit()
    return user


def _single_household():
    # Homebase is single-household (see README): every allowed user shares it.
    household = Household.query.first()
    if household is None:
        household = Household(name='Home')
        db.session.add(household)
        db.session.flush()
    return household
