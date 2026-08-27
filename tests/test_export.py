from datetime import date

from app.context_export_service import build_context_markdown
from app.models import Appliance, ApplianceStatus, MaintenanceLog, MaintenanceTask, ServiceRecord


class TestBuildContextMarkdown:
    def test_includes_home_profile_and_appliance_history(self, app, db, household):
        household.address = '123 Main St'
        household.square_footage = 2400
        household.year_built = 1998
        db.session.commit()

        appliance = Appliance(
            household_id=household.id, name='Furnace', category='furnace', make='Lennox',
            model_number='SL280UH090V36B-04',
        )
        db.session.add(appliance)
        db.session.commit()

        task = MaintenanceTask(
            appliance_id=appliance.id, title='Check filter', frequency_value=1, frequency_unit='months',
        )
        db.session.add(task)
        db.session.commit()
        db.session.add(MaintenanceLog(task_id=task.id, completed_at=date(2026, 1, 1), notes='Replaced filter'))
        db.session.add(ServiceRecord(
            appliance_id=appliance.id, service_date=date(2026, 2, 1), vendor='ACME HVAC', cost=189,
        ))
        db.session.commit()

        markdown = build_context_markdown(household)

        assert '123 Main St' in markdown
        assert '2400' in markdown
        assert 'Furnace' in markdown
        assert 'Lennox' in markdown
        assert 'Check filter' in markdown
        assert '2026-01-01' in markdown
        assert 'Replaced filter' in markdown
        assert 'ACME HVAC' in markdown
        assert '189.00' in markdown

    def test_archived_appliances_get_their_own_section(self, app, db, household):
        active = Appliance(household_id=household.id, name='Fridge', category='refrigerator')
        archived = Appliance(
            household_id=household.id, name='Old Dryer', category='dryer', status=ApplianceStatus.archived
        )
        db.session.add_all([active, archived])
        db.session.commit()

        markdown = build_context_markdown(household)
        assert '## Appliances' in markdown
        assert '## Archived appliances' in markdown
        assert 'Old Dryer' in markdown
        archived_section = markdown.split('## Archived appliances')[1]
        assert 'Old Dryer' in archived_section

    def test_empty_household_renders_without_error(self, app, db, household):
        markdown = build_context_markdown(household)
        assert '# Homebase Context Export' in markdown
        assert '(no active appliances)' in markdown


class TestExportRoutes:
    def test_requires_login(self, client):
        resp = client.get('/export')
        assert resp.status_code == 302

    def test_export_page_renders(self, logged_in_client, db, household):
        household.address = '789 Pine St'
        db.session.commit()
        resp = logged_in_client.get('/export')
        assert resp.status_code == 200
        assert b'789 Pine St' in resp.data
        assert b'Copy to clipboard' in resp.data

    def test_download_returns_markdown_attachment(self, logged_in_client, db, household):
        resp = logged_in_client.get('/export/download')
        assert resp.status_code == 200
        assert resp.mimetype == 'text/markdown'
        assert 'attachment' in resp.headers['Content-Disposition']
        assert '.md' in resp.headers['Content-Disposition']
        assert b'# Homebase Context Export' in resp.data
