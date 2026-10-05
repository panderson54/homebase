"""Validation, persistence, review, and Markdown/dict rendering for agent-filed
feature requests — shared by the /agent-request routes and the MCP server."""
from datetime import datetime

from app import db
from app.feature_request_data import CHOICES, FIELDS, STATUS_LABELS
from app.models import FeatureRequest, FeatureRequestStatus

FIELD_NAMES = [f[0] for f in FIELDS]


class FeatureRequestValidationError(ValueError):
    def __init__(self, errors):
        super().__init__('; '.join(errors))
        self.errors = errors


def clean(data):
    """Strip and validate submitted fields, returning {field: value-or-None}.
    Raises FeatureRequestValidationError listing every problem at once, so an agent
    can fix them all in one resubmission."""
    cleaned, errors = {}, []
    for name, label, kind, required, max_length, _help in FIELDS:
        value = (data.get(name) or '').strip() or None
        if value is None:
            if required:
                errors.append(f'{label} is required.')
        elif kind.startswith('select:') and value not in CHOICES[kind.split(':', 1)[1]]:
            errors.append(f'{label} must be one of: {", ".join(CHOICES[kind.split(":", 1)[1]])}.')
        elif max_length and len(value) > max_length:
            errors.append(f'{label} must be at most {max_length} characters.')
        cleaned[name] = value
    if errors:
        raise FeatureRequestValidationError(errors)
    return cleaned


def form_values(feature_request):
    return {name: getattr(feature_request, name) or '' for name in FIELD_NAMES}


def create(household_id, data):
    feature_request = FeatureRequest(household_id=household_id, **clean(data))
    db.session.add(feature_request)
    db.session.commit()
    return feature_request


def update(feature_request, data):
    """Replace every content field. Status/review fields are deliberately untouched —
    only review() changes those."""
    for name, value in clean(data).items():
        setattr(feature_request, name, value)
    db.session.commit()
    return feature_request


def review(feature_request, status, notes=None):
    try:
        status = FeatureRequestStatus(status)
    except ValueError:
        raise FeatureRequestValidationError([f'Status must be one of: {", ".join(STATUS_LABELS)}.'])
    feature_request.status = status
    feature_request.review_notes = (notes or '').strip() or None
    feature_request.reviewed_at = None if status == FeatureRequestStatus.unread else datetime.utcnow()
    db.session.commit()
    return feature_request


def list_for_household(household_id, status=None):
    """Unread requests oldest-first (a review queue); everything else newest-first."""
    query = FeatureRequest.query.filter_by(household_id=household_id)
    if status:
        query = query.filter_by(status=FeatureRequestStatus(status))
    if status == FeatureRequestStatus.unread.value:
        return query.order_by(FeatureRequest.created_at, FeatureRequest.id).all()
    return query.order_by(FeatureRequest.created_at.desc(), FeatureRequest.id.desc()).all()


def status_counts(household_id):
    counts = dict.fromkeys(STATUS_LABELS, 0)
    for (status,) in db.session.query(FeatureRequest.status).filter_by(household_id=household_id):
        counts[status.value] += 1
    return counts


def summary_dict(feature_request):
    return {
        'id': feature_request.id,
        'title': feature_request.title,
        'summary': feature_request.summary,
        'status': feature_request.status.value,
        'request_type': feature_request.request_type,
        'area': feature_request.area,
        'priority': feature_request.priority,
        'created_at': feature_request.created_at.isoformat(),
    }


def full_dict(feature_request):
    return {
        **form_values(feature_request),
        **summary_dict(feature_request),
        'review_notes': feature_request.review_notes,
        'reviewed_at': feature_request.reviewed_at.isoformat() if feature_request.reviewed_at else None,
        'updated_at': feature_request.updated_at.isoformat(),
    }


def to_markdown(feature_request):
    fr = feature_request
    lines = [
        f'# Feature request #{fr.id}: {fr.title}',
        '',
        f'**Status:** {fr.status_label}  ',
        f'**Type:** {fr.request_type_label}  ',
        f'**Area:** {fr.area_label}  ',
        f'**Priority (suggested):** {fr.priority_label}'
        + (f' — {fr.priority_reason}' if fr.priority_reason else '') + '  ',
        f'**Submitted by:** {fr.submitted_by} on {fr.created_at:%Y-%m-%d}',
    ]
    if fr.page_url:
        lines.append(f'  \n**Page where noticed:** {fr.page_url}')
    if fr.context_url:
        lines.append(f'  \n**Context:** {fr.context_url}')
    if fr.related_requests:
        lines.append(f'  \n**Related requests:** {fr.related_requests}')
    lines += ['', '## Summary', '', fr.summary]

    sections = [
        ('What the agent was trying to do', fr.trying_to_do),
        ("Problem / what's missing", fr.problem),
        ('Current workaround', fr.workaround),
        ('Proposed behavior', fr.proposed_behavior),
    ]
    for heading, body in sections:
        if body:
            lines += ['', f'## {heading}', '', body]
    lines += ['', '## Acceptance criteria', '']
    lines += [f'- [ ] {item}' for item in fr.acceptance_criteria_list]
    for heading, body in [
        ('Data / entities involved', fr.data_entities),
        ('Implementation notes', fr.implementation_notes),
        ('Out of scope', fr.out_of_scope),
    ]:
        if body:
            lines += ['', f'## {heading}', '', body]
    if fr.review_notes:
        lines += ['', '## Homeowner review notes', '', fr.review_notes]
    return '\n'.join(lines) + '\n'
