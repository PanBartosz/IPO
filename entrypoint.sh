#!/bin/sh
set -e

flask --app ipo_app:create_app db upgrade

exec "$@"
