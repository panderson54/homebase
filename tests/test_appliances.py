import io

from PIL import Image

from app.models import Appliance, ApplianceStatus, FrequencyUnit, Household, TemplateKind, CategoryTemplate


def _make_png_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (4, 4), color='blue').save(buf, format='PNG')
    buf.seek(0)
    return buf


class TestApplianceCreate:
    def test_create_without_template(self, logged_in_client, user):
        resp = logged_in_client.post('/appliances/new', data={
            'name': 'Dishwasher',
            'category': 'dishwasher',
            'make': 'KitchenAid',
            'model_number': 'KDTM404KPS2',
        })
        assert resp.status_code == 302
        appliance = Appliance.query.filter_by(household_id=user.household_id).first()
        assert appliance is not None
        assert appliance.name == 'Dishwasher'
        assert appliance.maintenance_tasks == []

    def test_create_with_custom_category(self, logged_in_client, user):
        resp = logged_in_client.post('/appliances/new', data={
            'name': 'Garage Door Opener',
            'category': '__other__',
            'custom_category': 'Garage Door Opener',
        })
        assert resp.status_code == 302
        appliance = Appliance.query.filter_by(household_id=user.household_id).first()
        assert appliance.category == 'garage_door_opener'

    def test_create_applies_template(self, logged_in_client, user, db, seeded_templates):
        resp = logged_in_client.post('/appliances/new', data={
            'name': 'Furnace',
            'category': 'furnace',
            'apply_template': 'on',
        })
        assert resp.status_code == 302
        appliance = Appliance.query.filter_by(household_id=user.household_id).first()
        assert len(appliance.maintenance_tasks) == 1
        assert appliance.maintenance_tasks[0].title == 'Check filter'
        assert len(appliance.consumables) == 1

    def test_create_with_documents(self, logged_in_client, user):
        from app import document_service
        resp = logged_in_client.post('/appliances/new', data={
            'name': 'Water Heater',
            'category': 'water_heater',
            'documents': [
                (_make_png_bytes(), 'nameplate.png'),
                (io.BytesIO(b'%PDF-1.4 fake manual'), 'manual.pdf'),
            ],
        }, content_type='multipart/form-data')
        assert resp.status_code == 302
        appliance = Appliance.query.filter_by(household_id=user.household_id).first()
        docs = document_service.get_documents_for('appliance', appliance.id)
        assert len(docs) == 2
        doc_types = {doc.doc_type.value for doc in docs}
        assert doc_types == {'photo', 'manual'}

    def test_create_without_documents_is_unaffected(self, logged_in_client, user):
        from app import document_service
        resp = logged_in_client.post('/appliances/new', data={
            'name': 'Dryer', 'category': 'dryer',
        })
        assert resp.status_code == 302
        appliance = Appliance.query.filter_by(household_id=user.household_id).first()
        assert document_service.get_documents_for('appliance', appliance.id) == []

    def test_create_with_pro_service_interval(self, logged_in_client, user):
        logged_in_client.post('/appliances/new', data={
            'name': 'Water Heater',
            'category': 'water_heater',
            'pro_service_interval_value': '1',
            'pro_service_interval_unit': 'years',
        })
        appliance = Appliance.query.filter_by(household_id=user.household_id).first()
        assert appliance.pro_service_interval_value == 1
        assert appliance.pro_service_interval_unit == FrequencyUnit.years


class TestApplianceScoping:
    def test_detail_404_for_other_household(self, logged_in_client, db, household):
        other_household = Household(name='Other Home')
        db.session.add(other_household)
        db.session.commit()
        other_appliance = Appliance(household_id=other_household.id, name='Other Fridge', category='refrigerator')
        db.session.add(other_appliance)
        db.session.commit()

        resp = logged_in_client.get(f'/appliances/{other_appliance.id}')
        assert resp.status_code == 404

    def test_detail_404_for_nonexistent(self, logged_in_client):
        resp = logged_in_client.get('/appliances/999999')
        assert resp.status_code == 404

    def test_detail_requires_login(self, client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()
        resp = client.get(f'/appliances/{appliance.id}')
        assert resp.status_code == 302


class TestApplianceListAndArchive:
    def test_list_shows_active_only_by_default(self, logged_in_client, db, household):
        active = Appliance(household_id=household.id, name='Furnace', category='furnace')
        archived = Appliance(
            household_id=household.id, name='Old Dryer', category='dryer', status=ApplianceStatus.archived
        )
        db.session.add_all([active, archived])
        db.session.commit()

        resp = logged_in_client.get('/appliances')
        assert b'Furnace' in resp.data
        assert b'Old Dryer' not in resp.data

    def test_archive_then_unarchive(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/appliances/{appliance.id}/archive')
        assert resp.status_code == 302
        db.session.refresh(appliance)
        assert appliance.status == ApplianceStatus.archived

        resp = logged_in_client.post(f'/appliances/{appliance.id}/unarchive')
        assert resp.status_code == 302
        db.session.refresh(appliance)
        assert appliance.status == ApplianceStatus.active


class TestApplianceEdit:
    def test_edit_updates_fields(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/appliances/{appliance.id}/edit', data={
            'name': 'Basement Furnace',
            'category': 'furnace',
            'location': 'Basement',
        })
        assert resp.status_code == 302
        db.session.refresh(appliance)
        assert appliance.name == 'Basement Furnace'
        assert appliance.location == 'Basement'


class TestApplianceProfilePhoto:
    def test_upload_sets_primary_photo(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/appliances/{appliance.id}/photo', data={
            'photo': (_make_png_bytes(), 'furnace.png'),
        }, content_type='multipart/form-data')
        assert resp.status_code == 302

        page = logged_in_client.get(f'/appliances/{appliance.id}')
        assert b'profile-photo"' in page.data

    def test_upload_404_for_other_household(self, logged_in_client, db):
        other = Household(name='Other')
        db.session.add(other)
        db.session.commit()
        appliance = Appliance(household_id=other.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/appliances/{appliance.id}/photo', data={
            'photo': (_make_png_bytes(), 'furnace.png'),
        }, content_type='multipart/form-data')
        assert resp.status_code == 404
