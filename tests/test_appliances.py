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
        assert details.count('—') == 9

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
            'name': 'Fridge', 'category': 'refrigerator', 'dimensions': '70 x 36 x 30 in', 'weight': '  ',
            'notes': 'Old notes',
        })
        assert resp.status_code == 302
        db.session.refresh(appliance)
        assert appliance.dimensions == '70 x 36 x 30 in'
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
            household_id=household.id, name='Fridge', category='refrigerator', weight='300 lb',
        )
        without_specs = Appliance(household_id=household.id, name='Washer', category='washer')
        db.session.add_all([with_specs, without_specs])
        db.session.commit()

        html = logged_in_client.get(f'/appliances/{with_specs.id}').get_data(as_text=True)
        specs_start = html.index('>Specifications<')
        assert html.index('Appliance details') < specs_start < html.index('>Documents<')
        assert '300 lb' in html[specs_start:html.index('>Documents<')]
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


class TestApplianceZone:
    def _zone(self, db, household, name='Home Network'):
        from app.models import Zone
        zone = Zone(household_id=household.id, name=name)
        db.session.add(zone)
        db.session.commit()
        return zone

    def _appliance(self, db, household, name='Router', **kwargs):
        appliance = Appliance(household_id=household.id, name=name, category='router', **kwargs)
        db.session.add(appliance)
        db.session.commit()
        return appliance

    def test_form_offers_zone_picker(self, logged_in_client, db, household):
        self._zone(db, household)
        for url in ('/appliances/new', f'/appliances/{self._appliance(db, household).id}/edit'):
            html = logged_in_client.get(url).get_data(as_text=True)
            assert 'name="zone_id"' in html
            assert 'Home Network' in html

    def test_create_with_room_and_zone_only_room_only_zone_or_neither(self, logged_in_client, db, household):
        from app.models import Room
        zone = self._zone(db, household)
        room = Room(household_id=household.id, name='Office')
        db.session.add(room)
        db.session.commit()
        cases = {
            'both': (room.id, zone.id), 'room only': (room.id, None),
            'zone only': (None, zone.id), 'neither': (None, None),
        }
        for name, (room_id, zone_id) in cases.items():
            resp = logged_in_client.post('/appliances/new', data={
                'name': name, 'category': 'router',
                'room_id': room_id or '', 'zone_id': zone_id or '',
            })
            assert resp.status_code == 302
            appliance = Appliance.query.filter_by(name=name).one()
            assert (appliance.room_id, appliance.zone_id) == (room_id, zone_id)

    def test_edit_sets_and_clears_zone(self, logged_in_client, db, household):
        zone = self._zone(db, household)
        appliance = self._appliance(db, household)
        data = {'name': 'Router', 'category': 'router'}
        logged_in_client.post(f'/appliances/{appliance.id}/edit', data={**data, 'zone_id': zone.id})
        assert db.session.get(Appliance, appliance.id).zone_id == zone.id
        logged_in_client.post(f'/appliances/{appliance.id}/edit', data={**data, 'zone_id': ''})
        assert db.session.get(Appliance, appliance.id).zone_id is None

    def test_other_households_zone_is_ignored(self, logged_in_client, db):
        other = Household(name='Other')
        db.session.add(other)
        db.session.commit()
        foreign_zone = self._zone(db, other, 'Foreign')
        for zone_id in (foreign_zone.id, 'abc', '99999'):
            logged_in_client.post('/appliances/new', data={'name': 'X', 'category': 'router', 'zone_id': zone_id})
        assert all(a.zone_id is None for a in Appliance.query.filter_by(name='X'))
        assert Appliance.query.filter_by(name='X').count() == 3

    def test_detail_shows_zone(self, logged_in_client, db, household):
        zone = self._zone(db, household)
        appliance = self._appliance(db, household, zone_id=zone.id)
        html = logged_in_client.get(f'/appliances/{appliance.id}').get_data(as_text=True)
        assert f'/zones/{zone.id}' in html
        assert 'Home Network' in html

    def test_list_shows_zone_and_filters_by_it(self, logged_in_client, db, household):
        zone = self._zone(db, household)
        self._appliance(db, household, 'Mesh Unit', zone_id=zone.id)
        self._appliance(db, household, 'Furnace')
        html = logged_in_client.get('/appliances').get_data(as_text=True)
        assert 'Mesh Unit' in html and 'Furnace' in html
        assert '<td>Home Network</td>' in html
        filtered = logged_in_client.get(f'/appliances?zone={zone.id}').get_data(as_text=True)
        assert 'Mesh Unit' in filtered and 'Furnace' not in filtered

    def test_list_ignores_unknown_zone_filter(self, logged_in_client, db, household):
        self._appliance(db, household, 'Furnace')
        html = logged_in_client.get('/appliances?zone=99999').get_data(as_text=True)
        assert 'Furnace' in html

    def test_room_only_appliance_unchanged(self, logged_in_client, db, household):
        from app.models import Room
        room = Room(household_id=household.id, name='Basement')
        db.session.add(room)
        db.session.commit()
        appliance = self._appliance(db, household, room_id=room.id)
        assert appliance.zone is None
        assert logged_in_client.get(f'/appliances/{appliance.id}').status_code == 200

    def test_deleting_zone_unassigns_appliances(self, logged_in_client, db, household):
        zone = self._zone(db, household)
        appliance = self._appliance(db, household, zone_id=zone.id)
        logged_in_client.post(f'/zones/{zone.id}/delete')
        assert db.session.get(Appliance, appliance.id).zone_id is None
