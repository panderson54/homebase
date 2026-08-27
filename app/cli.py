"""Flask CLI commands: `flask create-user`, `flask seed-templates`."""
import getpass

import click

from app import db
from app.category_templates_data import CATEGORY_TEMPLATES
from app.models import CategoryTemplate, FrequencyUnit, Household, TemplateKind, User


def register(app):
    @app.cli.command('create-user')
    @click.option('--email', prompt=True)
    @click.option('--name', prompt=True)
    @click.option('--household-name', default='Home', show_default=True)
    def create_user(email, name, household_name):
        """Create a household (if none exists yet) and a user account."""
        email = email.strip().lower()
        if User.query.filter_by(email=email).first():
            click.echo(f'A user with email {email} already exists.')
            return

        household = Household.query.first()
        if household is None:
            household = Household(name=household_name)
            db.session.add(household)
            db.session.flush()

        password = getpass.getpass('Password: ')
        confirm = getpass.getpass('Confirm password: ')
        if password != confirm:
            click.echo('Passwords did not match.')
            db.session.rollback()
            return

        user = User(household_id=household.id, email=email, name=name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f'Created user {email} in household "{household.name}".')

    @app.cli.command('seed-templates')
    def seed_templates():
        """Load/refresh category_templates seed rows from category_templates_data.py."""
        CategoryTemplate.query.delete()
        for category, template in CATEGORY_TEMPLATES.items():
            for task in template.get('maintenance', []):
                db.session.add(CategoryTemplate(
                    category=category,
                    kind=TemplateKind.maintenance,
                    title=task['title'],
                    description=task.get('description'),
                    frequency_value=task['frequency_value'],
                    frequency_unit=FrequencyUnit(task['frequency_unit']),
                ))
            for consumable in template.get('consumables', []):
                db.session.add(CategoryTemplate(
                    category=category,
                    kind=TemplateKind.consumable,
                    title=consumable['name'],
                    frequency_value=consumable.get('frequency_value'),
                    frequency_unit=FrequencyUnit(consumable['frequency_unit']) if consumable.get('frequency_unit') else None,
                    part_number_hint=consumable.get('part_number_hint'),
                ))
        db.session.commit()
        click.echo(f'Seeded category templates for {len(CATEGORY_TEMPLATES)} categories.')
