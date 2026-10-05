import pytest

from app import feature_request_service
from app.feature_request_data import agent_instructions_text
from app.mcp_server import (
    feature_request_instructions, get_feature_request, list_feature_requests,
    submit_feature_request, update_feature_request,
)
from app.models import FeatureRequest, FeatureRequestStatus, Household

VALID = {
    'title': 'Add warranty expiry to appliances',
    'summary': 'Track when each appliance warranty ends.',
    'request_type': 'missing_field',
    'area': 'appliances',
    'trying_to_do': 'Check whether the dishwasher repair is covered.',
    'problem': 'There is nowhere to record a warranty end date.',
    'proposed_behavior': 'Appliance form has a warranty expiry date.',
    'acceptance_criteria': '- Appliance form has a warranty expiry field\nDetail page shows it\n\n',
    'priority': 'medium',
    'submitted_by': 'maintenance agent',
}


@pytest.fixture
def feature_request(db, household):
    return feature_request_service.create(household.id, VALID)


@pytest.fixture
def other_household_request(db):
    other = Household(name='Other Home')
    db.session.add(other)
    db.session.commit()
    return feature_request_service.create(other.id, {**VALID, 'title': 'Not yours'})


class TestService:
    def test_clean_reports_every_error_at_once(self):
        with pytest.raises(feature_request_service.FeatureRequestValidationError) as exc:
            feature_request_service.clean({**VALID, 'title': '', 'area': 'garage', 'summary': 'x' * 301})
        assert len(exc.value.errors) == 3

    def test_create_strips_and_nulls_blank_optionals(self, db, household):
        fr = feature_request_service.create(household.id, {**VALID, 'title': '  Padded  ', 'workaround': '   '})
        assert fr.title == 'Padded'
        assert fr.workaround is None
        assert fr.status == FeatureRequestStatus.unread

    def test_acceptance_criteria_list_strips_bullets_and_blanks(self, feature_request):
        assert feature_request.acceptance_criteria_list == [
            'Appliance form has a warranty expiry field', 'Detail page shows it',
        ]

    def test_update_does_not_change_status(self, feature_request):
        feature_request_service.review(feature_request, 'approved', 'Go ahead')
        feature_request_service.update(feature_request, {**VALID, 'title': 'Renamed'})
        assert feature_request.title == 'Renamed'
        assert feature_request.status == FeatureRequestStatus.approved

    def test_review_sets_and_resetting_clears_reviewed_at(self, feature_request):
        feature_request_service.review(feature_request, 'denied', '  Not needed  ')
        assert feature_request.review_notes == 'Not needed'
        assert feature_request.reviewed_at is not None

        feature_request_service.review(feature_request, 'unread')
        assert feature_request.reviewed_at is None
        assert feature_request.review_notes is None

    def test_review_rejects_unknown_status(self, feature_request):
        with pytest.raises(feature_request_service.FeatureRequestValidationError):
            feature_request_service.review(feature_request, 'maybe')

    def test_list_orders_unread_oldest_first_and_others_newest_first(self, db, household):
        first = feature_request_service.create(household.id, {**VALID, 'title': 'First'})
        second = feature_request_service.create(household.id, {**VALID, 'title': 'Second'})
        assert [fr.id for fr in feature_request_service.list_for_household(household.id, 'unread')] == [first.id, second.id]
        assert [fr.id for fr in feature_request_service.list_for_household(household.id)] == [second.id, first.id]

    def test_status_counts(self, db, household, feature_request, other_household_request):
        feature_request_service.create(household.id, VALID)
        feature_request_service.review(feature_request, 'approved')
        assert feature_request_service.status_counts(household.id) == {
            'unread': 1, 'approved': 1, 'denied': 0, 'implemented': 0,
        }

    def test_markdown_includes_spec_sections(self, feature_request):
        feature_request_service.review(feature_request, 'approved', 'Keep it to one date field')
        md = feature_request_service.to_markdown(feature_request)
        assert md.startswith(f'# Feature request #{feature_request.id}: Add warranty expiry to appliances')
        assert '**Status:** Approved' in md
        assert '- [ ] Detail page shows it' in md
        assert 'Keep it to one date field' in md
        assert '## Current workaround' not in md


