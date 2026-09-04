from datetime import date

from app import document_service
from app.models import (
    Appliance, Consumable, Document, Household, MaintenanceLog, MaintenanceTask, ServiceRecord, Zone,
)


class TestMaintenanceTasks:
    def test_create_task(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/appliances/{appliance.id}/maintenance-tasks', data={
            'title': 'Check filter',
            'frequency_value': '1',
            'frequency_unit': 'months',
        })
        assert resp.status_code == 302
        task = MaintenanceTask.query.filter_by(appliance_id=appliance.id).first()
        assert task.title == 'Check filter'
        assert task.next_due_at is None

    def test_complete_task_sets_last_completed_and_next_due(self, logged_in_client, db, household, user):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()
        task = MaintenanceTask(
            appliance_id=appliance.id, title='Check filter', frequency_value=30, frequency_unit='days'
        )
        db.session.add(task)
        db.session.commit()

        resp = logged_in_client.post(f'/maintenance-tasks/{task.id}/complete', data={
            'completed_at': '2026-01-01',
        })
        assert resp.status_code == 302
        db.session.refresh(task)
        assert task.last_completed_at == date(2026, 1, 1)
        assert task.next_due_at == date(2026, 1, 31)
        log = MaintenanceLog.query.filter_by(task_id=task.id).first()
        assert log.completed_by_user_id == user.id

    def test_delete_task(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()
        task = MaintenanceTask(
            appliance_id=appliance.id, title='Check filter', frequency_value=1, frequency_unit='months'
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

        resp = logged_in_client.post(f'/maintenance-tasks/{task_id}/delete')
        assert resp.status_code == 302
        assert db.session.get(MaintenanceTask, task_id) is None

    def test_complete_task_for_other_household_is_404(self, logged_in_client, db):
        from app.models import Household
        other = Household(name='Other')
        db.session.add(other)
        db.session.commit()
        appliance = Appliance(household_id=other.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()
        task = MaintenanceTask(
            appliance_id=appliance.id, title='Check filter', frequency_value=1, frequency_unit='months'
        )
        db.session.add(task)
        db.session.commit()

        resp = logged_in_client.post(f'/maintenance-tasks/{task.id}/complete')
        assert resp.status_code == 404


class TestZoneMaintenanceTasks:
    def test_create_task(self, logged_in_client, db, household):
        zone = Zone(household_id=household.id, name='Roof')
        db.session.add(zone)
        db.session.commit()

        resp = logged_in_client.post(f'/zones/{zone.id}/maintenance-tasks', data={
            'title': 'Clear gutters',
            'frequency_value': '6',
            'frequency_unit': 'months',
        })
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(f'/zones/{zone.id}')
        task = MaintenanceTask.query.filter_by(zone_id=zone.id).first()
        assert task.title == 'Clear gutters'
        assert task.appliance_id is None

    def test_complete_task_redirects_to_zone(self, logged_in_client, db, household):
        zone = Zone(household_id=household.id, name='Roof')
        db.session.add(zone)
        db.session.commit()
        task = MaintenanceTask(zone_id=zone.id, title='Clear gutters', frequency_value=6, frequency_unit='months')
        db.session.add(task)
        db.session.commit()

        resp = logged_in_client.post(f'/maintenance-tasks/{task.id}/complete', data={
            'completed_at': '2026-01-01',
        })
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(f'/zones/{zone.id}')
        db.session.refresh(task)
        assert task.last_completed_at == date(2026, 1, 1)

    def test_delete_task_redirects_to_zone(self, logged_in_client, db, household):
        zone = Zone(household_id=household.id, name='Roof')
        db.session.add(zone)
        db.session.commit()
        task = MaintenanceTask(zone_id=zone.id, title='Clear gutters', frequency_value=6, frequency_unit='months')
        db.session.add(task)
        db.session.commit()
        task_id = task.id

        resp = logged_in_client.post(f'/maintenance-tasks/{task_id}/delete')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(f'/zones/{zone.id}')
        assert db.session.get(MaintenanceTask, task_id) is None

    def test_create_task_for_other_household_is_404(self, logged_in_client, db):
        other = Household(name='Other')
        db.session.add(other)
        db.session.commit()
        zone = Zone(household_id=other.id, name='Roof')
        db.session.add(zone)
        db.session.commit()

        resp = logged_in_client.post(f'/zones/{zone.id}/maintenance-tasks', data={
            'title': 'Clear gutters', 'frequency_value': '6', 'frequency_unit': 'months',
        })
        assert resp.status_code == 404


class TestConsumables:
    def test_create_and_replace(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Fridge', category='refrigerator')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/appliances/{appliance.id}/consumables', data={
            'name': 'Water filter',
            'frequency_value': '6',
            'frequency_unit': 'months',
        })
        assert resp.status_code == 302
        consumable = Consumable.query.filter_by(appliance_id=appliance.id).first()
        assert consumable.name == 'Water filter'

        resp = logged_in_client.post(f'/consumables/{consumable.id}/replace', data={
            'replaced_at': '2026-01-01',
        })
        assert resp.status_code == 302
        db.session.refresh(consumable)
        assert consumable.last_replaced_at == date(2026, 1, 1)
        assert consumable.next_due_at is not None

    def test_consumable_without_frequency_has_no_next_due(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Dehumidifier', category='dehumidifier')
        db.session.add(appliance)
        db.session.commit()

        logged_in_client.post(f'/appliances/{appliance.id}/consumables', data={'name': 'Washable filter'})
        consumable = Consumable.query.filter_by(appliance_id=appliance.id).first()
        assert consumable.frequency_value is None

        logged_in_client.post(f'/consumables/{consumable.id}/replace')
        db.session.refresh(consumable)
        assert consumable.next_due_at is None

    def test_edit_updates_fields(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Fridge', category='refrigerator')
        db.session.add(appliance)
        db.session.commit()
        logged_in_client.post(f'/appliances/{appliance.id}/consumables', data={'name': 'Water filter'})
        consumable = Consumable.query.filter_by(appliance_id=appliance.id).first()

        resp = logged_in_client.post(f'/consumables/{consumable.id}/edit', data={
            'name': 'Water filter (blue)',
            'part_number': 'WF-123',
            'purchase_url': 'https://example.com/wf-123',
            'frequency_value': '6',
            'frequency_unit': 'months',
        })
        assert resp.status_code == 302
        db.session.refresh(consumable)
        assert consumable.name == 'Water filter (blue)'
        assert consumable.part_number == 'WF-123'
        assert consumable.purchase_url == 'https://example.com/wf-123'
        assert consumable.frequency_value == 6
        assert consumable.frequency_unit.value == 'months'

    def test_edit_404_for_other_household(self, logged_in_client, db):
        other = Household(name='Other')
        db.session.add(other)
        db.session.commit()
        other_appliance = Appliance(household_id=other.id, name='Fridge', category='refrigerator')
        db.session.add(other_appliance)
        db.session.commit()
        other_consumable = Consumable(appliance_id=other_appliance.id, name='Filter')
        db.session.add(other_consumable)
        db.session.commit()

        resp = logged_in_client.get(f'/consumables/{other_consumable.id}/edit')
        assert resp.status_code == 404


class TestServiceRecords:
    def test_create_service_record_with_existing_vendor(self, logged_in_client, db, household, vendor):
        appliance = Appliance(
            household_id=household.id, name='Furnace', category='furnace',
            pro_service_interval_value=1, pro_service_interval_unit='years',
        )
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/appliances/{appliance.id}/service-records', data={
            'service_date': '2026-01-15',
            'vendor_id': vendor.id,
            'cost': '189.00',
        })
        assert resp.status_code == 302
        record = ServiceRecord.query.filter_by(appliance_id=appliance.id).first()
        assert record.vendor_id == vendor.id
        assert record.household_id == household.id
        db.session.refresh(appliance)
        assert appliance.pro_service_next_due == date(2027, 1, 15)

    def test_create_service_record_quick_creates_vendor(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/appliances/{appliance.id}/service-records', data={
            'service_date': '2026-01-15',
            'vendor_id': '__new__',
            'new_vendor_name': 'ACME HVAC',
            'new_vendor_type': 'HVAC',
        })
        assert resp.status_code == 302
        record = ServiceRecord.query.filter_by(appliance_id=appliance.id).first()
        assert record.vendor.name == 'ACME HVAC'
        assert record.vendor.vendor_type == 'hvac'

    def test_create_service_record_without_vendor_fails(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/appliances/{appliance.id}/service-records', data={
            'service_date': '2026-01-15',
        })
        assert resp.status_code == 302
        assert ServiceRecord.query.filter_by(appliance_id=appliance.id).count() == 0

    def test_delete_service_record(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()
        record = ServiceRecord(household_id=household.id, appliance_id=appliance.id, service_date=date(2026, 1, 1))
        db.session.add(record)
        db.session.commit()
        record_id = record.id

        resp = logged_in_client.post(f'/service-records/{record_id}/delete')
        assert resp.status_code == 302
        assert db.session.get(ServiceRecord, record_id) is None

    def test_upload_link_document(self, logged_in_client, db, household, vendor):
        record = ServiceRecord(household_id=household.id, vendor_id=vendor.id, service_date=date(2026, 1, 1))
        db.session.add(record)
        db.session.commit()

        resp = logged_in_client.post(f'/service-records/{record.id}/documents', data={
            'doc_type': 'invoice',
            'external_url': 'https://example.com/invoice.pdf',
        })
        assert resp.status_code == 302
        docs = document_service.get_documents_for('service_record', record.id)
        assert len(docs) == 1
        assert docs[0].doc_type.value == 'invoice'

    def test_upload_requires_file_or_link(self, logged_in_client, db, household, vendor):
        record = ServiceRecord(household_id=household.id, vendor_id=vendor.id, service_date=date(2026, 1, 1))
        db.session.add(record)
        db.session.commit()

        resp = logged_in_client.post(f'/service-records/{record.id}/documents', data={'doc_type': 'invoice'})
        assert resp.status_code == 302
        assert document_service.get_documents_for('service_record', record.id) == []

    def test_delete_document(self, logged_in_client, db, household, vendor):
        record = ServiceRecord(household_id=household.id, vendor_id=vendor.id, service_date=date(2026, 1, 1))
        db.session.add(record)
        db.session.commit()
        document = document_service.save_and_link(
            household_id=household.id, entity_type='service_record', entity_id=record.id,
            doc_type='invoice', external_url='https://example.com/invoice.pdf',
        )

        resp = logged_in_client.post(f'/service-records/{record.id}/documents/{document.id}/delete')
        assert resp.status_code == 302
        assert document_service.get_documents_for('service_record', record.id) == []

    def test_deleting_record_cleans_up_documents(self, logged_in_client, db, household, vendor):
        record = ServiceRecord(household_id=household.id, vendor_id=vendor.id, service_date=date(2026, 1, 1))
        db.session.add(record)
        db.session.commit()
        document = document_service.save_and_link(
            household_id=household.id, entity_type='service_record', entity_id=record.id,
            doc_type='invoice', external_url='https://example.com/invoice.pdf',
        )
        document_id = document.id

        logged_in_client.post(f'/service-records/{record.id}/delete')
        assert db.session.get(Document, document_id) is None

    def test_document_upload_404_for_other_household(self, logged_in_client, db):
        other = Household(name='Other')
        db.session.add(other)
        db.session.commit()
        other_record = ServiceRecord(household_id=other.id, service_date=date(2026, 1, 1))
        db.session.add(other_record)
        db.session.commit()

        resp = logged_in_client.post(f'/service-records/{other_record.id}/documents', data={
            'doc_type': 'invoice', 'external_url': 'https://example.com/invoice.pdf',
        })
        assert resp.status_code == 404

    def test_document_indicator_shows_on_appliance_detail(self, logged_in_client, db, household, vendor):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()
        record = ServiceRecord(
            household_id=household.id, vendor_id=vendor.id, appliance_id=appliance.id, service_date=date(2026, 1, 1)
        )
        db.session.add(record)
        db.session.commit()
        document_service.save_and_link(
            household_id=household.id, entity_type='service_record', entity_id=record.id,
            doc_type='invoice', external_url='https://example.com/invoice.pdf',
        )

        resp = logged_in_client.get(f'/appliances/{appliance.id}')
        body = resp.data.decode()
        # The Edit button always links to the edit page (1 occurrence); the
        # document-count badge links there too, so 2 occurrences means it's shown.
        assert body.count(f'/service-records/{record.id}/edit') == 2

    def test_no_document_indicator_when_no_documents(self, logged_in_client, db, household, vendor):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()
        record = ServiceRecord(
            household_id=household.id, vendor_id=vendor.id, appliance_id=appliance.id, service_date=date(2026, 1, 1)
        )
        db.session.add(record)
        db.session.commit()

        resp = logged_in_client.get(f'/appliances/{appliance.id}')
        body = resp.data.decode()
        assert body.count(f'/service-records/{record.id}/edit') == 1

    def test_edit_attaches_appliance_added_after_the_fact(self, logged_in_client, db, household, vendor):
        record = ServiceRecord(household_id=household.id, vendor_id=vendor.id, service_date=date(2026, 1, 1))
        db.session.add(record)
        db.session.commit()
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/service-records/{record.id}/edit', data={
            'service_date': '2026-01-01',
            'vendor_id': vendor.id,
            'target': f'appliance:{appliance.id}',
            'cost': '150.00',
            'notes': 'Annual tune-up',
            'category': 'improvement',
        })
        assert resp.status_code == 302
        db.session.refresh(record)
        assert record.appliance_id == appliance.id
        assert record.notes == 'Annual tune-up'
        assert record.category.value == 'improvement'

    def test_edit_reassigns_from_appliance_to_zone(self, logged_in_client, db, household, vendor):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        zone = Zone(household_id=household.id, name='Roof')
        db.session.add_all([appliance, zone])
        db.session.commit()
        record = ServiceRecord(
            household_id=household.id, vendor_id=vendor.id, appliance_id=appliance.id,
            service_date=date(2026, 1, 1),
        )
        db.session.add(record)
        db.session.commit()

        resp = logged_in_client.post(f'/service-records/{record.id}/edit', data={
            'service_date': '2026-01-01',
            'vendor_id': vendor.id,
            'target': f'zone:{zone.id}',
        })
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(f'/zones/{zone.id}')
        db.session.refresh(record)
        assert record.appliance_id is None
        assert record.zone_id == zone.id

    def test_edit_requires_vendor(self, logged_in_client, db, household, vendor):
        record = ServiceRecord(household_id=household.id, vendor_id=vendor.id, service_date=date(2026, 1, 1))
        db.session.add(record)
        db.session.commit()

        resp = logged_in_client.post(f'/service-records/{record.id}/edit', data={
            'service_date': '2026-01-01',
        })
        assert resp.status_code == 302
        db.session.refresh(record)
        assert record.vendor_id == vendor.id  # unchanged

    def test_edit_404_for_other_household(self, logged_in_client, db):
        from app.models import Household
        other = Household(name='Other')
        db.session.add(other)
        db.session.commit()
        record = ServiceRecord(household_id=other.id, service_date=date(2026, 1, 1))
        db.session.add(record)
        db.session.commit()

        resp = logged_in_client.get(f'/service-records/{record.id}/edit')
        assert resp.status_code == 404
