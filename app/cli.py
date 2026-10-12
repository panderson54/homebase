"""Flask CLI commands: `flask seed-templates`, `flask mcp-token`.

There is no `create-user`: users are created on first Google sign-in, from the
server-configured allowlist (see app/auth_service.py)."""
import click

from app import db, mcp_token_service
from app.category_templates_data import CATEGORY_TEMPLATES
from app.models import CategoryTemplate, FrequencyUnit, TemplateKind


def register(app):
    @app.cli.command('mcp-token')
    @click.argument('name')
    def mcp_token(name):
        """Generate a remote-MCP bearer token for NAME (e.g. muse) and its HOMEBASE_MCP_TOKENS entry."""
        name = name.strip().lower()
        if not mcp_token_service.is_valid_client_name(name):
            raise click.BadParameter('use lowercase letters, digits, "-" or "_" (max 64).', param_hint='NAME')
        token = mcp_token_service.generate_token()
        click.echo(f'Bearer token for {name} — give this to the agent; it is not stored anywhere:')
        click.echo(f'  {token}')
        click.echo('')
        click.echo('Add this entry to HOMEBASE_MCP_TOKENS (comma-separate multiple clients), then restart:')
        click.echo(f'  {name}:{mcp_token_service.hash_token(token)}')

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
