#!/bin/sh
set -e

flask db upgrade

# uvicorn (not gunicorn) so the ASGI app can serve the remote MCP endpoint at /mcp
# alongside the Flask site; see app/mcp_http.py.
exec uvicorn asgi:app --host 0.0.0.0 --port 5100 --workers 2 --no-access-log
