"""Blueprint + sub-module imports. Route handlers are split by domain."""
from flask import Blueprint

main_bp = Blueprint('main', __name__)

from app.routes import (  # noqa: E402,F401  (must import after main_bp is defined)
    auth,
    dashboard,
    appliances,
    documents,
    maintenance,
    consumables,
    service_records,
    vendors,
    paint_colors,
    home,
    export,
)
