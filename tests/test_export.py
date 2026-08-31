from datetime import date

from app.context_export_service import build_context_markdown
from app.models import (
    Appliance, ApplianceStatus, Document, DocumentLink, MaintenanceLog, MaintenanceTask, PaintColor, Room,
    ServiceRecord, Vendor,
)


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
        vendor = Vendor(household_id=household.id, name='ACME HVAC', vendor_type='hvac')
        db.session.add(vendor)
        db.session.commit()

        task = MaintenanceTask(
            appliance_id=appliance.id, title='Check filter', frequency_value=1, frequency_unit='months',
        )
        db.session.add(task)
        db.session.commit()
        db.session.add(MaintenanceLog(task_id=task.id, completed_at=date(2026, 1, 1), notes='Replaced filter'))
        db.session.add(ServiceRecord(
            household_id=household.id, vendor_id=vendor.id, appliance_id=appliance.id,
            service_date=date(2026, 2, 1), cost=189,
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
        assert '## Vendors' in markdown

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

    def test_vendors_section_includes_visits_with_and_without_appliance(self, app, db, household):
        appliance = Appliance(household_id=household.id, name='Roof', category='roofing')
        db.session.add(appliance)
        vendor = Vendor(
            household_id=household.id, name='Roofers Inc', vendor_type='roofing', phone='555-0100',
        )
        db.session.add(vendor)
        db.session.commit()

        db.session.add(ServiceRecord(
            household_id=household.id, vendor_id=vendor.id, appliance_id=appliance.id,
            service_date=date(2026, 4, 1), notes='Replaced shingles',
        ))
        db.session.add(ServiceRecord(
            household_id=household.id, vendor_id=vendor.id, appliance_id=None,
            service_date=date(2026, 5, 1), notes='Whole-house gutter cleaning',
        ))
        db.session.commit()

        markdown = build_context_markdown(household)
        vendors_section = markdown.split('## Vendors')[1]

        assert 'Roofers Inc' in vendors_section
        assert '555-0100' in vendors_section
        assert 'Replaced shingles' in vendors_section
        assert 'Roof' in vendors_section  # linked appliance named for the first visit
        assert 'Whole-house gutter cleaning' in vendors_section

    def test_paint_colors_section(self, app, db, household):
        db.session.add(PaintColor(
            household_id=household.id, location='Living room walls', manufacturer='Sherwin-Williams',
            color_name='Agreeable Gray', color_code='SW 7029', hex_color='#D1CBC1',
            product_url='https://example.com/agreeable-gray',
        ))
        db.session.commit()

        markdown = build_context_markdown(household)
        assert '## Paint Colors' in markdown
        paint_section = markdown.split('## Paint Colors')[1]
        assert 'Living room walls' in paint_section
        assert 'Agreeable Gray' in paint_section
        assert 'SW 7029' in paint_section
        assert '#D1CBC1' in paint_section
        assert 'https://example.com/agreeable-gray' in paint_section

    def test_no_paint_colors_section_when_none_exist(self, app, db, household):
        markdown = build_context_markdown(household)
        assert '## Paint Colors' not in markdown

    def test_rooms_section_lists_room_and_its_contents(self, app, db, household):
        room = Room(household_id=household.id, name='Kitchen', floor='1st floor')
        db.session.add(room)
        db.session.commit()

        appliance = Appliance(
            household_id=household.id, name='Fridge', category='refrigerator', room_id=room.id,
        )
        db.session.add(appliance)
        db.session.add(PaintColor(
            household_id=household.id, location='Kitchen walls', color_name='Alabaster', room_id=room.id,
        ))
        db.session.commit()

        markdown = build_context_markdown(household)
        assert '## Rooms' in markdown

        rooms_section = markdown.split('## Rooms')[1].split('##')[0]
        assert 'Kitchen' in rooms_section
        assert '1st floor' in rooms_section
        assert 'Fridge' in rooms_section
        assert 'Alabaster' in rooms_section

        assert 'Room: Kitchen' in markdown.split('## Appliances')[1]
        assert 'Room: Kitchen' in markdown.split('## Paint Colors')[1]

    def test_no_rooms_section_when_none_exist(self, app, db, household):
        markdown = build_context_markdown(household)
        assert '## Rooms' not in markdown

    def test_uploaded_file_documents_are_omitted(self, app, db, household):
        upload = Document(
            household_id=household.id, doc_type='manual', file_path='uploads/123545.jpg',
            original_filename='123545.jpg',
        )
        db.session.add(upload)
        db.session.commit()
        db.session.add(DocumentLink(document_id=upload.id, entity_type='home', entity_id=household.id))
        db.session.commit()

        markdown = build_context_markdown(household)
        assert '123545.jpg' not in markdown

    def test_linked_documents_are_included(self, app, db, household):
        link_doc = Document(
            household_id=household.id, doc_type='manual', external_url='https://example.com/manual.pdf',
        )
        db.session.add(link_doc)
        db.session.commit()
        db.session.add(DocumentLink(document_id=link_doc.id, entity_type='home', entity_id=household.id))
        db.session.commit()

        markdown = build_context_markdown(household)
        assert 'https://example.com/manual.pdf' in markdown


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
