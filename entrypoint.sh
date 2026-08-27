#!/bin/sh
set -e

flask db upgrade

exec gunicorn --bind 0.0.0.0:5100 --workers 2 --timeout 300 run:app
