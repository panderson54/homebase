from datetime import date, timedelta

from app.models import Appliance, Consumable, MaintenanceTask, Zone


class TestDashboard:
    def test_buckets_categorize_items_correctly(self, logged_in_client, db, household):
        appliance = Appliance(
            household_id=household.id, name='Furnace', category='furnace',
            pro_service_interval_value=1, pro_service_interval_unit='years',
            install_date=date.today() - timedelta(days=400),
        )
        db.session.add(appliance)
        db.session.commit()

        overdue_task = MaintenanceTask(
            appliance_id=appliance.id, title='Overdue task', frequency_value=1, frequency_unit='months',
            next_due_at=date.today() - timedelta(days=5),
        )
        soon_consumable = Consumable(
            appliance_id=appliance.id, name='Filter', frequency_value=1, frequency_unit='months',
            next_due_at=date.today() + timedelta(days=3),
        )
        ok_task = MaintenanceTask(
            appliance_id=appliance.id, title='Future task', frequency_value=1, frequency_unit='years',
            next_due_at=date.today() + timedelta(days=200),
        )
        db.session.add_all([overdue_task, soon_consumable, ok_task])
        db.session.commit()

        resp = logged_in_client.get('/dashboard')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'Overdue task' in body
        assert 'Filter' in body
        assert 'Future task' in body
        # pro service is overdue since install_date + 1yr < today's install offset of 400 days
        assert 'Professional service' in body

    def test_zone_maintenance_and_pro_service_appear(self, logged_in_client, db, household):
        zone = Zone(
            household_id=household.id, name='Roof',
            pro_service_interval_value=1, pro_service_interval_unit='years',
        )
        db.session.add(zone)
        db.session.commit()

        overdue_task = MaintenanceTask(
            zone_id=zone.id, title='Clear gutters', frequency_value=6, frequency_unit='months',
            next_due_at=date.today() - timedelta(days=5),
        )
        db.session.add(overdue_task)
        db.session.commit()

        resp = logged_in_client.get('/dashboard')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'Roof' in body
        assert 'Clear gutters' in body
        assert 'Professional service' in body
        assert f'/zones/{zone.id}"' in body

    def test_empty_dashboard_renders(self, logged_in_client):
        resp = logged_in_client.get('/dashboard')
        assert resp.status_code == 200
        assert b'Nothing overdue' in resp.data

    def test_dashboard_only_shows_own_household(self, logged_in_client, db, household):
        from app.models import Household
        other = Household(name='Other')
        db.session.add(other)
        db.session.commit()
        other_appliance = Appliance(household_id=other.id, name='Other Furnace', category='furnace')
        db.session.add(other_appliance)
        db.session.commit()
        db.session.add(MaintenanceTask(
            appliance_id=other_appliance.id, title='Other task', frequency_value=1, frequency_unit='months',
        ))
        db.session.commit()

        resp = logged_in_client.get('/dashboard')
        assert b'Other Furnace' not in resp.data
