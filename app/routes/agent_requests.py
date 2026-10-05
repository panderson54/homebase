"""Unlisted (no nav link) page where AI agents file feature requests and the
homeowner reviews them."""
from flask import Response, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import feature_request_service
from app.feature_request_data import (
    AGENT_INSTRUCTIONS, AGENT_INSTRUCTIONS_INTRO, CHOICES, FIELDS, STATUS_LABELS,
)
from app.routes import main_bp
from app.routes.helpers import get_household_feature_request_or_404


def _render_form(feature_request, values, errors=None, status=200):
    return render_template(
        'agent_requests/form.html', feature_request=feature_request, values=values, errors=errors or [],
        fields=FIELDS, choices=CHOICES,
        instructions=AGENT_INSTRUCTIONS, instructions_intro=AGENT_INSTRUCTIONS_INTRO,
    ), status


@main_bp.route('/agent-request')
@login_required
def agent_request_list():
    status = request.args.get('status', 'unread')
    if status not in STATUS_LABELS:
        status = None
    return render_template(
        'agent_requests/list.html',
        feature_requests=feature_request_service.list_for_household(current_user.household_id, status),
        counts=feature_request_service.status_counts(current_user.household_id),
        status=status, status_labels=STATUS_LABELS,
        instructions=AGENT_INSTRUCTIONS, instructions_intro=AGENT_INSTRUCTIONS_INTRO,
    )


@main_bp.route('/agent-request/new', methods=['GET', 'POST'])
@login_required
def agent_request_new():
    if request.method == 'POST':
        try:
            feature_request = feature_request_service.create(current_user.household_id, request.form)
        except feature_request_service.FeatureRequestValidationError as e:
            return _render_form(None, request.form, e.errors, status=400)
        return redirect(url_for('main.agent_request_detail', feature_request_id=feature_request.id))
    return _render_form(None, {})


@main_bp.route('/agent-request/<int:feature_request_id>')
@login_required
def agent_request_detail(feature_request_id):
    feature_request = get_household_feature_request_or_404(feature_request_id)
    return render_template(
        'agent_requests/detail.html', feature_request=feature_request, status_labels=STATUS_LABELS,
        markdown=feature_request_service.to_markdown(feature_request),
    )


@main_bp.route('/agent-request/<int:feature_request_id>.md')
@login_required
def agent_request_markdown(feature_request_id):
    feature_request = get_household_feature_request_or_404(feature_request_id)
    return Response(feature_request_service.to_markdown(feature_request), mimetype='text/markdown')


@main_bp.route('/agent-request/<int:feature_request_id>/edit', methods=['GET', 'POST'])
@login_required
def agent_request_edit(feature_request_id):
    feature_request = get_household_feature_request_or_404(feature_request_id)
    if request.method == 'POST':
        try:
            feature_request_service.update(feature_request, request.form)
        except feature_request_service.FeatureRequestValidationError as e:
            return _render_form(feature_request, request.form, e.errors, status=400)
        return redirect(url_for('main.agent_request_detail', feature_request_id=feature_request.id))
    return _render_form(feature_request, feature_request_service.form_values(feature_request))


@main_bp.route('/agent-request/<int:feature_request_id>/review', methods=['POST'])
@login_required
def agent_request_review(feature_request_id):
    feature_request = get_household_feature_request_or_404(feature_request_id)
    try:
        feature_request_service.review(feature_request, request.form.get('status', ''), request.form.get('review_notes'))
    except feature_request_service.FeatureRequestValidationError:
        abort(400)
    return redirect(url_for('main.agent_request_detail', feature_request_id=feature_request.id))
