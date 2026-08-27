from app import vendor_service
from app.models import Household, Vendor


class TestResolveVendor:
    def test_picks_existing_vendor(self, db, household, vendor):
        result = vendor_service.resolve_vendor(household.id, str(vendor.id))
        assert result is vendor

    def test_quick_creates_new_vendor(self, db, household):
        result = vendor_service.resolve_vendor(
            household.id, vendor_service.NEW_VENDOR_SENTINEL,
            new_vendor_name='Joe the Handyman', new_vendor_type='handyman',
        )
        assert result is not None
        assert result.id is not None
        assert result.name == 'Joe the Handyman'
        assert result.vendor_type == 'handyman'
        assert result.household_id == household.id

    def test_quick_create_defaults_type_to_other(self, db, household):
        result = vendor_service.resolve_vendor(
            household.id, vendor_service.NEW_VENDOR_SENTINEL, new_vendor_name='Some Vendor',
        )
        assert result.vendor_type == 'other'

    def test_no_vendor_id_and_no_new_name_returns_none(self, db, household):
        assert vendor_service.resolve_vendor(household.id, '') is None

    def test_new_sentinel_with_blank_name_returns_none(self, db, household):
        assert vendor_service.resolve_vendor(
            household.id, vendor_service.NEW_VENDOR_SENTINEL, new_vendor_name=''
        ) is None

    def test_rejects_vendor_from_other_household(self, db, household):
        other_household = Household(name='Other Home')
        db.session.add(other_household)
        db.session.commit()
        other_vendor = Vendor(household_id=other_household.id, name='Other Vendor', vendor_type='other')
        db.session.add(other_vendor)
        db.session.commit()

        assert vendor_service.resolve_vendor(household.id, str(other_vendor.id)) is None

    def test_nonexistent_vendor_id_returns_none(self, db, household):
        assert vendor_service.resolve_vendor(household.id, '999999') is None

    def test_non_numeric_vendor_id_returns_none(self, db, household):
        assert vendor_service.resolve_vendor(household.id, 'not-a-number') is None
