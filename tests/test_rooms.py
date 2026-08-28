from app.models import Appliance, Household, Room


class TestRoomCRUD:
    def test_create(self, logged_in_client, db, household):
        resp = logged_in_client.post('/rooms/new', data={'name': 'Kitchen', 'floor': '1st floor'})
        assert resp.status_code == 302
        room = Room.query.filter_by(household_id=household.id).first()
        assert room.name == 'Kitchen'
        assert room.floor == '1st floor'

    def test_create_requires_name(self, logged_in_client, db, household):
        resp = logged_in_client.post('/rooms/new', data={'name': ''})
        assert resp.status_code == 302
        assert Room.query.filter_by(household_id=household.id).count() == 0

    def test_edit_updates_fields(self, logged_in_client, db, household):
        room = Room(household_id=household.id, name='Bedroom 1')
        db.session.add(room)
        db.session.commit()

        resp = logged_in_client.post(f'/rooms/{room.id}/edit', data={'name': 'Primary Bedroom', 'floor': '2nd floor'})
        assert resp.status_code == 302
        db.session.refresh(room)
        assert room.name == 'Primary Bedroom'
        assert room.floor == '2nd floor'

    def test_edit_404_for_other_household(self, logged_in_client, db):
        other = Household(name='Other')
        db.session.add(other)
        db.session.commit()
        room = Room(household_id=other.id, name='Kitchen')
        db.session.add(room)
        db.session.commit()

        resp = logged_in_client.get(f'/rooms/{room.id}/edit')
        assert resp.status_code == 404

    def test_delete_unassigns_appliance_instead_of_cascading(self, logged_in_client, db, household):
        room = Room(household_id=household.id, name='Kitchen')
        db.session.add(room)
        db.session.commit()
        appliance = Appliance(household_id=household.id, name='Fridge', category='refrigerator', room_id=room.id)
        db.session.add(appliance)
        db.session.commit()
        appliance_id = appliance.id

        resp = logged_in_client.post(f'/rooms/{room.id}/delete')
        assert resp.status_code == 302
        assert db.session.get(Room, room.id) is None
        remaining = db.session.get(Appliance, appliance_id)
        assert remaining is not None
        assert remaining.room_id is None
