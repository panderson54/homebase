import os

# Must be set before `app` is imported, so create_app() picks up the in-memory DB.
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['GOOGLE_CLIENT_ID'] = 'test-client-id'
os.environ['GOOGLE_CLIENT_SECRET'] = 'test-client-secret'
os.environ['GOOGLE_REDIRECT_URI'] = ''
os.environ['HOMEBASE_ALLOWED_EMAILS'] = 'homeowner@example.com'

import pytest

from app import create_app
from app import db as _db


@pytest.fixture
def app():
    """A fresh app + fresh in-memory database per test — avoids any risk of
    SQLite rowid reuse colliding with SQLAlchemy's session identity map,
    which a single shared database across the whole test session ran into."""
    flask_app = create_app()
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def household(db):
    from app.models import Household
    h = Household(name='Test Home')
    db.session.add(h)
    db.session.commit()
    return h


@pytest.fixture
def user(db, household):
    from app.models import User
    u = User(household_id=household.id, email='homeowner@example.com', name='Homeowner',
             google_sub='google-sub-homeowner')
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def logged_in_client(client, user):
    # Sign-in itself goes through Google (covered in test_auth.py); everything
    # else just needs the Flask-Login session it leaves behind.
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
    return client


@pytest.fixture
def vendor(db, household):
    from app.models import Vendor
    v = Vendor(household_id=household.id, name='ACME HVAC', vendor_type='hvac')
    db.session.add(v)
    db.session.commit()
    return v


@pytest.fixture
def paint_color(db, household):
    from app.models import PaintColor
    p = PaintColor(household_id=household.id, location='Living room walls', hex_color='#D1CBC1')
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def seeded_templates(db):
    """A minimal category_templates fixture (furnace only) for template-application tests."""
    from app.models import CategoryTemplate, FrequencyUnit, TemplateKind
    rows = [
        CategoryTemplate(
            category='furnace', kind=TemplateKind.maintenance, title='Check filter',
            frequency_value=1, frequency_unit=FrequencyUnit.months,
        ),
        CategoryTemplate(
            category='furnace', kind=TemplateKind.consumable, title='Furnace filter',
            frequency_value=2, frequency_unit=FrequencyUnit.months,
        ),
    ]
    db.session.add_all(rows)
    db.session.commit()
    return rows
