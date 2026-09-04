"""SQLAlchemy ORM models. Thin: no business logic beyond simple property accessors."""
import enum
from datetime import date, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.category_templates_data import CATEGORY_LABELS
from app.maintenance_calc import compute_next_due
from app.vendor_types_data import VENDOR_TYPE_LABELS


class ApplianceStatus(str, enum.Enum):
    active = 'active'
    archived = 'archived'


class FrequencyUnit(str, enum.Enum):
    days = 'days'
    weeks = 'weeks'
    months = 'months'
    years = 'years'


class DocumentType(str, enum.Enum):
    photo = 'photo'
    manual = 'manual'
    receipt = 'receipt'
    floor_plan = 'floor_plan'
    inspection_report = 'inspection_report'
    quote = 'quote'
    invoice = 'invoice'
    other = 'other'


class DocumentEntityType(str, enum.Enum):
    """What a Document is linked to, via DocumentLink. A document can be linked to
    more than one entity (and to more entity types than these two, over time) —
    hence a generic link table rather than a per-relationship foreign key."""
    appliance = 'appliance'
    home = 'home'
    vendor = 'vendor'
    paint_color = 'paint_color'


class TemplateKind(str, enum.Enum):
    maintenance = 'maintenance'
    consumable = 'consumable'


class ServiceCategory(str, enum.Enum):
    maintenance = 'maintenance'
    improvement = 'improvement'


class Household(db.Model):
    __tablename__ = 'households'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(500))
    square_footage = db.Column(db.Integer)
    year_built = db.Column(db.Integer)
    notes = db.Column(db.Text)

    users = db.relationship('User', back_populates='household', cascade='all, delete-orphan')
    appliances = db.relationship('Appliance', back_populates='household', cascade='all, delete-orphan')
    vendors = db.relationship('Vendor', back_populates='household', cascade='all, delete-orphan')
    paint_colors = db.relationship('PaintColor', back_populates='household', cascade='all, delete-orphan')
    rooms = db.relationship(
        'Room', back_populates='household', cascade='all, delete-orphan',
        order_by='Room.floor, Room.name',
    )
    zones = db.relationship(
        'Zone', back_populates='household', cascade='all, delete-orphan', order_by='Zone.name',
    )

    @property
    def age_years(self):
        return date.today().year - self.year_built if self.year_built else None


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey('households.id'), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=False)

    household = db.relationship('Household', back_populates='users')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Appliance(db.Model):
    __tablename__ = 'appliances'

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey('households.id'), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    make = db.Column(db.String(120))
    model_number = db.Column(db.String(120))
    serial_number = db.Column(db.String(120))
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'))
    manufacture_year = db.Column(db.Integer)
    install_date = db.Column(db.Date)
    purchase_date = db.Column(db.Date)
    status = db.Column(
        db.Enum(ApplianceStatus, native_enum=False), nullable=False, default=ApplianceStatus.active
    )
    notes = db.Column(db.Text)
    pro_service_interval_value = db.Column(db.Integer)
    pro_service_interval_unit = db.Column(db.Enum(FrequencyUnit, native_enum=False))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    household = db.relationship('Household', back_populates='appliances')
    room = db.relationship('Room', back_populates='appliances')
    maintenance_tasks = db.relationship(
        'MaintenanceTask', back_populates='appliance', cascade='all, delete-orphan',
        order_by='MaintenanceTask.title',
    )
    consumables = db.relationship(
        'Consumable', back_populates='appliance', cascade='all, delete-orphan', order_by='Consumable.name'
    )
    service_records = db.relationship(
        'ServiceRecord', back_populates='appliance', cascade='all, delete-orphan',
        order_by='ServiceRecord.service_date.desc()',
    )

    @property
    def category_label(self):
        """Human-readable category, falling back to a humanized slug for a
        custom (non-seeded) category rather than showing the raw underscore_case."""
        return CATEGORY_LABELS.get(self.category) or self.category.replace('_', ' ').title()

    @property
    def latest_service_date(self):
        return self.service_records[0].service_date if self.service_records else None

    @property
    def pro_service_next_due(self):
        """Next pro-service due date, computed from the latest visit (or install date if none yet)."""
        if not self.pro_service_interval_value or not self.pro_service_interval_unit:
            return None
        baseline = self.latest_service_date or self.install_date or self.created_at.date()
        return compute_next_due(baseline, self.pro_service_interval_value, self.pro_service_interval_unit.value)


