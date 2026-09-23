from datetime import date

from app import service_record_service
from app.models import Appliance, ServiceRecord, Zone


class TestCreate:
    def test_creates_record_for_appliance(self, db, household, vendor):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        record = service_record_service.create(
            household_id=household.id, vendor=vendor, appliance=appliance,
            service_date=date(2026, 1, 15), notes='Tune-up', cost=150,
        )

        assert record.id is not None
        assert record.appliance_id == appliance.id
        assert record.zone_id is None
        assert record.vendor_id == vendor.id
        assert record.category.value == 'maintenance'

    def test_creates_record_for_zone(self, db, household, vendor):
        zone = Zone(household_id=household.id, name='Roof')
        db.session.add(zone)
        db.session.commit()

        record = service_record_service.create(
            household_id=household.id, vendor=vendor, zone=zone, service_date=date(2026, 1, 15),
        )

        assert record.zone_id == zone.id
        assert record.appliance_id is None

    def test_notes_blank_string_stored_as_none(self, db, household, vendor):
        record = service_record_service.create(
            household_id=household.id, vendor=vendor, service_date=date(2026, 1, 15), notes='',
        )
        assert record.notes is None

    def test_persists_via_commit(self, db, household, vendor):
        record = service_record_service.create(
            household_id=household.id, vendor=vendor, service_date=date(2026, 1, 15),
        )
        assert db.session.get(ServiceRecord, record.id) is not None