class TestRoutes:
    def test_requires_login(self, client):
        assert client.get('/agent-request').status_code == 302

    def test_page_is_not_in_nav(self, logged_in_client):
        assert b'/agent-request' not in logged_in_client.get('/').data

    def test_list_defaults_to_unread_and_shows_instructions(self, logged_in_client, feature_request):
        feature_request_service.create(feature_request.household_id, {**VALID, 'title': 'Already approved'})
        approved = FeatureRequest.query.filter_by(title='Already approved').one()
        feature_request_service.review(approved, 'approved')

        resp = logged_in_client.get('/agent-request')
        assert resp.status_code == 200
        assert b'For AI agents' in resp.data
        assert b'noindex' in resp.data
        assert b'Add warranty expiry' in resp.data
        assert b'Already approved' not in resp.data

        assert b'Already approved' in logged_in_client.get('/agent-request?status=all').data

    def test_list_excludes_other_households(self, logged_in_client, other_household_request):
        assert b'Not yours' not in logged_in_client.get('/agent-request?status=all').data

    def test_create_success(self, logged_in_client, household):
        resp = logged_in_client.post('/agent-request/new', data=VALID)
        fr = FeatureRequest.query.filter_by(household_id=household.id).one()
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(f'/agent-request/{fr.id}')

    def test_create_invalid_rerenders_with_errors_and_input(self, logged_in_client, household):
        resp = logged_in_client.post('/agent-request/new', data={**VALID, 'priority': 'urgent', 'problem': ''})
        assert resp.status_code == 400
        assert b'Suggested priority must be one of' in resp.data
        assert b"Problem / what&#39;s missing is required" in resp.data
        assert b'Add warranty expiry to appliances' in resp.data
        assert FeatureRequest.query.count() == 0

    def test_detail(self, logged_in_client, feature_request):
        resp = logged_in_client.get(f'/agent-request/{feature_request.id}')
        assert resp.status_code == 200
        assert b'Check whether the dishwasher repair is covered.' in resp.data
        assert b'Approve' in resp.data

    def test_markdown_endpoint(self, logged_in_client, feature_request):
        resp = logged_in_client.get(f'/agent-request/{feature_request.id}.md')
        assert resp.status_code == 200
        assert resp.mimetype == 'text/markdown'
        assert b'## Acceptance criteria' in resp.data

    @pytest.mark.parametrize('suffix,method', [
        ('', 'get'), ('.md', 'get'), ('/edit', 'get'), ('/edit', 'post'), ('/review', 'post'),
    ])
    def test_other_household_404s(self, logged_in_client, other_household_request, suffix, method):
        url = f'/agent-request/{other_household_request.id}{suffix}'
        resp = getattr(logged_in_client, method)(url, data={**VALID, 'status': 'approved'})
        assert resp.status_code == 404
        assert other_household_request.status == FeatureRequestStatus.unread

    def test_edit_prefills_and_saves(self, logged_in_client, feature_request):
        assert b'Add warranty expiry to appliances' in logged_in_client.get(f'/agent-request/{feature_request.id}/edit').data
        resp = logged_in_client.post(f'/agent-request/{feature_request.id}/edit', data={**VALID, 'title': 'Renamed'})
        assert resp.status_code == 302
        assert feature_request.title == 'Renamed'

    def test_edit_invalid(self, logged_in_client, feature_request):
        resp = logged_in_client.post(f'/agent-request/{feature_request.id}/edit', data={**VALID, 'title': ''})
        assert resp.status_code == 400
        assert feature_request.title == VALID['title']

    def test_review_approve(self, logged_in_client, feature_request):
        resp = logged_in_client.post(
            f'/agent-request/{feature_request.id}/review', data={'status': 'approved', 'review_notes': 'Yes'},
        )
        assert resp.status_code == 302
        assert feature_request.status == FeatureRequestStatus.approved
        assert feature_request.review_notes == 'Yes'

    def test_review_invalid_status(self, logged_in_client, feature_request):
        resp = logged_in_client.post(f'/agent-request/{feature_request.id}/review', data={'status': 'maybe'})
        assert resp.status_code == 400
        assert feature_request.status == FeatureRequestStatus.unread


class TestMcpTools:
    def test_instructions_list_fields_and_choices(self):
        text = feature_request_instructions()
        assert text == agent_instructions_text()
        assert 'acceptance_criteria (required)' in text
        assert 'missing_field' in text

    def test_submit_list_get(self, db, household, other_household_request):
        created = submit_feature_request(**VALID, workaround='Notes field')
        assert created['status'] == 'unread'

        assert [r['id'] for r in list_feature_requests()] == [created['id']]
        assert list_feature_requests(status='approved') == []

        full = get_feature_request(created['id'])
        assert full['workaround'] == 'Notes field'
        assert full['markdown'].startswith(f"# Feature request #{created['id']}")

    def test_submit_invalid_raises_value_error(self, db, household):
        with pytest.raises(ValueError, match='Area of site'):
            submit_feature_request(**{**VALID, 'area': 'garage'})

    def test_list_rejects_unknown_status(self, db, household):
        with pytest.raises(ValueError):
            list_feature_requests(status='maybe')

    def test_get_other_household_raises(self, db, household, other_household_request):
        with pytest.raises(ValueError):
            get_feature_request(other_household_request.id)

    def test_update_changes_only_passed_fields_and_keeps_status(self, db, household, feature_request):
        feature_request_service.review(feature_request, 'denied')
        update_feature_request(feature_request.id, trying_to_do='Also: filing a claim.')
        assert feature_request.trying_to_do == 'Also: filing a claim.'
        assert feature_request.title == VALID['title']
        assert feature_request.status == FeatureRequestStatus.denied