class Document(db.Model):
    """A stored file or external link. Not tied to any one owner directly — see
    DocumentLink for what it's attached to (an appliance, the home itself, etc.)."""
    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey('households.id'), nullable=False)
    doc_type = db.Column(db.Enum(DocumentType, native_enum=False), nullable=False)
    file_path = db.Column(db.String(500))
    external_url = db.Column(db.String(1000))
    original_filename = db.Column(db.String(255))
    content_type = db.Column(db.String(120))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.CheckConstraint(
            '(file_path IS NOT NULL AND external_url IS NULL) OR '
            '(file_path IS NULL AND external_url IS NOT NULL)',
            name='ck_document_file_xor_url',
        ),
    )


class DocumentLink(db.Model):
    """Generic (entity_type, entity_id) association from a Document to whatever
    references it. A document can have more than one link (e.g. a receipt relevant
    to two appliances), and new entity types don't need a new table."""
    __tablename__ = 'document_links'

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    entity_type = db.Column(db.Enum(DocumentEntityType, native_enum=False), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)

    document = db.relationship('Document')

    __table_args__ = (
        db.UniqueConstraint('document_id', 'entity_type', 'entity_id', name='uq_document_link'),
        db.Index('ix_document_links_entity', 'entity_type', 'entity_id'),
    )


class MaintenanceTask(db.Model):
    """A recurring owner-performed task, owned by either an Appliance or a Zone
    (never both/neither — see the check constraint) the same way ServiceRecord's
    appliance_id/zone_id pair works, just without ServiceRecord's "neither" case
    since a task with no owner has nowhere to be shown or completed from."""
    __tablename__ = 'maintenance_tasks'

    id = db.Column(db.Integer, primary_key=True)
    appliance_id = db.Column(db.Integer, db.ForeignKey('appliances.id'))
    zone_id = db.Column(db.Integer, db.ForeignKey('zones.id'))
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    frequency_value = db.Column(db.Integer, nullable=False)
    frequency_unit = db.Column(db.Enum(FrequencyUnit, native_enum=False), nullable=False)
    last_completed_at = db.Column(db.Date)
    next_due_at = db.Column(db.Date)
    active = db.Column(db.Boolean, nullable=False, default=True)

    appliance = db.relationship('Appliance', back_populates='maintenance_tasks')
    zone = db.relationship('Zone', back_populates='maintenance_tasks')
    logs = db.relationship(
        'MaintenanceLog', back_populates='task', cascade='all, delete-orphan',
        order_by='MaintenanceLog.completed_at.desc()',
    )

    __table_args__ = (
        db.CheckConstraint(
            '(appliance_id IS NOT NULL AND zone_id IS NULL) OR '
            '(appliance_id IS NULL AND zone_id IS NOT NULL)',
            name='ck_maintenance_task_appliance_xor_zone',
        ),
    )


class MaintenanceLog(db.Model):
    __tablename__ = 'maintenance_logs'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('maintenance_tasks.id'), nullable=False)
    completed_at = db.Column(db.Date, nullable=False)
    completed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)

    task = db.relationship('MaintenanceTask', back_populates='logs')
    completed_by = db.relationship('User')


