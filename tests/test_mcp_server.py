import pytest

from app.mcp_server import create_service, list_appliances, list_vendors, list_zones
from app.models import Appliance, Household, ServiceRecord, Vendor, Zone


@pytest.fixture
def appliance(db, household):
    a = Appliance(household_id=household.id, name='Furnace', category='furnace')
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def zone(db, household):
    z = Zone(household_id=household.id, name='Roof')
    db.session.add(z)
    db.session.commit()
    return z


class TestListing:
    def test_list_appliances(self, db, household, appliance):
        assert list_appliances() == [
            {'id': appliance.id, 'name': 'Furnace', 'category': 'Furnace', 'room': None}
        ]

    def test_list_zones(self, db, household, zone):
        assert list_zones() == [{'id': zone.id, 'name': 'Roof'}]

    def test_list_vendors(self, db, household, vendor):
        assert list_vendors() == [{'id': vendor.id, 'name': 'ACME HVAC', 'vendor_type': 'HVAC'}]

    def test_listings_are_household_scoped(self, db, household, appliance):
        other = Household(name='Other Home')
        db.session.add(other)
        db.session.commit()
        db.session.add(Appliance(household_id=other.id, name='Water Heater', category='water_heater'))
        db.session.commit()

        assert [a['name'] for a in list_appliances()] == ['Furnace']

    def test_no_household_raises(self, db):
        with pytest.raises(RuntimeError):
            list_appliances()


class TestCreateService:
    def test_creates_record_with_new_vendor_stub(self, db, household, appliance):
        result = create_service(
            service_date='2026-01-15', appliance_id=appliance.id,
            vendor_name='Acme HVAC', vendor_type='hvac', notes='Tune-up', cost=150,
        )

        assert result['vendor']['created'] is True
        vendor = db.session.get(Vendor, result['vendor']['id'])
        assert vendor.name == 'Acme HVAC'
        assert vendor.vendor_type == 'hvac'
        assert vendor.household_id == household.id

        record = db.session.get(ServiceRecord, result['service_record_id'])
        assert record.appliance_id == appliance.id
        assert record.vendor_id == vendor.id
        assert str(record.cost) == '150.00'
        assert record.category.value == 'maintenance'

    def test_reuses_existing_vendor_by_name_case_insensitive(self, db, household, appliance, vendor):
        result = create_service(service_date='2026-01-15', appliance_id=appliance.id, vendor_name='acme hvac')

        assert result['vendor']['id'] == vendor.id
        assert result['vendor']['created'] is False
        assert Vendor.query.filter_by(household_id=household.id).count() == 1

    def test_creates_record_against_zone_with_existing_vendor_id(self, db, household, zone, vendor):
        result = create_service(service_date='2026-03-01', zone_id=zone.id, vendor_id=vendor.id)

        record = db.session.get(ServiceRecord, result['service_record_id'])
        assert record.zone_id == zone.id
        assert record.appliance_id is None
        assert record.vendor_id == vendor.id

    def test_rejects_neither_appliance_nor_zone(self, db, household):
        with pytest.raises(ValueError, match='appliance_id or zone_id'):
            create_service(service_date='2026-01-01', vendor_name='Acme')

    def test_rejects_both_appliance_and_zone(self, db, household, appliance, zone):
        with pytest.raises(ValueError, match='appliance_id or zone_id'):
            create_service(
                service_date='2026-01-01', appliance_id=appliance.id, zone_id=zone.id, vendor_name='Acme',
            )

    def test_rejects_unknown_appliance(self, db, household):
        with pytest.raises(ValueError, match='No appliance'):
            create_service(service_date='2026-01-01', appliance_id=999, vendor_name='Acme')

    def test_rejects_appliance_from_other_household(self, db, household, appliance):
        other = Household(name='Other Home')
        db.session.add(other)
        db.session.commit()
        other_appliance = Appliance(household_id=other.id, name='Fridge', category='refrigerator')
        db.session.add(other_appliance)
        db.session.commit()

        with pytest.raises(ValueError, match='No appliance'):
            create_service(service_date='2026-01-01', appliance_id=other_appliance.id, vendor_name='Acme')

    def test_rejects_neither_vendor_id_nor_name(self, db, household, appliance):
        with pytest.raises(ValueError, match='vendor_id or vendor_name'):
            create_service(service_date='2026-01-01', appliance_id=appliance.id)

    def test_rejects_both_vendor_id_and_name(self, db, household, appliance, vendor):
        with pytest.raises(ValueError, match='vendor_id or vendor_name'):
            create_service(
                service_date='2026-01-01', appliance_id=appliance.id, vendor_id=vendor.id, vendor_name='Acme',
            )

    def test_rejects_unknown_vendor_id(self, db, household, appliance):
        with pytest.raises(ValueError, match='No vendor'):
            create_service(service_date='2026-01-01', appliance_id=appliance.id, vendor_id=999)

    def test_rejects_malformed_date(self, db, household, appliance):
        with pytest.raises(ValueError, match='YYYY-MM-DD'):
            create_service(service_date='01/01/2026', appliance_id=appliance.id, vendor_name='Acme')

    def test_rejects_invalid_category(self, db, household, appliance):
        with pytest.raises(ValueError, match='category must be'):
            create_service(
                service_date='2026-01-01', appliance_id=appliance.id, vendor_name='Acme', category='bogus',
            )
