from app.models import Appliance, Consumable, FrequencyUnit, MaintenanceTask
from app.template_service import apply_category_template


class TestApplyCategoryTemplate:
    def test_seeds_tasks_and_consumables_for_known_category(self, db, household, seeded_templates):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.flush()

        apply_category_template(appliance)
        db.session.commit()

        tasks = MaintenanceTask.query.filter_by(appliance_id=appliance.id).all()
        consumables = Consumable.query.filter_by(appliance_id=appliance.id).all()
        assert [t.title for t in tasks] == ['Check filter']
        assert [c.name for c in consumables] == ['Furnace filter']
        assert appliance.pro_service_interval_value == 1
        assert appliance.pro_service_interval_unit == FrequencyUnit.years

    def test_no_op_for_unknown_category(self, db, household, seeded_templates):
        appliance = Appliance(household_id=household.id, name='Mystery Box', category='mystery')
        db.session.add(appliance)
        db.session.flush()

        apply_category_template(appliance)
        db.session.commit()

        assert MaintenanceTask.query.filter_by(appliance_id=appliance.id).count() == 0
        assert appliance.pro_service_interval_value is None

    def test_explicit_pro_service_interval_not_overwritten(self, db, household, seeded_templates):
        appliance = Appliance(
            household_id=household.id, name='Furnace', category='furnace',
            pro_service_interval_value=2, pro_service_interval_unit=FrequencyUnit.years,
        )
        db.session.add(appliance)
        db.session.flush()

        apply_category_template(appliance)

        assert appliance.pro_service_interval_value == 2