class Consumable(db.Model):
    __tablename__ = 'consumables'

    id = db.Column(db.Integer, primary_key=True)
    appliance_id = db.Column(db.Integer, db.ForeignKey('appliances.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    part_number = db.Column(db.String(120))
    purchase_url = db.Column(db.String(1000))
    frequency_value = db.Column(db.Integer)
    frequency_unit = db.Column(db.Enum(FrequencyUnit, native_enum=False))
    last_replaced_at = db.Column(db.Date)
    next_due_at = db.Column(db.Date)

    appliance = db.relationship('Appliance', back_populates='consumables')


class ServiceRecord(db.Model):
    """A single vendor visit. Not every visit is about one specific appliance
    (a roofer, a whole-house inspection), so appliance_id is optional — but every
    record carries its own household_id so it can still be scoped/fetched without
    going through a (possibly absent) appliance."""
    __tablename__ = 'service_records'

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey('households.id'), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendors.id'))
    appliance_id = db.Column(db.Integer, db.ForeignKey('appliances.id'))
    zone_id = db.Column(db.Integer, db.ForeignKey('zones.id'))
    service_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    cost = db.Column(db.Numeric(10, 2))
    category = db.Column(
        db.Enum(ServiceCategory, native_enum=False), nullable=False, default=ServiceCategory.maintenance
    )

    vendor = db.relationship('Vendor', back_populates='services')
    appliance = db.relationship('Appliance', back_populates='service_records')
    zone = db.relationship('Zone', back_populates='service_records')


class Vendor(db.Model):
    __tablename__ = 'vendors'

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey('households.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    vendor_type = db.Column(db.String(80), nullable=False)
    contact_name = db.Column(db.String(120))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(255))
    website = db.Column(db.String(500))
    notes = db.Column(db.Text)
    rating = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    household = db.relationship('Household', back_populates='vendors')
    services = db.relationship(
        'ServiceRecord', back_populates='vendor', order_by='ServiceRecord.service_date.desc()'
    )

    __table_args__ = (
        db.CheckConstraint('rating IS NULL OR rating BETWEEN 1 AND 5', name='ck_vendor_rating_range'),
    )

    @property
    def vendor_type_label(self):
        """Human-readable vendor type, falling back to a humanized slug for a
        custom (non-seeded) type rather than showing the raw underscore_case."""
        return VENDOR_TYPE_LABELS.get(self.vendor_type) or self.vendor_type.replace('_', ' ').title()


class PaintColor(db.Model):
    """A paint color used somewhere in the home. Deliberately independent of
    appliances/vendors. The same color is often used in more than one room, so
    `location` holds a comma-separated list rather than modeling a many-to-many."""
    __tablename__ = 'paint_colors'

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey('households.id'), nullable=False)
    location = db.Column(db.String(500), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'))
    manufacturer = db.Column(db.String(120))
    color_name = db.Column(db.String(120))
    color_code = db.Column(db.String(80))
    hex_color = db.Column(db.String(7))
    product_url = db.Column(db.String(500))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    household = db.relationship('Household', back_populates='paint_colors')
    room = db.relationship('Room', back_populates='paint_colors')

    @property
    def location_list(self):
        return [loc.strip() for loc in self.location.split(',') if loc.strip()]


class Room(db.Model):
    """A named space in the home (e.g. "Kitchen", "Bedroom 2"), optionally grouped
    under a floor label. Appliances can be tied to one for a structured,
    browsable view of the house; paint colors can too, independent of the
    free-text location field that model already carries."""
    __tablename__ = 'rooms'

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey('households.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    floor = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    household = db.relationship('Household', back_populates='rooms')
    appliances = db.relationship('Appliance', back_populates='room')
    paint_colors = db.relationship('PaintColor', back_populates='room')


class Zone(db.Model):
    """An exterior or whole-house maintenance area that isn't a Room (roof,
    gutters, garden, siding, windows, solar, etc.). Services can attach to a
    Zone the same way they attach to an Appliance."""
    __tablename__ = 'zones'

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey('households.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    notes = db.Column(db.Text)
    pro_service_interval_value = db.Column(db.Integer)
    pro_service_interval_unit = db.Column(db.Enum(FrequencyUnit, native_enum=False))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    household = db.relationship('Household', back_populates='zones')
    service_records = db.relationship(
        'ServiceRecord', back_populates='zone', order_by='ServiceRecord.service_date.desc()',
    )
    maintenance_tasks = db.relationship(
        'MaintenanceTask', back_populates='zone', cascade='all, delete-orphan',
        order_by='MaintenanceTask.title',
    )

    @property
    def latest_service_date(self):
        return self.service_records[0].service_date if self.service_records else None

    @property
    def pro_service_next_due(self):
        """Next pro-service due date, computed from the latest visit (or creation date if none yet)."""
        if not self.pro_service_interval_value or not self.pro_service_interval_unit:
            return None
        baseline = self.latest_service_date or self.created_at.date()
        return compute_next_due(baseline, self.pro_service_interval_value, self.pro_service_interval_unit.value)


class CategoryTemplate(db.Model):
    __tablename__ = 'category_templates'

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(80), nullable=False, index=True)
    kind = db.Column(db.Enum(TemplateKind, native_enum=False), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    frequency_value = db.Column(db.Integer)
    frequency_unit = db.Column(db.Enum(FrequencyUnit, native_enum=False))
    part_number_hint = db.Column(db.String(120))


class AppSetting(db.Model):
    __tablename__ = 'app_settings'

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey('households.id'), nullable=False)
    key = db.Column(db.String(120), nullable=False)
    value = db.Column(db.Text)

    __table_args__ = (
        db.UniqueConstraint('household_id', 'key', name='uq_app_setting_household_key'),
    )
