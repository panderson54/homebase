from datetime import date

from flask import Response, render_template
from flask_login import current_user, login_required

from app.context_export_service import build_context_markdown
from app.routes import main_bp


@main_bp.route('/export')
@login_required
def context_export():
    markdown = build_context_markdown(current_user.household)
    return render_template('export/export.html', markdown=markdown)


@main_bp.route('/export/download')
@login_required
def context_export_download():
    markdown = build_context_markdown(current_user.household)
    filename = f'homebase-export-{date.today().isoformat()}.md'
    return Response(
        markdown,
        mimetype='text/markdown',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )
