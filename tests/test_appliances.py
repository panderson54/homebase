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
        assert appliance.category_label == 'Garage Door Opener'

    def test_category_label_for_seeded_category(self, household, db):
        appliance = Appliance(household_id=household.id, name='Furnace', category='furnace')
        db.session.add(appliance)
        db.session.commit()
        assert appliance.category_label == 'Furnace'

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


class TestApplianceDetailsSection:
    def test_shows_identity_fields(self, logged_in_client, db, household):
        from datetime import date
        from app.models import Room
        room = Room(household_id=household.id, name='Basement')
        db.session.add(room)
        db.session.flush()
        appliance = Appliance(
            household_id=household.id, name='Furnace', category='furnace', make='Carrier',
            model_number='59SC5A060', serial_number='SN-12345', manufacture_year=2019, room_id=room.id,
            install_date=date(2019, 6, 1), purchase_date=date(2019, 5, 20),
            pro_service_interval_value=1, pro_service_interval_unit=FrequencyUnit.years,
        )
        db.session.add(appliance)
        db.session.commit()

        html = logged_in_client.get(f'/appliances/{appliance.id}').get_data(as_text=True)
        details = html[html.index('Appliance details'):html.index('<h2 class="h5">Documents</h2>')]
        for expected in ('Carrier', '59SC5A060', 'SN-12345', '2019', 'Basement',
                         'Jun 1, 2019', 'May 20, 2019', 'Every 1 year<'):
            assert expected in details

    def test_empty_fields_render_placeholder(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Dryer', category='dryer')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.get(f'/appliances/{appliance.id}')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        details = html[html.index('Appliance details'):html.index('<h2 class="h5">Documents</h2>')]
        assert details.count('—') == 8

    def test_existing_sections_remain_in_order(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Dryer', category='dryer')
        db.session.add(appliance)
        db.session.commit()

        html = logged_in_client.get(f'/appliances/{appliance.id}').get_data(as_text=True)
        positions = [html.index(heading) for heading in (
            'Appliance details', '>Documents<', '>Homeowner maintenance<', '>Consumables<', '>Professional service<',
        )]
        assert positions == sorted(positions)


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
            'serial_number': 'ABC123',
        })
        assert resp.status_code == 302
        db.session.refresh(appliance)
        assert appliance.name == 'Basement Furnace'
        assert appliance.serial_number == 'ABC123'


class TestApplianceLookup:
    def test_lookup_returns_service_result_as_json(self, logged_in_client, monkeypatch):
        from app import appliance_lookup_service
        monkeypatch.setattr(
            appliance_lookup_service, 'lookup_appliance',
            lambda **kwargs: {'make': 'Whirlpool', 'category': 'dishwasher'},
        )
        resp = logged_in_client.post('/appliances/lookup', data={'model_number': 'WDT730PAHZ0'})
        assert resp.status_code == 200
        assert resp.get_json() == {'make': 'Whirlpool', 'category': 'dishwasher'}

    def test_lookup_requires_login(self, client):
        resp = client.post('/appliances/lookup', data={'model_number': 'WDT730PAHZ0'})
        assert resp.status_code == 302

    def test_create_with_manual_url_attaches_document(self, logged_in_client, user):
        from app import document_service
        resp = logged_in_client.post('/appliances/new', data={
            'name': 'Dishwasher', 'category': 'dishwasher',
            'manual_url': 'https://example.com/manuals/dishwasher.pdf',
        })
        assert resp.status_code == 302
        appliance = Appliance.query.filter_by(household_id=user.household_id).first()
        docs = document_service.get_documents_for('appliance', appliance.id)
        assert len(docs) == 1
        assert docs[0].doc_type.value == 'manual'
        assert docs[0].external_url == 'https://example.com/manuals/dishwasher.pdf'

    def test_create_with_manufacture_year(self, logged_in_client, user):
        resp = logged_in_client.post('/appliances/new', data={
            'name': 'Furnace', 'category': 'furnace', 'manufacture_year': '2018',
        })
        assert resp.status_code == 302
        appliance = Appliance.query.filter_by(household_id=user.household_id).first()
        assert appliance.manufacture_year == 2018


class TestApplianceSpecs:
    def test_create_with_spec_fields(self, logged_in_client, user):
        resp = logged_in_client.post('/appliances/new', data={
            'name': 'Dryer', 'category': 'dryer', 'capacity': ' 7.0 cu ft ',
            'electrical_specs': '240V / 30A', 'dimensions': '38 x 29 x 28 in', 'notes': 'Vent cleaned 2025',
        })
        assert resp.status_code == 302
        appliance = Appliance.query.filter_by(household_id=user.household_id).one()
        assert appliance.capacity == '7.0 cu ft'
        assert appliance.electrical_specs == '240V / 30A'
        assert appliance.weight is None
        assert appliance.notes == 'Vent cleaned 2025'

    def test_create_with_name_only_leaves_specs_empty(self, logged_in_client, user):
        resp = logged_in_client.post('/appliances/new', data={'name': 'Dehumidifier', 'category': 'dehumidifier'})
        assert resp.status_code == 302
        appliance = Appliance.query.filter_by(household_id=user.household_id).one()
        assert appliance.specs == []

    def test_edit_updates_and_clears_specs_preserving_notes(self, logged_in_client, db, household):
        appliance = Appliance(
            household_id=household.id, name='Fridge', category='refrigerator', weight='300 lb', notes='Old notes',
        )
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.post(f'/appliances/{appliance.id}/edit', data={
            'name': 'Fridge', 'category': 'refrigerator', 'refrigerant': 'R-600a', 'weight': '  ',
            'notes': 'Old notes',
        })
        assert resp.status_code == 302
        db.session.refresh(appliance)
        assert appliance.refrigerant == 'R-600a'
        assert appliance.weight is None
        assert appliance.notes == 'Old notes'

    def test_edit_form_prefills_specs(self, logged_in_client, db, household):
        appliance = Appliance(household_id=household.id, name='Fridge', category='refrigerator', capacity='25 cu ft')
        db.session.add(appliance)
        db.session.commit()

        resp = logged_in_client.get(f'/appliances/{appliance.id}/edit')
        assert resp.status_code == 200
        assert b'value="25 cu ft"' in resp.data

    def test_detail_shows_spec_section_only_when_specs_exist(self, logged_in_client, db, household):
        with_specs = Appliance(
            household_id=household.id, name='Fridge', category='refrigerator', warranty='10 yr compressor',
        )
        without_specs = Appliance(household_id=household.id, name='Washer', category='washer')
        db.session.add_all([with_specs, without_specs])
        db.session.commit()

        resp = logged_in_client.get(f'/appliances/{with_specs.id}')
        assert b'Specifications' in resp.data
        assert b'10 yr compressor' in resp.data
        resp = logged_in_client.get(f'/appliances/{without_specs.id}')
        assert b'Specifications' not in resp.data


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
