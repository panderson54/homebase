from datetime import date

from app.models import Appliance, Consumable, MaintenanceLog, MaintenanceTask, ServiceRecord


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
