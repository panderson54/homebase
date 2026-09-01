from app.models import Household, ServiceRecord, Vendor, Zone


class TestZoneCRUD:
    def test_create(self, logged_in_client, db, household):
        resp = logged_in_client.post('/zones/new', data={'name': 'Roof', 'notes': 'Reshingled 2019'})
        assert resp.status_code == 302
        zone = Zone.query.filter_by(household_id=household.id).first()
        assert zone.name == 'Roof'
        assert zone.notes == 'Reshingled 2019'

    def test_create_requires_name(self, logged_in_client, db, household):
        resp = logged_in_client.post('/zones/new', data={'name': ''})
        assert resp.status_code == 302
        assert Zone.query.filter_by(household_id=household.id).count() == 0

    def test_edit_updates_fields(self, logged_in_client, db, household):
        zone = Zone(household_id=household.id, name='Gutters')
        db.session.add(zone)
        db.session.commit()

        resp = logged_in_client.post(f'/zones/{zone.id}/edit', data={'name': 'Gutters & Downspouts', 'notes': 'Cleared twice a year'})
        assert resp.status_code == 302
        db.session.refresh(zone)
        assert zone.name == 'Gutters & Downspouts'
        assert zone.notes == 'Cleared twice a year'

    def test_edit_404_for_other_household(self, logged_in_client, db):
        other = Household(name='Other')
        db.session.add(other)
        db.session.commit()
        zone = Zone(household_id=other.id, name='Roof')
        db.session.add(zone)
        db.session.commit()

        resp = logged_in_client.get(f'/zones/{zone.id}/edit')
        assert resp.status_code == 404

    def test_delete(self, logged_in_client, db, household):
        zone = Zone(household_id=household.id, name='Garden')
        db.session.add(zone)
        db.session.commit()
        zone_id = zone.id

        resp = logged_in_client.post(f'/zones/{zone_id}/delete')
        assert resp.status_code == 302
        assert db.session.get(Zone, zone_id) is None


class TestZoneDetail:
    def test_detail_requires_login(self, client, db, household):
        zone = Zone(household_id=household.id, name='Roof')
        db.session.add(zone)
        db.session.commit()

        resp = client.get(f'/zones/{zone.id}')
        assert resp.status_code == 302

    def test_detail_renders(self, logged_in_client, db, household):
        zone = Zone(household_id=household.id, name='Roof', notes='Reshingled 2019')
        db.session.add(zone)
        db.session.commit()

        resp = logged_in_client.get(f'/zones/{zone.id}')
        assert resp.status_code == 200
        assert b'Roof' in resp.data
        assert b'Reshingled 2019' in resp.data

    def test_detail_404_for_other_household(self, logged_in_client, db):
        other = Household(name='Other')
        db.session.add(other)
        db.session.commit()
        zone = Zone(household_id=other.id, name='Roof')
        db.session.add(zone)
        db.session.commit()

        resp = logged_in_client.get(f'/zones/{zone.id}')
        assert resp.status_code == 404


class TestZoneServiceVisits:
    def test_log_visit_with_new_vendor(self, logged_in_client, db, household):
        zone = Zone(household_id=household.id, name='Roof')
        db.session.add(zone)
        db.session.commit()

        resp = logged_in_client.post(f'/zones/{zone.id}/service-records', data={
            'service_date': '2026-06-01',
            'new_vendor_name': 'Roofers Inc',
            'new_vendor_type': 'Roofing',
            'category': 'improvement',
            'cost': '4200.00',
        })
        assert resp.status_code == 302

        record = ServiceRecord.query.filter_by(zone_id=zone.id).first()
        assert record is not None
        assert record.household_id == household.id
        assert record.appliance_id is None
        assert record.category.value == 'improvement'
        assert record.cost == 4200
        vendor = Vendor.query.filter_by(household_id=household.id, name='Roofers Inc').first()
        assert vendor is not None
        assert record.vendor_id == vendor.id

    def test_log_visit_requires_vendor(self, logged_in_client, db, household):
        zone = Zone(household_id=household.id, name='Roof')
        db.session.add(zone)
        db.session.commit()

        resp = logged_in_client.post(f'/zones/{zone.id}/service-records', data={'service_date': '2026-06-01'})
        assert resp.status_code == 302
        assert ServiceRecord.query.filter_by(zone_id=zone.id).count() == 0
